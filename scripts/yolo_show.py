"""
YOLO label visualization for detection (det) and segmentation (seg).
Supports TXT/JSON labels and auto mode detection.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sys

import cv2
import numpy as np
from tqdm import tqdm

try:
    import freetype
except Exception:
    freetype = None

_IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp")

_PLATECH_FONT_CANDIDATES = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "resources", "fonts", "platech.ttf")),
    os.path.abspath(os.path.join(os.getcwd(), "resources", "fonts", "platech.ttf")),
]
if getattr(sys, "_MEIPASS", None):
    _PLATECH_FONT_CANDIDATES.append(
        os.path.abspath(os.path.join(sys._MEIPASS, "resources", "fonts", "platech.ttf"))
    )

_CJK_FONT_CANDIDATES = [
    os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "msyh.ttc"),
    os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "msyhbd.ttc"),
    os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "platech.ttf"),
    os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "simsun.ttc"),
]

_FREETYPE_FACE_CACHE: dict[tuple[str, int], object] = {}
_FONT_DEBUG_REPORTED: set[str] = set()
_FREETYPE_ERROR_REPORTED: set[str] = set()


def cv2_imread_unicode(path: str):
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


def cv2_imwrite_unicode(path: str, img) -> bool:
    ext = os.path.splitext(path)[1]
    ok, enc = cv2.imencode(ext, img)
    if not ok:
        return False
    try:
        enc.tofile(path)
        return True
    except Exception:
        return False


def _resolve_platech_font_path() -> str | None:
    for p in _PLATECH_FONT_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


_PLATECH_FONT_PATH = _resolve_platech_font_path()


def _select_font_path() -> str | None:
    if _PLATECH_FONT_PATH and os.path.isfile(_PLATECH_FONT_PATH):
        return _PLATECH_FONT_PATH
    for p in _CJK_FONT_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def _get_freetype_face(font_size: int):
    if freetype is None:
        if "module_not_found" not in _FREETYPE_ERROR_REPORTED:
            print("[yolo_show][font] freetype-py not installed, fallback to cv2.putText")
            _FREETYPE_ERROR_REPORTED.add("module_not_found")
        return None
    font_path = _select_font_path()
    if not font_path:
        if "font_not_found" not in _FREETYPE_ERROR_REPORTED:
            print("[yolo_show][font] no CJK font found, fallback to cv2.putText")
            _FREETYPE_ERROR_REPORTED.add("font_not_found")
        return None

    key = (font_path, int(font_size))
    if key in _FREETYPE_FACE_CACHE:
        return _FREETYPE_FACE_CACHE[key]
    try:
        face = freetype.Face(font_path)
        face.set_pixel_sizes(0, int(font_size))
        _FREETYPE_FACE_CACHE[key] = face
        return face
    except Exception as e:
        err_key = f"face_load:{font_path}:{font_size}"
        if err_key not in _FREETYPE_ERROR_REPORTED:
            print(f"[yolo_show][font] freetype face load failed: {e}")
            _FREETYPE_ERROR_REPORTED.add(err_key)
        return None


def _freetype_measure_text(face, text: str) -> tuple[int, int, int]:
    if not text:
        return 1, max(1, int(face.size.ascender >> 6)), max(0, int(-(face.size.descender >> 6)))
    pen_x = 0
    prev_idx = 0
    min_x = None
    max_x = None
    top_max = 0
    bottom_max = 0
    for ch in text:
        glyph_idx = face.get_char_index(ord(ch))
        if prev_idx and glyph_idx:
            kerning = face.get_kerning(prev_idx, glyph_idx)
            pen_x += int(kerning.x >> 6)
        face.load_char(ch, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_NORMAL)
        g = face.glyph
        left = pen_x + int(g.bitmap_left)
        right = left + int(g.bitmap.width)
        top = int(g.bitmap_top)
        bottom = int(g.bitmap.rows) - top
        min_x = left if min_x is None else min(min_x, left)
        max_x = right if max_x is None else max(max_x, right)
        top_max = max(top_max, top)
        bottom_max = max(bottom_max, bottom)
        pen_x += int(g.advance.x >> 6)
        prev_idx = glyph_idx
    text_w = max(1, (max_x - min_x) if (min_x is not None and max_x is not None) else pen_x)
    ascent = max(1, top_max if top_max > 0 else int(face.size.ascender >> 6))
    baseline = max(0, bottom_max if bottom_max > 0 else int(-(face.size.descender >> 6)))
    return text_w, ascent, baseline


def _blend_bitmap_to_bgr(img, bitmap, dst_x: int, dst_y: int, color: tuple[int, int, int]):
    h, w = img.shape[:2]
    bw = int(bitmap.width)
    bh = int(bitmap.rows)
    pitch = int(bitmap.pitch)
    if bw <= 0 or bh <= 0:
        return
    # FreeType bitmap rows may be padded by pitch; trim to visible width.
    abs_pitch = abs(pitch) if pitch != 0 else bw
    # freetype-py buffer type may vary by platform (bytes/bytearray/list).
    if isinstance(bitmap.buffer, (bytes, bytearray, memoryview)):
        raw = np.frombuffer(bitmap.buffer, dtype=np.uint8)
    else:
        raw = np.asarray(bitmap.buffer, dtype=np.uint8)
    if raw.size < bh * abs_pitch:
        return
    src_full = raw[: bh * abs_pitch].reshape((bh, abs_pitch))
    src = src_full[:, :bw]
    x0 = max(0, dst_x)
    y0 = max(0, dst_y)
    x1 = min(w, dst_x + bw)
    y1 = min(h, dst_y + bh)
    if x0 >= x1 or y0 >= y1:
        return
    sx0 = x0 - dst_x
    sy0 = y0 - dst_y
    sx1 = sx0 + (x1 - x0)
    sy1 = sy0 + (y1 - y0)
    alpha = src[sy0:sy1, sx0:sx1].astype(np.float32) / 255.0
    if alpha.size == 0:
        return
    roi = img[y0:y1, x0:x1].astype(np.float32)
    color_arr = np.array(color, dtype=np.float32).reshape((1, 1, 3))
    roi[:] = roi * (1.0 - alpha[..., None]) + color_arr * alpha[..., None]
    img[y0:y1, x0:x1] = roi.astype(np.uint8)


def _draw_text_with_freetype_baseline(
    img,
    text: str,
    org: tuple[int, int],
    color: tuple[int, int, int],
    font_size: int,
) -> bool:
    face = _get_freetype_face(font_size)
    if face is None:
        return False
    pen_x = int(org[0])
    baseline_y = int(org[1])
    prev_idx = 0
    for ch in text:
        glyph_idx = face.get_char_index(ord(ch))
        if prev_idx and glyph_idx:
            kerning = face.get_kerning(prev_idx, glyph_idx)
            pen_x += int(kerning.x >> 6)
        face.load_char(ch, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_NORMAL)
        g = face.glyph
        dst_x = pen_x + int(g.bitmap_left)
        dst_y = baseline_y - int(g.bitmap_top)
        _blend_bitmap_to_bgr(img, g.bitmap, dst_x, dst_y, color)
        pen_x += int(g.advance.x >> 6)
        prev_idx = glyph_idx
    return True


def _measure_text_baseline(text: str, font_scale: float = 0.5, thickness: int = 1) -> tuple[int, int, int]:
    """
    Return (width, ascent_height, baseline).
    """
    font_size = max(12, int(font_scale * 32))

    face = _get_freetype_face(font_size)
    if face is not None:
        try:
            return _freetype_measure_text(face, text)
        except Exception:
            pass

    size, baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
    return max(1, size[0]), max(1, size[1]), max(0, baseline)


def _measure_label_text_lt(text: str, font_scale: float = 0.5, thickness: int = 1) -> tuple[int, int]:
    w, ascent, baseline = _measure_text_baseline(text, font_scale, thickness)
    return w, ascent + baseline


def _draw_label_text_lt(
    img,
    text: str,
    org: tuple[int, int],  # top-left text origin
    color: tuple[int, int, int] = (255, 255, 255),
    font_scale: float = 0.5,
    thickness: int = 1,
):
    """
    Draw text with top-left semantics.
    Priority: freetype-py (native) -> cv2.
    """
    font_size = max(12, int(font_scale * 32))
    _, ascent, _ = _measure_text_baseline(text, font_scale, thickness)
    if _draw_text_with_freetype_baseline(
        img, text, (int(org[0]), int(org[1] + ascent)), color, font_size
    ):
        debug_key = "label-freetype-py"
        if debug_key not in _FONT_DEBUG_REPORTED:
            print("[yolo_show][font] label uses freetype-py")
            _FONT_DEBUG_REPORTED.add(debug_key)
        return

    size, baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
    ascent = max(1, int(size[1]))
    cv2.putText(
        img,
        text,
        (int(org[0]), int(org[1] + ascent)),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        color,
        thickness,
    )
    debug_key = "label-cv2"
    if debug_key not in _FONT_DEBUG_REPORTED:
        print("[yolo_show][font] label uses cv2 built-in font (possible CJK garbled)")
        _FONT_DEBUG_REPORTED.add(debug_key)


def _draw_text_baseline(
    img,
    text: str,
    org: tuple[int, int],  # baseline origin
    color: tuple[int, int, int] = (255, 255, 255),
    font_scale: float = 0.5,
    thickness: int = 1,
):
    font_size = max(12, int(font_scale * 32))
    if _draw_text_with_freetype_baseline(img, text, org, color, font_size):
        return

    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness)


def _draw_det_label(
    img,
    label_text: str,
    anchor: tuple[int, int],  # box top-left
    color: tuple[int, int, int],
    font_scale: float,
    text_thickness: int,
    text_pad: int,
):
    h, w = img.shape[:2]
    x1, y1 = int(anchor[0]), int(anchor[1])
    text_w, text_h = _measure_label_text_lt(label_text, font_scale, text_thickness)
    pad = max(2, int(text_pad))

    label_w = text_w + pad * 2
    label_h = text_h + pad * 2

    if y1 - label_h >= 0:
        label_top = y1 - label_h
    else:
        label_top = min(max(0, y1), max(0, h - label_h))

    label_left = min(max(0, x1), max(0, w - label_w))
    label_right = min(w - 1, label_left + label_w)
    label_bottom = min(h - 1, label_top + label_h)

    text_x = label_left + pad
    text_y = label_top + pad

    cv2.rectangle(img, (label_left, label_top), (label_right, label_bottom), color, -1)
    _draw_label_text_lt(
        img,
        label_text,
        (text_x, text_y),
        (255, 255, 255),
        font_scale,
        text_thickness,
    )


def _get_det_style_params(img_w: int, img_h: int) -> dict[str, float | int]:
    scale = max(1.0, max(img_w / 1920.0, img_h / 1080.0))
    return {
        "box_thickness": max(2, int(round(2 * scale))),
        "font_scale": 0.5 * scale,
        "text_thickness": max(1, int(round(1 * scale))),
        "text_pad": max(10, int(round(10 * scale))) // 2,
    }


def _classify_yolo_line(parts: list[str]) -> str | None:
    n = len(parts)
    if n == 5:
        return "det"
    if n >= 7 and (n - 1) % 2 == 0:
        return "seg"
    return None


def _normalize_mode(mode: str) -> str:
    m = (mode or "auto").strip().lower()
    if m in ("auto", ""):
        return "auto"
    if m in ("det", "detect", "bbox"):
        return "det"
    if m in ("seg", "segment", "segmentation"):
        return "seg"
    print(f"[yolo_show] Unknown mode {mode!r}, fallback to auto")
    return "auto"


def _detect_visualize_mode_txt(label_folder: str, img_files: list[str], max_files: int = 30) -> str:
    det_n = 0
    seg_n = 0
    for img_name in img_files[:max_files]:
        txt_path = os.path.join(label_folder, os.path.splitext(img_name)[0] + ".txt")
        if not os.path.isfile(txt_path):
            continue
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) < 5:
                        continue
                    kind = _classify_yolo_line(parts)
                    if kind == "det":
                        det_n += 1
                    elif kind == "seg":
                        seg_n += 1
        except Exception:
            continue
    return "seg" if seg_n > det_n else "det"


def _detect_visualize_mode_json(label_folder: str, img_files: list[str], max_files: int = 30) -> str:
    det_n = 0
    seg_n = 0
    for img_name in img_files[:max_files]:
        json_path = os.path.join(label_folder, os.path.splitext(img_name)[0] + ".json")
        if not os.path.isfile(json_path):
            continue
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for shape in data.get("shapes", []):
                st = shape.get("shape_type", "")
                if st == "rectangle":
                    det_n += 1
                elif st == "polygon":
                    seg_n += 1
        except Exception:
            continue
    return "seg" if seg_n > det_n else "det"


def _scan_type_presence_txt(label_folder: str, img_files: list[str]) -> tuple[bool, bool]:
    has_det = False
    has_seg = False
    for img_name in img_files:
        txt_path = os.path.join(label_folder, os.path.splitext(img_name)[0] + ".txt")
        if not os.path.isfile(txt_path):
            continue
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) < 5:
                        continue
                    kind = _classify_yolo_line(parts)
                    if kind == "det":
                        has_det = True
                    elif kind == "seg":
                        has_seg = True
                    if has_det and has_seg:
                        return has_det, has_seg
        except Exception:
            continue
    return has_det, has_seg


def _scan_type_presence_json(label_folder: str, img_files: list[str]) -> tuple[bool, bool]:
    has_det = False
    has_seg = False
    for img_name in img_files:
        json_path = os.path.join(label_folder, os.path.splitext(img_name)[0] + ".json")
        if not os.path.isfile(json_path):
            continue
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for shape in data.get("shapes", []):
                st = shape.get("shape_type", "")
                if st == "rectangle":
                    has_det = True
                elif st == "polygon":
                    has_seg = True
                if has_det and has_seg:
                    return has_det, has_seg
        except Exception:
            continue
    return has_det, has_seg


def visualize_yolo(
    img_folder,
    label_folder=None,
    output_folder="",
    mode="auto",
    label_format="txt",
    txt_folder=None,
    **_kwargs,
):
    # Backward compatibility:
    # older runners pass `txt_folder` instead of `label_folder`.
    if label_folder is None:
        label_folder = txt_folder
    if label_folder is None:
        raise TypeError("visualize_yolo() missing required argument: 'label_folder' (or 'txt_folder')")

    random.seed(42)
    class_colors: dict[str, list[int]] = {}

    def get_color(label: str) -> list[int]:
        key = str(label)
        if key not in class_colors:
            seed = int(hashlib.md5(key.encode("utf-8")).hexdigest()[:8], 16)
            r = random.Random(seed)
            class_colors[key] = [r.randint(0, 255) for _ in range(3)]
        return class_colors[key]

    label_format = (label_format or "txt").strip().lower()
    if label_format not in ("txt", "json"):
        label_format = "txt"
    mode = _normalize_mode(mode)

    img_files = [f for f in os.listdir(img_folder) if f.lower().endswith(_IMG_EXTS)]
    if not img_files:
        print(f"[yolo_show] no image found in: {img_folder}")
        return

    out = (output_folder or "").strip()
    preview = not bool(out)

    auto_split_mixed = False
    if mode == "auto":
        if label_format == "json":
            has_det, has_seg = _scan_type_presence_json(label_folder, img_files)
            if not (has_det and has_seg):
                mode = _detect_visualize_mode_json(label_folder, img_files)
        else:
            has_det, has_seg = _scan_type_presence_txt(label_folder, img_files)
            if not (has_det and has_seg):
                mode = _detect_visualize_mode_txt(label_folder, img_files)
        auto_split_mixed = has_det and has_seg

    if auto_split_mixed:
        if preview:
            print("[yolo_show] mixed det+seg in auto mode requires output folder")
            return
        out_det = os.path.join(out, "det")
        out_seg = os.path.join(out, "seg")
        os.makedirs(out_det, exist_ok=True)
        os.makedirs(out_seg, exist_ok=True)
    else:
        if mode == "det" and preview:
            print("[yolo_show] det mode requires output folder")
            return
        if not preview:
            os.makedirs(out, exist_ok=True)

    print(f"[yolo_show] label_format={label_format}, mode={mode}, images={len(img_files)}")

    det_saved = 0
    seg_saved = 0

    if mode == "det" or auto_split_mixed:
        for img_name in tqdm(img_files, desc="det visualize", unit="img"):
            img_path = os.path.join(img_folder, img_name)
            stem = os.path.splitext(img_name)[0]
            txt_path = os.path.join(label_folder, f"{stem}.txt")
            json_path = os.path.join(label_folder, f"{stem}.json")

            img = cv2_imread_unicode(img_path)
            if img is None:
                continue

            h, w = img.shape[:2]
            style = _get_det_style_params(w, h)
            has_det_label = False

            if label_format == "json":
                if os.path.isfile(json_path):
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        for shape in data.get("shapes", []):
                            if shape.get("shape_type", "") != "rectangle":
                                continue
                            pts = shape.get("points", [])
                            if len(pts) < 2:
                                continue
                            x1, y1 = pts[0]
                            x2, y2 = pts[1]
                            x_min, x_max = int(min(x1, x2)), int(max(x1, x2))
                            y_min, y_max = int(min(y1, y2)), int(max(y1, y2))
                            label_raw = str(shape.get("label", "0"))
                            color = get_color(label_raw)
                            has_det_label = True
                            cv2.rectangle(
                                img, (x_min, y_min), (x_max, y_max), color, int(style["box_thickness"])
                            )
                            _draw_det_label(
                                img,
                                f"{label_raw}",
                                (x_min, y_min),
                                tuple(color),
                                float(style["font_scale"]),
                                int(style["text_thickness"]),
                                int(style["text_pad"]),
                            )
                    except Exception as e:
                        tqdm.write(f"json process failed: {json_path} | {e}")
            else:
                if os.path.isfile(txt_path):
                    try:
                        with open(txt_path, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                        for line in lines:
                            data = line.strip().split()
                            if _classify_yolo_line(data) != "det":
                                continue
                            cls_label = str(data[0])
                            x_c, y_c, bw, bh = map(float, data[1:5])
                            x1 = int((x_c - bw / 2.0) * w)
                            y1 = int((y_c - bh / 2.0) * h)
                            x2 = int((x_c + bw / 2.0) * w)
                            y2 = int((y_c + bh / 2.0) * h)
                            color = get_color(cls_label)
                            has_det_label = True
                            cv2.rectangle(img, (x1, y1), (x2, y2), color, int(style["box_thickness"]))
                            _draw_det_label(
                                img,
                                f"{cls_label}",
                                (x1, y1),
                                tuple(color),
                                float(style["font_scale"]),
                                int(style["text_thickness"]),
                                int(style["text_pad"]),
                            )
                    except Exception as e:
                        tqdm.write(f"txt process failed: {txt_path} | {e}")

            if not has_det_label:
                continue
            save_root = out_det if auto_split_mixed else out
            save_path = os.path.join(save_root, img_name)
            if cv2_imwrite_unicode(save_path, img):
                det_saved += 1

    if mode == "seg" or auto_split_mixed:
        try:
            for img_name in tqdm(img_files, desc="seg visualize", unit="img"):
                img_path = os.path.join(img_folder, img_name)
                stem = os.path.splitext(img_name)[0]
                txt_path = os.path.join(label_folder, f"{stem}.txt")
                json_path = os.path.join(label_folder, f"{stem}.json")

                if label_format == "json" and not os.path.isfile(json_path):
                    continue
                if label_format == "txt" and not os.path.isfile(txt_path):
                    continue

                img = cv2_imread_unicode(img_path)
                if img is None:
                    continue
                h, w = img.shape[:2]
                overlay = img.copy()
                has_label = False

                if label_format == "json":
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        for shape in data.get("shapes", []):
                            if shape.get("shape_type", "") != "polygon":
                                continue
                            points = shape.get("points", [])
                            if len(points) < 3:
                                continue
                            label_raw = str(shape.get("label", "0"))
                            color = get_color(label_raw)
                            pts = np.array(points, dtype=np.int32)
                            has_label = True
                            cv2.fillPoly(overlay, [pts], color)
                            cv2.polylines(img, [pts], True, color, 2)
                            _draw_text_baseline(
                                img,
                                f"cls:{label_raw}",
                                (int(pts[0][0]), int(pts[0][1] - 8)),
                                tuple(color),
                                0.6,
                                2,
                            )
                    except Exception as e:
                        tqdm.write(f"json process failed: {json_path} | {e}")
                        continue
                else:
                    try:
                        with open(txt_path, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                        for line in lines:
                            parts = line.strip().split()
                            if len(parts) < 7:
                                continue
                            cls_label = str(parts[0])
                            coords = np.array(parts[1:], dtype=np.float32).reshape(-1, 2)
                            coords[:, 0] *= w
                            coords[:, 1] *= h
                            pts = coords.astype(np.int32)
                            color = get_color(cls_label)
                            has_label = True
                            cv2.fillPoly(overlay, [pts], color)
                            cv2.polylines(img, [pts], True, color, 2)
                            _draw_text_baseline(
                                img,
                                f"cls:{cls_label}",
                                (int(pts[0][0]), int(pts[0][1] - 8)),
                                tuple(color),
                                0.6,
                                2,
                            )
                    except Exception as e:
                        tqdm.write(f"txt process failed: {txt_path} | {e}")
                        continue

                if not has_label:
                    continue
                out_img = cv2.addWeighted(overlay, 0.6, img, 0.4, 0)

                if preview:
                    show = cv2.resize(out_img, (1280, 720)) if w > 1280 else out_img
                    cv2.imshow("Preview", show)
                    if cv2.waitKey(0) & 0xFF == ord("q"):
                        break
                else:
                    save_root = out_seg if auto_split_mixed else out
                    save_path = os.path.join(save_root, img_name)
                    if cv2_imwrite_unicode(save_path, out_img):
                        seg_saved += 1
        finally:
            if preview:
                cv2.destroyAllWindows()

    if auto_split_mixed:
        print(f"[yolo_show] det saved: {det_saved}, seg saved: {seg_saved}")
    print(f"[yolo_show] classes: {sorted(class_colors.keys())}")


def draw_and_save(img_folder, txt_folder, output_folder, mode="auto"):
    visualize_yolo(img_folder, txt_folder, output_folder, mode=mode)


if __name__ == "__main__":
    IMAGE_DIR = r"C:/Users/RS/Desktop/1"
    LABEL_DIR = r"C:/Users/RS/Desktop/1/2/labels/det"
    SAVE_DIR = r"C:/Users/RS/Desktop/1/yolo_show"
    visualize_yolo(IMAGE_DIR, LABEL_DIR, SAVE_DIR, mode="auto", label_format="txt")
