import subprocess
import json
import math
import os
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_video_info_accurate(video_path: str) -> dict:
    """
    通过高效的 FFmpeg 解复用（demuxing）过程，精确且快速地获取视频的总帧数和时长。
    此方法避免了完整的视频解码，速度比旧的 ffprobe -count_frames 方法快几个数量级。
    """
    # 1. 首先，使用 ffprobe 快速、可靠地获取视频时长。
    duration = 0.0
    try:
        probe_command = [
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=duration', '-of', 'json', video_path
        ]
        probe_result = subprocess.run(probe_command, capture_output=True, text=True, check=True)
        info = json.loads(probe_result.stdout)['streams'][0]
        duration = float(info.get('duration', 0.0))
    except Exception as e:
        print(f"使用 ffprobe 获取视频 '{video_path}' 时长失败: {e}")
        # 即使获取时长失败，我们仍然可以继续尝试获取帧数。

    # 2. 接着，使用 ffmpeg 的流复制功能到 null 来快速统计总帧数。
    # 这个过程只解析容器和数据包，不解码帧，所以非常快。
    frame_count = 0
    demux_command = [
        'ffmpeg',
        '-i', video_path,
        '-map', '0:v:0',      # 仅选择第一个视频流
        '-c', 'copy',         # 直接复制流，不进行编解码
        '-f', 'null', '-'     # 输出到空设备，不写入任何文件
    ]
    try:
        # 我们需要捕获 stderr，因为 ffmpeg 将其进度和摘要信息输出到此处。
        # check=False 是因为即使任务“成功”，ffmpeg 在输出到 null 时也可能返回非零退出码。
        demux_result = subprocess.run(demux_command, capture_output=True, text=True)
        stderr_output = demux_result.stderr

        # 从 stderr 的最后几行中用正则表达式解析出最终的 frame=... 计数值。
        frame_matches = re.findall(r'frame=\s*(\d+)', stderr_output)
        if frame_matches:
            # 最后一个匹配项就是视频的总帧数。
            frame_count = int(frame_matches[-1])
        else:
            print(f"无法从 ffmpeg 的输出中解析帧数。视频: '{video_path}'. Stderr: {stderr_output}")
            return None

        return {
            'frame_count': frame_count,
            'duration': duration
        }
    except FileNotFoundError:
        print("错误: 'ffmpeg' 或 'ffprobe' 命令未找到。请确保它们已安装并在系统的 PATH 中。")
        return None
    except Exception as e:
        print(f"使用 ffmpeg 解复用获取帧数时发生未知错误，视频 '{video_path}': {e}")
        return None

def get_video_info(video_path: str) -> dict:
    """
    Quickly gets video duration and estimates frame count from metadata.
    This is much faster as it does not decode the video.
    """
    command = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=duration,avg_frame_rate',
        '-of', 'json',
        video_path
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)['streams'][0]
        duration = float(info.get('duration', 0.0))
        
        frame_rate_str = info.get('avg_frame_rate', '0/0')
        num, den = map(int, frame_rate_str.split('/'))
        frame_rate = num / den if den > 0 else 0
        
        estimated_frames = int(duration * frame_rate) if duration > 0 and frame_rate > 0 else 0
        
        return {
            'frame_count': estimated_frames, # This is an estimate
            'duration': duration
        }
    except (subprocess.CalledProcessError, json.JSONDecodeError, IndexError, KeyError) as e:
        print(f"Error getting fast video info for {video_path}: {e}")
        return None

def run_ffmpeg_command(command: list):
    """
    Executes an FFmpeg command and captures its output.
    """
    try:
        process = subprocess.run(command, capture_output=True, text=True, check=True)
        return True, process.stderr
    except subprocess.CalledProcessError as e:
        error_message = f"FFmpeg command failed with exit code {e.returncode}\n"
        error_message += f"Stdout:\n{e.stdout}\n"
        error_message += f"Stderr:\n{e.stderr}"
        return False, error_message

def decode_and_count_frames_gpu(video_path: str) -> (int, float):
    """
    Decodes a video using GPU to a null output, and parses the frame count from stderr.
    Returns the frame count.
    """
    command = [
        'ffmpeg',
        '-hide_banner',
        '-hwaccel', 'cuda',
        '-c:v', 'h264_cuvid',
        '-i', video_path,
        '-f', 'null', '-'
    ]
    success, stderr_output = run_ffmpeg_command(command)
    if not success:
        print(f"Failed to decode {video_path}. Error:\n{stderr_output}")
        return 0
    frame_matches = re.findall(r'frame=\s*(\d+)', stderr_output)
    decoded_frames = int(frame_matches[-1]) if frame_matches else 0
    return decoded_frames

def split_video_by_gpu(video_path: str, output_dir: str, num_splits: int = 4, total_frames: int = 0) -> list:
    """
    Splits a video into multiple parts using FFmpeg with GPU acceleration (decode-encode method).
    This method is frame-accurate.
    If total_frames is not provided, it will be calculated using a slow but accurate method.
    """
    if total_frames == 0:
        print("`total_frames` not provided, calculating accurately (this may be slow)...")
        video_info = get_video_info_accurate(video_path)
        if not video_info or video_info['frame_count'] == 0:
            print(f"Could not get valid video info for {video_path}")
            return []
        total_frames = video_info['frame_count']

    os.makedirs(output_dir, exist_ok=True)

    frames_per_split = math.ceil(total_frames / num_splits)
    video_path_obj = Path(video_path)
    
    commands = []
    split_parts_info = []

    for i in range(num_splits):
        start_frame = i * frames_per_split
        end_frame = min((i + 1) * frames_per_split - 1, total_frames - 1)
        
        if start_frame >= total_frames:
            continue

        output_filename = f"{video_path_obj.stem}_part_{i+1}{video_path_obj.suffix}"
        output_path = os.path.join(output_dir, output_filename)
        
        part_info = {
            'path': output_path,
            'expected_frames': (end_frame - start_frame + 1)
        }
        split_parts_info.append(part_info)

        command = [
            'ffmpeg',
            '-hide_banner',
            '-y',
            '-hwaccel', 'cuda',
            '-c:v', 'h264_cuvid',
            '-i', video_path,
            '-vf', f"select='between(n,{start_frame},{end_frame})',setpts=PTS-STARTPTS",
            '-c:v', 'h264_nvenc',
            '-preset:v', 'p1',       # 使用最快的预设 (p1=fastest)
            '-cq:v', '30',          # 使用较低的质量设置 (Constant Quality, 值越高速度越快)
            '-an',
            output_path
        ]
        commands.append(command)

    successful_splits = []
    with ThreadPoolExecutor(max_workers=num_splits) as executor:
        future_to_index = {executor.submit(run_ffmpeg_command, cmd): i for i, cmd in enumerate(commands)}
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            part_info = split_parts_info[index]
            try:
                success, output = future.result()
                if success:
                    successful_splits.append(part_info)
                else:
                    print(f"Failed to split part to {part_info['path']}. Error:\n{output}")
            except Exception as exc:
                print(f"Command for {part_info['path']} generated an exception: {exc}")

    return sorted(successful_splits, key=lambda x: x['path'])