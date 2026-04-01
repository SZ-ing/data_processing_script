import os
from tqdm import tqdm


def replace_label_class(txt_dir, output_dir, old_class, new_class):
    """
    批量替换 TXT 标签中每一行的第一个字段。
    适用于 YOLO 标签格式，也适用于“类别在每行开头”的普通 TXT。

    Args:
        txt_dir: TXT 文件夹路径
        output_dir: 修改后 TXT 的输出文件夹
        old_class: 要替换的原类别
        new_class: 替换后的新类别
    """
    if not os.path.isdir(txt_dir):
        print(f"路径不存在: {txt_dir}")
        return

    os.makedirs(output_dir, exist_ok=True)

    txt_files = sorted([f for f in os.listdir(txt_dir) if f.lower().endswith(".txt")])
    if not txt_files:
        print(f"未找到 TXT 文件: {txt_dir}")
        return

    changed_files = 0
    changed_lines = 0

    for txt_file in tqdm(txt_files, desc="替换标签类别", unit="file"):
        txt_path = os.path.join(txt_dir, txt_file)
        output_path = os.path.join(output_dir, txt_file)

        with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        updated_lines = []
        file_changed = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                updated_lines.append(line)
                continue

            parts = stripped.split()
            if parts and parts[0] == str(old_class):
                parts[0] = str(new_class)
                updated_lines.append(" ".join(parts) + "\n")
                changed_lines += 1
                file_changed = True
            else:
                updated_lines.append(line)

        with open(output_path, "w", encoding="utf-8") as f:
            f.writelines(updated_lines)

        if file_changed:
            changed_files += 1

    print("-" * 30)
    print(f"处理完成")
    print(f"扫描 TXT 文件数: {len(txt_files)}")
    print(f"修改文件数: {changed_files}")
    print(f"替换行数: {changed_lines}")
    print(f"输出目录: {output_dir}")


if __name__ == "__main__":
    txt_dir = r"D:\dataset\labels"
    output_dir = r"D:\dataset\labels_replaced"
    old_class = "trunck"
    new_class = "0"

    replace_label_class(txt_dir, output_dir, old_class, new_class)
