"""
脚本注册表 —— 定义每个脚本的显示名称、说明、参数列表及入口函数。
views/script_page.py 根据这里的元数据自动生成 UI 控件。

参数类型:
  folder   - 文件夹选择（带浏览按钮）
  file_or_folder - 文件或文件夹选择
  text     - 文本输入
  int      - 整数（QSpinBox）
  float    - 浮点数（QDoubleSpinBox）
  bool     - 复选框
  radio    - 互斥单选，choices 同 [{"value": "...", "label": "中文"}, ...]
"""

import shutil

# LabelMe→YOLO / YOLO 可视化 共用的模式选项（value 传给脚本，label 为界面显示）
MODE_RADIO_AUTO_DET_SEG = [
    {"value": "auto", "label": "自动判断"},
    {"value": "det", "label": "检测（矩形框 bbox）"},
    {"value": "seg", "label": "分割（多边形 polygon）"},
]

SCRIPT_REGISTRY = [
    # ── 格式转换 ─────────────────────────────────────
    {
        "id": "labelme2yolo",
        "group": "格式转换",
        "name": "LabelMe → YOLO",
        "description": "将 LabelMe JSON 转换为 YOLO TXT 格式。\n自动识别 rectangle→检测 / polygon→分割，也可手动指定。",
        "module": "scripts.labelme2yolo",
        "function": "labelme2yolo",
        "params": [
            {"key": "json_dir",    "label": "JSON 文件夹",  "type": "folder"},
            {"key": "output_dir",  "label": "输出文件夹",    "type": "folder"},
            {"key": "mode",        "label": "模式", "type": "radio",
             "default": "auto", "choices": MODE_RADIO_AUTO_DET_SEG},
        ],
    },
    {
        "id": "yolo2labelme",
        "group": "格式转换",
        "name": "YOLO → LabelMe",
        "description": "将 YOLO TXT 转换为 LabelMe JSON。\n自动识别: 5列→检测(rectangle) / ≥7列→分割(polygon)。",
        "module": "scripts.yolo2labelme",
        "function": "yolo2labelme",
        "params": [
            {"key": "txt_dir",            "label": "TXT 标签文件夹",  "type": "folder"},
            {"key": "images_dir",          "label": "图片文件夹",      "type": "folder"},
            {"key": "output_dir",          "label": "输出 JSON 文件夹","type": "folder"},
            {"key": "include_image_data",  "label": "写入 imageData",  "type": "bool", "default": True},
        ],
    },

    # ── 数据可视化 ────────────────────────────────────
    {
        "id": "yolo_show",
        "group": "数据可视化",
        "name": "YOLO 标签可视化",
        "description": "读取 YOLO TXT + 对应图片输出叠图。\n模式：单选 自动判断 / 检测框 / 分割叠图。",
        "module": "scripts.yolo_show",
        "function": "visualize_yolo",
        "params": [
            {"key": "img_folder",    "label": "图片文件夹",  "type": "folder"},
            {"key": "txt_folder",    "label": "TXT 标签文件夹","type": "folder"},
            {"key": "output_folder", "label": "输出文件夹",    "type": "folder"},
            {"key": "mode",          "label": "模式", "type": "radio",
             "default": "auto", "choices": MODE_RADIO_AUTO_DET_SEG},
        ],
    },

    # ── 数据清洗 ──────────────────────────────────────
    {
        "id": "remove_blurring",
        "group": "数据清洗",
        "name": "模糊图片筛除",
        "description": "使用 Laplacian 方差检测模糊图，将低于阈值的图移入子目录。",
        "module": "scripts.remove_blurring",
        "function": "remove_blurry_images",
        "params": [
            {"key": "folder_path",     "label": "图片文件夹",  "type": "folder"},
            {"key": "threshold",       "label": "模糊阈值（低于此值视为模糊，推荐 60-150）",
             "type": "float", "default": 100.0, "min": 0, "max": 9999},
            {"key": "backup_dir_name", "label": "回收子目录名",  "type": "text", "default": "removed_blur"},
        ],
    },
    {
        "id": "remove_duplication_hanming",
        "group": "数据清洗",
        "name": "重复图片去除（汉明距离）",
        "description": "使用 dHash + 汉明距离检测近似重复图，移入子目录。\n阈值 0=完全一样，3-6 适合连拍去重，>10 可能误删。",
        "module": "scripts.remove_duplication_hanming",
        "function": "find_and_remove_duplicates",
        "params": [
            {"key": "folder_path",     "label": "图片文件夹",  "type": "folder"},
            {"key": "threshold",       "label": "汉明距离阈值（推荐 3-8）",
             "type": "int", "default": 5, "min": 0, "max": 64},
            {"key": "backup_dir_name", "label": "回收子目录名",  "type": "text", "default": "removed_duplicates"},
        ],
    },
    {
        "id": "sync_by_stem",
        "group": "数据清洗",
        "name": "文件名对齐（主名同步）",
        "description": "按文件主名同步两个文件夹，将缺少匹配项的文件移入各自回收子目录。",
        "module": "scripts.sync_by_stem_move_unmatched",
        "function": "sync_folders_by_stem",
        "params": [
            {"key": "folder_a",        "label": "文件夹 A",    "type": "folder"},
            {"key": "folder_b",        "label": "文件夹 B",    "type": "folder"},
            {"key": "backup_dir_name", "label": "回收子目录名",  "type": "text", "default": "unmatched_files"},
        ],
    },

    # ── 数据处理 ──────────────────────────────────────
    {
        "id": "extract_frames",
        "group": "数据处理",
        "name": "视频抽帧",
        "description": "按固定时间间隔从视频中抽取帧并保存为 JPG。\n支持单个视频文件或整个文件夹。\n检测到 FFmpeg 时优先使用（更快）；否则回退 OpenCV。",
        "module": "scripts.extract_frames_from_mp4",
        "function": "extract_frames",
        "wrapper": "extract_frames_wrapper",
        "params": [
            {"key": "input_path",        "label": "视频文件/文件夹", "type": "file_or_folder"},
            {"key": "output_dir",        "label": "输出文件夹",       "type": "folder"},
            {"key": "interval_seconds",  "label": "抽帧间隔（秒）",   "type": "int", "default": 3, "min": 1, "max": 3600},
            {"key": "ffmpeg_path",       "label": "FFmpeg 路径（留空自动检测）",
             "type": "file_or_folder", "default": shutil.which("ffmpeg") or "", "optional": True},
        ],
    },
    {
        "id": "replace_txt_label",
        "group": "数据处理",
        "name": "替换标签类别",
        "description": "批量替换 YOLO TXT 标签中每行的第一个字段（类别 ID）。",
        "module": "scripts.replace_txt_label_class",
        "function": "replace_label_class",
        "params": [
            {"key": "txt_dir",    "label": "TXT 文件夹",  "type": "folder"},
            {"key": "output_dir", "label": "输出文件夹",    "type": "folder"},
            {"key": "old_class",  "label": "原类别",        "type": "text", "default": "0"},
            {"key": "new_class",  "label": "新类别",        "type": "text", "default": "1"},
        ],
    },
    {
        "id": "count_quantity",
        "group": "数据处理",
        "name": "标签统计",
        "description": "统计 YOLO 标签文件夹中各类别的实例数和包含该类别的图片数。",
        "module": "scripts.count_quantity",
        "function": "count_yolo_labels",
        "params": [
            {"key": "label_dir", "label": "标签文件夹", "type": "folder"},
        ],
    },
    {
        "id": "split_dataset",
        "group": "数据处理",
        "name": "数据集拆分",
        "description": "将图片 + YOLO 标签按比例拆分为 train / val / test 三个子集。\n自动匹配同名图片-标签对，随机打乱后按比例分配，并生成 dataset.yaml。",
        "module": "scripts.split_dataset",
        "function": "split_dataset",
        "params": [
            {"key": "images_dir",   "label": "图片文件夹",   "type": "folder"},
            {"key": "labels_dir",   "label": "标签文件夹",   "type": "folder"},
            {"key": "output_dir",   "label": "输出文件夹",   "type": "folder"},
            {"key": "train_ratio",  "label": "训练集比例",
             "type": "float", "default": 0.8, "min": 0, "max": 1},
            {"key": "val_ratio",    "label": "验证集比例",
             "type": "float", "default": 0.2, "min": 0, "max": 1},
            {"key": "test_ratio",   "label": "测试集比例",
             "type": "float", "default": 0.0, "min": 0, "max": 1},
        ],
    },
    {
        "id": "get_empty_labels",
        "group": "数据处理",
        "name": "生成空白标签",
        "description": "为图片文件夹中的每张图生成空白 YOLO TXT 标签文件（0 字节）。\n常用于「负样本」—— 图片存在但无标注对象，训练时需要对应的空 .txt。\n\n• 仅填图片文件夹：在同目录生成 .txt\n• 同时填标签文件夹：在指定目录生成，已有同名 .txt 的自动跳过",
        "module": "scripts.get_empty_labels",
        "function": "generate_empty_labels",
        "params": [
            {"key": "image_dir", "label": "图片文件夹", "type": "folder"},
            {"key": "txt_dir",   "label": "标签输出文件夹（留空则输出到图片同目录）",
             "type": "folder", "default": "", "optional": True},
        ],
    },
    {
        "id": "split_classes_to_folders",
        "group": "数据处理",
        "name": "按类别拆分到文件夹",
        "description": "根据标签中的类别值创建同名文件夹，并在每个类别目录下生成 images/labels。\n同一图片含多个类别时会复制到多个类别目录；每个类别的 labels 仅保留该类别行。\n可选将拆分后的类别值统一重映射为 0（默认开启，适合单类别训练）。",
        "module": "scripts.split_classes_to_folders",
        "function": "split_classes_to_folders",
        "params": [
            {"key": "images_dir", "label": "图片文件夹", "type": "folder"},
            {"key": "labels_dir", "label": "标签文件夹", "type": "folder"},
            {"key": "output_dir", "label": "输出文件夹", "type": "folder"},
            {"key": "remap_to_zero", "label": "将拆分后的类别重映射为 0", "type": "bool", "default": True},
        ],
    },
    {
        "id": "merge_m3u8",
        "group": "数据处理",
        "name": "M3U8 合并为 MP4",
        "description": "解析 m3u8，校验 TS 分片并合并为 MP4。\n检测到 FFmpeg 时使用流拷贝（极快，保留原始画质）；否则回退 OpenCV 逐帧合并。\n可跳过最前 N 个、最后 M 个 TS（按播放列表顺序；回退为目录排序时按该顺序裁剪）。\n输出名 = m3u8 所在文件夹名；可选统一输出目录，重名自动加随机后缀。",
        "module": "scripts.merge_m3u8_to_mp4",
        "function": "merge_m3u8_folder",
        "params": [
            {"key": "input_path",            "label": "M3U8 文件或文件夹", "type": "file_or_folder"},
            {"key": "recursive_subfolders",  "label": "递归子文件夹查找 m3u8", "type": "bool", "default": False},
            {"key": "output_folder",         "label": "输出文件夹（留空则保存在各 m3u8 同目录）",
             "type": "folder", "default": "", "optional": True},
            {"key": "skip_first_ts",         "label": "跳过最前 N 个 TS 分片",
             "type": "int", "default": 0, "min": 0, "max": 999999},
            {"key": "skip_last_ts",          "label": "跳过最后 M 个 TS 分片",
             "type": "int", "default": 0, "min": 0, "max": 999999},
            {"key": "ffmpeg_path",           "label": "FFmpeg 路径（留空自动检测）",
             "type": "file_or_folder", "default": shutil.which("ffmpeg") or "", "optional": True},
        ],
    },
]


def get_groups():
    """返回按 group 分组的有序字典 {group_name: [script_entries]}"""
    from collections import OrderedDict
    groups = OrderedDict()
    for entry in SCRIPT_REGISTRY:
        g = entry.get("group", "其他")
        groups.setdefault(g, []).append(entry)
    return groups
