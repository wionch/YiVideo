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
        except av.AVError as e:
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
                except (av.AVError, IndexError):
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