# -*- coding: utf-8 -*- 

import subprocess
import json
import math
import os
import re
import shutil
import time
import multiprocessing
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_video_info(video_path: str) -> dict:
    """
    (首选方法) 使用 MediaInfo 和 ffprobe 快速、准确地获取视频信息。

    此函数结合了两个工具的优点：
    - 使用 MediaInfo 获取总帧数，因为它通常比 FFmpeg 的 `-vcodec copy` 方法更快、更准确，
      特别是对于没有精确帧数元数据的视频文件。
    - 使用 ffprobe 获取视频时长，这是一个标准且可靠的方法。

    请确保 'mediainfo' 和 'ffprobe' 已在环境中安装并添加到系统的 PATH 环境变量中。

    :param video_path: 视频文件的绝对路径。
    :return: 一个包含 'frame_count' (总帧数) 和 'duration' (时长, 秒) 的字典。
             如果任一工具执行失败或找不到，可能会返回部分信息或 None。
    """
    # 1. 使用 MediaInfo 获取帧数
    frame_count = 0
    try:
        # 构建 mediainfo 命令，只输出视频流的 FrameCount 字段
        command = ['mediainfo', '--Output=Video;%FrameCount%', video_path]
        # 执行命令，设置10秒超时
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=10)
        # 将输出的字符串转换为整数
        frame_count = int(result.stdout.strip())
    except FileNotFoundError:
        # 如果系统找不到 mediainfo 命令
        print("错误: 'mediainfo' 命令未找到。请确保它已安装并在系统的 PATH 中。")
        return None
    except (subprocess.CalledProcessError, ValueError) as e:
        # 如果命令执行出错或输出无法转换为整数
        print(f"使用 mediainfo 获取帧数失败: {e}")
        pass  # 即使获取帧数失败，也继续尝试获取时长

    # 2. 使用 ffprobe 获取时长
    duration = 0.0
    try:
        # 构建 ffprobe 命令，只输出格式信息中的 duration 字段
        command = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', video_path
        ]
        # 执行命令，设置10秒超时
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=10)
        # 将输出的字符串转换为浮点数
        duration = float(result.stdout.strip())
    except FileNotFoundError:
        # 如果系统找不到 ffprobe 命令
        print("错误: 'ffprobe' 命令未找到。请确保它已安装并在系统的 PATH 中。")
        return None
    except (subprocess.CalledProcessError, ValueError) as e:
        # 如果命令执行出错或输出无法转换为浮点数
        print(f"使用 ffprobe 获取时长失败: {e}")
        if frame_count == 0:  # 如果帧数和时长都获取失败，则返回 None
            return None

    # 返回包含帧数和时长的字典
    return {
        'frame_count': frame_count,
        'duration': duration
    }

def split_video_fast(video_path: str, output_dir: str, num_splits: int) -> list:
    """
    (快速分割) 使用 ffmpeg 的流复制模式 (`-c copy`) 快速将视频分割成多个部分。

    这种方法非常快，因为它不进行重新编码，直接复制视频流。但缺点是分割点可能不精确，
    因为它只能在视频的关键帧 (I-frame) 处进行分割。

    :param video_path: 原始视频文件的路径。
    :param output_dir: 存放分割后视频片段的目录。
    :param num_splits: 要将视频分割成的份数。
    :return: 一个包含所有成功生成的视频片段路径的列表。
    """
    # 获取视频信息，特别是时长
    video_info = get_video_info(video_path)
    if not video_info or video_info['duration'] == 0:
        print(f"无法获取视频 '{video_path}' 的时长信息，分割失败。")
        return []

    total_duration = video_info['duration']
    # 计算每个分段的大致时长
    segment_duration = total_duration / num_splits

    # 如果输出目录已存在，则清空它，以防旧文件干扰
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    # 定义输出文件的命名格式，例如 segment_001.mp4, segment_002.mp4 ...
    output_pattern = os.path.join(output_dir, 'segment_%03d.mp4')
    
    # 构建 ffmpeg 命令
    command = [
        'ffmpeg',
        '-y',  # 覆盖已存在的文件
        '-i', video_path,  # 输入文件
        '-c', 'copy',  # 使用流复制模式，不重新编码
        '-map', '0',  # 映射所有流（视频、音频等）
        '-f', 'segment',  # 使用 segment muxer
        '-segment_time', str(segment_duration),  # 设置每个分段的时长
        '-reset_timestamps', '1',  # 重置每个分段的时间戳，使其从0开始
        output_pattern  # 输出文件格式
    ]

    try:
        # 执行命令，设置5分钟超时
        subprocess.run(command, capture_output=True, text=True, check=True, timeout=300)
        # 收集所有生成的文件路径并返回
        generated_files = [os.path.join(output_dir, f) for f in sorted(os.listdir(output_dir)) if f.startswith('segment_')]
        return generated_files
    except subprocess.CalledProcessError as e:
        # 如果 ffmpeg 执行失败
        print(f"""错误：ffmpeg 快速分割失败。\nFFmpeg Stderr: {e.stderr.strip()} """ )
        return []
    except FileNotFoundError:
        # 如果找不到 ffmpeg 命令
        print("错误: 'ffmpeg' 命令未找到。请确保它已安装并在系统的 PATH 中。")
        return []

