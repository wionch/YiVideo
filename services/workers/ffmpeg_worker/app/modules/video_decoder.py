import subprocess
import json
import math
import os
import re
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_video_info(video_path: str) -> dict:
    """
    (首选方法) 使用 MediaInfo 和 ffprobe 快速、准确地获取视频信息。
    - 使用 MediaInfo 获取总帧数，速度极快且结果准确。
    - 使用 ffprobe 获取视频时长。
    请确保 'mediainfo' 和 'ffprobe' 已在环境中安装。
    """
    # 1. 使用 MediaInfo 获取帧数
    frame_count = 0
    try:
        command = ['mediainfo', '--Output=Video;%FrameCount%', video_path]
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=10)
        frame_count = int(result.stdout.strip())
    except FileNotFoundError:
        print("错误: 'mediainfo' 命令未找到。请确保它已安装并在系统的 PATH 中。")
        return None
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"使用 mediainfo 获取帧数失败: {e}")
        # 即使获取帧数失败，我们仍然可以继续尝试获取时长。
        pass

    # 2. 使用 ffprobe 获取时长
    duration = 0.0
    try:
        command = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', video_path
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=10)
        duration = float(result.stdout.strip())
    except FileNotFoundError:
        print("错误: 'ffprobe' 命令未找到。请确保它已安装并在系统的 PATH 中。")
        return None
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"使用 ffprobe 获取时长失败: {e}")
        # 如果两者都失败，则返回 None
        if frame_count == 0:
            return None

    return {
        'frame_count': frame_count,
        'duration': duration
    }

def split_video_fast(video_path: str, output_dir: str, num_splits: int) -> list:
    """
    (快速分割) 使用 ffmpeg 的流复制模式 (-c copy) 快速将视频分割成多个部分。
    这种方法非常快，因为它不进行重新编码，但分割点可能不是100%精确到帧。
    适用于对速度要求高、对分割精度要求不高的场景。
    """
    # 首先获取视频总时长，用于计算每个分段的长度
    video_info = get_video_info(video_path)
    if not video_info or video_info['duration'] == 0:
        print(f"无法获取视频 '{video_path}' 的时长信息，分割失败。")
        return []

    total_duration = video_info['duration']
    segment_duration = total_duration / num_splits

    # 清理并创建输出目录
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    output_pattern = os.path.join(output_dir, 'segment_%03d.mp4')
    
    command = [
        'ffmpeg',
        '-y',
        '-i', video_path,
        '-c', 'copy',
        '-map', '0',
        '-f', 'segment',
        '-segment_time', str(segment_duration),
        '-reset_timestamps', '1',
        output_pattern
    ]

    try:
        subprocess.run(command, capture_output=True, text=True, check=True, timeout=300) # 增加超时
        generated_files = [os.path.join(output_dir, f) for f in sorted(os.listdir(output_dir)) if f.startswith('segment_')]
        return generated_files
    except subprocess.CalledProcessError as e:
        print(f"错误：ffmpeg 快速分割失败。FFmpeg Stderr: {e.stderr.strip()}")
        return []
    except FileNotFoundError:
        print("错误: 'ffmpeg' 命令未找到。请确保它已安装并在系统的 PATH 中。")
        return []


def run_ffmpeg_command(command: list):
    """
    执行一个 FFmpeg 命令并捕获其输出。
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
    使用GPU解码视频到null输出，并从stderr中解析帧数。
    返回解码出的帧数。
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
    (精确分割) 使用 FFmpeg 和 GPU 加速进行解码和重新编码来分割视频。
    这种方法是帧精确的，但由于需要重新编码，速度比 `split_video_fast` 慢得多。
    适用于需要精确控制每个分片起始和结束帧的场景。
    """
    if total_frames == 0:
        print("警告: `total_frames` 未提供, 将使用 `get_video_info` 自动计算...")
        video_info = get_video_info(video_path)
        if not video_info or video_info['frame_count'] == 0:
            print(f"无法获取视频 '{video_path}' 的有效信息，分割失败。")
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
