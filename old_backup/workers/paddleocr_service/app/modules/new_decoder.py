# -*- coding: utf-8 -*-
import subprocess
import json
import os
from multiprocessing import Process, Queue
from typing import List, Callable

def get_video_info(video_path: str) -> dict:
    """
    获取视频信息，如帧数、时长、码率等。

    :param video_path: 视频文件路径。
    :return: 包含视频信息的字典。
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"视频文件未找到: {video_path}")

    command = [
        'ffprobe',
        '-v', 'error',
        '-count_frames', # 强制对每一帧进行计数以获得精确值
        '-select_streams', 'v:0',
        '-show_entries', 'stream=nb_read_frames,duration,width,height,avg_frame_rate',
        '-of', 'json',
        video_path
    ]
    
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)['streams'][0]
        
        # avg_frame_rate 是 'num/den' 格式, 我们需要计算它
        num, den = map(int, info['avg_frame_rate'].split('/'))
        info['fps'] = num / den if den != 0 else 0
        
        # ffprobe可能不直接提供总帧数，如果是，则使用 nb_read_frames
        if 'nb_read_frames' in info and info['nb_read_frames'] != 'N/A':
             info['total_frames'] = int(info['nb_read_frames'])
        else:
            # 如果无法直接读取帧数，则估算
            duration = float(info['duration'])
            info['total_frames'] = int(duration * info['fps'])

        return info
    except (subprocess.CalledProcessError, json.JSONDecodeError, IndexError) as e:
        print(f"获取视频信息失败: {e}")
        return {}

def split_video(video_path: str, num_splits: int, output_dir: str) -> List[str]:
    """
    将视频按指定数量分割成子视频，确保不丢帧。
    使用基于帧的分割来确保精度。

    :param video_path: 原始视频路径。
    :param num_splits: 要分割的数量。
    :param output_dir: 子视频保存目录。
    :return: 分割后的子视频路径列表。
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    video_info = get_video_info(video_path)
    total_frames = video_info.get('total_frames')

    if not total_frames:
        print("无法获取总帧数，无法分割视频。")
        return []

    frames_per_split = total_frames // num_splits
    remainder_frames = total_frames % num_splits
    
    split_points = []
    current_frame = 0
    for i in range(num_splits):
        start_frame = current_frame
        # 将余数帧平均分配给前面的分片
        num_frames_in_split = frames_per_split + (1 if i < remainder_frames else 0)
        split_points.append((start_frame, num_frames_in_split))
        current_frame += num_frames_in_split

    sub_video_paths = []
    base_name = os.path.splitext(os.path.basename(video_path))[0]

    for i, (start_frame, num_frames) in enumerate(split_points):
        output_filename = f"{base_name}_part_{i+1}.mp4"
        output_path = os.path.join(output_dir, output_filename)
        
        # 计算结束帧 (包含)
        end_frame = start_frame + num_frames - 1

        # 使用GPU加速的ffmpeg命令
        # -c:v h264_cuvid: 指定NVIDIA GPU解码器 (必须放在 -i 前面)
        # -vf ...: 在CPU上执行帧选择和时间戳重置
        # -c:v h264_nvenc: 指定NVIDIA GPU编码器
        command = [
            'ffmpeg',
            '-c:v', 'h264_cuvid', # 使用GPU解码
            '-i', video_path,
            '-vf', f"select='between(n,{start_frame},{end_frame})',setpts=PTS-STARTPTS",
            '-c:v', 'h264_nvenc', # 使用GPU编码
            '-an', # 根据需要可以移除此行以保留音频
            '-y', # 覆盖输出文件
            output_path
        ]
        
        print(f"正在执行分割: {' '.join(command)}")
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
            sub_video_paths.append(output_path)
        except subprocess.CalledProcessError as e:
            print(f"分割视频 part {i+1} 失败: {e.stderr}")
            return [] # 如果一个分片失败，则提前返回

    return sub_video_paths

import av

