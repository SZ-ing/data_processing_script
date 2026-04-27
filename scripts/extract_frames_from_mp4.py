import os
import shutil
import subprocess
from collections import deque

from tqdm import tqdm

VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".flv")


# ────────────────────────────────────────
#  FFmpeg 工具
# ────────────────────────────────────────

def _resolve_ffmpeg(ffmpeg_path=""):
    """将用户输入解析为可执行的 ffmpeg 路径，解析失败返回 None。"""
    path = (ffmpeg_path or "").strip()
    if path:
        if os.path.isfile(path):
            return path
        found = shutil.which(path)
        return found
    return shutil.which("ffmpeg")


def _resolve_ffprobe(ffmpeg_exe):
    if not ffmpeg_exe:
        return shutil.which("ffprobe")
    dirname = os.path.dirname(ffmpeg_exe)
    probe_name = os.path.basename(ffmpeg_exe).replace("ffmpeg", "ffprobe")
    probe_path = os.path.join(dirname, probe_name)
    if os.path.isfile(probe_path):
        return probe_path
    return shutil.which("ffprobe")


def _probe_video(video_path, ffprobe_exe):
    """用 ffprobe 获取 duration / fps / total_frames。"""
    cmd = [
        ffprobe_exe, "-v", "quiet",
        "-select_streams", "v:0",
        "-show_entries", "format=duration:stream=r_frame_rate,nb_frames",
        "-of", "csv=p=0",
        video_path,
    ]
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        lines = [l.strip() for l in r.stdout.strip().splitlines() if l.strip()]
        stream_parts = lines[0].split(",") if lines else []
        fps_str = stream_parts[0] if len(stream_parts) >= 1 else ""
        num, den = fps_str.split("/")
        fps = float(num) / float(den)

        duration = float(lines[1]) if len(lines) > 1 else None
        return fps, duration
    except Exception:
        return None, None


# ────────────────────────────────────────
#  FFmpeg 抽帧
# ────────────────────────────────────────

def _extract_single_ffmpeg(video_path, output_dir, interval_seconds, prefix, ffmpeg_exe):
    """用 FFmpeg 按固定间隔抽帧。成功返回 True。"""
    os.makedirs(output_dir, exist_ok=True)
    output_pattern = os.path.join(output_dir, f"{prefix}_%05d.jpg")

    video_filename = os.path.basename(video_path)
    print(f"\n正在处理: {video_filename}")

    ffprobe_exe = _resolve_ffprobe(ffmpeg_exe)
    fps, duration = (None, None)
    if ffprobe_exe:
        fps, duration = _probe_video(video_path, ffprobe_exe)
    extract_every_frame = float(interval_seconds) == -1.0
    estimated = None
    if duration:
        if extract_every_frame and fps:
            estimated = max(1, int(duration * fps))
        elif not extract_every_frame:
            estimated = int(duration / interval_seconds) + 1
        info = f"时长≈{duration:.1f}s, "
        if fps:
            info += f"fps≈{fps:.2f}, "
        if extract_every_frame:
            info += "间隔=每一帧"
        else:
            info += f"间隔={interval_seconds}s"
        if estimated:
            info += f", 预估≈{estimated} 帧"
        print(info)

    cmd = [
        ffmpeg_exe, "-y", "-hide_banner",
        "-progress", "pipe:1",
        "-nostats",
        "-i", video_path,
    ]
    if not extract_every_frame:
        cmd.extend(["-vf", f"fps=1/{interval_seconds}"])
    cmd.extend([
        "-q:v", "2",
        "-start_number", "0",
        output_pattern,
    ])

    print("使用 FFmpeg 抽帧…")
    pbar = tqdm(total=estimated, unit="img", desc="进度") if estimated else tqdm(unit="img", desc="进度")
    last_frame = 0
    err_lines = deque(maxlen=5)
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    try:
        if process.stdout:
            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line:
                    continue

                if "=" in line:
                    key, value = line.split("=", 1)
                    if key == "frame":
                        try:
                            current_frame = int(value.strip())
                        except ValueError:
                            continue
                        if current_frame > last_frame:
                            pbar.update(current_frame - last_frame)
                            last_frame = current_frame
                elif "error" in line.lower() or "failed" in line.lower():
                    err_lines.append(line)
        process.wait()
    finally:
        pbar.close()

    if process.returncode != 0:
        for line in err_lines:
            print(f"  FFmpeg: {line}")

    saved = sum(
        1 for f in os.listdir(output_dir)
        if f.startswith(prefix + "_") and f.lower().endswith(".jpg")
    )

    if saved > 0:
        print(f"完成！共抽取 {saved} 张图片。")
        return True

    print("FFmpeg 抽帧未产出文件。")
    return False


# ────────────────────────────────────────
#  OpenCV 抽帧（回退方案）
# ────────────────────────────────────────

def _imwrite_jpg(path, bgr):
    import cv2
    ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok:
        return False
    buf.tofile(path)
    return True


