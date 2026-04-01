import base64
import json
import os
from io import BytesIO

from PIL import Image
from tqdm import tqdm


def _image_to_base64(image_path):
    with Image.open(image_path) as img:
        buffer = BytesIO()
        img_format = img.format if img.format else "PNG"
        img.save(buffer, format=img_format)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _find_image_path(images_dir, base_name):
    valid_extensions = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp")
    for ext in valid_extensions:
        image_path = os.path.join(images_dir, base_name + ext)
        if os.path.exists(image_path):
            return image_path
    return None


def _parse_det_line(parts, img_width, img_height):
    """5 列检测格式 → rectangle shape"""
    x_center = float(parts[1])
    y_center = float(parts[2])
    w = float(parts[3])
    h = float(parts[4])

    bw = w * img_width
    bh = h * img_height
    cx = x_center * img_width
    cy = y_center * img_height

    xmin = max(0.0, min(img_width, cx - bw / 2.0))
    ymin = max(0.0, min(img_height, cy - bh / 2.0))
    xmax = max(0.0, min(img_width, cx + bw / 2.0))
    ymax = max(0.0, min(img_height, cy + bh / 2.0))

    return [[xmin, ymin], [xmax, ymax]], "rectangle"


def _parse_seg_line(parts, img_width, img_height):
    """≥7 列分割格式 → polygon shape"""
    coords = parts[1:]
    points = []
    for i in range(0, len(coords), 2):
        x = max(0.0, min(img_width, float(coords[i]) * img_width))
        y = max(0.0, min(img_height, float(coords[i + 1]) * img_height))
        points.append([x, y])
    return points, "polygon"


def yolo2labelme(txt_dir, images_dir, output_dir, include_image_data=True):
    """
    将 YOLO TXT 转换为 LabelMe JSON。
    自动根据每行列数判断检测 (5列) 或分割 (≥7列) 格式。

    Args:
        txt_dir:            YOLO TXT 标签文件夹
        images_dir:         对应图片文件夹
        output_dir:         输出 JSON 文件夹
        include_image_data: 是否在 JSON 中写入 imageData
    """
    os.makedirs(output_dir, exist_ok=True)

    txt_files = sorted([f for f in os.listdir(txt_dir) if f.lower().endswith(".txt")])
    if not txt_files:
        print(f"未找到 TXT 文件: {txt_dir}")
        return

    print(f"共找到 {len(txt_files)} 个 TXT 文件，开始转换...")

    converted_count = 0
    skipped_count = 0
    det_count, seg_count = 0, 0

    for txt_file in tqdm(txt_files, desc="YOLO → LabelMe", unit="file"):
        base_name = os.path.splitext(txt_file)[0]
        txt_path = os.path.join(txt_dir, txt_file)
        image_path = _find_image_path(images_dir, base_name)

        if not image_path:
            tqdm.write(f"跳过 {txt_file}: 未找到同名图片")
            skipped_count += 1
            continue

        try:
            with Image.open(image_path) as img:
                img_width, img_height = img.size
        except Exception as e:
            tqdm.write(f"跳过 {txt_file}: 无法读取图片尺寸，原因: {e}")
            skipped_count += 1
            continue

        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
        except Exception as e:
            tqdm.write(f"跳过 {txt_file}: 无法读取标签文件，原因: {e}")
            skipped_count += 1
            continue

        shapes = []
        for line_no, line in enumerate(lines, start=1):
            parts = line.split()
            num_parts = len(parts)

            try:
                label = parts[0]

                if num_parts == 5:
                    points, shape_type = _parse_det_line(parts, img_width, img_height)
                    det_count += 1
                elif num_parts >= 7 and (num_parts - 1) % 2 == 0:
                    points, shape_type = _parse_seg_line(parts, img_width, img_height)
                    seg_count += 1
                else:
                    tqdm.write(f"警告: {txt_file} 第 {line_no} 行列数异常 ({num_parts})，已跳过。")
                    continue
            except (ValueError, IndexError):
                tqdm.write(f"警告: {txt_file} 第 {line_no} 行解析失败，已跳过。内容: {line}")
                continue

            shapes.append({
                "label": label,
                "points": points,
                "group_id": None,
                "description": "",
                "shape_type": shape_type,
                "flags": {},
            })

        image_data = None
        if include_image_data:
            try:
                image_data = _image_to_base64(image_path)
            except Exception as e:
                tqdm.write(f"警告: {txt_file} 对应图片无法写入 imageData，已置空。原因: {e}")

        labelme_data = {
            "version": "5.5.0",
            "flags": {},
            "shapes": shapes,
            "imagePath": os.path.basename(image_path),
            "imageData": image_data,
            "imageHeight": img_height,
            "imageWidth": img_width,
        }

        output_path = os.path.join(output_dir, f"{base_name}.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(labelme_data, f, ensure_ascii=False, indent=2)

        converted_count += 1

    print("-" * 30)
    print(f"转换完成！共生成 {converted_count} 个 JSON 文件。")
    print(f"检测框: {det_count} 个，分割多边形: {seg_count} 个")
    print(f"跳过文件数: {skipped_count}")
    print(f"保存路径: {os.path.abspath(output_dir)}")


# 兼容别名
yolo2labelme_seg = yolo2labelme


if __name__ == "__main__":
    TXT_FOLDER = r"H:\3.24 非机动车——董嘉琪\labels"
    IMAGES_FOLDER = r"H:\3.24 非机动车——董嘉琪\images"
    OUTPUT_JSON_FOLDER = r"H:\3.24 非机动车——董嘉琪\json_labels"

    yolo2labelme(TXT_FOLDER, IMAGES_FOLDER, OUTPUT_JSON_FOLDER)
