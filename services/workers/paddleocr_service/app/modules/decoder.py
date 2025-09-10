# pipeline/modules/decoder.py
import av
import torch
import numpy as np
from typing import Generator, Tuple
import time
from ..utils.progress_logger import create_progress_bar

class GPUDecoder:
    """
    使用 PyAV 和 Torch 实现的高效视频解码器。
    它能将视频文件解码成一批批的 Torch Tensor，为后续的GPU处理做准备。
    """
    def __init__(self, config):
        self.config = config
        self.batch_size = config.get('batch_size', 32)
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"模块: GPU解码器已加载, 将在设备 {self.device} 上运行。")

    def decode(self, video_path: str, fps: int = None, log_progress=False) -> Generator[Tuple[torch.Tensor, np.ndarray], None, None]:
        """
        创建一个生成器，用于解码视频并按批次(batch)产生帧。

        Args:
            video_path (str): 视频文件的路径。
            fps (int, optional): 指定输出的帧率。如果为None，则使用视频的原始帧率。
            log_progress (bool): 是否打印解码进度日志。

        Yields:
            Generator[Tuple[torch.Tensor, np.ndarray], None, None]: 
            一个元组，包含 (批量帧的Tensor, 对应的时间戳Numpy数组)。
        """
        try:
            container = av.open(video_path)
            stream = container.streams.video[0]
            total_frames = stream.frames
            if total_frames == 0:
                total_frames = int(stream.duration * stream.time_base * stream.average_rate)
        except Exception as e:
            print(f"错误: 无法打开或解码视频文件: {video_path}. PyAV 错误: {e}")
            return

        stream.thread_type = "AUTO"

        if fps:
            resampler = av.VideoResampler(format='rgb24', width=stream.width, height=stream.height, rate=fps)
        else:
            resampler = None

        frames_buffer = []
        timestamps_buffer = []

        progress_bar = None
        if log_progress:
            progress_bar = create_progress_bar(total_frames, "视频解码", show_rate=True, show_eta=True)
        
        frame_count = 0
        batch_count = 0

        for frame in container.decode(stream):
            if resampler:
                try:
                    frame = resampler.resample(frame)[0]
                except (Exception, IndexError):
                    continue
            
            frame_np = frame.to_ndarray(format='rgb24')
            frames_buffer.append(torch.from_numpy(frame_np).permute(2, 0, 1))
            timestamps_buffer.append(frame.pts * stream.time_base)
            frame_count += 1

            # 每处理一帧就更新进度条
            if progress_bar:
                progress_bar.update(1)

            if len(frames_buffer) == self.batch_size:
                batch_tensor = torch.stack(frames_buffer).to(self.device, non_blocking=True)
                timestamps_np = np.array(timestamps_buffer, dtype=np.float64)
                yield batch_tensor, timestamps_np
                frames_buffer, timestamps_buffer = [], []
                batch_count += 1
            
        if frames_buffer:
            batch_tensor = torch.stack(frames_buffer).to(self.device, non_blocking=True)
            timestamps_np = np.array(timestamps_buffer, dtype=np.float64)
            yield batch_tensor, timestamps_np
        
        if progress_bar:
            progress_bar.finish(f"✅ 解码完成，总共 {frame_count} 帧")
        
        container.close()

    def sample_frames_precise(self, video_path: str, target_timestamps: list) -> list:
        """
        精准采样：使用seek定位到指定时间戳，只解码目标帧。
        
        Args:
            video_path (str): 视频文件路径
            target_timestamps (list): 目标时间戳列表（秒为单位）
            
        Returns:
            list: 采样得到的帧数据列表（numpy格式）
        """
        sampled_frames = []
        
        try:
            container = av.open(video_path)
            stream = container.streams.video[0]
            
            # 排序时间戳，优化seek效率
            sorted_timestamps = sorted(target_timestamps)
            
            for timestamp in sorted_timestamps:
                try:
                    # 精准定位到目标时间点 (修复API兼容性)
                    seek_target = int(timestamp / stream.time_base)
                    container.seek(seek_target, stream=stream)
                    
                    # 解码该时间点附近的帧
                    frame_found = False
                    for frame in container.decode(stream):
                        frame_time = frame.pts * stream.time_base
                        
                        # 找到最接近目标时间的帧
                        if abs(frame_time - timestamp) < 0.5:  # 0.5秒容差
                            frame_np = frame.to_ndarray(format='rgb24')
                            sampled_frames.append(frame_np)
                            frame_found = True
                            break
                    
                    if not frame_found:
                        print(f"警告: 无法在时间戳 {timestamp:.2f}s 附近找到有效帧")
                        
                except Exception as e:
                    print(f"警告: seek到时间戳 {timestamp:.2f}s 失败: {e}")
                    continue
            
            container.close()
            
        except Exception as e:
            print(f"错误: 无法打开视频文件 {video_path}: {e}")
            return []
        
        print(f"精准采样完成: 目标 {len(target_timestamps)} 帧，成功获取 {len(sampled_frames)} 帧")
        return sampled_frames

    def decode_gpu(self, video_path: str, fps: int = None, log_progress=False) -> Generator[Tuple[torch.Tensor, np.ndarray], None, None]:
        """
        使用GPU硬件解码器 (NVDEC) 进行视频解码，显著提升解码性能。
        
        Args:
            video_path (str): 视频文件的路径
            fps (int, optional): 指定输出的帧率。如果为None，则使用视频的原始帧率
            log_progress (bool): 是否打印解码进度日志
            
        Yields:
            Generator[Tuple[torch.Tensor, np.ndarray], None, None]: 
            一个元组，包含 (批量帧的GPU Tensor, 对应的时间戳Numpy数组)
        """
        if not torch.cuda.is_available():
            print("警告: CUDA不可用，回退到CPU软件解码")
            yield from self.decode(video_path, fps, log_progress)
            return
            
        try:
            # 尝试使用NVDEC硬件解码器
            container = av.open(video_path, options={
                'hwaccel': 'cuda',
                'hwaccel_device': '0',
                'hwaccel_output_format': 'cuda'
            })
            stream = container.streams.video[0]
            total_frames = stream.frames
            if total_frames == 0:
                total_frames = int(stream.duration * stream.time_base * stream.average_rate)
            print(f"✅ GPU硬件解码器已启用 (NVDEC)")
            
        except Exception as e:
            print(f"警告: GPU硬件解码初始化失败: {e}")
            print("回退到CPU软件解码")
            container.close() if 'container' in locals() else None
            yield from self.decode(video_path, fps, log_progress)
            return

        # 配置多线程解码
        stream.thread_type = "AUTO"

        # 设置重采样器（如果需要）
        if fps:
            resampler = av.VideoResampler(format='rgb24', width=stream.width, height=stream.height, rate=fps)
        else:
            resampler = None

        frames_buffer = []
        timestamps_buffer = []

        progress_bar = None
        if log_progress:
            progress_bar = create_progress_bar(total_frames, "GPU视频解码", show_rate=True, show_eta=True)
        
        frame_count = 0
        batch_count = 0

        try:
            for frame in container.decode(stream):
                # GPU硬件解码后的帧处理
                if resampler:
                    try:
                        frame = resampler.resample(frame)[0]
                    except (Exception, IndexError):
                        continue
                
                # 检查帧格式，如果是GPU格式需要特殊处理
                if hasattr(frame, 'to_rgb'):
                    # 对于GPU解码帧，先转换为标准格式
                    frame_np = frame.to_rgb().to_ndarray(format='rgb24')
                else:
                    # 标准帧处理
                    frame_np = frame.to_ndarray(format='rgb24')
                
                # 直接创建GPU tensor，避免CPU->GPU数据传输开销
                frame_tensor = torch.from_numpy(frame_np).permute(2, 0, 1).to(self.device, non_blocking=True)
                frames_buffer.append(frame_tensor)
                timestamps_buffer.append(frame.pts * stream.time_base)
                frame_count += 1

                # 更新进度条
                if progress_bar:
                    progress_bar.update(1)

                # 批次处理
                if len(frames_buffer) == self.batch_size:
                    batch_tensor = torch.stack(frames_buffer)
                    timestamps_np = np.array(timestamps_buffer, dtype=np.float64)
                    yield batch_tensor, timestamps_np
                    frames_buffer, timestamps_buffer = [], []
                    batch_count += 1
                
            # 处理剩余帧
            if frames_buffer:
                batch_tensor = torch.stack(frames_buffer)
                timestamps_np = np.array(timestamps_buffer, dtype=np.float64)
                yield batch_tensor, timestamps_np
            
            if progress_bar:
                progress_bar.finish(f"✅ GPU解码完成，总共 {frame_count} 帧，{batch_count + (1 if frames_buffer else 0)} 批次")
            
        except Exception as e:
            print(f"GPU解码过程中出错: {e}")
            if progress_bar:
                progress_bar.finish("❌ GPU解码中断")
        finally:
            container.close()

    def sample_frames_precise_gpu(self, video_path: str, target_timestamps: list) -> list:
        """
        使用GPU硬件解码器进行精准帧采样，提升采样性能。
        
        Args:
            video_path (str): 视频文件路径
            target_timestamps (list): 目标时间戳列表（秒为单位）
            
        Returns:
            list: 采样得到的帧数据列表（numpy格式）
        """
        if not torch.cuda.is_available():
            print("警告: CUDA不可用，使用CPU精准采样")
            return self.sample_frames_precise(video_path, target_timestamps)
            
        sampled_frames = []
        
        try:
            # 尝试使用GPU硬件解码
            container = av.open(video_path, options={
                'hwaccel': 'cuda',
                'hwaccel_device': '0',
                'hwaccel_output_format': 'cuda'
            })
            stream = container.streams.video[0]
            print(f"✅ GPU精准采样已启用")
            
        except Exception as e:
            print(f"警告: GPU精准采样初始化失败: {e}")
            print("回退到CPU精准采样")
            return self.sample_frames_precise(video_path, target_timestamps)
        
        try:
            # 排序时间戳，优化seek效率
            sorted_timestamps = sorted(target_timestamps)
            
            for timestamp in sorted_timestamps:
                try:
                    # 精准定位到目标时间点 (修复API兼容性)
                    seek_target = int(timestamp / stream.time_base)
                    container.seek(seek_target, stream=stream)
                    
                    # 解码该时间点附近的帧
                    frame_found = False
                    for frame in container.decode(stream):
                        frame_time = frame.pts * stream.time_base
                        
                        # 找到最接近目标时间的帧
                        if abs(frame_time - timestamp) < 0.5:  # 0.5秒容差
                            if hasattr(frame, 'to_rgb'):
                                # GPU解码帧处理
                                frame_np = frame.to_rgb().to_ndarray(format='rgb24')
                            else:
                                # 标准帧处理
                                frame_np = frame.to_ndarray(format='rgb24')
                            sampled_frames.append(frame_np)
                            frame_found = True
                            break
                    
                    if not frame_found:
                        print(f"警告: 无法在时间戳 {timestamp:.2f}s 附近找到有效帧")
                        
                except Exception as e:
                    print(f"警告: GPU seek到时间戳 {timestamp:.2f}s 失败: {e}")
                    continue
            
        except Exception as e:
            print(f"GPU精准采样过程中出错: {e}")
        finally:
            container.close()
        
        print(f"GPU精准采样完成: 目标 {len(target_timestamps)} 帧，成功获取 {len(sampled_frames)} 帧")
        return sampled_frames