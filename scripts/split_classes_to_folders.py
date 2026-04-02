"""
按类别拆分 YOLO 数据到独立文件夹。

规则：
1) 同一张图包含多个类别时，复制到多个类别目录。
2) 每个类别目录下的标签文件仅保留该类别对应行。
3) 仅复制，不移动原始文件。
"""

from __future__ import annotations

import os
import re
import shutil
from collections import defaultdict

from tqdm import tqdm

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def _safe_class_dir_name(class_name: str) -> str:
    """Windows 兼容目录名清洗，尽量保留原类别文本。"""
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", str(class_name).strip())
    return cleaned or "_empty_class_"


def _collect_images(images_dir: str) -> dict[str, str]:
    """收集图片 stem -> 文件名（不含路径）。"""
    out: dict[str, str] = {}
    for name in os.listdir(images_dir):
        full = os.path.join(images_dir, name)
        if not os.path.isfile(full):
            continue
        stem, ext = os.path.splitext(name)
        if ext.lower() in IMAGE_EXTS:
            out[stem] = name
    return out


def _parse_label_lines(label_path: str) -> dict[str, list[str]]:
    """解析单个 txt，返回 class -> 该类别所有原始行（去除空行）。"""
    class_to_lines: dict[str, list[str]] = defaultdict(list)
    with open(label_path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            parts = line.split()
            if not parts:
                continue
            class_to_lines[parts[0]].append(line)
    return class_to_lines


def _remap_lines_to_zero(lines: list[str]) -> list[str]:
    """将每行首列类别值重写为 0，保留其余坐标内容。"""
    out: list[str] = []
    for line in lines:
        parts = line.split()
        if len(parts) <= 1:
            out.append("0")
        else:
            out.append("0 " + " ".join(parts[1:]))
    return out


def split_classes_to_folders(
    images_dir: str,
    labels_dir: str,
    output_dir: str,
    remap_to_zero: bool = True,
):
    """
    按类别拆分 YOLO 数据。

    输出结构：
      output_dir/
        <class>/
          images/
          labels/
    """
    images_dir = os.path.abspath(images_dir)
    labels_dir = os.path.abspath(labels_dir)
    output_dir = os.path.abspath(output_dir)

    if not os.path.isdir(images_dir):
        raise FileNotFoundError(f"图片目录不存在: {images_dir}")
    if not os.path.isdir(labels_dir):
        raise FileNotFoundError(f"标签目录不存在: {labels_dir}")

    os.makedirs(output_dir, exist_ok=True)

    image_map = _collect_images(images_dir)
    label_files = sorted(
        n for n in os.listdir(labels_dir)
        if os.path.isfile(os.path.join(labels_dir, n)) and n.lower().endswith(".txt")
    )

    total_labels = len(label_files)
    paired = 0
    skipped_no_image = 0
    skipped_empty = 0
    class_image_count: dict[str, int] = defaultdict(int)
    class_label_line_count: dict[str, int] = defaultdict(int)

    print(f"图片目录: {images_dir}")
    print(f"标签目录: {labels_dir}")
    print(f"输出目录: {output_dir}")
    print(f"共发现标签文件: {total_labels}")
    print(f"类别重映射为 0: {'是' if remap_to_zero else '否'}")

    for label_name in tqdm(label_files, desc="按类别拆分", unit="file"):
        stem = os.path.splitext(label_name)[0]
        image_name = image_map.get(stem)
        if not image_name:
            skipped_no_image += 1
            continue

        label_path = os.path.join(labels_dir, label_name)
        class_to_lines = _parse_label_lines(label_path)
        if not class_to_lines:
            skipped_empty += 1
            continue

        paired += 1
        image_path = os.path.join(images_dir, image_name)

        for class_name, lines in class_to_lines.items():
            class_dir = _safe_class_dir_name(class_name)
            cls_images_dir = os.path.join(output_dir, class_dir, "images")
            cls_labels_dir = os.path.join(output_dir, class_dir, "labels")
            os.makedirs(cls_images_dir, exist_ok=True)
            os.makedirs(cls_labels_dir, exist_ok=True)

            dst_img = os.path.join(cls_images_dir, image_name)
            dst_lbl = os.path.join(cls_labels_dir, label_name)

            shutil.copy2(image_path, dst_img)
            write_lines = _remap_lines_to_zero(lines) if remap_to_zero else lines
            with open(dst_lbl, "w", encoding="utf-8") as f:
                f.write("\n".join(write_lines) + "\n")

            class_image_count[class_dir] += 1
            class_label_line_count[class_dir] += len(lines)

    print("-" * 50)
    print(f"处理完成：共标签 {total_labels}，成功匹配图片 {paired}")
    print(f"跳过：无同名图片 {skipped_no_image}，空标签 {skipped_empty}")

    if not class_image_count:
        print("未生成任何类别目录。")
        return

    print("类别统计：")
    for cls in sorted(class_image_count.keys()):
        print(
            f"  {cls}: 图片 {class_image_count[cls]}，"
            f"标签行 {class_label_line_count[cls]}"
        )


if __name__ == "__main__":
    # 示例：按需修改后手动运行
    split_classes_to_folders(
        images_dir=r"D:\dataset\images",
        labels_dir=r"D:\dataset\labels",
        output_dir=r"D:\dataset\split_by_class",
        remap_to_zero=True,
    )
