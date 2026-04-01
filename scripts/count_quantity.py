import os
from collections import defaultdict
from tqdm import tqdm

def count_yolo_labels(label_dir):
    """
    统计 YOLO 标签文件夹中的类别数量和图片分布
    支持检测格式 (5列) 和 分割格式 (多列)
    """
    # instance_counts: 统计各个类别的框（实例）总数 {class_id: total_count}
    instance_counts = defaultdict(int)
    # image_counts: 统计包含该类别的图片数量 {class_id: image_count}
    image_counts = defaultdict(int)
    
    # 获取目录下所有 txt 文件
    txt_files = [f for f in os.listdir(label_dir) if f.lower().endswith('.txt') and f != 'classes.txt']
    
    if not txt_files:
        print(f"在目录 {label_dir} 中未找到 TXT 标签文件。")
        return

    print(f"正在分析 {len(txt_files)} 个标签文件...\n")

    for txt_name in tqdm(txt_files, desc="统计标签数量", unit="file"):
        txt_path = os.path.join(label_dir, txt_name)
        
        # 使用 set 记录当前这张图中出现了哪些类别（去重）
        classes_in_this_image = set()
        
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            for line in lines:
                parts = line.strip().split()
                if not parts:
                    continue
                
                # 第一列永远是类别 ID
                try:
                    class_id = int(parts[0])
                    # 1. 累加框的总数
                    instance_counts[class_id] += 1
                    # 2. 记录到当前图片的类别集合中
                    classes_in_this_image.add(class_id)
                except ValueError:
                    # 如果第一列不是数字（如 classes.txt 的内容），跳过
                    continue
            
            # 遍历当前图片中出现过的类别，对应的图片计数 +1
            for cls in classes_in_this_image:
                image_counts[cls] += 1
                
        except Exception as e:
            tqdm.write(f"读取文件 {txt_name} 出错: {e}")

    # --- 打印统计结果 ---
    # 按照类别 ID 从小到大排序显示
    sorted_ids = sorted(instance_counts.keys())
    
    print(f"{'类别 ID':<10} | {'框(实例)总数':<15} | {'包含该类别的图片数':<15}")
    print("-" * 50)
    
    total_all_instances = 0
    for cid in sorted_ids:
        instances = instance_counts[cid]
        images = image_counts[cid]
        total_all_instances += instances
        print(f"{cid:<12} | {instances:<17} | {images:<15}")
    
    print("-" * 50)
    print(f"总计: {len(sorted_ids)} 个类别，共 {total_all_instances} 个标注框。")

# ================= 配置与执行 =================
if __name__ == "__main__":
    # 填写你的标签文件夹路径
    LABEL_FOLDER = r"H:\3.24 非机动车——董嘉琪\labels"
    
    count_yolo_labels(LABEL_FOLDER)