# 必须在顶层定义，以便多进程模块 (multiprocessing) 可以序列化 (pickle) 它
def _decode_worker(args):
    """
    解码单个视频文件到帧图片的工作进程函数。
    此函数被 `decode_videos_to_frames_concurrently` 并发调用。

    :param args: 一个元组，包含 (video_path, output_dir, start_frame, process_index)。
    :return: 一个包含解码结果和性能数据的字典。
    """
    video_path, output_dir, start_frame, process_index = args
    start_time = time.perf_counter()  # 记录开始时间
    
    # 定义输出帧的文件名格式，例如 00000001.jpg, 00000002.jpg ...
    # %08d 表示8位零填充的十进制数
    output_pattern = os.path.join(output_dir, '%08d.jpg')
    
    # 构建 ffmpeg 解码命令
    command = [
        'ffmpeg',
        '-hide_banner',  # 隐藏 ffmpeg 的版本和编译信息
        '-hwaccel', 'cuda',  # 使用 NVIDIA CUDA 进行硬件加速
        '-c:v', 'h264_cuvid',  # 指定使用 h264_cuvid 解码器
        '-i', video_path,  # 输入视频文件
        '-start_number', str(start_frame),  # 设置输出图片文件的起始编号
        '-f', 'image2',  # 指定输出格式为图片序列
        output_pattern  # 输出文件格式
    ]
    
    success = False
    error_message = ""
    try:
        # 执行解码命令，设置5分钟超时
        subprocess.run(command, capture_output=True, text=True, check=True, timeout=300)
        success = True
    except subprocess.CalledProcessError as e:
        # 如果 ffmpeg 返回非零退出码
        error_message = e.stderr.strip()
    except Exception as e:
        # 捕获其他可能的异常，如超时
        error_message = str(e)
        
    end_time = time.perf_counter()  # 记录结束时间
    duration = end_time - start_time  # 计算耗时
    
    # 返回该进程的执行结果
    return {
        'process_index': process_index,  # 进程编号
        'video_path': os.path.basename(video_path),  # 被解码的视频文件名
        'duration': duration,  # 耗时
        'success': success,  # 是否成功
        'error': error_message  # 错误信息（如果有）
    }

