"""
YOLO 标签可视化：支持 TXT / JSON，检测框 (det) / 分割 (seg)，
支持 auto 自动判断并在混合场景下拆分输出 det/seg。
"""

import hashlib
import json
import os
import random
import sys

import cv2
import numpy as np
from tqdm import tqdm

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = None
    ImageDraw = None
    ImageFont = None

_IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp")
_PLATECH_FONT_CANDIDATES = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "resources", "fonts", "simhei.ttf")),
    os.path.abspath(os.path.join(os.getcwd(), "resources", "fonts", "simhei.ttf")),
]
if getattr(sys, "_MEIPASS", None):
    _PLATECH_FONT_CANDIDATES.append(
        os.path.abspath(os.path.join(sys._MEIPASS, "resources", "fonts", "simhei.ttf"))
    )


def _resolve_platech_font_path() -> str | None:
    for font_path in _PLATECH_FONT_CANDIDATES:
        if os.path.isfile(font_path):
            return font_path
    return None


_PLATECH_FONT_PATH = _resolve_platech_font_path()
_PLATECH_FONT_CACHE: dict[int, object] = {}
_CJK_FONT_CACHE: dict[int, object] = {}
_FREETYPE_CACHE: dict[str, object] = {}
_CJK_FONT_CANDIDATES = [
    os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "msyh.ttc"),   # 微软雅黑
    os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "msyhbd.ttc"), # 微软雅黑 Bold
    os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "simhei.ttf"), # 黑体
    os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "simsun.ttc"), # 宋体
]
_FONT_DEBUG_REPORTED: set[str] = set()
_FREETYPE_ERROR_REPORTED: set[str] = set()


def cv2_imread_unicode(path: str):
    """读取包含中文路径的图片"""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


def cv2_imwrite_unicode(path: str, img) -> bool:
    """保存包含中文路径的图片"""
    ext = os.path.splitext(path)[1]
    result, enc = cv2.imencode(ext, img)
    if not result:
        return False
    try:
        enc.tofile(path)
        return True
    except Exception:
        return False


def _get_platech_font(font_size: int):
    """优先返回 platech 字体；不可用时返回 None。"""
    if ImageFont is None:
        return None
    if not _PLATECH_FONT_PATH:
        return None
    if font_size in _PLATECH_FONT_CACHE:
        return _PLATECH_FONT_CACHE[font_size]
    try:
        font = ImageFont.truetype(_PLATECH_FONT_PATH, font_size)
        _PLATECH_FONT_CACHE[font_size] = font
        return font
    except Exception:
        return None


def _contains_cjk(text: str) -> bool:
    for ch in text:
        code = ord(ch)
        if 0x4E00 <= code <= 0x9FFF:
            return True
    return False


def _get_cjk_font(font_size: int):
    """获取可显示中文的系统字体。"""
    if ImageFont is None:
        return None
    if font_size in _CJK_FONT_CACHE:
        return _CJK_FONT_CACHE[font_size]
    for font_path in _CJK_FONT_CANDIDATES:
        if not os.path.isfile(font_path):
            continue
        try:
            font = ImageFont.truetype(font_path, font_size)
            _CJK_FONT_CACHE[font_size] = font
            return font
        except Exception:
            continue
    return None


def _select_font_for_text(text: str, font_size: int):
    """统一字体策略：中英文都优先使用 resources/fonts/simhei.ttf。"""
    return _get_platech_font(font_size) or _get_cjk_font(font_size)


