"""
按指定尺寸与重叠度裁剪图片（支持递归子目录）。
"""

import os
from collections import defaultdict

import cv2
import numpy as np
from PIL import Image
from tqdm import tqdm


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp")


def _imread_unicode(path: str):
    """
    Windows 中文路径安全读取。
    优先: np.fromfile + cv2.imdecode
    回退: PIL 读取后转 BGR
    """
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if data.size > 0:
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if img is not None:
                return img
    except Exception:
        pass

    try:
        with Image.open(path) as pil_img:
            rgb = pil_img.convert("RGB")
            arr = np.asarray(rgb, dtype=np.uint8)
            return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def _imwrite_unicode(path: str, image) -> bool:
    """
    Windows 中文路径安全保存。
    优先: cv2.imencode + tofile
    回退: PIL 保存
    """
    ext = os.path.splitext(path)[1].lower() or ".jpg"
    try:
        ok, buf = cv2.imencode(ext, image)
        if ok:
            buf.tofile(path)
            return True
    except Exception:
        pass

    try:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        Image.fromarray(rgb).save(path)
        return True
    except Exception:
        return False


def _collect_images(folder_path: str, recursive_subfolders: bool = False):
    folder_path = os.path.abspath(folder_path)
    if not recursive_subfolders:
        return sorted(
            os.path.join(folder_path, f)
            for f in os.listdir(folder_path)
            if os.path.isfile(os.path.join(folder_path, f))
            and f.lower().endswith(IMAGE_EXTS)
        )

    paths = []
    for root, _, files in os.walk(folder_path):
        for f in files:
            if f.lower().endswith(IMAGE_EXTS):
                paths.append(os.path.join(root, f))
    return sorted(paths)


def _sliding_positions(total_len: int, crop_len: int, overlap_ratio: float):
    """
    计算滑窗起始位置，保证覆盖末端。
    当 total_len <= crop_len 时返回 [0]。
    """
    if total_len <= crop_len:
        return [0]

    stride = int(crop_len * (1.0 - overlap_ratio))
    stride = max(1, stride)

    positions = []
    cur = 0
    while cur + crop_len < total_len:
        positions.append(cur)
        cur += stride

    last = total_len - crop_len
    if not positions or positions[-1] != last:
        positions.append(last)
    return positions


def crop_images_by_size(
    folder_path: str,
    recursive_subfolders: bool,
    output_dir: str,
    crop_h: int,
    crop_w: int,
    overlap_h_ratio: float,
    overlap_w_ratio: float,
):
    """
    Args:
        folder_path: 图片文件夹路径
        recursive_subfolders: 是否递归子文件夹
        output_dir: 输出文件夹路径
        crop_h: 裁剪高度
        crop_w: 裁剪宽度
        overlap_h_ratio: 高度重叠度(0~0.99建议)
        overlap_w_ratio: 宽度重叠度(0~0.99建议)
    """
    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"输入文件夹不存在: {folder_path}")
    if crop_h <= 0 or crop_w <= 0:
        raise ValueError("裁剪高度和宽度必须大于 0")
    if not (0 <= overlap_h_ratio < 1) or not (0 <= overlap_w_ratio < 1):
        raise ValueError("重叠度需满足 0 <= overlap < 1")

    os.makedirs(output_dir, exist_ok=True)

    image_paths = _collect_images(folder_path, recursive_subfolders)
    if not image_paths:
        print("未找到图片。")
        return

    print(f"输入目录: {os.path.abspath(folder_path)}")
    print(f"输出目录: {os.path.abspath(output_dir)}")
    print(f"递归子目录: {'是' if recursive_subfolders else '否'}")
    print(f"裁剪尺寸: {crop_h}x{crop_w}")
    print(f"重叠度(H/W): {overlap_h_ratio}/{overlap_w_ratio}")
    print(f"待处理图片数: {len(image_paths)}")

    # 同名 stem 出现计数（跨目录）
    stem_occurrence = defaultdict(int)
    total_saved = 0

    for img_path in tqdm(image_paths, desc="裁剪图片", unit="img"):
        stem = os.path.splitext(os.path.basename(img_path))[0]
        ext = os.path.splitext(os.path.basename(img_path))[1].lower() or ".jpg"

        stem_occurrence[stem] += 1
        occ = stem_occurrence[stem]
        # 第一次出现: 1_1.jpg、1_2.jpg...
        # 第二次出现: 1_2_1.jpg、1_2_2.jpg...
        prefix = stem if occ == 1 else f"{stem}_{occ}"

        img = _imread_unicode(img_path)
        if img is None:
            tqdm.write(f"无法读取图片，跳过: {img_path}")
            continue

        h, w = img.shape[:2]

        # 要求4：若裁剪高宽都大于原图尺寸，不裁剪，直接保存为 *_1
        if crop_h > h and crop_w > w:
            out_name = f"{prefix}_1{ext}"
            out_path = os.path.join(output_dir, out_name)
            if _imwrite_unicode(out_path, img):
                total_saved += 1
            else:
                tqdm.write(f"保存失败，跳过: {out_path}")
            continue

        ys = _sliding_positions(h, crop_h, overlap_h_ratio)
        xs = _sliding_positions(w, crop_w, overlap_w_ratio)

        tile_idx = 0
        for y in ys:
            for x in xs:
                y2 = min(y + crop_h, h)
                x2 = min(x + crop_w, w)
                y1 = max(0, y2 - crop_h)
                x1 = max(0, x2 - crop_w)
                crop_img = img[y1:y2, x1:x2]

                tile_idx += 1
                out_name = f"{prefix}_{tile_idx}{ext}"
                out_path = os.path.join(output_dir, out_name)
                if _imwrite_unicode(out_path, crop_img):
                    total_saved += 1
                else:
                    tqdm.write(f"保存失败，跳过: {out_path}")

    print("-" * 40)
    print(f"处理完成，共生成 {total_saved} 张裁剪图。")
    print(f"保存目录: {os.path.abspath(output_dir)}")


if __name__ == "__main__":
    crop_images_by_size(
        folder_path=r"D:\data\images", # 图片文件夹
        recursive_subfolders=False, # 是否递归子文件查找
        output_dir=r"D:\data\images_cropped", # 裁剪结果路径
        crop_h=1440, # 裁剪高度
        crop_w=1440, # 裁剪宽度
        overlap_h_ratio=0, # 裁剪高度重叠度(0~0.99建议)
        overlap_w_ratio=0, # 裁剪宽度重叠度(0~0.99建议)
    )

