import json
import os
from pathlib import Path
from tqdm import tqdm


def _shape_to_yolo_det(shape, img_width, img_height):
    """rectangle / 任意形状 → YOLO 检测格式: class cx cy w h"""
    points = shape.get("points", [])
    if not points:
        return None

    x_coords = [p[0] for p in points]
    y_coords = [p[1] for p in points]
    xmin, xmax = min(x_coords), max(x_coords)
    ymin, ymax = min(y_coords), max(y_coords)

    dw, dh = 1.0 / img_width, 1.0 / img_height
    cx = max(0, min(1, (xmin + xmax) / 2.0 * dw))
    cy = max(0, min(1, (ymin + ymax) / 2.0 * dh))
    w = max(0, min(1, (xmax - xmin) * dw))
    h = max(0, min(1, (ymax - ymin) * dh))
    return f"{cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


def _shape_to_yolo_seg(shape, img_width, img_height):
    """polygon → YOLO 分割格式: class x1 y1 x2 y2 ..."""
    points = shape.get("points", [])
    if len(points) < 3:
        return None

    parts = []
    for p in points:
        px = max(0, min(1, p[0] / img_width))
        py = max(0, min(1, p[1] / img_height))
        parts.append(f"{px:.6f}")
        parts.append(f"{py:.6f}")
    return " ".join(parts)


def _detect_mode(json_dir, json_files):
    """扫描前几个 JSON，根据 shape_type 自动判断 检测 / 分割。"""
    sample_count = min(10, len(json_files))
    rect_count, poly_count = 0, 0

    for json_file in json_files[:sample_count]:
        json_path = os.path.join(json_dir, json_file)
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for shape in data.get("shapes", []):
                st = shape.get("shape_type", "")
                if st == "rectangle":
                    rect_count += 1
                elif st == "polygon":
                    poly_count += 1
        except Exception:
            continue

    if poly_count > rect_count:
        return "seg"
    return "det"


def _collect_labels(json_dir, json_files):
    """预扫描所有 JSON，收集全部唯一 label。"""
    all_labels = set()
    for json_file in json_files:
        json_path = os.path.join(json_dir, json_file)
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for shape in data.get("shapes", []):
                label = shape.get("label", "")
                if label:
                    all_labels.add(label)
        except Exception:
            continue
    return all_labels


def labelme2yolo(json_dir, output_dir, mode="auto"):
    """
    将 LabelMe JSON 转换为 YOLO TXT 格式。
    自动根据 shape_type 判断输出检测格式还是分割格式。
    支持数字标签和字符串标签，字符串标签会自动分配 class_id。

    Args:
        json_dir:   存放 JSON 文件的文件夹路径
        output_dir: 存放生成的 TXT 标签的文件夹路径
        mode:       "auto" 自动判断 | "det" 强制检测 | "seg" 强制分割
    """
    os.makedirs(output_dir, exist_ok=True)

    json_files = [f for f in os.listdir(json_dir) if f.endswith(".json")]
    if not json_files:
        print(f"未找到 JSON 文件: {json_dir}")
        return

    if mode == "auto":
        mode = _detect_mode(json_dir, json_files)

    mode_label = "检测 (bbox)" if mode == "det" else "分割 (polygon)"
    print(f"自动识别模式: {mode_label}")

    print("正在预扫描标签...")
    all_labels = _collect_labels(json_dir, json_files)
    print(f"发现 {len(all_labels)} 个类别: {sorted(all_labels)}")
    print(f"共找到 {len(json_files)} 个 JSON 文件，开始转换...")

    converter = _shape_to_yolo_det if mode == "det" else _shape_to_yolo_seg
    count = 0

    for json_file in tqdm(json_files, desc=f"LabelMe → YOLO {mode_label}", unit="file"):
        json_path = os.path.join(json_dir, json_file)

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            tqdm.write(f"无法读取文件 {json_file}: {e}")
            continue

        image_path_field = data.get("imagePath", "")
        if image_path_field:
            base_name = os.path.splitext(os.path.basename(image_path_field))[0]
        else:
            base_name = os.path.splitext(json_file)[0]

        img_width = data.get("imageWidth")
        img_height = data.get("imageHeight")
        if not img_width or not img_height:
            tqdm.write(f"跳过 {json_file}: 缺少尺寸信息")
            continue

        txt_path = os.path.join(output_dir, f"{base_name}.txt")

        yolo_lines = []
        for shape in data.get("shapes", []):
            label_str = shape.get("label", "")
            if not label_str:
                continue

            coords = converter(shape, img_width, img_height)
            if coords is None:
                continue
            yolo_lines.append(f"{label_str} {coords}")

        with open(txt_path, "w", encoding="utf-8") as f:
            if yolo_lines:
                f.write("\n".join(yolo_lines))
        count += 1

    print("-" * 30)
    print(f"转换完成！模式: {mode_label}，共处理 {count} 个文件。")
    print(f"涉及类别: {sorted(all_labels)}")
    print(f"保存路径: {os.path.abspath(output_dir)}")


# 保留旧函数名作为兼容别名
labelme2yolo_direct_id = labelme2yolo
labelme2yolo_seg_direct_id = lambda json_dir, output_dir: labelme2yolo(json_dir, output_dir, mode="seg")


if __name__ == "__main__":
    JSON_FOLDER = r"H:\3.24 非机动车——董嘉琪\json_labels"
    OUTPUT_FOLDER = r"H:\3.24 非机动车——董嘉琪\labels"

    labelme2yolo(JSON_FOLDER, OUTPUT_FOLDER)
