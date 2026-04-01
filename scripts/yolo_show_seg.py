"""
已合并至 yolo_show.visualize_yolo；保留此模块供旧代码 / 打包 hiddenimport 兼容。
"""

from scripts.yolo_show import visualize_yolo


def show_yolo_seg(image_dir, label_dir, output_dir=None):
    """强制分割模式；output_dir 为空时仅预览（与合并前行为一致）。"""
    out = output_dir if output_dir is not None else ""
    return visualize_yolo(image_dir, label_dir, out, mode="seg")
