"""
YOLO TXT 可视化：检测框 (det) / 分割 (seg)，支持 auto 根据标签列数自动判断。
"""

import os
import random

import cv2
import numpy as np
from tqdm import tqdm

_IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp")


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


def visualize_yolo(img_folder, txt_folder, output_folder, mode="auto"):
    """
    读取 YOLO TXT + 对应图片，绘制后保存（或分割模式下无输出目录时逐张预览）。

    Args:
        img_folder:    图片目录
        txt_folder:    TXT 标签目录
        output_folder: 输出目录；分割模式下留空则仅 cv2.imshow 预览（按任意键下一张，q 退出）
        mode:          auto | det | seg（与 LabelMe→YOLO 一致，亦可写 detect / segment 等别名）
    """
    random.seed(42)
    class_colors: dict[int, list[int]] = {}

    def get_color(cls_id: int) -> list[int]:
        if cls_id not in class_colors:
            class_colors[cls_id] = [random.randint(0, 255) for _ in range(3)]
        return class_colors[cls_id]

    mode = _normalize_mode(mode)

    img_files = [
        f
        for f in os.listdir(img_folder)
        if f.lower().endswith(_IMG_EXTS)
    ]
    if not img_files:
        print(f"错误: 在 {img_folder} 中没找到图片文件。")
        return

    if mode == "auto":
        mode = _detect_visualize_mode(txt_folder, img_files)

    mode_cn = "分割 (polygon)" if mode == "seg" else "检测 (bbox)"
    print(f"模式: {mode_cn}  ({mode})")
    print(f"找到 {len(img_files)} 张图片，开始可视化...")

    out = (output_folder or "").strip()
    preview = not bool(out)

    if mode == "det" and preview:
        print("检测模式必须指定输出文件夹。")
        return

    if not preview:
        os.makedirs(out, exist_ok=True)
        print(f"输出目录: {out}")

    if mode == "det":
        for img_name in tqdm(img_files, desc="YOLO 检测框可视化", unit="img"):
            img_path = os.path.join(img_folder, img_name)
            txt_name = os.path.splitext(img_name)[0] + ".txt"
            txt_path = os.path.join(txt_folder, txt_name)

            img = cv2_imread_unicode(img_path)
            if img is None:
                continue

            h, w, _ = img.shape
            has_label = False

            if os.path.exists(txt_path):
                with open(txt_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                for line in lines:
                    data = line.strip().split()
                    if len(data) != 5:
                        continue
                    try:
                        cls_id = int(data[0])
                        color = get_color(cls_id)
                        x_c, y_c, bw, bh = map(float, data[1:5])
                        has_label = True
                        x1 = int((x_c - bw / 2) * w)
                        y1 = int((y_c - bh / 2) * h)
                        x2 = int((x_c + bw / 2) * w)
                        y2 = int((y_c + bh / 2) * h)
                        label_text = f"ID: {cls_id}"
                        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
                        text_size = cv2.getTextSize(
                            label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
                        )[0]
                        cv2.rectangle(
                            img,
                            (x1, y1 - text_size[1] - 10),
                            (x1 + text_size[0], y1),
                            color,
                            -1,
                        )
                        cv2.putText(
                            img,
                            label_text,
                            (x1, y1 - 5),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (255, 255, 255),
                            1,
                        )
                    except Exception as e:
                        tqdm.write(f"解析文件 {txt_name} 时出错: {e}")
                        continue

            save_path = os.path.join(out, img_name)
            cv2_imwrite_unicode(save_path, img)

    else:
        try:
            for img_name in tqdm(img_files, desc="YOLO 分割可视化", unit="img"):
                img_path = os.path.join(img_folder, img_name)
                txt_name = os.path.splitext(img_name)[0] + ".txt"
                txt_path = os.path.join(txt_folder, txt_name)

                if not os.path.exists(txt_path):
                    continue

                img = cv2_imread_unicode(img_path)
                if img is None:
                    tqdm.write(f"无法读取图片: {img_name}")
                    continue

                h, w = img.shape[:2]
                mask_overlay = img.copy()
                has_label = False

                with open(txt_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                for line in lines:
                    data = line.strip().split()
                    if len(data) < 7:
                        continue
                    try:
                        class_id = int(data[0])
                        color = get_color(class_id)
                        has_label = True
                        coords = np.array(data[1:], dtype=np.float32).reshape(-1, 2)
                        coords[:, 0] *= w
                        coords[:, 1] *= h
                        pts = coords.astype(np.int32)
                        cv2.fillPoly(mask_overlay, [pts], color)
                        cv2.polylines(img, [pts], True, color, 2)
                        label_text = f"cls:{class_id}"
                        cv2.putText(
                            img,
                            label_text,
                            (pts[0][0], pts[0][1] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            color,
                            2,
                        )
                    except Exception as e:
                        tqdm.write(f"处理文件 {txt_name} 的某一行时出错: {e}")
                        continue

                if not has_label:
                    continue

                res_img = cv2.addWeighted(mask_overlay, 0.4, img, 0.6, 0)

                if preview:
                    display_img = (
                        cv2.resize(res_img, (1280, 720)) if w > 1280 else res_img
                    )
                    cv2.imshow("Preview", display_img)
                    if cv2.waitKey(0) & 0xFF == ord("q"):
                        break
                else:
                    save_path = os.path.join(out, img_name)
                    cv2_imwrite_unicode(save_path, res_img)
        finally:
            if preview:
                cv2.destroyAllWindows()

    print("\n处理完成！")
    print(f"共发现类别 ID: {sorted(class_colors.keys())}")


def draw_and_save(img_folder, txt_folder, output_folder, mode="auto"):
    """兼容旧名：等同于 visualize_yolo。"""
    visualize_yolo(img_folder, txt_folder, output_folder, mode=mode)


if __name__ == "__main__":
    IMAGE_DIR = r"F:\class_8\predict"
    LABEL_DIR = r"F:\class_8\labels"
    SAVE_DIR = r"F:\class_8\predict_yolo_show"
    visualize_yolo(IMAGE_DIR, LABEL_DIR, SAVE_DIR, mode="auto")
