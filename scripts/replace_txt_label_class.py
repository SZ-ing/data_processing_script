import os
import json
from tqdm import tqdm


def replace_label_class(
    input_dir,
    output_dir,
    old_class,
    new_class,
    label_type="txt",
    all_to_zero=False,
):
    """
    批量替换标签类别，支持 TXT / JSON 两种格式。

    Args:
        input_dir: 输入标签文件夹
        output_dir: 修改后标签的输出文件夹
        old_class: 要替换的原类别
        new_class: 替换后的新类别
        label_type: 标签类型，txt 或 json
        all_to_zero: True 时忽略 old/new，所有类别统一改为 0
    """
    if not os.path.isdir(input_dir):
        print(f"路径不存在: {input_dir}")
        return

    os.makedirs(output_dir, exist_ok=True)

    label_type = (label_type or "txt").strip().lower()
    if label_type not in ("txt", "json"):
        raise ValueError(f"不支持的标签类型: {label_type}")

    ext = ".txt" if label_type == "txt" else ".json"
    label_files = sorted([f for f in os.listdir(input_dir) if f.lower().endswith(ext)])
    if not label_files:
        print(f"未找到 {label_type.upper()} 文件: {input_dir}")
        return

    changed_files = 0
    changed_lines = 0
    bad_files = 0

    for file_name in tqdm(label_files, desc="替换标签类别", unit="file"):
        src_path = os.path.join(input_dir, file_name)
        output_path = os.path.join(output_dir, file_name)

        file_changed = False

        if label_type == "txt":
            with open(src_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            updated_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    updated_lines.append(line)
                    continue

                parts = stripped.split()
                if not parts:
                    updated_lines.append(line)
                    continue

                if all_to_zero:
                    if parts[0] != "0":
                        parts[0] = "0"
                        changed_lines += 1
                        file_changed = True
                    updated_lines.append(" ".join(parts) + "\n")
                else:
                    if parts[0] == str(old_class):
                        parts[0] = str(new_class)
                        updated_lines.append(" ".join(parts) + "\n")
                        changed_lines += 1
                        file_changed = True
                    else:
                        updated_lines.append(line)

            with open(output_path, "w", encoding="utf-8") as f:
                f.writelines(updated_lines)
        else:
            try:
                with open(src_path, "r", encoding="utf-8", errors="replace") as f:
                    data = json.load(f)

                shapes = data.get("shapes", [])
                for shape in shapes:
                    label = str(shape.get("label", ""))
                    if all_to_zero:
                        if label != "0":
                            shape["label"] = "0"
                            changed_lines += 1
                            file_changed = True
                    else:
                        if label == str(old_class):
                            shape["label"] = str(new_class)
                            changed_lines += 1
                            file_changed = True

                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                bad_files += 1
                tqdm.write(f"跳过异常 JSON: {file_name} | {e}")
                continue

        if file_changed:
            changed_files += 1

    print("-" * 30)
    print(f"处理完成")
    print(f"标签类型: {label_type}")
    print(f"统一替换为0: {'是' if all_to_zero else '否'}")
    print(f"扫描文件数: {len(label_files)}")
    print(f"修改文件数: {changed_files}")
    print(f"替换行数: {changed_lines}")
    if bad_files:
        print(f"跳过异常文件数: {bad_files}")
    print(f"输出目录: {output_dir}")


if __name__ == "__main__":
    input_dir = r"D:\dataset\labels"
    output_dir = r"D:\dataset\labels_replaced"
    old_class = "trunck"
    new_class = "0"

    replace_label_class(
        input_dir,
        output_dir,
        old_class,
        new_class,
        label_type="txt",
        all_to_zero=False,
    )
