import os

from tqdm import tqdm

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


def generate_empty_labels(image_dir, txt_dir=""):
    """
    为图片生成空白 YOLO 标签（空 .txt 文件），已有标签的图片自动跳过。

    Args:
        image_dir: 图片文件夹路径。
        txt_dir:   TXT 标签文件夹路径。
                   - 留空：在 image_dir 同目录生成 .txt。
                   - 非空：在指定目录生成 .txt，已存在的不覆盖。
    """
    image_dir = os.path.abspath(image_dir)
    if not os.path.isdir(image_dir):
        print(f"错误: 图片文件夹不存在 → {image_dir}")
        return

    image_files = [
        f for f in sorted(os.listdir(image_dir))
        if os.path.isfile(os.path.join(image_dir, f))
        and os.path.splitext(f)[1].lower() in IMAGE_EXTS
    ]

    if not image_files:
        print("图片文件夹中没有找到任何图片。")
        return

    output_dir = (txt_dir or "").strip()
    if output_dir:
        output_dir = os.path.abspath(output_dir)
        os.makedirs(output_dir, exist_ok=True)
    else:
        output_dir = image_dir

    print(f"图片文件夹: {image_dir}")
    print(f"标签输出到: {output_dir}")
    print(f"检测到 {len(image_files)} 张图片\n")

    created = 0
    skipped = 0

    for img_file in tqdm(image_files, desc="生成空白标签", unit="img"):
        stem = os.path.splitext(img_file)[0]
        txt_path = os.path.join(output_dir, stem + ".txt")

        if os.path.exists(txt_path):
            skipped += 1
            continue

        with open(txt_path, "w"):
            pass
        created += 1

    print(f"\n处理完成: 新建 {created} 个, 已存在跳过 {skipped} 个")


if __name__ == "__main__":
    generate_empty_labels(
        image_dir=r"C:\Users\RS\Desktop\游泳\images",
        txt_dir="",
    )
