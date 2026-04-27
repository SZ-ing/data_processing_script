import json
import os
import shutil
import uuid
from tqdm import tqdm

IMAGE_EXTS = [".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"]


def _list_json_files(input_dir, recursive_subfolders=False):
    """返回 JSON 绝对路径列表。"""
    input_dir = os.path.abspath(input_dir)
    if not recursive_subfolders:
        return sorted(
            os.path.join(input_dir, f)
            for f in os.listdir(input_dir)
            if os.path.isfile(os.path.join(input_dir, f)) and f.lower().endswith(".json")
        )

    json_paths = []
    for root, _, files in os.walk(input_dir):
        for f in files:
            if f.lower().endswith(".json"):
                json_paths.append(os.path.join(root, f))
    return sorted(json_paths)


def _build_image_index(input_dir, recursive_subfolders=False):
    """
    构建图片索引:
      - by_name: 完整文件名(小写) -> [绝对路径...]
      - by_stem: 文件主名(小写)   -> [绝对路径...]
    """
    by_name = {}
    by_stem = {}
    input_dir = os.path.abspath(input_dir)

    if recursive_subfolders:
        candidates = []
        for root, _, files in os.walk(input_dir):
            for f in files:
                candidates.append(os.path.join(root, f))
    else:
        candidates = [
            os.path.join(input_dir, f)
            for f in os.listdir(input_dir)
            if os.path.isfile(os.path.join(input_dir, f))
        ]

    for p in candidates:
        name = os.path.basename(p)
        stem, ext = os.path.splitext(name)
        if ext.lower() not in IMAGE_EXTS:
            continue
        by_name.setdefault(name.lower(), []).append(p)
        by_stem.setdefault(stem.lower(), []).append(p)

    return by_name, by_stem


def _unique_stem(stem, exists_fn):
    """
    返回可用且唯一的文件 stem。
    若冲突则追加随机值并重复校验，直到不冲突。
    """
    candidate = stem
    while exists_fn(candidate):
        candidate = f"{stem}_{uuid.uuid4().hex[:8]}"
    return candidate


def _shape_to_yolo_det(shape, img_width, img_height):
    """rectangle → YOLO 检测格式: class cx cy w h"""
    points = shape.get("points", [])
    if not points:
        return None

    x_coords = [p[0] for p in points]
    y_coords = [p[1] for p in points]
    xmin, xmax = min(x_coords), max(x_coords)
    ymin, ymax = min(y_coords), max(y_coords)

    dw, dh = 1.0 / img_width, 1.0 / img_height
    cx = max(0, min(1, (xmin + xmax) / 2.0 * dw))
    cy = max(0, min(1, (ymin + ymax) / 2.0 * dh))
    w = max(0, min(1, (xmax - xmin) * dw))
    h = max(0, min(1, (ymax - ymin) * dh))
    return f"{cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


def _shape_to_yolo_seg(shape, img_width, img_height):
    """polygon → YOLO 分割格式: class x1 y1 x2 y2 ..."""
    points = shape.get("points", [])
    if len(points) < 3:
        return None

    parts = []
    for p in points:
        px = max(0, min(1, p[0] / img_width))
        py = max(0, min(1, p[1] / img_height))
        parts.append(f"{px:.6f}")
        parts.append(f"{py:.6f}")
    return " ".join(parts)


def _detect_mode(json_paths):
    """扫描前几个 JSON，根据 shape_type 自动判断 检测 / 分割。"""
    sample_count = min(10, len(json_paths))
    rect_count, poly_count = 0, 0

    for json_path in json_paths[:sample_count]:
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for shape in data.get("shapes", []):
                st = shape.get("shape_type", "")
                if st == "rectangle":
                    rect_count += 1
                elif st == "polygon":
                    poly_count += 1
        except Exception:
            continue

    if poly_count > rect_count:
        return "seg"
    return "det"


def _scan_shape_type_presence(json_paths):
    """扫描全部 JSON，返回是否包含 rectangle / polygon。"""
    has_rect = False
    has_poly = False
    for json_path in json_paths:
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for shape in data.get("shapes", []):
                st = shape.get("shape_type", "")
                if st == "rectangle":
                    has_rect = True
                elif st == "polygon":
                    has_poly = True
                if has_rect and has_poly:
                    return has_rect, has_poly
        except Exception:
            continue
    return has_rect, has_poly