def decode_videos_to_frames_concurrently(video_paths: list, output_dir: str, process_count: int = None) -> dict:
    """
    使用多进程并发地将一系列视频文件解码为全局连续编号的图片帧。

    这个函数协调整个解码流程：
    1. 清理输出目录。
    2. 并发获取所有视频片段的帧数信息。
    3. 根据每个片段的帧数，计算出每个解码任务的全局起始帧编号。
    4. 使用多进程池 (`multiprocessing.Pool`) 并发执行解码任务。
    5. 收集并返回所有任务的结果和总体性能数据。

    :param video_paths: 要解码的视频文件路径列表 (通常是分割后的小视频片段)。
    :param output_dir: 存放解码后图片帧的根目录。
    :param process_count: 使用的并发进程数。如果为 None，则默认为系统的 CPU 核心数。
    :return: 一个包含详细解码结果、总耗时和总解码帧数的字典。
    """
    if not video_paths:
        return {'results': [], 'total_time': 0, 'total_frames_decoded': 0}

    # 1. 清理并创建输出目录
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    # 2. 并发获取所有视频的帧数信息
    # 使用线程池来执行 I/O 密集型的 get_video_info 函数，这样比串行执行快得多
    print("--- 并发获取所有子视频的帧数信息 ---")
    with ThreadPoolExecutor() as executor:
        # 创建一个 future 到路径的映射，方便后续获取结果
        future_to_path = {executor.submit(get_video_info, path): path for path in video_paths}
        video_infos = []
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                info = future.result()
                if info:
                    video_infos.append({'path': path, 'frame_count': info['frame_count']})
                else:
                    video_infos.append({'path': path, 'frame_count': 0}) # 如果获取失败，帧数记为0
            except Exception as exc:
                print(f"获取 '{path}' 信息时出错: {exc}")
                video_infos.append({'path': path, 'frame_count': 0})
    
    # 创建一个从路径到帧数的映射，并按原始 video_paths 列表的顺序重新排序信息
    # 这确保了后续计算起始帧编号的顺序是正确的
    info_map = {info['path']: info['frame_count'] for info in video_infos}
    sorted_infos = [(path, info_map.get(path, 0)) for path in video_paths]

    # 3. 准备每个解码任务的参数 (包括计算全局起始帧编号)
    tasks = []
    current_frame_start = 1  # 全局帧编号从 1 开始
    for i, (path, frame_count) in enumerate(sorted_infos):
        # 每个任务的参数是 (视频路径, 输出目录, 起始帧号, 进程索引)
        tasks.append((path, output_dir, current_frame_start, i + 1))
        # 累加当前视频的帧数，为下一个视频计算起始帧号
        current_frame_start += frame_count

    # 4. 使用多进程池执行解码
    # `process_count` 为 None 时，`multiprocessing.Pool` 会自动使用 `os.cpu_count()`
    print(f"--- 使用 {process_count or '默认'} 个进程并发解码... ---")
    total_start_time = time.perf_counter()
    
    # 创建进程池
    pool = multiprocessing.Pool(processes=process_count)
    # `map` 方法会将 `tasks` 列表中的每个元素作为参数传递给 `_decode_worker` 函数
    # 这是一个阻塞操作，会等待所有进程完成
    results = pool.map(_decode_worker, tasks)
    pool.close()  # 关闭进程池，不再接受新任务
    pool.join()   # 等待所有子进程退出
    
    total_end_time = time.perf_counter()
    total_duration = total_end_time - total_start_time

    # 5. 统计最终结果
    # 统计输出目录中实际生成的 .jpg 文件数量，作为验证
    total_frames_in_dir = len([name for name in os.listdir(output_dir) if name.endswith('.jpg')])

    # 返回包含所有信息的汇总字典
    return {
        'results': results,  # 每个解码进程的返回结果列表
        'total_time': total_duration,  # 解码总耗时
        'total_frames_in_dir': total_frames_in_dir  # 最终在目录中的总帧数
    }


def run_ffmpeg_command(command: list):
    """
    一个通用的辅助函数，用于执行一个 FFmpeg 命令并捕获其输出。

    :param command: 一个包含 ffmpeg 命令及其参数的列表。
    :return: 一个元组 (success, output)，其中 success 是布尔值，output 是 stderr 的内容。
    """
    try:
        # 运行命令，如果返回非零退出码，`check=True` 会抛出 CalledProcessError
        process = subprocess.run(command, capture_output=True, text=True, check=True)
        return True, process.stderr  # 成功时返回 True 和 stderr (ffmpeg 常把信息输出到 stderr)
    except subprocess.CalledProcessError as e:
        # 失败时构造详细的错误信息
        error_message = f"FFmpeg command failed with exit code {e.returncode}\n"
        error_message += f"Stdout:\n{e.stdout}\n"
        error_message += f"Stderr:\n{e.stderr}"
        return False, error_message