def _extract_single_cv2(video_path, output_dir, interval_seconds, prefix):
    """用 OpenCV 逐帧解码抽帧（较慢，仅在无 FFmpeg 时使用）。"""
    import cv2
    os.makedirs(output_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    try:
        if not cap.isOpened():
            print(f"无法打开视频（OpenCV）: {video_path}")
            return

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps is None or fps <= 0:
            fps = 30.0

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            total_frames = None

        extract_every_frame = float(interval_seconds) == -1.0
        step = 1 if extract_every_frame else max(1, int(round(float(interval_seconds) * fps)))
        estimated = max(1, total_frames // step + 1) if total_frames else None

        video_filename = os.path.basename(video_path)
        print(f"\n正在处理: {video_filename}")
        if total_frames is not None:
            duration = total_frames / fps
            interval_desc = "每一帧" if extract_every_frame else f"{interval_seconds}s"
            print(f"约 {total_frames} 帧, fps≈{fps:.2f}, 时长≈{duration:.2f}s, "
                  f"间隔≈{interval_desc}, 步进 {step} 帧")
        else:
            interval_desc = "每一帧" if extract_every_frame else f"{interval_seconds}s"
            print(f"fps≈{fps:.2f}, 间隔≈{interval_desc}, 步进 {step} 帧")

        pbar = tqdm(total=estimated, unit="img", desc="进度") if estimated else tqdm(unit="img", desc="进度")
        saved = 0
        frame_idx = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if frame_idx % step == 0:
                    out_path = os.path.join(output_dir, f"{prefix}_{saved:05d}.jpg")
                    if not _imwrite_jpg(out_path, frame):
                        print(f"写入失败: {out_path}")
                    saved += 1
                    pbar.update(1)
                frame_idx += 1

            if estimated and saved:
                pbar.n = saved
                pbar.refresh()
            print(f"完成！共抽取 {saved} 张图片。")
        finally:
            pbar.close()
    finally:
        cap.release()


# ────────────────────────────────────────
#  统一入口
# ────────────────────────────────────────

def extract_frames(video_path, output_dir, interval_seconds, prefix, ffmpeg_exe=None):
    """抽取单个视频的帧。优先 FFmpeg，回退 OpenCV。"""
    if not os.path.exists(video_path):
        print(f"跳过: 找不到视频文件 -> {video_path}")
        return

    if ffmpeg_exe:
        ok = _extract_single_ffmpeg(video_path, output_dir, interval_seconds, prefix, ffmpeg_exe)
        if ok:
            return
        print("回退到 OpenCV 逐帧抽取…")

    _extract_single_cv2(video_path, output_dir, interval_seconds, prefix)


def get_video_files(input_path, recursive_subfolders=False):
    if os.path.isfile(input_path):
        return [input_path]
    if os.path.isdir(input_path):
        if recursive_subfolders:
            video_files = []
            for root, _, files in os.walk(input_path):
                for f in files:
                    if f.lower().endswith(VIDEO_EXTS):
                        video_files.append(os.path.join(root, f))
            return sorted(video_files)

        return [
            os.path.join(input_path, f)
            for f in sorted(os.listdir(input_path))
            if os.path.isfile(os.path.join(input_path, f))
            and f.lower().endswith(VIDEO_EXTS)
        ]
    return []


def extract_frames_wrapper(
    input_path,
    output_dir,
    interval_seconds=-1,
    ffmpeg_path="",
    recursive_subfolders=False,
):
    """供 GUI 调用的入口，自动扫描视频并逐个抽帧。"""
    from datetime import datetime

    interval_seconds = float(interval_seconds)
    if interval_seconds != -1.0 and interval_seconds < 0.1:
        print(f"参数错误: 抽帧间隔仅支持 -1（每一帧）或 >= 0.1，当前值: {interval_seconds}")
        return

    ffmpeg_exe = _resolve_ffmpeg(ffmpeg_path)
    if ffmpeg_exe:
        print(f"✔ FFmpeg 已就绪: {ffmpeg_exe}")
    else:
        print("⚠ 未检测到 FFmpeg，将使用 OpenCV 逐帧抽取（速度较慢）")

    run_timestamp = datetime.now().strftime("%Y%m%d%H%M")
    base_prefix = f"frame_{run_timestamp}_"

    recursive_enabled = bool(recursive_subfolders) and os.path.isdir(input_path)
    if os.path.isfile(input_path) and recursive_subfolders:
        print("提示: 当前输入为单个视频文件，已忽略“递归子文件夹查找视频”选项。")

    video_files = get_video_files(input_path, recursive_subfolders=recursive_enabled)
    if not video_files:
        print(f"未找到可处理的视频文件: {input_path}")
        return

    if os.path.isdir(input_path):
        print(f"递归子文件夹查找视频: {'是' if recursive_enabled else '否'}")
    print(f"共找到 {len(video_files)} 个视频\n")

    total_videos = len(video_files)
    for index, path in enumerate(video_files):
        print(f"\n视频进度: {index + 1}/{total_videos}")
        current_prefix = f"{base_prefix}{index}"
        extract_frames(path, output_dir, interval_seconds, current_prefix, ffmpeg_exe)


if __name__ == "__main__":
    extract_frames_wrapper(
        input_path=r"D:\docker_volume\yolo_train\runs\video",
        output_dir=r"D:\docker_volume\yolo_train\runs\extract_frames",
        interval_seconds=-1,
    )
