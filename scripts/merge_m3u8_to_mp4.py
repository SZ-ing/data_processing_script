import os
import shutil
import subprocess
import uuid

from tqdm import tqdm


# ────────────────────────────────────────
#  FFmpeg 路径解析
# ────────────────────────────────────────

def _resolve_ffmpeg(ffmpeg_path: str) -> str | None:
    """将用户输入解析为可执行的 ffmpeg 路径，解析失败返回 None。"""
    path = (ffmpeg_path or "").strip()
    if path:
        if os.path.isfile(path):
            return path
        found = shutil.which(path)
        return found
    return shutil.which("ffmpeg")


def _resolve_ffprobe(ffmpeg_exe: str | None) -> str | None:
    """根据 ffmpeg 路径推导 ffprobe 路径。"""
    if not ffmpeg_exe:
        return shutil.which("ffprobe")
    dirname = os.path.dirname(ffmpeg_exe)
    basename = os.path.basename(ffmpeg_exe)
    probe_name = basename.replace("ffmpeg", "ffprobe")
    probe_path = os.path.join(dirname, probe_name)
    if os.path.isfile(probe_path):
        return probe_path
    return shutil.which("ffprobe")


# ────────────────────────────────────────
#  M3U8 解析 / TS 索引
# ────────────────────────────────────────

def parse_m3u8_segments(m3u8_path):
    """解析 m3u8，返回 ts 分片文件名列表。"""
    with open(m3u8_path, "r", encoding="utf-8", errors="replace") as f:
        lines = [line.strip() for line in f]

    segments = []
    for line in lines:
        if not line or line.startswith("#"):
            continue
        segments.append(line)
    return segments


def build_ts_index(root_dir):
    """递归扫描目录，建立 ts 文件名 → 绝对路径 的索引。"""
    ts_index = {}
    all_ts_files = []
    root_dir = os.path.abspath(root_dir)
    for current_root, _, files in os.walk(root_dir):
        for file_name in files:
            if not file_name.lower().endswith(".ts"):
                continue
            full_path = os.path.join(current_root, file_name)
            ts_index.setdefault(file_name, []).append(full_path)
            all_ts_files.append(full_path)
    all_ts_files.sort()
    return ts_index, all_ts_files


def resolve_segment_path(m3u8_dir, segment, ts_index):
    """将 m3u8 中的分片名解析为磁盘上的绝对路径。"""
    direct_path = os.path.normpath(os.path.join(m3u8_dir, segment))
    if os.path.exists(direct_path):
        return direct_path

    file_name = os.path.basename(segment)
    matched_paths = ts_index.get(file_name, [])
    if matched_paths:
        return matched_paths[0]

    return direct_path


# ────────────────────────────────────────
#  分片校验 / 视频信息
# ────────────────────────────────────────

def probe_ts(ts_path, min_size=512):
    """快速校验：文件存在且大小 >= min_size 字节。"""
    try:
        return os.path.isfile(ts_path) and os.path.getsize(ts_path) >= min_size
    except OSError:
        return False


def get_video_props(ts_path, ffprobe_exe=None):
    """从一个 ts 文件读取 fps、宽、高。优先 ffprobe，回退 cv2。"""
    if ffprobe_exe:
        try:
            cmd = [
                ffprobe_exe, "-v", "quiet",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate",
                "-of", "csv=p=0",
                ts_path,
            ]
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            parts = r.stdout.strip().split(",")
            w, h = int(parts[0]), int(parts[1])
            num, den = parts[2].split("/")
            fps = float(num) / float(den)
            if fps <= 0:
                fps = 25.0
            return fps, w, h
        except Exception:
            pass

    import cv2
    cap = cv2.VideoCapture(ts_path)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        cap.release()
    if fps <= 0:
        fps = 25.0
    return fps, w, h


def build_valid_segment_list(m3u8_dir, segments, ts_index):
    """校验分片，跳过不可用的，返回可用分片列表和缺失数。"""
    valid_segments = []
    missing_count = 0

    for segment in tqdm(segments, desc="检查分片", unit="seg"):
        ts_path = resolve_segment_path(m3u8_dir, segment, ts_index)
        if probe_ts(ts_path):
            valid_segments.append(ts_path)
        else:
            missing_count += 1

    return valid_segments, missing_count


# ────────────────────────────────────────
#  合并：FFmpeg 流拷贝（首选）
# ────────────────────────────────────────

