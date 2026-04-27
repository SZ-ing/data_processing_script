import cv2
import os
import shutil
from tqdm import tqdm

def _collect_image_paths(folder_path, valid_extensions, recursive_subfolders=False):
    folder_path = os.path.abspath(folder_path)
    if not recursive_subfolders:
        return sorted(
            os.path.join(folder_path, f)
            for f in os.listdir(folder_path)
            if os.path.isfile(os.path.join(folder_path, f))
            and f.lower().endswith(valid_extensions)
        )

    image_paths = []
    for root, _, files in os.walk(folder_path):
        for f in files:
            if not f.lower().endswith(valid_extensions):
                continue
            image_paths.append(os.path.join(root, f))
    return sorted(image_paths)


def _safe_move_with_unique_name(src_path, dst_dir, prefix=""):
    """移动文件到 dst_dir，重名自动加计数后缀。"""
    base_name = os.path.basename(src_path)
    name, ext = os.path.splitext(base_name)
    candidate = f"{prefix}{base_name}" if prefix else base_name
    dst_path = os.path.join(dst_dir, candidate)
    counter = 1
    while os.path.exists(dst_path):
        candidate = f"{prefix}{name}_{counter}{ext}" if prefix else f"{name}_{counter}{ext}"
        dst_path = os.path.join(dst_dir, candidate)
        counter += 1
    shutil.move(src_path, dst_path)


def _blur_score_laplacian(gray):
    """Laplacian 方差，值越小通常越模糊。"""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _blur_score_tenengrad(gray):
    """Tenengrad 梯度能量，值越小通常越模糊。"""
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    energy = gx * gx + gy * gy
    return float(energy.mean())


def _blur_score_uav_fusion(gray):
    """
    无人机场景融合清晰度分数：
    - 核心：Laplacian + Tenengrad
    - 增益：亮度正常区间时适度抬分；过暗/过亮时轻微降权
    """
    lap = _blur_score_laplacian(gray)
    ten = _blur_score_tenengrad(gray)
    brightness = float(gray.mean())

    # 将 ten 压缩到与 lap 同量级，便于统一阈值经验。
    ten_scaled = ten / 100.0

    # 对极暗/极亮图轻微降权，减少曝光异常导致的误判。
    if brightness < 35 or brightness > 220:
        light_factor = 0.8
    elif brightness < 55 or brightness > 200:
        light_factor = 0.9
    else:
        light_factor = 1.0

    score = (0.6 * ten_scaled + 0.4 * lap) * light_factor
    return float(score)


def _calc_blur_score(gray, method):
    m = (method or "uav_fusion").strip().lower()
    if m == "laplacian":
        return _blur_score_laplacian(gray)
    if m == "tenengrad":
        return _blur_score_tenengrad(gray)
    if m == "uav_fusion":
        return _blur_score_uav_fusion(gray)
    raise ValueError(f"未知 method: {method}")


def remove_blurry_images(
    folder_path,
    threshold=100.0,
    backup_dir_name="removed_blur",
    recursive_subfolders=False,
    method="uav_fusion",
    _stop_event=None,
):
    """
    独立脚本：筛出模糊图片并移动到待手动删除文件夹
    :param folder_path: 图片目录
    :param threshold: 阈值 (低于此值视为模糊)。
                      - 60: 只有非常模糊的会被移走
                      - 100: 推荐默认值
                      - 150+: 对清晰度要求极高
    :param backup_dir_name: 在目标目录下创建的待手动删除文件夹名
    :param recursive_subfolders: 是否递归子文件夹查找图片
    :param method: 模糊检测策略
                   - laplacian: Laplacian 方差
                   - tenengrad: Sobel 梯度能量
                   - uav_fusion: 无人机场景融合策略（推荐）
    """
    if not os.path.exists(folder_path):
        print(f"路径不存在: {folder_path}")
        return

    # 在 target_dir 下创建待手动删除文件夹，不直接删除原图
    trash_dir = os.path.join(folder_path, backup_dir_name)
    if not os.path.exists(trash_dir):
        os.makedirs(trash_dir)

    valid_extensions = ('.jpg', '.jpeg', '.png', '.bmp')
    files = _collect_image_paths(
        folder_path, valid_extensions, recursive_subfolders=recursive_subfolders
    )
    
    print(f"--- 开始模糊检测 ---")
    print(f"目标文件夹: {folder_path}")
    print(f"递归子文件夹: {'是' if recursive_subfolders else '否'}")
    print(f"检测方法: {method}")
    print(f"模糊阈值: {threshold}")
    print(f"待手动删除文件夹: {trash_dir}")
    
    moved_count = 0

    total_files = len(files)
    if total_files == 0:
        print("未找到可处理的图片文件。")
        return

    for idx, file_path in enumerate(tqdm(files, desc="检测模糊度", unit="img"), start=1):
        if _stop_event is not None and _stop_event.is_set():
            print("\n检测已被用户终止。")
            return

        # 每处理一段输出一次普通日志，避免仅依赖 tqdm 刷新导致“看起来卡住”。
        if idx == 1 or idx % 50 == 0 or idx == total_files:
            print(f"检测进度: {idx}/{total_files}")

        if os.path.commonpath([os.path.abspath(file_path), os.path.abspath(trash_dir)]) == os.path.abspath(trash_dir):
            continue
        file_name = os.path.basename(file_path)
        
        # 读取图片
        img = cv2.imread(file_path)
        if img is None:
            continue

        # 转灰度并计算清晰度分数（分数越低通常越模糊）
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        try:
            score = _calc_blur_score(gray, method)
        except ValueError as e:
            print(str(e))
            return

        # 判断并移动到 target_dir 下的待手动删除文件夹
        if score < threshold:
            # 在文件名前加分数值，方便手动复核
            prefix = f""
            _safe_move_with_unique_name(file_path, trash_dir, prefix=prefix)
            moved_count += 1

    print(f"\n处理完成！")
    print(f"共移动了 {moved_count} 张模糊图片。")
    print(f"请手动检查并删除: {trash_dir}")

if __name__ == "__main__":
    # 修改这里的路径
    target_dir = r"D:\docker_volume\yolo_train\runs\extract_frames"
    
    # - 60: 只有非常模糊的会被移走
    # - 100: 推荐默认值
    # - 150+: 对清晰度要求极高
                      
    # 修改阈值
    blur_limit = 60

    # 在 target_dir 下创建这个文件夹，存放筛出的模糊图片
    backup_dir_name = "removed_blur"
    method = "uav_fusion"
    
    remove_blurry_images(
        target_dir,
        blur_limit,
        backup_dir_name,
        recursive_subfolders=False,
        method=method,
    )