def decode_and_count_frames_gpu(video_path: str) -> (int, float):
    """
    (已弃用/备用) 使用GPU解码视频到null输出，并从stderr中解析帧数。

    这种方法通过将视频解码到 `/dev/null` (或等效的 null 输出) 来模拟解码过程，
    然后从 ffmpeg 的日志输出中提取最终的帧数。这比完整解码要快，但不如 `mediainfo` 精确和高效。

    :param video_path: 视频文件的路径。
    :return: 解码的总帧数。
    """
    command = [
        'ffmpeg', '-hide_banner',
        '-hwaccel', 'cuda', '-c:v', 'h264_cuvid',  # GPU 加速解码
        '-i', video_path,
        '-f', 'null', '-'  # 输出到 null 设备，不写入文件
    ]
    success, stderr_output = run_ffmpeg_command(command)
    if not success:
        print(f"Failed to decode {video_path}. Error:\n{stderr_output}")
        return 0
    
    # 使用正则表达式从 ffmpeg 的 stderr 输出中查找 "frame= xxx" 这样的行
    frame_matches = re.findall(r'frame=\s*(\d+)', stderr_output)
    # 取最后一个匹配项，因为它代表解码结束时的总帧数
    decoded_frames = int(frame_matches[-1]) if frame_matches else 0
    return decoded_frames

def split_video_by_gpu(video_path: str, output_dir: str, num_splits: int = 10, total_frames: int = 0) -> list:
    """
    (精确分割) 使用 FFmpeg 和 GPU 加速进行解码和重新编码来精确分割视频。

    这种方法通过选择精确的帧范围 (`-vf select`) 并重新编码来创建分段。
    优点是分割点非常精确（精确到帧），缺点是速度比流复制慢，因为它需要重新编码。
    整个过程利用 GPU 加速 (解码 `h264_cuvid` 和编码 `h264_nvenc`) 来提高效率。

    :param video_path: 原始视频文件的路径。
    :param output_dir: 存放分割后视频片段的目录。
    :param num_splits: 要分割成的份数。
    :param total_frames: 视频的总帧数。如果提供，可以避免再次计算，提高效率。
    :return: 一个包含成功分割的片段信息的列表，每个元素是一个字典。
    """
    if total_frames == 0:
        video_info = get_video_info(video_path)
        if not video_info or video_info['frame_count'] == 0:
            print(f"无法获取视频 '{video_path}' 的有效信息，分割失败。")
            return []
        total_frames = video_info['frame_count']

    os.makedirs(output_dir, exist_ok=True)

    # 计算每个分段应包含的帧数
    frames_per_split = math.ceil(total_frames / num_splits)
    video_path_obj = Path(video_path)
    
    commands = []
    split_parts_info = []

    # 为每个分段生成对应的 ffmpeg 命令
    for i in range(num_splits):
        start_frame = i * frames_per_split
        # 确保结束帧不会超过总帧数
        end_frame = min((i + 1) * frames_per_split - 1, total_frames - 1)
        
        # 如果计算出的起始帧已经超出了视频总帧数，则停止创建更多分段
        if start_frame >= total_frames:
            continue

        output_filename = f"{video_path_obj.stem}_part_{i+1}{video_path_obj.suffix}"
        output_path = os.path.join(output_dir, output_filename)
        
        # 存储每个分段的元信息，用于后续验证
        part_info = {
            'path': output_path,
            'expected_frames': (end_frame - start_frame + 1)
        }
        split_parts_info.append(part_info)

        # 构建精确分割和重编码的 ffmpeg 命令
        command = [
            'ffmpeg', '-hide_banner', '-y',
            '-hwaccel', 'cuda', '-c:v', 'h264_cuvid',  # GPU 解码
            '-i', video_path,
            # 使用视频滤镜（vf）选择指定范围的帧
            # `select` 用于选择帧，`setpts` 用于重置时间戳，确保分段从0开始播放
            '-vf', f"select='between(n,{start_frame},{end_frame})',setpts=PTS-STARTPTS",
            '-c:v', 'h264_nvenc',  # 使用 NVIDIA GPU 编码器
            '-preset:v', 'p1',  # p1 是最快的预设，质量较低
            '-cq:v', '30',  # 设置恒定质量因子，数值越大，压缩率越高，质量越低
            '-an',  # 去除音频流
            output_path
        ]
        commands.append(command)

    successful_splits = []
    # 使用线程池并发执行所有分割命令
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

    # 按路径排序后返回成功分割的列表
    return sorted(successful_splits, key=lambda x: x['path'])