def _select_font_path_for_text(text: str) -> str | None:
    """freetype 字体路径：中英文都优先 simhei.ttf。"""
    if _PLATECH_FONT_PATH and os.path.isfile(_PLATECH_FONT_PATH):
        return _PLATECH_FONT_PATH
    for p in _CJK_FONT_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def _get_freetype_drawer(font_path: str):
    """在 PIL 不可用时，尝试使用 cv2.freetype 画字。"""
    if not font_path:
        return None
    if font_path in _FREETYPE_CACHE:
        return _FREETYPE_CACHE[font_path]
    try:
        if not hasattr(cv2, "freetype"):
            if "no_module" not in _FREETYPE_ERROR_REPORTED:
                print("[yolo_show][font] cv2.freetype 模块不存在")
                _FREETYPE_ERROR_REPORTED.add("no_module")
            return None
        if not hasattr(cv2.freetype, "createFreeType2"):
            if "no_create" not in _FREETYPE_ERROR_REPORTED:
                print("[yolo_show][font] cv2.freetype.createFreeType2 不可用")
                _FREETYPE_ERROR_REPORTED.add("no_create")
            return None
        ft2 = cv2.freetype.createFreeType2()
        loaded = False
        load_errors = []
        # 不同 OpenCV 版本的 Python 绑定参数签名不一致，这里做兼容尝试。
        for loader in (
            lambda: ft2.loadFontData(fontFileName=font_path, idx=0),
            lambda: ft2.loadFontData(fontFileName=font_path, id=0),
            lambda: ft2.loadFontData(font_path, 0),
        ):
            try:
                loader()
                loaded = True
                break
            except Exception as e:
                load_errors.append(str(e))
        if not loaded:
            raise RuntimeError(" | ".join(load_errors))
        _FREETYPE_CACHE[font_path] = ft2
        return ft2
    except Exception as e:
        err_key = f"load_fail:{font_path}"
        if err_key not in _FREETYPE_ERROR_REPORTED:
            print(f"[yolo_show][font] freetype 加载字体失败: {font_path} | {e}")
            _FREETYPE_ERROR_REPORTED.add(err_key)
        return None


def _debug_print_font_env():
    print("[yolo_show][font] PIL 可用:", ImageFont is not None)
    print("[yolo_show][font] simhei 命中路径:", _PLATECH_FONT_PATH or "<未找到>")
    print("[yolo_show][font] simhei 候选路径:")
    for p in _PLATECH_FONT_CANDIDATES:
        print(f"  - {p} ({'存在' if os.path.isfile(p) else '不存在'})")
    print("[yolo_show][font] 中文字体候选路径:")
    for p in _CJK_FONT_CANDIDATES:
        print(f"  - {p} ({'存在' if os.path.isfile(p) else '不存在'})")


def _get_text_metrics(
    label_text: str, font_scale: float = 0.5, thickness: int = 1
) -> tuple[int, int, int]:
    """返回文本宽、高(基线以上)和 baseline。"""
    font_size = max(12, int(font_scale * 32))
    font = _select_font_for_text(label_text, font_size)
    if font is not None and Image is not None and ImageDraw is not None:
        draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        # 优先按“基线锚点”获取真实包围盒，避免 getmetrics 在不同字体上过宽导致位置偏差。
        try:
            x0, y0, x1, y1 = draw.textbbox((0, 0), label_text, font=font, anchor="ls")
            text_w = max(1, x1 - x0)
            text_h = max(1, int(-y0))  # 基线以上像素
            baseline = max(0, int(y1))  # 基线以下像素
            return text_w, text_h, baseline
        except TypeError:
            # 旧版 Pillow 不支持 anchor 参数，回退到 getmetrics。
            x0, y0, x1, y1 = draw.textbbox((0, 0), label_text, font=font)
            text_w = max(1, x1 - x0)
            try:
                ascent, descent = font.getmetrics()
                return text_w, max(1, int(ascent)), max(0, int(descent))
            except Exception:
                return text_w, max(1, y1 - y0), 0
    font_path = _select_font_path_for_text(label_text)
    ft2 = _get_freetype_drawer(font_path) if font_path else None
    if ft2 is not None:
        try:
            size, baseline = ft2.getTextSize(label_text, font_size, thickness)
            return max(1, size[0]), max(1, size[1]), max(0, baseline)
        except Exception:
            pass
    size, baseline = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
    return max(1, size[0]), max(1, size[1]), max(0, baseline)


def _get_text_size(label_text: str, font_scale: float = 0.5, thickness: int = 1) -> tuple[int, int]:
    """兼容旧调用：返回文本总宽高（含 baseline）。"""
    text_w, text_h, baseline = _get_text_metrics(label_text, font_scale, thickness)
    return text_w, text_h + baseline


