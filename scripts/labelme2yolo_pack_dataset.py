"""兼容入口：逻辑已合并到 scripts.labelme2yolo。"""

from scripts.labelme2yolo import labelme2yolo_pack_dataset


if __name__ == "__main__":
    INPUT_DIR = r"D:\dataset\mixed_input"
    OUTPUT_DIR = r"D:\dataset\packed_output"
    labelme2yolo_pack_dataset(INPUT_DIR, OUTPUT_DIR, mode="auto", remap_to_zero=False)
