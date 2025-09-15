import subprocess
import json
import math
import os
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_video_info(video_path: str) -> dict:
    """
    Uses ffprobe to get video information like duration and frame count.
    """
    command = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-count_frames',
        '-show_entries', 'stream=nb_read_frames,duration',
        '-of', 'json',
        video_path
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)['streams'][0]
        return {
            'frame_count': int(info.get('nb_read_frames', 0)),
            'duration': float(info.get('duration', 0.0))
        }
    except (subprocess.CalledProcessError, json.JSONDecodeError, IndexError, KeyError) as e:
        print(f"Error getting video info for {video_path}: {e}")
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

def split_video_by_gpu(video_path: str, output_dir: str, num_splits: int = 4) -> list:
    """
    Splits a video into multiple parts using FFmpeg with GPU acceleration (decode-encode method).
    This method is frame-accurate.
    """
    video_info = get_video_info(video_path)
    if not video_info or video_info['frame_count'] == 0:
        print(f"Could not get valid video info for {video_path}")
        return []

    os.makedirs(output_dir, exist_ok=True)
    
    total_frames = video_info['frame_count']
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