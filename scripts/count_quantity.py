import json
import os
from collections import defaultdict

from tqdm import tqdm


def _label_sort_key(label):
    """类别排序：数字优先按数值，再按字符串。"""
    s = str(label)
    if s.isdigit():
        return (0, int(s))
    return (1, s)


def _print_summary(instance_counts, image_counts, label_type, total_images_with_labels):
    sorted_ids = sorted(instance_counts.keys(), key=_label_sort_key)

    title = "类别值"
    print(f"{title:<14} | {'文件数':<10} | {'标注框数':<12}")
    print("-" * 60)

    total_boxes = 0
    for cid in sorted_ids:
        boxes = instance_counts[cid]
        images = image_counts[cid]
        total_boxes += boxes
        print(f"{str(cid):<16} | {images:<12} | {boxes:<14}")

    print("-" * 60)
    print(
        f"总计: {len(sorted_ids)}个类别，{total_images_with_labels}张图片，{total_boxes}个标注框。"
        f"（标签类型: {label_type}）"
    )


def _collect_label_files(label_dir, suffix, recursive_subfolders=False):
    """收集标签文件路径列表，支持可选递归子目录。"""
    suffix = str(suffix).lower()
    if recursive_subfolders:
        result = []
        for root, _, files in os.walk(label_dir):
            for name in files:
                low = name.lower()
                if low.endswith(suffix) and low != "classes.txt":
                    result.append(os.path.join(root, name))
        return result

    return [
        os.path.join(label_dir, f)
        for f in os.listdir(label_dir)
        if f.lower().endswith(suffix) and f.lower() != "classes.txt"
    ]


def _image_key_from_label_path(label_path):
    """用于“图片数”去重的 key：同名标签文件视为同一张图片。"""
    base_name = os.path.basename(label_path)
    stem, _ = os.path.splitext(base_name)
    return stem


def _count_from_txt(label_dir, recursive_subfolders=False):
    """统计 YOLO TXT 标签文件夹中的类别数量和图片分布。"""
    instance_counts = defaultdict(int)
    image_name_sets = defaultdict(set)
    total_image_name_set = set()

    txt_files = _collect_label_files(
        label_dir, ".txt", recursive_subfolders=recursive_subfolders
    )
    if not txt_files:
        print(f"在目录 {label_dir} 中未找到 TXT 标签文件。")
        return

    print(f"正在分析 {len(txt_files)} 个 TXT 标签文件...\n")

    for txt_path in tqdm(txt_files, desc="统计 TXT 标签", unit="file"):
        classes_in_this_file = set()
        image_key = _image_key_from_label_path(txt_path)

        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split()
                    if not parts:
                        continue
                    class_id = parts[0]
                    instance_counts[class_id] += 1
                    classes_in_this_file.add(class_id)

            for cls in classes_in_this_file:
                image_name_sets[cls].add(image_key)
            if classes_in_this_file:
                total_image_name_set.add(image_key)
        except Exception as e:
            tqdm.write(f"读取文件 {txt_path} 出错: {e}")

    image_counts = {cls: len(name_set) for cls, name_set in image_name_sets.items()}
    total_images_with_labels = len(total_image_name_set)
    _print_summary(instance_counts, image_counts, "txt", total_images_with_labels)


def _count_from_labelme_json(label_dir, recursive_subfolders=False):
    """统计 LabelMe JSON 中各类别实例数与文件分布。"""
    instance_counts = defaultdict(int)
    image_name_sets = defaultdict(set)
    total_image_name_set = set()

    json_files = _collect_label_files(
        label_dir, ".json", recursive_subfolders=recursive_subfolders
    )
    if not json_files:
        print(f"在目录 {label_dir} 中未找到 JSON 标签文件。")
        return

    print(f"正在分析 {len(json_files)} 个 LabelMe JSON 文件...\n")

    for json_path in tqdm(json_files, desc="统计 JSON 标签", unit="file"):
        classes_in_this_file = set()
        image_key = _image_key_from_label_path(json_path)
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for shape in data.get("shapes", []):
                label = str(shape.get("label", "")).strip()
                if not label:
                    continue
                instance_counts[label] += 1
                classes_in_this_file.add(label)

            for cls in classes_in_this_file:
                image_name_sets[cls].add(image_key)
            if classes_in_this_file:
                total_image_name_set.add(image_key)
        except Exception as e:
            tqdm.write(f"读取文件 {json_path} 出错: {e}")

    image_counts = {cls: len(name_set) for cls, name_set in image_name_sets.items()}
    total_images_with_labels = len(total_image_name_set)
    _print_summary(instance_counts, image_counts, "labelme_json", total_images_with_labels)


def count_yolo_labels(label_dir, label_type="txt", recursive_subfolders=False):
    """
    统计标签类别数量与文件分布。

    Args:
        label_dir: 标签文件夹
        label_type: txt | json
        recursive_subfolders: 是否递归子文件夹
    """
    if not os.path.isdir(label_dir):
        print(f"目录不存在: {label_dir}")
        return

    lt = str(label_type).strip().lower()
    if lt == "json":
        _count_from_labelme_json(
            label_dir, recursive_subfolders=bool(recursive_subfolders)
        )
    else:
        _count_from_txt(label_dir, recursive_subfolders=bool(recursive_subfolders))


if __name__ == "__main__":
    LABEL_FOLDER = r"H:\3.24 非机动车——董嘉琪\labels"
    count_yolo_labels(LABEL_FOLDER, label_type="txt")