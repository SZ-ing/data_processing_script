import cv2
import os
import shutil
from tqdm import tqdm

def remove_blurry_images(folder_path, threshold=100.0, backup_dir_name="removed_blur"):
    """
    独立脚本：筛出模糊图片并移动到待手动删除文件夹
    :param folder_path: 图片目录
    :param threshold: 阈值 (低于此值视为模糊)。
                      - 60: 只有非常模糊的会被移走
                      - 100: 推荐默认值
                      - 150+: 对清晰度要求极高
    :param backup_dir_name: 在目标目录下创建的待手动删除文件夹名
    """
    if not os.path.exists(folder_path):
        print(f"路径不存在: {folder_path}")
        return

    # 在 target_dir 下创建待手动删除文件夹，不直接删除原图
    trash_dir = os.path.join(folder_path, backup_dir_name)
    if not os.path.exists(trash_dir):
        os.makedirs(trash_dir)

    valid_extensions = ('.jpg', '.jpeg', '.png', '.bmp')
    files = sorted([f for f in os.listdir(folder_path) if f.lower().endswith(valid_extensions)])
    
    print(f"--- 开始模糊检测 ---")
    print(f"目标文件夹: {folder_path}")
    print(f"模糊阈值: {threshold}")
    print(f"待手动删除文件夹: {trash_dir}")
    
    moved_count = 0

    for file_name in tqdm(files, desc="检测模糊度", unit="img"):
        file_path = os.path.join(folder_path, file_name)
        
        # 读取图片
        img = cv2.imread(file_path)
        if img is None:
            continue

        # 转灰度并计算方差
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        score = cv2.Laplacian(gray, cv2.CV_64F).var()

        # 判断并移动到 target_dir 下的待手动删除文件夹
        if score < threshold:
            # 在文件名前加分数值，方便手动复核
            new_name = f"score_{int(score)}_{file_name}"
            shutil.move(file_path, os.path.join(trash_dir, new_name))
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
    
    remove_blurry_images(target_dir, blur_limit, backup_dir_name)
