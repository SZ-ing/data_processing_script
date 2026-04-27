"""
按类别拆分 YOLO 数据到独立文件夹。

规则：
1) 同一张图包含多个类别时，复制到多个类别目录。
2) 每个类别目录下的标签文件仅保留该类别对应行。
3) 仅复制，不移动原始文件。
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
from collections import defaultdict

from tqdm import tqdm

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
IMAGE_EXT_PRIORITY = [".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"]


def _safe_class_dir_name(class_name: str) -> str:
    """Windows 兼容目录名清洗，尽量保留原类别文本。"""
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", str(class_name).strip())
    return cleaned or "_empty_class_"


def _collect_images(images_dir: str) -> dict[str, str]:
    """收集图片 stem -> 文件名（不含路径），同名不同后缀按优先级选一个。"""
    candidates: dict[str, list[str]] = defaultdict(list)
    for name in sorted(os.listdir(images_dir)):
        full = os.path.join(images_dir, name)
        if not os.path.isfile(full):
            continue
        stem, ext = os.path.splitext(name)
        if ext.lower() in IMAGE_EXTS:
            candidates[stem].append(name)

    ext_rank = {ext: idx for idx, ext in enumerate(IMAGE_EXT_PRIORITY)}
    out: dict[str, str] = {}
    for stem, names in candidates.items():
        if len(names) == 1:
            out[stem] = names[0]
            continue

        names_sorted = sorted(
            names,
            key=lambda n: (ext_rank.get(os.path.splitext(n)[1].lower(), 999), n.lower()),
        )
        out[stem] = names_sorted[0]
        print(
            f"[警告] 检测到同名多图: {stem} -> {names}；"
            f"已按优先级使用: {out[stem]}"
        )
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


def _parse_labelme_json_by_class(label_path: str) -> tuple[dict[str, list[dict]], dict]:
    """解析单个 LabelMe JSON，返回 class -> shapes 以及原始 JSON 数据。"""
    with open(label_path, "r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)

    class_to_shapes: dict[str, list[dict]] = defaultdict(list)
    for shape in data.get("shapes", []):
        label = str(shape.get("label", "")).strip()
        if not label:
            continue
        class_to_shapes[label].append(shape)
    return class_to_shapes, data


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


def _remap_shapes_to_zero(shapes: list[dict]) -> list[dict]:
    """将 LabelMe shape 的 label 统一改为 '0'。"""
    out: list[dict] = []
    for shape in shapes:
        copied = dict(shape)
        copied["label"] = "0"
        out.append(copied)
    return out


def split_classes_to_folders(
    images_dir: str,
    labels_dir: str,
    output_dir: str,
    remap_to_zero: bool = False,
    label_type: str = "txt",
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

    lt = str(label_type).strip().lower()
    if lt not in ("txt", "json"):
        raise ValueError(f"不支持的标签类型: {label_type}")

    image_map = _collect_images(images_dir)
    label_ext = ".txt" if lt == "txt" else ".json"
    label_files = sorted(
        n for n in os.listdir(labels_dir)
        if os.path.isfile(os.path.join(labels_dir, n)) and n.lower().endswith(label_ext)
    )

    total_labels = len(label_files)
    paired = 0
    skipped_no_image = 0
    skipped_empty = 0
    bad_json = 0
    class_image_count: dict[str, int] = defaultdict(int)
    class_label_line_count: dict[str, int] = defaultdict(int)

    print(f"图片目录: {images_dir}")
    print(f"标签目录: {labels_dir}")
    print(f"输出目录: {output_dir}")
    print(f"标签类型: {lt}")
    print(f"共发现标签文件: {total_labels}")
    print(f"类别重映射为 0: {'是' if remap_to_zero else '否'}")

    for label_name in tqdm(label_files, desc="按类别拆分", unit="file"):
        stem = os.path.splitext(label_name)[0]
        image_name = image_map.get(stem)
        if not image_name:
            skipped_no_image += 1
            continue

        label_path = os.path.join(labels_dir, label_name)
        if lt == "json":
            try:
                class_to_shapes, json_data = _parse_labelme_json_by_class(label_path)
            except Exception:
                bad_json += 1
                tqdm.write(f"跳过损坏 JSON: {label_name}")
                continue
            if not class_to_shapes:
                skipped_empty += 1
                continue
        else:
            class_to_lines = _parse_label_lines(label_path)
            if not class_to_lines:
                skipped_empty += 1
                continue

        if lt == "json":
            class_entries = class_to_shapes.items()
        else:
            class_entries = class_to_lines.items()

        if not class_entries:
            skipped_empty += 1
            continue

        paired += 1
        image_path = os.path.join(images_dir, image_name)

        for class_name, rows in class_entries:
            class_dir = _safe_class_dir_name(class_name)
            cls_images_dir = os.path.join(output_dir, class_dir, "images")
            cls_labels_dir = os.path.join(output_dir, class_dir, "labels")
            os.makedirs(cls_images_dir, exist_ok=True)
            os.makedirs(cls_labels_dir, exist_ok=True)

            dst_img = os.path.join(cls_images_dir, image_name)
            dst_lbl = os.path.join(cls_labels_dir, label_name)

            shutil.copy2(image_path, dst_img)
            if lt == "json":
                write_shapes = _remap_shapes_to_zero(rows) if remap_to_zero else rows
                out_data = copy.deepcopy(json_data)
                out_data["shapes"] = write_shapes
                with open(dst_lbl, "w", encoding="utf-8") as f:
                    json.dump(out_data, f, ensure_ascii=False, indent=2)
            else:
                write_lines = _remap_lines_to_zero(rows) if remap_to_zero else rows
                with open(dst_lbl, "w", encoding="utf-8") as f:
                    f.write("\n".join(write_lines) + "\n")

            class_image_count[class_dir] += 1
            class_label_line_count[class_dir] += len(rows)

    print("-" * 50)
    print(f"处理完成：共标签 {total_labels}，成功匹配图片 {paired}")
    print(f"跳过：无同名图片 {skipped_no_image}，空标签 {skipped_empty}，损坏 JSON {bad_json}")

    if not class_image_count:
        print("未生成任何类别目录。")
        return

    print("类别统计：")
    for cls in sorted(class_image_count.keys()):
        print(
            f"  {cls}: 图片 {class_image_count[cls]} 张，"
            f"标签 {class_label_line_count[cls]} 个"
        )


if __name__ == "__main__":
    # 示例：按需修改后手动运行
    split_classes_to_folders(
        images_dir=r"D:\dataset\images",
        labels_dir=r"D:\dataset\labels",
        output_dir=r"D:\dataset\split_by_class",
        remap_to_zero=False,
        label_type="txt",
    )
