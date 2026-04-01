import os
import shutil
from tqdm import tqdm


def collect_file_map(folder_path):
    file_map = {}
    for file_name in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file_name)
        if not os.path.isfile(file_path):
            continue

        stem = os.path.splitext(file_name)[0]
        file_map.setdefault(stem, []).append(file_name)
    return file_map


def move_files(file_names, source_dir, target_dir, desc="移动文件"):
    moved_count = 0
    for file_name in tqdm(file_names, desc=desc, unit="file"):
        src_path = os.path.join(source_dir, file_name)
        dst_path = os.path.join(target_dir, file_name)

        if os.path.exists(dst_path):
            name, ext = os.path.splitext(file_name)
            counter = 1
            while os.path.exists(dst_path):
                dst_path = os.path.join(target_dir, f"{name}_{counter}{ext}")
                counter += 1

        shutil.move(src_path, dst_path)
        moved_count += 1

    return moved_count


def sync_folders_by_stem(folder_a, folder_b, backup_dir_name="unmatched_files"):
    """
    按文件名主名同步两个文件夹。
    只保留两个文件夹中都存在的主名文件，将缺失匹配项移动到各自目录下的回收文件夹。

    Args:
        folder_a: 文件夹 A
        folder_b: 文件夹 B
        backup_dir_name: 各目录下存放未匹配文件的文件夹名
    """
    if not os.path.exists(folder_a):
        print(f"路径不存在: {folder_a}")
        return

    if not os.path.exists(folder_b):
        print(f"路径不存在: {folder_b}")
        return

    backup_a = os.path.join(folder_a, backup_dir_name)
    backup_b = os.path.join(folder_b, backup_dir_name)
    os.makedirs(backup_a, exist_ok=True)
    os.makedirs(backup_b, exist_ok=True)

    files_a = collect_file_map(folder_a)
    files_b = collect_file_map(folder_b)

    stems_a = set(files_a.keys())
    stems_b = set(files_b.keys())
    common_stems = stems_a & stems_b
    only_a = stems_a - stems_b
    only_b = stems_b - stems_a

    print(f"A 文件夹: {folder_a}")
    print(f"B 文件夹: {folder_b}")
    print(f"A 回收文件夹: {backup_a}")
    print(f"B 回收文件夹: {backup_b}")
    print(f"A 文件主名数: {len(stems_a)}")
    print(f"B 文件主名数: {len(stems_b)}")
    print(f"共同保留主名数: {len(common_stems)}")

    move_list_a = []
    for stem in sorted(only_a):
        move_list_a.extend(files_a[stem])

    move_list_b = []
    for stem in sorted(only_b):
        move_list_b.extend(files_b[stem])

    moved_a = move_files(move_list_a, folder_a, backup_a, desc="移动 A 未匹配文件") if move_list_a else 0
    moved_b = move_files(move_list_b, folder_b, backup_b, desc="移动 B 未匹配文件") if move_list_b else 0

    print("-" * 30)
    print(f"已从 A 移动未匹配文件数: {moved_a}")
    print(f"已从 B 移动未匹配文件数: {moved_b}")
    print("处理完成，请手动检查各自回收文件夹。")


if __name__ == "__main__":
    FOLDER_A = r"D:\dataset\6.道路分割\道路分割3.26\use_images"
    FOLDER_B = r"D:\dataset\6.道路分割\道路分割3.26\labels"
    BACKUP_DIR_NAME = "unmatched_files"

    sync_folders_by_stem(FOLDER_A, FOLDER_B, BACKUP_DIR_NAME)