def _collect_labels(json_paths):
    """预扫描所有 JSON，收集全部唯一 label。"""
    all_labels = set()
    for json_path in json_paths:
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for shape in data.get("shapes", []):
                label = shape.get("label", "")
                if label:
                    all_labels.add(label)
        except Exception:
            continue
    return all_labels


def _find_image_for_json(
    input_dir,
    base_name,
    image_path_field="",
    json_dir=None,
    image_index_by_name=None,
    image_index_by_stem=None,
):
    """优先按 imagePath 字段匹配图片，失败则按同名 stem + 常见后缀查找。"""
    if image_path_field:
        img_field_norm = image_path_field.replace("\\", os.sep).replace("/", os.sep)
        # 1) 绝对路径
        if os.path.isabs(img_field_norm) and os.path.isfile(img_field_norm):
            return img_field_norm
        # 2) 相对 json 所在目录
        if json_dir:
            by_json_dir = os.path.join(json_dir, img_field_norm)
            if os.path.isfile(by_json_dir):
                return by_json_dir
        # 3) 仅文件名落在输入根目录
        by_input_root = os.path.join(input_dir, os.path.basename(img_field_norm))
        if os.path.isfile(by_input_root):
            return by_input_root
        # 4) 递归索引按完整文件名兜底
        if image_index_by_name:
            key = os.path.basename(img_field_norm).lower()
            candidates = image_index_by_name.get(key, [])
            if candidates:
                return candidates[0]

    if json_dir:
        for ext in IMAGE_EXTS:
            p = os.path.join(json_dir, base_name + ext)
            if os.path.isfile(p):
                return p
            p_upper = os.path.join(json_dir, base_name + ext.upper())
            if os.path.isfile(p_upper):
                return p_upper

    for ext in IMAGE_EXTS:
        p = os.path.join(input_dir, base_name + ext)
        if os.path.isfile(p):
            return p
        p_upper = os.path.join(input_dir, base_name + ext.upper())
        if os.path.isfile(p_upper):
            return p_upper

    # 递归索引按 stem 兜底
    if image_index_by_stem:
        candidates = image_index_by_stem.get(base_name.lower(), [])
        if candidates:
            return candidates[0]
    return None