def _merge_ffmpeg(segment_paths, output_path, ffmpeg_exe):
    """FFmpeg concat demuxer + stream copy，无需解码/编码。"""
    concat_file = output_path + ".concat.txt"
    try:
        with open(concat_file, "w", encoding="utf-8") as f:
            for p in segment_paths:
                safe = p.replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{safe}'\n")

        cmd = [
            ffmpeg_exe, "-y", "-hide_banner",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            "-movflags", "+faststart",
            "-loglevel", "error",
            output_path,
        ]

        print(f"使用 FFmpeg 流拷贝合并 {len(segment_paths)} 个分片…")
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        if result.stderr.strip():
            for line in result.stderr.strip().splitlines()[:5]:
                print(f"  FFmpeg: {line}")

        if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
            return True

        print("FFmpeg 合并失败。")
        return False
    finally:
        try:
            os.remove(concat_file)
        except OSError:
            pass


# ────────────────────────────────────────
#  合并：OpenCV 逐帧（回退方案）
# ────────────────────────────────────────

def _merge_cv2(segment_paths, output_path, fps, width, height):
    """OpenCV 逐帧解码→重编码，速度较慢，仅在无 FFmpeg 时使用。"""
    import cv2

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    if not writer.isOpened():
        print(f"无法创建输出文件: {output_path}")
        writer.release()
        return False

    total_frames = 0
    try:
        for ts_path in tqdm(segment_paths, desc="合并分片", unit="seg"):
            cap = cv2.VideoCapture(ts_path)
            try:
                if not cap.isOpened():
                    tqdm.write(f"警告: 无法打开 {os.path.basename(ts_path)}，已跳过")
                    continue

                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    if frame.shape[1] != width or frame.shape[0] != height:
                        frame = cv2.resize(frame, (width, height))
                    writer.write(frame)
                    total_frames += 1
            finally:
                cap.release()
    finally:
        writer.release()

    print(f"共写入 {total_frames} 帧")
    return total_frames > 0


# ────────────────────────────────────────
#  合并入口
# ────────────────────────────────────────

def merge_segments_to_mp4(segment_paths, output_path, ffmpeg_exe=None):
    """合并分片为 mp4。有 FFmpeg 时流拷贝，否则 OpenCV 逐帧。"""
    if not segment_paths:
        print("没有可用于合并的分片。")
        return False

    ffprobe_exe = _resolve_ffprobe(ffmpeg_exe)
    fps, width, height = get_video_props(segment_paths[0], ffprobe_exe)
    print(f"视频参数: {width}x{height} @ {fps:.2f}fps")

    if ffmpeg_exe:
        success = _merge_ffmpeg(segment_paths, output_path, ffmpeg_exe)
        if success:
            return True
        print("FFmpeg 失败，回退到 OpenCV 逐帧合并…")

    if not ffmpeg_exe:
        print("未检测到 FFmpeg，使用 OpenCV 逐帧合并（速度较慢）…")

    return _merge_cv2(segment_paths, output_path, fps, width, height)


# ────────────────────────────────────────
#  m3u8 收集 / 输出路径
# ────────────────────────────────────────

def collect_m3u8_paths(path, recursive=False):
    """
    收集待处理的 m3u8 绝对路径列表。
    - 若为 .m3u8 文件：仅该文件（与 recursive 无关）
    - 若为文件夹且 recursive=False：只扫描该文件夹一层内的 .m3u8
    - 若为文件夹且 recursive=True：递归子文件夹查找所有 .m3u8
    """
    path = os.path.abspath(path)
    if os.path.isfile(path):
        if path.lower().endswith(".m3u8"):
            return [path]
        print(f"所选文件不是 .m3u8: {path}")
        return []
    if os.path.isdir(path):
        found = []
        if recursive:
            for root, _, files in os.walk(path):
                for name in sorted(files):
                    if name.lower().endswith(".m3u8"):
                        found.append(os.path.join(root, name))
        else:
            try:
                for name in sorted(os.listdir(path)):
                    if not name.lower().endswith(".m3u8"):
                        continue
                    full = os.path.join(path, name)
                    if os.path.isfile(full):
                        found.append(full)
            except OSError as e:
                print(f"无法列出目录: {path} ({e})")
                return []
        return sorted(found)
    print(f"路径不存在或类型不支持: {path}")
    return []


def mp4_stem_from_m3u8(m3u8_path):
    """输出 mp4 主名：m3u8 所在目录的文件夹名；若在盘符根目录则用 m3u8 主文件名。"""
    m3u8_path = os.path.abspath(m3u8_path)
    m3u8_dir = os.path.dirname(m3u8_path)
    stem = os.path.basename(os.path.normpath(m3u8_dir))
    if not stem:
        return os.path.splitext(os.path.basename(m3u8_path))[0]
    return stem


def resolve_output_mp4_path(m3u8_path, output_folder):
    """
    决定输出 mp4 的完整路径。
    - output_folder 非空：输出到该目录（自动创建），文件名 {父文件夹名}.mp4
    - 否则：输出到 m3u8 同目录
    重名则在主名后追加 _{随机8位}
    """
    stem = mp4_stem_from_m3u8(m3u8_path)
    m3u8_dir = os.path.dirname(os.path.abspath(m3u8_path))
    folder = (output_folder or "").strip()
    if folder:
        target_dir = os.path.abspath(folder)
        os.makedirs(target_dir, exist_ok=True)
    else:
        target_dir = m3u8_dir

    candidate = os.path.join(target_dir, f"{stem}.mp4")
    if not os.path.exists(candidate):
        return candidate

    suffix = uuid.uuid4().hex[:8]
    return os.path.join(target_dir, f"{stem}_{suffix}.mp4")