# --- 新增并发解码函数 ---

def _decode_concurrently_worker(args):
    """
    为 decode_video_concurrently 解码单个视频文件到帧图片的工作进程函数。
    此函数必须在模块顶层定义，以便多进程可以序列化它。
    支持裁剪。

    :param args: 一个元组，包含 (video_path, output_dir, start_frame, crop_filter, process_index)。
    :return: 一个包含解码结果和性能数据的字典。
    """
    video_path, output_dir, start_frame, crop_filter, process_index = args
    start_time = time.perf_counter()
    
    # 直接将帧输出到最终的 frames 目录
    frames_dir = os.path.join(output_dir, 'frames')
    output_pattern = os.path.join(frames_dir, '%08d.jpg')
    
    # 构建 ffmpeg 命令
    command = [
        'ffmpeg',
        '-hide_banner',
        '-hwaccel', 'cuda',
        '-c:v', 'h264_cuvid',  # <-- [修复] 明确指定CUDA解码器
        '-i', video_path,
        '-start_number', str(start_frame),
        '-q:v', '2',  # 使用 -q:v 2 (或 -qscale:v 2) 来保证高质量JPG输出
    ]

    # 如果提供了裁剪过滤器，则添加到命令中
    if crop_filter:
        command.extend(['-vf', crop_filter])

    command.extend(['-f', 'image2', output_pattern])
    
    success = False
    error_message = ""
    try:
        # 执行解码命令，设置超时，并捕获输出
        # 使用 text=True 和正确的编码来避免解码错误
        subprocess.run(command, capture_output=True, text=True, check=True, timeout=300, encoding='utf-8', errors='ignore')
        success = True
    except subprocess.CalledProcessError as e:
        # 如果 ffmpeg 返回非零退出码
        error_message = e.stderr.strip()
    except Exception as e:
        # 捕获其他可能的异常，如超时
        error_message = str(e)
        
    end_time = time.perf_counter()
    duration = end_time - start_time
    
    # 返回该进程的执行结果
    return {
        'process_index': process_index,
        'video_path': os.path.basename(video_path),
        'duration': duration,
        'success': success,
        'error': error_message
    }

