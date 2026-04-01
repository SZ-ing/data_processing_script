import os
import shutil
import imagehash
from PIL import Image
from tqdm import tqdm # 导入tqdm

def find_and_remove_duplicates(folder_path, threshold=5, backup_dir_name="removed_duplicates"):
    """
    使用tqdm进度条检测重复图片，并移动到目标目录下的待手动删除文件夹。
    
    :param folder_path: 图片文件夹路径
    :param threshold: 汉明距离阈值。
                      0 表示完全一样；
                      1-5 表示极其相似（连拍、轻微抖动）；
                      10以上可能会误删不同但构图相似的图。
                      针对无人机连拍，建议设置在 3-6 之间。
    :param backup_dir_name: 在目标目录下创建的待手动删除文件夹名
    """
    print(f"正在扫描文件夹: {folder_path} ...")

    if not os.path.exists(folder_path):
        print(f"路径不存在: {folder_path}")
        return

    trash_dir = os.path.join(folder_path, backup_dir_name)
    if not os.path.exists(trash_dir):
        os.makedirs(trash_dir)

    print(f"待手动删除文件夹: {trash_dir}")
    
    # 支持的图片格式
    valid_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.dng')
    
    # 获取所有图片文件
    image_files = [f for f in os.listdir(folder_path) 
                   if f.lower().endswith(valid_extensions)]
    image_files.sort() # 排序，保证优先保留文件名靠前的
    
    if not image_files:
        print("未找到图片。")
        return

    # 第一步：计算所有图片的哈希值
    hashes = {}
    
    # 使用tqdm包装循环，显示进度条
    for f in tqdm(image_files, desc="1/3 计算图片指纹 (Hashing)"):
        path = os.path.join(folder_path, f)
        try:
            with Image.open(path) as img:
                h = imagehash.dhash(img, hash_size=8)
                hashes[f] = h
        except Exception as e:
            print(f"无法读取图片 {f}: {e}")

    # 第二步：比较并标记删除
    print(f"开始比对 {len(hashes)} 张图片，相似度阈值: {threshold}")
    
    files_list = list(hashes.keys())
    files_to_remove = set()
    
    # 使用tqdm包装外层循环，显示比对进度
    for i in tqdm(range(len(files_list)), desc="2/3 比对图片相似度"):
        file_a = files_list[i]
        
        if file_a in files_to_remove:
            continue
            
        for j in range(i + 1, len(files_list)):
            file_b = files_list[j]
            
            if file_b in files_to_remove:
                continue
            
            distance = hashes[file_a] - hashes[file_b]
            
            if distance <= threshold:
                # 不再打印每一条重复记录，直接添加到集合
                files_to_remove.add(file_b)

    # 第三步：执行移动并报告总数
    num_to_remove = len(files_to_remove)
    print(f"\n扫描结束。发现 {num_to_remove} 张可移动的重复图片。")

    if num_to_remove > 0:
        for f in tqdm(files_to_remove, desc="3/3 移动重复图片"):
            try:
                src_path = os.path.join(folder_path, f)
                dst_path = os.path.join(trash_dir, f)

                if os.path.exists(dst_path):
                    name, ext = os.path.splitext(f)
                    counter = 1
                    while os.path.exists(dst_path):
                        dst_path = os.path.join(trash_dir, f"{name}_{counter}{ext}")
                        counter += 1

                shutil.move(src_path, dst_path)
            except Exception as e:
                print(f"移动失败 {f}: {e}")
        print(f"清理完成。总共移动了 {num_to_remove} 张重复图片。")
        print(f"请手动检查并删除: {trash_dir}")
    else:
        print("无需清理，未发现重复图片。")

if __name__ == "__main__":
    # --- 配置区 ---
    
    # 替换为你的无人机图片文件夹路径
    TARGET_FOLDER = r"D:\docker_volume\yolo_train\runs\extract_frames" 
    
    # 相似度阈值
    # - 悬停连拍（几乎完全一样）：设为 2 或 3
    # - 航线重叠度高（有轻微位移）：设为 5 或 6
    # 0 表示完全一样；
    # 1-5 表示极其相似（连拍、轻微抖动）；
    # 10以上可能会误删不同但构图相似的图。
    # 针对无人机连拍，建议设置在 3-6 之间。
    SIMILARITY_THRESHOLD = 8
    
    # 在 target_dir 下创建这个文件夹，存放筛出的重复图片
    BACKUP_DIR_NAME = "removed_duplicates"
    
    # --- 执行 ---
    find_and_remove_duplicates(
        TARGET_FOLDER, 
        threshold=SIMILARITY_THRESHOLD, 
        backup_dir_name=BACKUP_DIR_NAME
    )