# ────────────────────────────────────────
#  单文件 / 批量处理
# ────────────────────────────────────────

def merge_single_m3u8(m3u8_path, output_mp4_path, ffmpeg_exe=None):
    """处理单个 m3u8：在其所在目录树内索引 ts 并合并。"""
    m3u8_path = os.path.abspath(m3u8_path)
    m3u8_dir = os.path.dirname(m3u8_path)

    segments = parse_m3u8_segments(m3u8_path)
    if not segments:
        print(f"m3u8 中未找到可用分片: {m3u8_path}")
        return False

    ts_index, all_ts_files = build_ts_index(m3u8_dir)

    print(f"播放列表: {m3u8_path}")
    print(f"分片目录: {m3u8_dir}")
    print(f"输出文件: {output_mp4_path}")
    print(f"分片数量: {len(segments)}")
    print(f"扫描到 ts 文件数: {len(all_ts_files)}")
    if ffmpeg_exe:
        print(f"合并引擎: FFmpeg 流拷贝 ({ffmpeg_exe})")
    else:
        print("合并引擎: OpenCV 逐帧重编码（较慢；配置 FFmpeg 路径可大幅提速）")

    valid_segments, missing_count = build_valid_segment_list(
        m3u8_dir, segments, ts_index
    )

    if not valid_segments:
        print("警告: 无法按 m3u8 匹配到可用分片，改为按该目录树中的 ts 文件排序后合并。")
        valid_segments = [p for p in all_ts_files if probe_ts(p)]

    if not valid_segments:
        print("错误: 没有任何可用的 ts 分片。")
        return False

    print("-" * 30)
    print(f"缺失或不可用分片数: {missing_count}")
    print(f"实际参与合并分片数: {len(valid_segments)}")

    success = merge_segments_to_mp4(valid_segments, output_mp4_path, ffmpeg_exe)
    if success:
        size_mb = os.path.getsize(output_mp4_path) / (1024 * 1024)
        print(f"合并完成: {output_mp4_path} ({size_mb:.1f} MB)")
    else:
        print("合并失败。")
    return success


def merge_m3u8_folder(input_path, output_folder="",
                      recursive_subfolders=False, ffmpeg_path=""):
    """
    合并 M3U8 为 MP4。

    Args:
        input_path: 单个 .m3u8 文件路径，或包含 m3u8 的文件夹路径
        output_folder: 可选。非空则所有 mp4 输出到此目录；空则每个 mp4 输出到对应 m3u8 同目录。
        recursive_subfolders: 输入为文件夹时，False=只扫描该文件夹一层；True=递归子目录查找所有 m3u8。
        ffmpeg_path: FFmpeg 可执行文件路径。留空自动检测 PATH，找不到则回退 OpenCV。
    """
    ffmpeg_exe = _resolve_ffmpeg(ffmpeg_path)
    if ffmpeg_exe:
        print(f"✔ FFmpeg 已就绪: {ffmpeg_exe}")
    else:
        print("⚠ 未检测到 FFmpeg，将使用 OpenCV 逐帧合并（速度较慢）")
        print("  提示: 安装 FFmpeg 并填写路径可提速数十倍")

    paths = collect_m3u8_paths(input_path, recursive=recursive_subfolders)
    if not paths:
        print("未找到任何 .m3u8 文件。")
        return

    mode = "递归子文件夹" if recursive_subfolders else "仅当前文件夹"
    print(f"m3u8 查找范围: {mode}")
    print(f"共找到 {len(paths)} 个 m3u8，开始处理...\n")

    ok, fail = 0, 0
    for i, m3u8_path in enumerate(paths, start=1):
        print("=" * 50)
        print(f"[{i}/{len(paths)}] {m3u8_path}")
        print("=" * 50)
        out_path = resolve_output_mp4_path(m3u8_path, output_folder)
        try:
            if merge_single_m3u8(m3u8_path, out_path, ffmpeg_exe):
                ok += 1
            else:
                fail += 1
        except Exception as e:
            print(f"处理异常: {e}")
            fail += 1
        print()

    print("=" * 50)
    print(f"全部结束: 成功 {ok}，失败 {fail}")


merge_m3u8 = merge_m3u8_folder


if __name__ == "__main__":
    input_path = r"H:\download\大客车\2025-01\videos\Record_38_Events_1"
    output_folder = ""
    recursive_subfolders = False

    merge_m3u8_folder(input_path, output_folder, recursive_subfolders)