def decode_video_concurrently(video_path: str, output_dir: str, num_processes: int = 10, crop_area: list = None):
    """
    将指定视频分割并进行多进程并发解码, 保存相应的视频帧截图。

    功能流程:
    1. 获取视频信息 (时长、总帧数)。
    2. 将视频快速分割成指定数量的子视频片段。
    3. 多进程并发解码子视频，支持对帧进行区域裁剪。
    4. 保存视频信息和任务执行数据到 task.json。
    5. 在 `output_dir` 下创建 `frames` (保存图片) 和 `segments` (保存子视频) 目录。

    :param video_path: [str] 需要解码的视频文件路径; 必填项。
    :param output_dir: [str] 保存解码结果的目录; 必填项。
    :param num_processes: [int] 并发解码的进程数量, 也是视频分割的数量; 默认: 10。
    :param crop_area: [list] 视频帧截取的区域数据. 默认: 空; 格式: [x1, y1, x2, y2]。
    :return: [dict] 任务信息, 格式: {"status": bool, "msg": str}。
    """
    total_start_time = time.time()
    logging.info(f"开始视频并发解码任务: {video_path}")
    num_processes = min(10, num_processes)
    
    # 1. 准备目录
    frames_dir = os.path.join(output_dir, "frames")
    segments_dir = os.path.join(output_dir, "segments")
    # 清理可能存在的旧文件
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(frames_dir)
    os.makedirs(segments_dir)
    logging.info(f"输出目录已创建并清理: {output_dir}")

    task_data = {
        "video_path": video_path,
        "output_dir": output_dir,
        "num_processes": num_processes,
        "crop_area": crop_area,
        "decoding_stats": [],
    }

    # 2. 获取视频信息
    logging.info("正在获取视频信息...")
    video_info = get_video_info(video_path)
    if not video_info or not video_info.get('duration') or not video_info.get('frame_count'):
        msg = "获取视频信息失败，任务终止。"
        logging.error(msg)
        return {"status": False, "msg": msg}
    
    task_data.update({
        'total_frames': video_info['frame_count'],
        'total_duration': video_info['duration']
    })
    logging.info(f"视频信息获取成功: 总时长={task_data['total_duration']:.2f}s, 总帧数={task_data['total_frames']}")

    # 3. 快速视频分割
    logging.info(f"正在将视频快速分割成 {num_processes} 段...")
    split_start_time = time.time()
    
    # 使用项目内已有的 split_video_fast 函数进行分割
    segments = split_video_fast(video_path, segments_dir, num_processes)
    
    if not segments:
        msg = "视频分割失败。"
        logging.error(msg)
        return {"status": False, "msg": msg}

    split_duration = time.time() - split_start_time
    task_data['split_duration'] = split_duration
    logging.info(f"视频分割成功，耗时: {split_duration:.2f} 秒，生成 {len(segments)} 个片段。")

    # 4. 并发获取各片段帧数以计算偏移量
    logging.info("正在并发获取所有子视频的帧数信息...")
    with ThreadPoolExecutor() as executor:
        future_to_path = {executor.submit(get_video_info, path): path for path in segments}
        info_map = {}
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                info = future.result()
                info_map[path] = info['frame_count'] if info else 0
            except Exception as e:
                logging.warning(f"获取片段 '{os.path.basename(path)}' 信息时出错: {e}")
                info_map[path] = 0
    
    # 保证分段信息与分段文件列表的顺序一致
    sorted_infos = [(path, info_map.get(path, 0)) for path in segments]

    # 5. 准备并发解码任务
    crop_filter = None
    if crop_area and len(crop_area) == 4:
        x1, y1, x2, y2 = crop_area
        width = x2 - x1
        height = y2 - y1
        crop_filter = f"crop={width}:{height}:{x1}:{y1}"
        logging.info(f"将应用裁剪区域: {crop_filter}")

    tasks = []
    current_frame_start = 1  # 帧编号从 1 开始
    for i, (path, frame_count) in enumerate(sorted_infos):
        # 如果一个片段的帧数为0，则跳过，不为其创建解码任务
        if frame_count > 0:
            tasks.append((path, output_dir, current_frame_start, crop_filter, i + 1))
            current_frame_start += frame_count

    # 6. 执行并发解码
    logging.info(f"准备就绪，开始使用 {len(tasks)} 个进程进行并发解码...")
    decoding_start_time = time.time()
    
    with multiprocessing.Pool(processes=num_processes) as pool:
        results = pool.map(_decode_concurrently_worker, tasks)

    decoding_duration = time.time() - decoding_start_time
    task_data['decoding_duration'] = decoding_duration
    task_data['decoding_stats'] = results
    logging.info(f"所有解码任务完成，总耗时: {decoding_duration:.2f} 秒")

    # 7. 保存任务信息
    total_task_duration = time.time() - total_start_time
    task_data['total_task_duration'] = total_task_duration
    
    task_json_path = os.path.join(output_dir, "task.json")
    try:
        with open(task_json_path, 'w', encoding='utf-8') as f:
            json.dump(task_data, f, ensure_ascii=False, indent=4)
        logging.info(f"任务信息已保存到: {task_json_path}")
    except IOError as e:
        msg = f"保存 task.json 失败: {e}"
        logging.error(msg)
        return {"status": False, "msg": msg}

    # 检查是否有失败的解码任务
    if any(not r['success'] for r in results):
        msg = "一个或多个解码任务失败，请检查日志和 task.json 获取详细信息。"
        logging.warning(msg)
        return {"status": False, "msg": msg}

    msg = f"视频并发解码任务成功完成。任务耗时: {total_task_duration}"
    logging.info(msg)
    return {"status": True, "msg": msg}
