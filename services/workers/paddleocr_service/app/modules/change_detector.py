# pipeline/modules/change_detector.py
import torch
import numpy as np
import cv2
from typing import List, Tuple
from enum import Enum, auto

from .decoder import GPUDecoder
from ..utils.progress_logger import create_stage_progress

class ChangeType(Enum):
    """
    定义关键帧的变化性质
    """
    TEXT_APPEARED = auto()      # 文本出现 (从无到有)
    TEXT_DISAPPEARED = auto()   # 文本消失 (从有到无)
    CONTENT_CHANGED = auto()    # 文本内容变化 (从有到有，但内容不同)

class ChangeDetector:
    """
    通过dHash和像素标准差的混合方法，高效检测字幕变化的关键帧及其变化类型。
    """
    def __init__(self, config):
        self.config = config
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        
        # dHash配置
        self.hash_size = config.get('dhash_size', 8)
        
        # 变化检测阈值
        self.hamming_threshold = config.get('hamming_threshold', 3)
        
        print("模块: 变化检测器已加载 (V2 - 事件驱动)。")

    def find_key_frames(self, video_path: str, decoder: GPUDecoder, subtitle_area: Tuple[int, int, int, int]) -> List[Tuple[int, ChangeType]]:
        """
        执行变化检测，找出所有关键帧的索引及其变化类型。

        Args:
            video_path (str): 视频文件的路径。
            decoder (GPUDecoder): 解码器实例。
            subtitle_area (Tuple[int, int, int, int]): 字幕区域 (x1, y1, x2, y2)。

        Returns:
            List[Tuple[int, ChangeType]]: 包含所有关键事件的列表 (帧号, 变化类型)。
        """
        print("🔍 开始分析字幕变化...")
        x1, y1, x2, y2 = subtitle_area

        # 1. 批量计算所有帧的dHash和标准差
        all_hashes, all_stds = self._compute_metrics_for_all_frames(video_path, decoder, (x1, y1, x2, y2))
        print(f"📊 完成特征计算: {len(all_hashes)} 帧")

        # 2. 使用大津法自动确定空白帧阈值
        blank_threshold = self._get_otsu_threshold(all_stds)
        print(f"🎯 空白帧阈值: {blank_threshold:.4f}")

        # 3. 找出所有变化点
        key_events = self._detect_change_points(all_hashes, all_stds, blank_threshold)
        
        print(f"✅ 检测到 {len(key_events)} 个关键变化事件")

        return key_events

    def _compute_metrics_for_all_frames(self, video_path: str, decoder: GPUDecoder, crop_rect: Tuple[int, int, int, int]) -> Tuple[List[np.ndarray], np.ndarray]:
        """在GPU上批量计算所有帧的指标"""
        all_hashes = []
        all_stds = []
        x1, y1, x2, y2 = crop_rect

        # 简单的计数器，不使用进度条（因为总帧数未知）
        frame_count = 0
        batch_count = 0
        
        print("🔄 正在计算视频特征...")
        
        for batch_tensor, _ in decoder.decode(video_path):
            # 裁剪字幕区域
            cropped_batch = batch_tensor[:, :, y1:y2, x1:x2]

            # --- 在GPU上批量计算 --- #
            # 1. 计算标准差
            stds = torch.std(cropped_batch.float().view(cropped_batch.size(0), -1), dim=1)
            all_stds.extend(stds.cpu().numpy())

            # 2. 计算dHash
            grayscale_batch = cropped_batch.float().mean(dim=1, keepdim=True)
            resized_batch = torch.nn.functional.interpolate(grayscale_batch, size=(self.hash_size, self.hash_size + 1), mode='bilinear', align_corners=False)
            diff = resized_batch[:, :, :, 1:] > resized_batch[:, :, :, :-1]
            hashes_np = diff.cpu().numpy().astype(np.uint8).reshape(diff.shape[0], -1)
            all_hashes.extend(hashes_np)
            
            frame_count += batch_tensor.size(0)
            batch_count += 1
            
            # 每50个batch显示一次进度
            if batch_count % 50 == 0:
                print(f"  📊 已处理 {frame_count} 帧...")
            
        print(f"✅ 特征计算完成: 共处理 {frame_count} 帧")
            
        return all_hashes, np.array(all_stds)

    def _get_otsu_threshold(self, stds: np.ndarray) -> float:
        """对标准差列表使用大津法（Otsu's method）找到最佳阈值"""
        if stds.max() == stds.min(): return 0.0
        stds_normalized = (255 * (stds - stds.min()) / (stds.max() - stds.min())).astype(np.uint8)
        threshold_otsu, _ = cv2.threshold(stds_normalized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        original_threshold = threshold_otsu / 255 * (stds.max() - stds.min()) + stds.min()
        return float(original_threshold)

    def _detect_change_points(self, hashes: List[np.ndarray], stds: np.ndarray, blank_threshold: float) -> List[Tuple[int, ChangeType]]:
        """根据哈希和标准差找出所有变化点事件"""
        key_events = []
        is_blank_list = (stds < blank_threshold)

        # 第0帧特殊处理
        if not is_blank_list[0]:
            key_events.append((0, ChangeType.TEXT_APPEARED))

        print(f"🔄 正在分析 {len(hashes)} 帧的变化点...")
        
        for i in range(1, len(hashes)):
            prev_is_blank = is_blank_list[i-1]
            curr_is_blank = is_blank_list[i]

            if prev_is_blank and not curr_is_blank:
                # 从无到有
                key_events.append((i, ChangeType.TEXT_APPEARED))
            elif not prev_is_blank and curr_is_blank:
                # 从有到无
                key_events.append((i, ChangeType.TEXT_DISAPPEARED))
            elif not prev_is_blank and not curr_is_blank:
                # 都是有，判断内容是否变化
                hamming_distance = np.count_nonzero(hashes[i-1] != hashes[i])
                if hamming_distance > self.hamming_threshold:
                    key_events.append((i, ChangeType.CONTENT_CHANGED))
            
            # 每1000帧显示一次进度
            if i % 1000 == 0:
                progress_percent = (i / len(hashes)) * 100
                print(f"  🔍 变化检测进度: {i}/{len(hashes)} ({progress_percent:.1f}%), 已找到 {len(key_events)} 个事件")
        
        print(f"✅ 变化检测完成，共找到 {len(key_events)} 个关键事件")
        
        return key_events
