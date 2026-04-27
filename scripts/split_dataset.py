import os
import random
import shutil

from tqdm import tqdm

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


def _detect_and_validate_classes(labels_dir, label_files):
    """扫描全部标签文件，提取类别 ID 并校验是否为从 0 开始的连续整数。

    Returns:
        (class_ids, error_msg)  —— 校验通过时 error_msg 为 None
    """
    class_ids = set()
    bad_files = []
    read_errors = []

    for lf in label_files:
        path = os.path.join(labels_dir, lf)
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, 1):
                    parts = line.strip().split()
                    if not parts:
                        continue
                    try:
                        cid = int(parts[0])
                    except ValueError:
                        bad_files.append((lf, line_no, parts[0]))
                        continue
                    if cid < 0:
                        bad_files.append((lf, line_no, str(cid)))
                        continue
                    class_ids.add(cid)
        except OSError as e:
            read_errors.append((lf, str(e)))
            continue

    if bad_files:
        detail = "\n".join(
            f"  {f} 第{ln}行: 类别值 '{v}'" for f, ln, v in bad_files[:10]
        )
        extra = f"\n  …（共 {len(bad_files)} 处）" if len(bad_files) > 10 else ""
        return None, f"标签数据异常: 存在非法类别 ID（必须为非负整数）\n{detail}{extra}"

    if read_errors:
        detail = "\n".join(f"  {f}: {msg}" for f, msg in read_errors[:10])
        extra = f"\n  …（共 {len(read_errors)} 个文件读取失败）" if len(read_errors) > 10 else ""
        return None, f"标签读取异常: 存在无法读取的标签文件\n{detail}{extra}"

    if not class_ids:
        return [0], None

    sorted_ids = sorted(class_ids)
    expected = list(range(sorted_ids[-1] + 1))
    if sorted_ids != expected:
        missing = set(expected) - class_ids
        return None, (
            f"标签数据异常: 类别 ID 不连续\n"
            f"  检测到的类别: {sorted_ids}\n"
            f"  缺失的类别:   {sorted(missing)}\n"
            f"  YOLO (ultralytics) 要求类别 ID 必须为从 0 开始的连续整数 (0, 1, 2, …)"
        )

    return sorted_ids, None


def _write_yaml(output_dir, class_ids):
    """生成 YOLO 训练用的 dataset.yaml。"""
    yaml_path = os.path.join(output_dir, "dataset.yaml")
    names_block = "\n".join(f"  {cid}: class_{cid}" for cid in class_ids)

    lines = [
        f"path: {output_dir}",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        f"nc: {len(class_ids)}",
        f"names:\n{names_block}",
    ]

    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"YAML 配置已生成: {yaml_path}")


def split_dataset(images_dir, labels_dir, output_dir,
                  train_ratio=0.8, val_ratio=0.2, test_ratio=0.0):
    """
    将图片 + 标签数据集按比例拆分为 train / val / test。

    Args:
        images_dir:  原始图片文件夹
        labels_dir:  原始标签文件夹（YOLO TXT）
        output_dir:  输出根目录，自动建 images/{train,val,test} 和 labels/{train,val,test}
        train_ratio: 训练集比例
        val_ratio:   验证集比例
        test_ratio:  测试集比例（三者之和必须为 1）
    """
    # ── 参数校验 ──
    ratio_sum = train_ratio + val_ratio + test_ratio
    if abs(ratio_sum - 1.0) > 1e-4:
        print(f"错误: 三个比例之和为 {ratio_sum:.4f}，必须等于 1.0")
        return

    images_dir = os.path.abspath(images_dir)
    labels_dir = os.path.abspath(labels_dir)
    output_dir = os.path.abspath(output_dir)

    if not os.path.isdir(images_dir):
        print(f"错误: 图片文件夹不存在 → {images_dir}")
        return
    if not os.path.isdir(labels_dir):
        print(f"错误: 标签文件夹不存在 → {labels_dir}")
        return

    # ── 收集图片-标签配对 ──
    paired_images = []
    label_files_used = []
    for fname in sorted(os.listdir(images_dir)):
        if os.path.splitext(fname)[1].lower() not in IMAGE_EXTS:
            continue
        stem = os.path.splitext(fname)[0]
        label_name = stem + ".txt"
        if os.path.isfile(os.path.join(labels_dir, label_name)):
            paired_images.append(fname)
            label_files_used.append(label_name)

    if not paired_images:
        print("错误: 没有找到任何图片-标签配对（图片文件夹与标签文件夹中无同名文件）。")
        return

    print(f"图片文件夹: {images_dir}")
    print(f"标签文件夹: {labels_dir}")
    print(f"输出文件夹: {output_dir}")
    print(f"找到 {len(paired_images)} 个有效的图片-标签对\n")

    # ── 校验类别 ID ──
    print("正在校验标签类别…")
    class_ids, err = _detect_and_validate_classes(labels_dir, label_files_used)
    if err:
        print(f"\n错误: {err}")
        return
    print(f"检测到 {len(class_ids)} 个类别: {class_ids}  ✔\n")

    # ── 随机打乱 & 拆分 ──
    random.shuffle(paired_images)
    total = len(paired_images)
    train_end = int(total * train_ratio)
    val_end = train_end + int(total * val_ratio)

    splits = {"train": paired_images[:train_end],
              "val": paired_images[train_end:val_end],
              "test": paired_images[val_end:]}

    for name, files in splits.items():
        print(f"  {name}: {len(files)} 个")

    # ── 创建目录（始终创建 train / val / test） ──
    for split_name in splits:
        os.makedirs(os.path.join(output_dir, "images", split_name), exist_ok=True)
        os.makedirs(os.path.join(output_dir, "labels", split_name), exist_ok=True)

    # ── 复制文件 ──
    print()
    for split_name, file_list in splits.items():
        img_dst = os.path.join(output_dir, "images", split_name)
        lbl_dst = os.path.join(output_dir, "labels", split_name)
        for fname in tqdm(file_list, desc=f"复制 {split_name}", unit="pair"):
            shutil.copy2(os.path.join(images_dir, fname),
                         os.path.join(img_dst, fname))
            lbl_name = os.path.splitext(fname)[0] + ".txt"
            shutil.copy2(os.path.join(labels_dir, lbl_name),
                         os.path.join(lbl_dst, lbl_name))

    # ── 生成 YAML ──
    _write_yaml(output_dir, class_ids)

    # ── 统计信息 ──
    print(f"\n{'='*40}")
    print(f"数据集拆分完成!")
    print(f"  总计: {total}")
    for name, files in splits.items():
        pct = len(files) / total * 100
        print(f"  {name}: {len(files)}  ({pct:.1f}%)")
    print(f"输出目录: {output_dir}")


if __name__ == "__main__":
    random.seed(42)
    split_dataset(
        images_dir=r"D:\dataset\15.横幅\train_dataset\横幅20260328\images",
        labels_dir=r"D:\dataset\15.横幅\train_dataset\横幅20260328\labels",
        output_dir=r"D:\dataset\15.横幅\train_datasets",
        train_ratio=0.8,
        val_ratio=0.2,
        test_ratio=0.0,
    )