def _draw_text(
    img,
    text: str,
    org: tuple[int, int],
    color: tuple[int, int, int] = (255, 255, 255),
    font_scale: float = 0.5,
    thickness: int = 1,
):
    """绘制文本：优先 platech.ttf，不可用则回退 cv2 内置字体。"""
    has_cjk = _contains_cjk(text)
    font_size = max(12, int(font_scale * 32))
    font = _select_font_for_text(text, font_size)
    font_path = _select_font_path_for_text(text)
    ft2 = _get_freetype_drawer(font_path) if font_path else None

    if font is not None:
        route = "pil"
    elif ft2 is not None:
        route = "freetype"
    else:
        route = "cv2"
    debug_key = f"{'cjk' if has_cjk else 'ascii'}-{route}"
    if debug_key not in _FONT_DEBUG_REPORTED:
        if route == "pil":
            font_src = getattr(font, "path", "<unknown>")
            print(
                f"[yolo_show][font] 文本示例 {text!r} -> 使用 PIL 字体: {font_src}"
            )
        elif route == "freetype":
            print(
                f"[yolo_show][font] 文本示例 {text!r} -> 使用 cv2.freetype 字体: {font_path}"
            )
        else:
            print(
                f"[yolo_show][font] 文本示例 {text!r} -> 回退 cv2 内置字体（可能导致中文乱码）"
            )
        _FONT_DEBUG_REPORTED.add(debug_key)

    if font is None or Image is None or ImageDraw is None:
        if ft2 is not None:
            try:
                ft2.putText(
                    img,
                    text,
                    org,
                    font_size,
                    color,
                    -1,
                    cv2.LINE_AA,
                    False,
                )
                return
            except Exception:
                pass
        cv2.putText(
            img,
            text,
            org,
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            color,
            thickness,
        )
        return
    pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    fill_color = (int(color[2]), int(color[1]), int(color[0]))
    # 外部传入的 org 按 OpenCV 语义是“基线点”，优先使用 PIL baseline 锚点保持一致。
    try:
        draw.text(org, text, fill=fill_color, font=font, anchor="ls")
    except TypeError:
        # 兼容不支持 anchor 的旧 Pillow：手动把 baseline 转为左上角。
        try:
            ascent, _descent = font.getmetrics()
            text_h = max(1, int(ascent))
        except Exception:
            x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
            text_h = max(1, y1 - y0)
        draw.text(
            (org[0], org[1] - text_h),
            text,
            fill=fill_color,
            font=font,
        )
    img[:] = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def _get_det_style_params(img_w: int, img_h: int) -> dict[str, float | int]:
    """
    检测可视化参数：
    - 1920x1080 作为最低基准，不缩小；
    - 仅当图片更大时按比例放大。
    """
    scale = max(1.0, max(img_w / 1920.0, img_h / 1080.0))
    return {
        "box_thickness": max(2, int(round(2 * scale))),
        "font_scale": 0.5 * scale,
        "text_thickness": max(1, int(round(1 * scale))),
        "text_pad": max(10, int(round(10 * scale))),
        "text_baseline_offset": max(5, int(round(5 * scale))),
    }


def _classify_yolo_line(parts: list) -> str | None:
    """单行是检测 (5 列) 还是分割 (class + 偶数个坐标，且总列数 >= 7)。"""
    n = len(parts)
    if n == 5:
        return "det"
    if n >= 7 and (n - 1) % 2 == 0:
        return "seg"
    return None


def _detect_visualize_mode(txt_folder: str, img_files: list[str], max_files: int = 30) -> str:
    """扫描若干 TXT，按行投票判断 det / seg（与 yolo2labelme 思路一致）。"""
    det_n, seg_n = 0, 0
    for img_name in img_files[:max_files]:
        txt_path = os.path.join(txt_folder, os.path.splitext(img_name)[0] + ".txt")
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


def _scan_visualize_type_presence(txt_folder: str, img_files: list[str]) -> tuple[bool, bool]:
    """扫描全部标签，返回是否存在 det / seg。"""
    has_det = False
    has_seg = False
    for img_name in img_files:
        txt_path = os.path.join(txt_folder, os.path.splitext(img_name)[0] + ".txt")
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