def labelme2yolo(
    json_dir,
    output_dir,
    mode="auto",
    remap_to_zero=False,
    recursive_subfolders=False,
):
    """
    将 LabelMe JSON 转换为 YOLO TXT 格式。
    自动根据 shape_type 判断输出检测格式还是分割格式。
    支持数字标签和字符串标签，字符串标签会自动分配 class_id。

    Args:
        json_dir:   存放 JSON 文件的文件夹路径
        output_dir: 存放生成的 TXT 标签的文件夹路径
        mode:       "auto" 自动判断 | "det" 强制检测 | "seg" 强制分割
        remap_to_zero: True 时将所有输出类别统一为 0
    """
    os.makedirs(output_dir, exist_ok=True)

    json_paths = _list_json_files(json_dir, recursive_subfolders=recursive_subfolders)
    if not json_paths:
        print(f"未找到 JSON 文件: {json_dir}")
        return

    auto_split_mixed = False
    mode_for_convert = mode
    if mode == "auto":
        has_rect, has_poly = _scan_shape_type_presence(json_paths)
        if has_rect and has_poly:
            auto_split_mixed = True
            print("自动识别模式: 检测+分割混合，输出拆分为 det/ 与 seg/")
        else:
            mode_for_convert = _detect_mode(json_paths)
            mode_label = "检测 (bbox)" if mode_for_convert == "det" else "分割 (polygon)"
            print(f"自动识别模式: {mode_label}")
    else:
        mode_label = "检测 (bbox)" if mode_for_convert == "det" else "分割 (polygon)"
        print(f"转换模式: {mode_label}")

    print("正在预扫描标签...")
    all_labels = _collect_labels(json_paths)
    print(f"发现 {len(all_labels)} 个类别: {sorted(all_labels)}")
    print(f"共找到 {len(json_paths)} 个 JSON 文件，开始转换...")

    count = 0
    count_det = 0
    count_seg = 0

    det_out_dir = os.path.join(output_dir, "det")
    seg_out_dir = os.path.join(output_dir, "seg")
    if auto_split_mixed:
        os.makedirs(det_out_dir, exist_ok=True)
        os.makedirs(seg_out_dir, exist_ok=True)

    progress_desc = "LabelMe → YOLO (auto split det/seg)" if auto_split_mixed else f"LabelMe → YOLO {mode_label}"
    for json_path in tqdm(json_paths, desc=progress_desc, unit="file"):
        json_file = os.path.basename(json_path)

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            tqdm.write(f"无法读取文件 {json_file}: {e}")
            continue

        image_path_field = data.get("imagePath", "")
        if image_path_field:
            base_name = os.path.splitext(os.path.basename(image_path_field))[0]
        else:
            base_name = os.path.splitext(json_file)[0]

        img_width = data.get("imageWidth")
        img_height = data.get("imageHeight")
        if not img_width or not img_height:
            tqdm.write(f"跳过 {json_file}: 缺少尺寸信息")
            continue

        yolo_lines = []
        yolo_lines_det = []
        yolo_lines_seg = []
        for shape in data.get("shapes", []):
            label_str = shape.get("label", "")
            if not label_str:
                continue

            class_out = "0" if remap_to_zero else str(label_str)
            shape_type = shape.get("shape_type", "")

            if auto_split_mixed:
                if shape_type == "rectangle":
                    coords_det = _shape_to_yolo_det(shape, img_width, img_height)
                    if coords_det is not None:
                        yolo_lines_det.append(f"{class_out} {coords_det}")
                elif shape_type == "polygon":
                    coords_seg = _shape_to_yolo_seg(shape, img_width, img_height)
                    if coords_seg is not None:
                        yolo_lines_seg.append(f"{class_out} {coords_seg}")
                continue

            if mode_for_convert == "det":
                if shape_type != "rectangle":
                    continue
                coords = _shape_to_yolo_det(shape, img_width, img_height)
            else:
                if shape_type != "polygon":
                    continue
                coords = _shape_to_yolo_seg(shape, img_width, img_height)
            if coords is None:
                continue
            yolo_lines.append(f"{class_out} {coords}")

        if auto_split_mixed:
            if yolo_lines_det:
                stem_det = _unique_stem(
                    base_name,
                    exists_fn=lambda s: os.path.exists(os.path.join(det_out_dir, f"{s}.txt")),
                )
                if stem_det != base_name:
                    tqdm.write(f"det 名称重复: {base_name} -> 已更名为 {stem_det}")
                txt_path_det = os.path.join(det_out_dir, f"{stem_det}.txt")
                with open(txt_path_det, "w", encoding="utf-8") as f:
                    f.write("\n".join(yolo_lines_det))
                count_det += 1

            if yolo_lines_seg:
                stem_seg = _unique_stem(
                    base_name,
                    exists_fn=lambda s: os.path.exists(os.path.join(seg_out_dir, f"{s}.txt")),
                )
                if stem_seg != base_name:
                    tqdm.write(f"seg 名称重复: {base_name} -> 已更名为 {stem_seg}")
                txt_path_seg = os.path.join(seg_out_dir, f"{stem_seg}.txt")
                with open(txt_path_seg, "w", encoding="utf-8") as f:
                    f.write("\n".join(yolo_lines_seg))
                count_seg += 1
            continue

        if not yolo_lines:
            continue

        stem = _unique_stem(
            base_name,
            exists_fn=lambda s: os.path.exists(os.path.join(output_dir, f"{s}.txt")),
        )
        if stem != base_name:
            tqdm.write(f"名称重复: {base_name} -> 已更名为 {stem}")
        txt_path = os.path.join(output_dir, f"{stem}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(yolo_lines))
        count += 1

    print("-" * 30)
    if auto_split_mixed:
        print("转换完成！模式: 自动混合拆分")
        print(f"det 文件数: {count_det}，路径: {os.path.abspath(det_out_dir)}")
        print(f"seg 文件数: {count_seg}，路径: {os.path.abspath(seg_out_dir)}")
    else:
        print(f"转换完成！模式: {mode_label}，共处理 {count} 个文件。")
    print(f"涉及类别: {sorted(all_labels)}")
    if not auto_split_mixed:
        print(f"保存路径: {os.path.abspath(output_dir)}")


def labelme2yolo_pack_dataset(
    input_dir,
    output_dir,
    mode="auto",
    remap_to_zero=False,
    recursive_subfolders=False,
):
    """
    输入目录为“图片+json 混合目录”：
    - 在 output_dir 下创建 images/ 与 labels/
    - 将 json 转成 txt 保存到 labels/
    - 将有对应 json 的图片复制到 images/
    """
    input_dir = os.path.abspath(input_dir)
    output_dir = os.path.abspath(output_dir)
    images_out = os.path.join(output_dir, "images")
    labels_out = os.path.join(output_dir, "labels")

    os.makedirs(images_out, exist_ok=True)
    os.makedirs(labels_out, exist_ok=True)

    json_paths = _list_json_files(input_dir, recursive_subfolders=recursive_subfolders)
    if not json_paths:
        print(f"未找到 JSON 文件: {input_dir}")
        return

    auto_split_mixed = False
    mode_for_convert = mode
    if mode == "auto":
        has_rect, has_poly = _scan_shape_type_presence(json_paths)
        if has_rect and has_poly:
            auto_split_mixed = True
        else:
            mode_for_convert = _detect_mode(json_paths)
    mode_label = "检测 (bbox)" if mode_for_convert == "det" else "分割 (polygon)"

    labels_det_out = os.path.join(labels_out, "det")
    labels_seg_out = os.path.join(labels_out, "seg")
    if auto_split_mixed:
        os.makedirs(labels_det_out, exist_ok=True)
        os.makedirs(labels_seg_out, exist_ok=True)
    image_index_by_name, image_index_by_stem = _build_image_index(
        input_dir, recursive_subfolders=recursive_subfolders
    )

    print(f"输入目录: {input_dir}")
    print(f"输出目录: {output_dir}")
    if auto_split_mixed:
        print("转换模式: 自动混合拆分（labels/det + labels/seg）")
    else:
        print(f"转换模式: {mode_label}")
    print(f"类别重映射为 0: {'是' if remap_to_zero else '否'}")
    print(f"共找到 {len(json_paths)} 个 JSON，开始处理...")

    ok_txt = 0
    ok_img = 0
    miss_img = 0
    skip_size = 0
    skip_empty = 0
    bad_json = 0
    ok_txt_det = 0
    ok_txt_seg = 0

    for json_path in tqdm(json_paths, desc="LabelMe -> YOLO 打包", unit="file"):
        json_file = os.path.basename(json_path)
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            bad_json += 1
            tqdm.write(f"无法读取 JSON {json_file}: {e}")
            continue

        image_path_field = data.get("imagePath", "")
        if image_path_field:
            base_name = os.path.splitext(os.path.basename(image_path_field))[0]
        else:
            base_name = os.path.splitext(json_file)[0]

        img_width = data.get("imageWidth")
        img_height = data.get("imageHeight")
        if not img_width or not img_height:
            skip_size += 1
            tqdm.write(f"跳过 {json_file}: 缺少 imageWidth/imageHeight")
            continue

        yolo_lines = []
        yolo_lines_det = []
        yolo_lines_seg = []
        for shape in data.get("shapes", []):
            label_str = shape.get("label", "")
            if not label_str:
                continue
            class_out = "0" if remap_to_zero else str(label_str)
            shape_type = shape.get("shape_type", "")

            if auto_split_mixed:
                if shape_type == "rectangle":
                    coords_det = _shape_to_yolo_det(shape, img_width, img_height)
                    if coords_det is not None:
                        yolo_lines_det.append(f"{class_out} {coords_det}")
                elif shape_type == "polygon":
                    coords_seg = _shape_to_yolo_seg(shape, img_width, img_height)
                    if coords_seg is not None:
                        yolo_lines_seg.append(f"{class_out} {coords_seg}")
                continue

            if mode_for_convert == "det":
                if shape_type != "rectangle":
                    continue
                coords = _shape_to_yolo_det(shape, img_width, img_height)
            else:
                if shape_type != "polygon":
                    continue
                coords = _shape_to_yolo_seg(shape, img_width, img_height)
            if coords is None:
                continue
            yolo_lines.append(f"{class_out} {coords}")

        if auto_split_mixed:
            if not yolo_lines_det and not yolo_lines_seg:
                skip_empty += 1
                continue
        else:
            if not yolo_lines:
                skip_empty += 1
                continue

        image_src = _find_image_for_json(
            input_dir=input_dir,
            base_name=base_name,
            image_path_field=image_path_field,
            json_dir=os.path.dirname(json_path),
            image_index_by_name=image_index_by_name,
            image_index_by_stem=image_index_by_stem,
        )
        image_ext = os.path.splitext(image_src)[1] if image_src else ""
        if auto_split_mixed:
            stem = _unique_stem(
                base_name,
                exists_fn=lambda s: (
                    os.path.exists(os.path.join(labels_det_out, f"{s}.txt"))
                    or os.path.exists(os.path.join(labels_seg_out, f"{s}.txt"))
                    or (bool(image_ext) and os.path.exists(os.path.join(images_out, f"{s}{image_ext}")))
                ),
            )
        else:
            stem = _unique_stem(
                base_name,
                exists_fn=lambda s: (
                    os.path.exists(os.path.join(labels_out, f"{s}.txt"))
                    or (bool(image_ext) and os.path.exists(os.path.join(images_out, f"{s}{image_ext}")))
                ),
            )
        if stem != base_name:
            tqdm.write(f"名称重复: {base_name} -> 已更名为 {stem}")

        if auto_split_mixed:
            if yolo_lines_det:
                txt_path_det = os.path.join(labels_det_out, f"{stem}.txt")
                with open(txt_path_det, "w", encoding="utf-8") as f:
                    f.write("\n".join(yolo_lines_det))
                ok_txt_det += 1
                ok_txt += 1
            if yolo_lines_seg:
                txt_path_seg = os.path.join(labels_seg_out, f"{stem}.txt")
                with open(txt_path_seg, "w", encoding="utf-8") as f:
                    f.write("\n".join(yolo_lines_seg))
                ok_txt_seg += 1
                ok_txt += 1
        else:
            txt_path = os.path.join(labels_out, f"{stem}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write("\n".join(yolo_lines))
            ok_txt += 1

        if image_src:
            image_dst = os.path.join(images_out, f"{stem}{image_ext}")
            shutil.copy2(image_src, image_dst)
            ok_img += 1
        else:
            miss_img += 1
            tqdm.write(f"未找到对应图片: {json_file}")

    print("-" * 40)
    if auto_split_mixed:
        print("处理完成，模式: 自动混合拆分")
        print(f"det TXT 成功: {ok_txt_det}")
        print(f"seg TXT 成功: {ok_txt_seg}")
    else:
        print(f"处理完成，模式: {mode_label}")
    print(f"JSON 转 TXT 成功: {ok_txt}")
    print(f"图片复制成功: {ok_img}")
    print(f"缺少对应图片: {miss_img}")
    print(f"跳过(缺尺寸信息): {skip_size}")
    print(f"跳过(无有效标注): {skip_empty}")
    print(f"JSON 读取失败: {bad_json}")
    if auto_split_mixed:
        print(f"labels/det 路径: {labels_det_out}")
        print(f"labels/seg 路径: {labels_seg_out}")
    else:
        print(f"labels 路径: {labels_out}")
    print(f"images 路径: {images_out}")


def labelme2yolo_unified(
    input_kind="json_only",
    input_dir="",
    output_dir="",
    mode="auto",
    remap_to_zero=False,
    recursive_subfolders=False,
):
    """
    UI 统一入口：
    - json_only: 仅 JSON 目录 -> 输出 TXT
    - mixed_pack: 图片+JSON 混合目录 -> 输出 images/labels 打包目录
    """
    if not output_dir:
        raise ValueError("输出文件夹不能为空")
    if not input_dir:
        raise ValueError("输入文件夹不能为空")

    if input_kind == "mixed_pack":
        return labelme2yolo_pack_dataset(
            input_dir=input_dir,
            output_dir=output_dir,
            mode=mode,
            remap_to_zero=remap_to_zero,
            recursive_subfolders=recursive_subfolders,
        )

    return labelme2yolo(
        json_dir=input_dir,
        output_dir=output_dir,
        mode=mode,
        remap_to_zero=remap_to_zero,
        recursive_subfolders=recursive_subfolders,
    )


# 保留旧函数名作为兼容别名
labelme2yolo_direct_id = labelme2yolo
labelme2yolo_seg_direct_id = lambda json_dir, output_dir: labelme2yolo(json_dir, output_dir, mode="seg")


if __name__ == "__main__":
    JSON_FOLDER = r"H:\3.24 非机动车——董嘉琪\json_labels"
    OUTPUT_FOLDER = r"H:\3.24 非机动车——董嘉琪\labels"

    labelme2yolo(JSON_FOLDER, OUTPUT_FOLDER)
