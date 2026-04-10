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


def _print_summary(instance_counts, image_counts, label_type):
    sorted_ids = sorted(instance_counts.keys(), key=_label_sort_key)

    title = "类别值"
    print(f"{title:<14} | {'实例总数':<12} | {'包含该类别的文件数':<18}")
    print("-" * 60)

    total_all_instances = 0
    for cid in sorted_ids:
        instances = instance_counts[cid]
        images = image_counts[cid]
        total_all_instances += instances
        print(f"{str(cid):<16} | {instances:<14} | {images:<18}")

    print("-" * 60)
    print(
        f"总计: {len(sorted_ids)} 个类别，共 {total_all_instances} 个标注实例。"
        f"（标签类型: {label_type}）"
    )


def _count_from_txt(label_dir):
    """统计 YOLO TXT 标签文件夹中的类别数量和图片分布。"""
    instance_counts = defaultdict(int)
    image_counts = defaultdict(int)

    txt_files = [
        f for f in os.listdir(label_dir)
        if f.lower().endswith(".txt") and f != "classes.txt"
    ]
    if not txt_files:
        print(f"在目录 {label_dir} 中未找到 TXT 标签文件。")
        return

    print(f"正在分析 {len(txt_files)} 个 TXT 标签文件...\n")

    for txt_name in tqdm(txt_files, desc="统计 TXT 标签", unit="file"):
        txt_path = os.path.join(label_dir, txt_name)
        classes_in_this_file = set()

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
                image_counts[cls] += 1
        except Exception as e:
            tqdm.write(f"读取文件 {txt_name} 出错: {e}")

    _print_summary(instance_counts, image_counts, "txt")


def _count_from_labelme_json(label_dir):
    """统计 LabelMe JSON 中各类别实例数与文件分布。"""
    instance_counts = defaultdict(int)
    image_counts = defaultdict(int)

    json_files = [f for f in os.listdir(label_dir) if f.lower().endswith(".json")]
    if not json_files:
        print(f"在目录 {label_dir} 中未找到 JSON 标签文件。")
        return

    print(f"正在分析 {len(json_files)} 个 LabelMe JSON 文件...\n")

    for json_name in tqdm(json_files, desc="统计 JSON 标签", unit="file"):
        json_path = os.path.join(label_dir, json_name)
        classes_in_this_file = set()
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
                image_counts[cls] += 1
        except Exception as e:
            tqdm.write(f"读取文件 {json_name} 出错: {e}")

    _print_summary(instance_counts, image_counts, "labelme_json")


def count_yolo_labels(label_dir, label_type="txt"):
    """
    统计标签类别数量与文件分布。

    Args:
        label_dir: 标签文件夹
        label_type: txt | json
    """
    if not os.path.isdir(label_dir):
        print(f"目录不存在: {label_dir}")
        return

    lt = str(label_type).strip().lower()
    if lt == "json":
        _count_from_labelme_json(label_dir)
    else:
        _count_from_txt(label_dir)


if __name__ == "__main__":
    LABEL_FOLDER = r"H:\3.24 非机动车——董嘉琪\labels"
    count_yolo_labels(LABEL_FOLDER, label_type="txt")