# pipeline/modules/change_detector.py
import torch
import numpy as np
import cv2
from typing import List, Tuple

from .decoder import GPUDecoder

class ChangeDetector:
    """
    通过dHash和像素标准差的混合方法，高效检测字幕变化的关键帧。
    """
    def __init__(self, config):
        self.config = config
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        
        # dHash配置
        self.hash_size = config.get('dhash_size', 8)
        
        # 变化检测阈值
        self.hamming_threshold = config.get('hamming_threshold', 3)
        
        print("模块: 变化检测器已加载。")

    def find_key_frames(self, video_path: str, decoder: GPUDecoder, subtitle_area: Tuple[int, int, int, int]) -> List[int]:
        """
        执行变化检测，找出所有关键帧的索引。

        Args:
            video_path (str): 视频文件的路径。
            decoder (GPUDecoder): 解码器实例。
            subtitle_area (Tuple[int, int, int, int]): 字幕区域 (x1, y1, x2, y2)。

        Returns:
            List[int]: 包含所有关键帧帧号的列表。
        """
        print("开始检测字幕变化关键帧...")
        x1, y1, x2, y2 = subtitle_area

        # 1. 批量计算所有帧的dHash和标准差
        all_hashes, all_stds = self._compute_metrics_for_all_frames(video_path, decoder, (x1, y1, x2, y2))
        print(f"已计算 {len(all_hashes)} 帧的dHash和标准差。")

        # 2. 使用大津法自动确定空白帧阈值
        blank_threshold = self._get_otsu_threshold(all_stds)
        print(f"通过大津法自动确定空白帧标准差阈值: {blank_threshold:.4f}")

        # 3. 找出所有变化点
        key_frame_indices = self._detect_change_points(all_hashes, all_stds, blank_threshold)
        print(f"检测到 {len(key_frame_indices)} 个关键帧。")

        return key_frame_indices

    def _compute_metrics_for_all_frames(self, video_path: str, decoder: GPUDecoder, crop_rect: Tuple[int, int, int, int]) -> Tuple[List[np.ndarray], np.ndarray]:
        """在GPU上批量计算所有帧的指标"""
        all_hashes = []
        all_stds = []
        x1, y1, x2, y2 = crop_rect

        for batch_tensor, _ in decoder.decode(video_path):
            # 裁剪字幕区域
            cropped_batch = batch_tensor[:, :, y1:y2, x1:x2]

            # --- 在GPU上批量计算 --- #
            # 1. 计算标准差
            # 将Tensor展平为 (batch_size, num_pixels), 然后计算标准差
            stds = torch.std(cropped_batch.float().view(cropped_batch.size(0), -1), dim=1)
            all_stds.extend(stds.cpu().numpy())

            # 2. 计算dHash
            # 灰度化: (R+G+B)/3
            grayscale_batch = cropped_batch.float().mean(dim=1, keepdim=True)
            # 缩放至 (hash_size + 1, hash_size)
            resized_batch = torch.nn.functional.interpolate(grayscale_batch, size=(self.hash_size, self.hash_size + 1), mode='bilinear', align_corners=False)
            # 计算差异: 左边的像素是否比右边的大
            diff = resized_batch[:, :, :, 1:] > resized_batch[:, :, :, :-1]
            # 将布尔值转换为8位哈希
            hashes_np = diff.cpu().numpy().astype(np.uint8).reshape(diff.shape[0], -1)
            all_hashes.extend(hashes_np)
            
        return all_hashes, np.array(all_stds)

    def _get_otsu_threshold(self, stds: np.ndarray) -> float:
        """对标准差列表使用大津法（Otsu's method）找到最佳阈值"""
        # 大津法需要8位整数输入
        if stds.max() == stds.min(): return 0.0 # 避免全黑或全白视频出错
        stds_normalized = (255 * (stds - stds.min()) / (stds.max() - stds.min())).astype(np.uint8)
        threshold_otsu, _ = cv2.threshold(stds_normalized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # 将阈值转换回原始标准差的范围
        original_threshold = threshold_otsu / 255 * (stds.max() - stds.min()) + stds.min()
        return float(original_threshold)

    def _detect_change_points(self, hashes: List[np.ndarray], stds: np.ndarray, blank_threshold: float) -> List[int]:
        """根据哈希和标准差找出所有变化点"""
        key_indices = {0} # 第一帧总是关键帧
        is_blank_list = (stds < blank_threshold)

        for i in range(1, len(hashes)):
            # 1. 哈希值变化检测
            # 使用异或(XOR)计算汉明距离
            hamming_distance = np.count_nonzero(hashes[i-1] != hashes[i])
            if hamming_distance > self.hamming_threshold:
                key_indices.add(i)
                continue # 如果哈希变化剧烈，肯定是关键帧，无需后续判断
            
            # 2. 空白/非空白状态转换检测
            if is_blank_list[i] != is_blank_list[i-1]:
                key_indices.add(i)

        return sorted(list(key_indices))