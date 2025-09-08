# app/modules/keyframe_detector.py
import torch
import numpy as np
import cv2
from typing import List, Tuple, Dict
from .decoder import GPUDecoder

class KeyFrameDetector:
    """
    关键帧检测器 - 重构版本
    基于相似度的关键帧检测，替代原有的事件检测系统
    
    实现用户需求的关键帧逻辑:
    1. 第一帧默认为关键帧
    2. 逐帧比对: 1vs0, 2vs1, 3vs2...
    3. 相似度低于阈值 → 新关键帧
    """
    
    def __init__(self, config):
        self.config = config
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        
        # dHash配置
        self.hash_size = config.get('dhash_size', 8)
        
        # 相似度阈值配置 (新增，基于行业标准)
        self.similarity_threshold = config.get('similarity_threshold', 0.90)  # 90%默认
        
        # 从相似度换算汉明距离阈值
        max_bits = self.hash_size * self.hash_size
        self.hamming_threshold = int((1 - self.similarity_threshold) * max_bits)
        
        print(f"模块: 关键帧检测器已加载 (重构版本) - 相似度阈值: {self.similarity_threshold:.0%}, "
              f"汉明阈值: {self.hamming_threshold}")

    def detect_keyframes(self, video_path: str, decoder: GPUDecoder, 
                        subtitle_area: Tuple[int, int, int, int]) -> List[int]:
        """
        检测视频中所有关键帧 (原版本，不缓存)
        
        实现逻辑:
        1. 第一帧默认为关键帧
        2. 逐帧比对: 1vs0, 2vs1, 3vs2...
        3. 相似度低于阈值 → 新关键帧
        
        Args:
            video_path: 视频文件路径
            decoder: GPU解码器实例
            subtitle_area: 字幕区域坐标 (x1, y1, x2, y2)
            
        Returns:
            关键帧索引列表 [0, 45, 89, 156, ...]
        """
        keyframes, _ = self.detect_keyframes_with_cache(video_path, decoder, subtitle_area)
        return keyframes

    def detect_keyframes_with_cache(self, video_path: str, decoder: GPUDecoder, 
                                   subtitle_area: Tuple[int, int, int, int]) -> Tuple[List[int], Dict[int, np.ndarray]]:
        """
        检测视频中所有关键帧 + 同步缓存关键帧图像数据
        
        🆕 新增功能: 在关键帧检测过程中同步缓存关键帧的图像数据，
        避免后续OCR识别阶段的重复视频解码
        
        Args:
            video_path: 视频文件路径
            decoder: GPU解码器实例
            subtitle_area: 字幕区域坐标 (x1, y1, x2, y2)
            
        Returns:
            Tuple[List[int], Dict[int, np.ndarray]]: 
            - 关键帧索引列表 [0, 45, 89, ...]
            - 关键帧图像缓存 {0: image_array, 45: image_array, ...}
        """
        print("🔍 开始关键帧检测 (同步缓存模式)...")
        x1, y1, x2, y2 = subtitle_area

        # 1. 批量计算所有帧的特征 + 同步缓存
        all_hashes, all_stds, keyframe_cache = self._compute_frame_features_with_cache(
            video_path, decoder, (x1, y1, x2, y2)
        )
        print(f"📊 完成特征计算: {len(all_hashes)} 帧")

        # 2. 使用大津法确定空白帧阈值
        blank_threshold = self._get_otsu_threshold(all_stds)
        print(f"🎯 空白帧阈值: {blank_threshold:.4f}")

        # 3. 关键帧逐帧检测
        keyframes = self._detect_keyframes_sequential(all_hashes, all_stds, blank_threshold)
        
        # 4. 只保留检测到的关键帧缓存，释放其他缓存
        final_keyframe_cache = {k: keyframe_cache[k] for k in keyframes if k in keyframe_cache}
        
        # 5. 显示缓存统计信息
        cache_size_mb = len(final_keyframe_cache) * 0.307  # 每帧约307KB
        print(f"✅ 检测到 {len(keyframes)} 个关键帧")
        print(f"🗂️  关键帧缓存: {len(final_keyframe_cache)} 帧，约 {cache_size_mb:.1f}MB")
        
        return keyframes, final_keyframe_cache
    
    def _detect_keyframes_sequential(self, hashes: List[np.ndarray], 
                                   stds: np.ndarray, blank_threshold: float) -> List[int]:
        """
        按照新逻辑进行关键帧检测
        实现用户需求的具体算法
        """
        keyframes = []
        
        # 统计数据初始化
        similarity_stats = {
            'gte_80_percent': 0,  # >=80%的帧数
            'lt_80_percent': 0,   # <80%但>0%的帧数
            'zero_percent': 0     # 0%的帧数
        }
        
        # 1. 第一帧默认为关键帧
        keyframes.append(0)
        print(f"📌 关键帧 0: 默认第一帧")
        
        print(f"🔄 正在分析 {len(hashes)} 帧的相似度...")
        
        # 2. 从第1帧开始逐帧比对
        for curr_frame in range(1, len(hashes)):
            prev_frame = curr_frame - 1
            
            # 计算相似度
            similarity = self._calculate_similarity(
                hashes[prev_frame], hashes[curr_frame],
                stds[prev_frame], stds[curr_frame], 
                blank_threshold
            )
            
            # 统计相似度分布
            if similarity == 0.0:
                similarity_stats['zero_percent'] += 1
            elif similarity >= 0.80:
                similarity_stats['gte_80_percent'] += 1
            else:
                similarity_stats['lt_80_percent'] += 1
            
            # 3. 相似度低于阈值 → 新关键帧
            if similarity < self.similarity_threshold:
                keyframes.append(curr_frame)
            
            # 进度显示 (每1000帧更新一次)
            if curr_frame % 1000 == 0:
                progress = (curr_frame / len(hashes)) * 100
                print(f"  🔍 检测进度: {curr_frame}/{len(hashes)} ({progress:.1f}%) | "
                      f"相似度分布: >={int(0.8*100)}%帧:{similarity_stats['gte_80_percent']}/"
                      f"<{int(0.8*100)}%帧:{similarity_stats['lt_80_percent']}/"
                      f"0%帧:{similarity_stats['zero_percent']} | "
                      f"关键帧:{len(keyframes)}个")
        
        # 输出最终统计
        total_compared = len(hashes) - 1  # 第一帧不参与比较
        print(f"📊 相似度统计(总计{total_compared}帧): >={int(0.8*100)}%帧:{similarity_stats['gte_80_percent']}/"
              f"<{int(0.8*100)}%帧:{similarity_stats['lt_80_percent']}/0%帧:{similarity_stats['zero_percent']}")
        print(f"✅ 关键帧检测完成: 共找到 {len(keyframes)} 个关键帧")
        return keyframes
    
    def _calculate_similarity(self, hash1: np.ndarray, hash2: np.ndarray,
                            std1: float, std2: float, blank_threshold: float) -> float:
        """
        计算两帧之间的相似度
        
        相似度计算规则:
        - 空白帧 vs 空白帧: 100%
        - 空白帧 vs 内容帧: 0%  
        - 内容帧 vs 内容帧: 基于dHash的汉明距离
        
        基于行业标准Dr. Neal Krawetz的研究成果
        """
        # 判断帧类型
        is_blank1 = std1 < blank_threshold
        is_blank2 = std2 < blank_threshold
        
        # Case 1: 两帧都是空白帧 → 相似度100%
        if is_blank1 and is_blank2:
            return 1.0
        
        # Case 2: 一个空白一个非空白 → 相似度0% (完全不同)
        if is_blank1 != is_blank2:
            return 0.0
        
        # Case 3: 两帧都有内容 → 基于dHash计算相似度
        hamming_distance = np.count_nonzero(hash1 != hash2)
        max_possible_distance = hash1.size  # 64 for 8x8 dHash
        
        # 相似度 = 1 - (汉明距离 / 最大可能距离)
        similarity = 1.0 - (hamming_distance / max_possible_distance)
        
        return similarity
    
    def _compute_frame_features(self, video_path: str, decoder: GPUDecoder, 
                               crop_rect: Tuple[int, int, int, int]) -> Tuple[List[np.ndarray], np.ndarray]:
        """
        批量计算所有帧的dHash和标准差
        复用原有的GPU批量计算逻辑
        """
        all_hashes = []
        all_stds = []
        x1, y1, x2, y2 = crop_rect

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
            resized_batch = torch.nn.functional.interpolate(
                grayscale_batch, 
                size=(self.hash_size, self.hash_size + 1), 
                mode='bilinear', align_corners=False
            )
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
    
    def _compute_frame_features_with_cache(self, video_path: str, decoder: GPUDecoder, 
                                          crop_rect: Tuple[int, int, int, int]) -> Tuple[List[np.ndarray], np.ndarray, Dict[int, np.ndarray]]:
        """
        批量计算所有帧的dHash和标准差 + 智能缓存关键帧图像
        
        🆕 新功能: 在计算特征的同时，智能缓存可能成为关键帧的图像数据
        通过粗筛选机制，减少无关帧的缓存，控制内存使用
        
        Args:
            video_path: 视频文件路径
            decoder: GPU解码器实例 
            crop_rect: 裁剪区域 (x1, y1, x2, y2)
            
        Returns:
            Tuple[List[np.ndarray], np.ndarray, Dict[int, np.ndarray]]:
            - all_hashes: 所有帧的dHash特征列表
            - all_stds: 所有帧的标准差数组
            - keyframe_cache: 候选关键帧的图像缓存字典
        """
        all_hashes = []
        all_stds = []
        keyframe_cache = {}
        x1, y1, x2, y2 = crop_rect

        frame_count = 0
        batch_count = 0
        prev_hash = None
        cached_frames_count = 0
        
        print("🔄 正在计算视频特征并智能缓存...")
        
        for batch_tensor, _ in decoder.decode(video_path):
            # 裁剪字幕区域
            cropped_batch = batch_tensor[:, :, y1:y2, x1:x2]

            # --- 在GPU上批量计算特征 --- #
            # 1. 计算标准差
            stds = torch.std(cropped_batch.float().view(cropped_batch.size(0), -1), dim=1)
            batch_stds = stds.cpu().numpy()
            all_stds.extend(batch_stds)

            # 2. 计算dHash
            grayscale_batch = cropped_batch.float().mean(dim=1, keepdim=True)
            resized_batch = torch.nn.functional.interpolate(
                grayscale_batch, 
                size=(self.hash_size, self.hash_size + 1), 
                mode='bilinear', align_corners=False
            )
            diff = resized_batch[:, :, :, 1:] > resized_batch[:, :, :, :-1]
            batch_hashes = diff.cpu().numpy().astype(np.uint8).reshape(diff.shape[0], -1)
            all_hashes.extend(batch_hashes)
            
            # --- 🆕 智能缓存候选关键帧 --- #
            for i, curr_hash in enumerate(batch_hashes):
                frame_idx = frame_count + i
                
                # 第一帧默认缓存
                if frame_idx == 0:
                    frame_np = cropped_batch[i].permute(1, 2, 0).cpu().numpy().astype(np.uint8)
                    keyframe_cache[frame_idx] = frame_np
                    prev_hash = curr_hash
                    cached_frames_count += 1
                    continue
                
                # 快速相似度预判断 (粗筛)
                if prev_hash is not None:
                    hamming_distance = np.count_nonzero(curr_hash != prev_hash)
                    rough_similarity = 1.0 - (hamming_distance / curr_hash.size)
                    
                    # 缓存可能是关键帧的帧 (相似度 < 95%，宽松预筛选)
                    if rough_similarity < 0.95:
                        frame_np = cropped_batch[i].permute(1, 2, 0).cpu().numpy().astype(np.uint8)
                        keyframe_cache[frame_idx] = frame_np
                        prev_hash = curr_hash
                        cached_frames_count += 1
            
            frame_count += batch_tensor.size(0)
            batch_count += 1
            
            # 每50个batch显示一次进度 + 缓存统计
            if batch_count % 50 == 0:
                cache_mb = cached_frames_count * 0.307  # 每帧约307KB
                cache_ratio = (cached_frames_count / frame_count) * 100
                print(f"  📊 已处理 {frame_count} 帧，预缓存 {cached_frames_count} 帧 ({cache_ratio:.1f}%, ~{cache_mb:.1f}MB)")
            
        # 最终统计
        final_cache_mb = cached_frames_count * 0.307
        cache_ratio = (cached_frames_count / frame_count) * 100
        print(f"✅ 特征计算完成: 共处理 {frame_count} 帧")
        print(f"🗂️  预缓存统计: {cached_frames_count} 帧 ({cache_ratio:.1f}%), 约 {final_cache_mb:.1f}MB")
        
        return all_hashes, np.array(all_stds), keyframe_cache
    
    def _get_otsu_threshold(self, stds: np.ndarray) -> float:
        """使用大津法计算最佳空白帧阈值"""
        if stds.max() == stds.min(): 
            return 0.0
        
        stds_normalized = (255 * (stds - stds.min()) / (stds.max() - stds.min())).astype(np.uint8)
        threshold_otsu, _ = cv2.threshold(stds_normalized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        original_threshold = threshold_otsu / 255 * (stds.max() - stds.min()) + stds.min()
        return float(original_threshold)

    def generate_subtitle_segments(self, keyframes: List[int], 
                                 fps: float, total_frames: int) -> List[Dict]:
        """
        从关键帧列表生成字幕段落
        每两个连续关键帧之间形成一个段落
        
        Args:
            keyframes: 关键帧索引列表
            fps: 视频帧率
            total_frames: 视频总帧数
            
        Returns:
            段落列表，包含关键帧信息
        """
        segments = []
        
        print(f"🏗️ 从 {len(keyframes)} 个关键帧生成字幕段落...")
        
        for i in range(len(keyframes)):
            start_frame = keyframes[i]
            
            # 确定结束帧
            if i + 1 < len(keyframes):
                end_frame = keyframes[i + 1] - 1  # 下一关键帧的前一帧
            else:
                end_frame = total_frames - 1  # 视频的最后一帧
            
            # 计算时间戳
            start_time = start_frame / fps
            end_time = end_frame / fps
            
            segments.append({
                'key_frame': start_frame,      # 🆕 关键帧信息
                'start_frame': start_frame,
                'end_frame': end_frame, 
                'start_time': start_time,
                'end_time': end_time,
                'duration': end_time - start_time
            })
        
        print(f"✅ 生成了 {len(segments)} 个字幕段落")
        return segments