def split_video_pyav(video_path: str, num_splits: int, output_dir: str) -> List[str]:
    """
    使用 PyAV 将视频按指定数量分割成子视频，支持GPU和CPU编码fallback机制。

    :param video_path: 原始视频路径。
    :param num_splits: 要分割的数量。
    :param output_dir: 子视频保存目录。
    :return: 分割后的子视频路径列表。
    """ 
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    video_info = get_video_info(video_path)
    total_frames = video_info.get('total_frames')

    if not total_frames:
        print("无法获取总帧数，无法分割视频。")
        return []

    frames_per_split = total_frames // num_splits
    remainder_frames = total_frames % num_splits
    
    split_points = []
    current_frame = 0
    for i in range(num_splits):
        start_frame = current_frame
        num_frames_in_split = frames_per_split + (1 if i < remainder_frames else 0)
        end_frame = start_frame + num_frames_in_split
        split_points.append((start_frame, end_frame))
        current_frame = end_frame

    sub_video_paths = []
    base_name = os.path.splitext(os.path.basename(video_path))[0]

    # 尝试GPU解码，如果失败则fallback到CPU解码
    decoder_options = [
        {'c:v': 'h264_cuvid'},  # GPU解码
        {}  # CPU解码 (默认)
    ]
    
    # 尝试GPU编码，如果失败则fallback到CPU编码
    encoder_options = [
        ('h264_nvenc', 'GPU'),  # GPU编码
        ('libx264', 'CPU')      # CPU编码
    ]

    for decoder_opt in decoder_options:
        decoder_name = "GPU" if decoder_opt else "CPU"
        print(f"尝试使用 {decoder_name} 解码...")
        
        try:
            # 1. 打开输入容器
            with av.open(video_path, mode='r', options=decoder_opt) as input_container:
                input_stream = input_container.streams.video[0]
                
                # 2. 尝试不同的编码器
                for encoder_codec, encoder_name in encoder_options:
                    print(f"尝试使用 {encoder_name} 编码 ({encoder_codec})...")
                    
                    try:
                        # 重置路径列表
                        current_sub_video_paths = []
                        output_containers = []
                        
                        # 为每个分割点创建一个输出容器
                        for i, (start_frame, end_frame) in enumerate(split_points):
                            output_filename = f"{base_name}_pyav_part_{i+1}.mp4"
                            output_path = os.path.join(output_dir, output_filename)
                            current_sub_video_paths.append(output_path)
                            
                            output_container = av.open(output_path, mode='w')
                            output_stream = output_container.add_stream(encoder_codec, rate=input_stream.average_rate)
                            output_stream.width = input_stream.codec_context.width
                            output_stream.height = input_stream.codec_context.height
                            output_stream.pix_fmt = 'yuv420p'
                            output_containers.append(output_container)

                        # 3. 迭代帧并分配到正确的输出
                        frame_count = 0
                        current_split_index = 0
                        start_pts_of_current_split = None

                        for frame in input_container.decode(input_stream):
                            # 确定当前帧属于哪个分片
                            if frame_count >= split_points[current_split_index][1]:
                                current_split_index += 1
                                start_pts_of_current_split = None # 重置下一分片的起始PTS
                            
                            if current_split_index >= len(output_containers):
                                break # 所有分片都处理完了

                            # 获取当前分片对应的输出容器和流
                            output_container = output_containers[current_split_index]
                            output_stream = output_container.streams.video[0]

                            # 重置时间戳 (关键步骤)
                            if start_pts_of_current_split is None:
                                start_pts_of_current_split = frame.pts
                            
                            frame.pts -= start_pts_of_current_split
                            frame.dts -= start_pts_of_current_split

                            # 将帧编码并写入输出容器
                            for packet in output_stream.encode(frame):
                                output_container.mux(packet)
                            
                            frame_count += 1

                        # 4. 清理：刷新并关闭所有输出容器
                        for container in output_containers:
                            # 刷新编码器中剩余的帧
                            for packet in container.streams.video[0].encode():
                                container.mux(packet)
                            container.close()
                        
                        # 如果成功完成，返回结果
                        print(f"视频分割成功！使用了 {decoder_name} 解码 + {encoder_name} 编码")
                        return current_sub_video_paths
                        
                    except Exception as e:
                        print(f"使用 {encoder_name} 编码失败: {e}")
                        # 清理可能已创建的文件
                        for path in current_sub_video_paths:
                            if os.path.exists(path):
                                try:
                                    os.remove(path)
                                except:
                                    pass
                        # 尝试下一个编码器
                        continue
                
                # 如果所有编码器都失败了，尝试下一个解码器
                print(f"所有编码器在 {decoder_name} 解码下都失败了")
                continue
                
        except Exception as e:
            print(f"使用 {decoder_name} 解码失败: {e}")
            # 尝试下一个解码器
            continue
    
    print("所有 PyAV 解码/编码组合都失败了")
    return []




def manage_processes(task_list: List, num_processes: int, target_function: Callable):
    """
    使用生产者-消费者模式启动指定数量的进程来处理任务列表。

    :param task_list: 待处理的任务列表 (例如，视频片段路径列表)。
    :param num_processes: 要启动的进程数量。
    :param target_function: 每个进程要执行的目标函数，该函数应接受一个任务作为参数。
    """
    task_queue = Queue()
    for task in task_list:
        task_queue.put(task)

    # 添加哨兵值，用于告知工作进程任务已结束
    for _ in range(num_processes):
        task_queue.put(None)

    processes = []
    for _ in range(num_processes):
        p = Process(target=worker, args=(task_queue, target_function))
        processes.append(p)
        p.start()

    # 等待所有进程完成
    for p in processes:
        p.join()
    
    print("所有进程已完成任务。")