def _normalize_mode(mode: str) -> str:
    m = (mode or "auto").strip().lower()
    if m in ("auto", ""):
        return "auto"
    if m in ("det", "detect", "bbox"):
        return "det"
    if m in ("seg", "segment", "segmentation"):
        return "seg"
    print(f"警告: 未知模式 {mode!r}，将按 auto 处理。")
    return "auto"


def _scan_visualize_type_presence_json(label_folder: str, img_files: list[str]) -> tuple[bool, bool]:
    """扫描 JSON 标签，返回是否存在 det / seg。"""
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


def _detect_visualize_mode_json(label_folder: str, img_files: list[str], max_files: int = 30) -> str:
    """扫描若干 JSON，按 shape_type 投票判断 det / seg。"""
    det_n, seg_n = 0, 0
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


def visualize_yolo(img_folder, txt_folder, output_folder, mode="auto", label_format="txt"):
    """
    读取 YOLO TXT + 对应图片，绘制后保存（或分割模式下无输出目录时逐张预览）。

    Args:
        img_folder:    图片目录
        txt_folder:    标签目录
        output_folder: 输出目录；分割模式下留空则仅 cv2.imshow 预览（按任意键下一张，q 退出）
        mode:          auto | det | seg（与 LabelMe→YOLO 一致，亦可写 detect / segment 等别名）
        label_format:  txt | json（默认 txt）
    """
    random.seed(42)
    class_colors: dict[str, list[int]] = {}
    _debug_print_font_env()

    def get_color(cls_label: str) -> list[int]:
        key = str(cls_label)
        if key not in class_colors:
            # 用 md5 生成跨进程稳定种子，保证同一标签长期颜色一致，
            # 同时支持 "a-22-；" 这类非数字标签。
            seed = int(hashlib.md5(key.encode("utf-8")).hexdigest()[:8], 16)
            seeded = random.Random(seed)
            class_colors[key] = [seeded.randint(0, 255) for _ in range(3)]
        return class_colors[key]

    mode = _normalize_mode(mode)
    label_format = (label_format or "txt").strip().lower()
    if label_format not in ("txt", "json"):
        print(f"警告: 未知标签格式 {label_format!r}，将按 txt 处理。")
        label_format = "txt"

    img_files = [
        f
        for f in os.listdir(img_folder)
        if f.lower().endswith(_IMG_EXTS)
    ]
    if not img_files:
        print(f"错误: 在 {img_folder} 中没找到图片文件。")
        return

    out = (output_folder or "").strip()
    preview = not bool(out)

    auto_split_mixed = False
    if mode == "auto":
        if label_format == "json":
            has_det, has_seg = _scan_visualize_type_presence_json(txt_folder, img_files)
        else:
            has_det, has_seg = _scan_visualize_type_presence(txt_folder, img_files)
        if has_det and has_seg:
            auto_split_mixed = True
        else:
            if label_format == "json":
                mode = _detect_visualize_mode_json(txt_folder, img_files)
            else:
                mode = _detect_visualize_mode(txt_folder, img_files)

    if auto_split_mixed:
        if preview:
            print("自动混合模式需要指定输出文件夹。")
            return
        out_det = os.path.join(out, "det")
        out_seg = os.path.join(out, "seg")
        os.makedirs(out_det, exist_ok=True)
        os.makedirs(out_seg, exist_ok=True)
        print(f"标签格式: {label_format}")
        print("模式: 自动混合拆分 (det + seg)")
        print(f"输出目录 det: {out_det}")
        print(f"输出目录 seg: {out_seg}")
    else:
        mode_cn = "分割 (polygon)" if mode == "seg" else "检测 (bbox)"
        print(f"标签格式: {label_format}")
        print(f"模式: {mode_cn}  ({mode})")
        if mode == "det" and preview:
            print("检测模式必须指定输出文件夹。")
            return
        if not preview:
            os.makedirs(out, exist_ok=True)
            print(f"输出目录: {out}")

    print(f"找到 {len(img_files)} 张图片，开始可视化...")

    det_saved = 0
    seg_saved = 0

    if mode == "det" or auto_split_mixed:
        for img_name in tqdm(img_files, desc="YOLO 检测框可视化", unit="img"):
            img_path = os.path.join(img_folder, img_name)
            label_stem = os.path.splitext(img_name)[0]
            txt_name = f"{label_stem}.txt"
            txt_path = os.path.join(txt_folder, txt_name)
            json_name = f"{label_stem}.json"
            json_path = os.path.join(txt_folder, json_name)

            img = cv2_imread_unicode(img_path)
            if img is None:
                continue

            h, w, _ = img.shape
            det_style = _get_det_style_params(w, h)
            has_det_label = False

            if label_format == "json":
                if os.path.exists(json_path):
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
                            label_text = f"ID: {label_raw}"
                            cv2.rectangle(
                                img,
                                (x_min, y_min),
                                (x_max, y_max),
                                color,
                                int(det_style["box_thickness"]),
                            )
                            text_w, text_h, text_baseline = _get_text_metrics(
                                label_text,
                                float(det_style["font_scale"]),
                                int(det_style["text_thickness"]),
                            )
                            text_pad = max(2, int(det_style["text_pad"]) // 2)
                            # 对齐采用“顶部 padding + 字体高度”，避免不同 freetype baseline
                            # 在各 OpenCV 版本下差异导致文字沉到底部。
                            label_h = text_h + text_baseline + text_pad * 2
                            prefer_top = y_min - label_h >= 0
                            if prefer_top:
                                label_top = y_min - label_h
                                label_bottom = y_min
                            else:
                                label_top = y_min
                                label_bottom = min(h - 1, y_min + label_h)
                            text_y = min(label_top + text_pad + text_h, h - 1)
                            cv2.rectangle(
                                img,
                                (x_min, label_top),
                                (x_min + text_w, label_bottom),
                                color,
                                -1,
                            )
                            _draw_text(
                                img,
                                label_text,
                                (x_min, text_y),
                                (255, 255, 255),
                                float(det_style["font_scale"]),
                                int(det_style["text_thickness"]),
                            )
                    except Exception as e:
                        tqdm.write(f"解析文件 {json_name} 时出错: {e}")
            else:
                if os.path.exists(txt_path):
                    with open(txt_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()

                    for line in lines:
                        data = line.strip().split()
                        if _classify_yolo_line(data) != "det":
                            continue
                        try:
                            cls_label = str(data[0])
                            color = get_color(cls_label)
                            x_c, y_c, bw, bh = map(float, data[1:5])
                            has_det_label = True
                            x1 = int((x_c - bw / 2) * w)
                            y1 = int((y_c - bh / 2) * h)
                            x2 = int((x_c + bw / 2) * w)
                            y2 = int((y_c + bh / 2) * h)
                            label_text = f"ID: {cls_label}"
                            cv2.rectangle(
                                img,
                                (x1, y1),
                                (x2, y2),
                                color,
                                int(det_style["box_thickness"]),
                            )
                            text_w, text_h, text_baseline = _get_text_metrics(
                                label_text,
                                float(det_style["font_scale"]),
                                int(det_style["text_thickness"]),
                            )
                            text_pad = max(2, int(det_style["text_pad"]) // 2)
                            label_h = text_h + text_baseline + text_pad * 2
                            prefer_top = y1 - label_h >= 0
                            if prefer_top:
                                label_top = y1 - label_h
                                label_bottom = y1
                            else:
                                label_top = y1
                                label_bottom = min(h - 1, y1 + label_h)
                            text_y = min(label_top + text_pad + text_h, h - 1)
                            cv2.rectangle(
                                img,
                                (x1, label_top),
                                (x1 + text_w, label_bottom),
                                color,
                                -1,
                            )
                            _draw_text(
                                img,
                                label_text,
                                (x1, text_y),
                                (255, 255, 255),
                                float(det_style["font_scale"]),
                                int(det_style["text_thickness"]),
                            )
                        except Exception as e:
                            tqdm.write(f"解析文件 {txt_name} 时出错: {e}")
                            continue

            # 与分割模式保持一致：仅当存在且解析出有效标签时才输出
            if not has_det_label:
                continue

            save_root = out_det if auto_split_mixed else out
            save_path = os.path.join(save_root, img_name)
            if cv2_imwrite_unicode(save_path, img):
                det_saved += 1

    if mode == "seg" or auto_split_mixed:
        try:
            for img_name in tqdm(img_files, desc="YOLO 分割可视化", unit="img"):
                img_path = os.path.join(img_folder, img_name)
                label_stem = os.path.splitext(img_name)[0]
                txt_name = f"{label_stem}.txt"
                txt_path = os.path.join(txt_folder, txt_name)
                json_name = f"{label_stem}.json"
                json_path = os.path.join(txt_folder, json_name)

                if label_format == "json":
                    if not os.path.exists(json_path):
                        continue
                else:
                    if not os.path.exists(txt_path):
                        continue

                img = cv2_imread_unicode(img_path)
                if img is None:
                    tqdm.write(f"无法读取图片: {img_name}")
                    continue

                h, w = img.shape[:2]
                mask_overlay = img.copy()
                has_label = False

                if label_format == "json":
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            data_json = json.load(f)
                        for shape in data_json.get("shapes", []):
                            if shape.get("shape_type", "") != "polygon":
                                continue
                            points = shape.get("points", [])
                            if len(points) < 3:
                                continue
                            label_raw = str(shape.get("label", "0"))
                            color = get_color(label_raw)
                            has_label = True
                            pts = np.array(points, dtype=np.int32)
                            cv2.fillPoly(mask_overlay, [pts], color)
                            cv2.polylines(img, [pts], True, color, 2)
                            label_text = f"cls:{label_raw}"
                            _draw_text(
                                img,
                                label_text,
                                (pts[0][0], pts[0][1] - 10),
                                tuple(color),
                                0.6,
                                2,
                            )
                    except Exception as e:
                        tqdm.write(f"处理文件 {json_name} 时出错: {e}")
                        continue
                else:
                    with open(txt_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()

                    for line in lines:
                        data = line.strip().split()
                        if len(data) < 7:
                            continue
                        try:
                            cls_label = str(data[0])
                            color = get_color(cls_label)
                            has_label = True
                            coords = np.array(data[1:], dtype=np.float32).reshape(-1, 2)
                            coords[:, 0] *= w
                            coords[:, 1] *= h
                            pts = coords.astype(np.int32)
                            cv2.fillPoly(mask_overlay, [pts], color)
                            cv2.polylines(img, [pts], True, color, 2)
                            label_text = f"cls:{cls_label}"
                            _draw_text(
                                img,
                                label_text,
                                (pts[0][0], pts[0][1] - 10),
                                tuple(color),
                                0.6,
                                2,
                            )
                        except Exception as e:
                            tqdm.write(f"处理文件 {txt_name} 的某一行时出错: {e}")
                            continue

                if not has_label:
                    continue

                # 降低透明度（让分割区域更实一点）
                res_img = cv2.addWeighted(mask_overlay, 0.6, img, 0.4, 0)

                if preview:
                    display_img = (
                        cv2.resize(res_img, (1280, 720)) if w > 1280 else res_img
                    )
                    cv2.imshow("Preview", display_img)
                    if cv2.waitKey(0) & 0xFF == ord("q"):
                        break
                else:
                    save_root = out_seg if auto_split_mixed else out
                    save_path = os.path.join(save_root, img_name)
                    if cv2_imwrite_unicode(save_path, res_img):
                        seg_saved += 1
        finally:
            if preview:
                cv2.destroyAllWindows()

    print("\n处理完成！")
    if auto_split_mixed:
        print(f"det 可视化输出: {det_saved} 张")
        print(f"seg 可视化输出: {seg_saved} 张")
    print(f"共发现类别 ID: {sorted(class_colors.keys())}")


def draw_and_save(img_folder, txt_folder, output_folder, mode="auto"):
    """兼容旧名：等同于 visualize_yolo。"""
    visualize_yolo(img_folder, txt_folder, output_folder, mode=mode)


if __name__ == "__main__":
    IMAGE_DIR = r"F:\class_8\predict"
    LABEL_DIR = r"F:\class_8\labels"
    SAVE_DIR = r"F:\class_8\predict_yolo_show"
    visualize_yolo(IMAGE_DIR, LABEL_DIR, SAVE_DIR, mode="auto")
