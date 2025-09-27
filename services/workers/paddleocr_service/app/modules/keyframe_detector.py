# app/modules/keyframe_detector.py
import gc  # 🆕 内存优化: 引入垃圾回收模块
import json
import os
from datetime import datetime
from typing import Dict
from typing import List
from typing import Tuple

import cv2
import numpy as np
import torch

from .decoder import GPUDecoder
from .base_detector import BaseDetector, ConfigManager, ProgressTracker
from services.common.logger import get_logger

logger = get_logger('keyframe_detector')


class KeyFrameDetector(BaseDetector):
    """
    关键帧检测器 - 简化版本 (仅dHash)
    基于dHash相似度的关键帧检测，已移除标准差和大津算法
    
    实现逻辑:
    1. 第一帧默认为关键帧
    2. 逐帧比对: 1vs0, 2vs1, 3vs2...
    3. dHash相似度低于阈值 → 新关键帧
    
    已注释功能:
    - 标准差计算 (空白帧检测)
    - 大津算法 (自适应阈值)
    - 空白帧vs内容帧的分类逻辑
    """
    
    def __init__(self, config):
        """
        初始化关键帧检测器

        Args:
            config: 检测器配置
        """
        # 使用ConfigManager验证和规范化配置
        required_keys = []  # 关键帧检测器没有必需的配置项
        optional_keys = {
            'dhash_size': 8,
            'similarity_threshold': 0.90,
            'frame_memory_estimate_mb': 0.307,
            'dhash_focus_ratio': 3.0,
            'min_focus_width': 200,
            'progress_interval_frames': 1000,
            'progress_interval_batches': 50
        }

        validated_config = ConfigManager.validate_config(config, required_keys, optional_keys)

        # 调用父类初始化
        super().__init__(validated_config)

        # 设置关键帧检测器特有的配置
        self.hash_size = ConfigManager.validate_range(
            validated_config['dhash_size'], 1, 32, 'dhash_size'
        )

        self.similarity_threshold = ConfigManager.validate_range(
            validated_config['similarity_threshold'], 0.0, 1.0, 'similarity_threshold'
        )

        self.dhash_focus_ratio = ConfigManager.validate_range(
            validated_config['dhash_focus_ratio'], 0.1, 10.0, 'dhash_focus_ratio'
        )

        self.min_focus_width = ConfigManager.validate_range(
            validated_config['min_focus_width'], 1, 1000, 'min_focus_width'
        )

        # 初始化进度跟踪器
        self.progress_tracker = None

        logger.info(f"关键帧检测器已加载 - 相似度阈值: {self.similarity_threshold:.0%}, "
                   f"dHash焦点区域: 高差×{self.dhash_focus_ratio}")

    def _optimize_dhash_region(self, subtitle_area: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
        """
        优化dHash分析区域，聚焦字幕条中心部分
        
        策略: 使用高差×系数计算中心区域宽度，避免背景变化干扰
        
        Args:
            subtitle_area: 原始字幕区域 (x1, y1, x2, y2)
            
        Returns:
            优化后的dHash分析区域 (x1, y1, x2, y2)
        """
        orig_x1, orig_y1, orig_x2, orig_y2 = subtitle_area
        
        # 计算原区域尺寸
        orig_width = orig_x2 - orig_x1
        orig_height = orig_y2 - orig_y1
        
        # 计算中心焦点区域宽度 (高差×系数)
        focus_width = int(orig_height * self.dhash_focus_ratio)
        
        # 应用最小宽度保护
        focus_width = max(focus_width, self.min_focus_width)
        
        # 确保焦点区域不超过原区域
        focus_width = min(focus_width, orig_width)
        
        # 计算居中的焦点区域边界
        center_x = (orig_x1 + orig_x2) // 2
        focus_x1 = center_x - focus_width // 2
        focus_x2 = focus_x1 + focus_width
        
        # 边界检查，确保在原区域内
        focus_x1 = max(focus_x1, orig_x1)
        focus_x2 = min(focus_x2, orig_x2)
        
        # 高度保持不变
        focus_y1, focus_y2 = orig_y1, orig_y2
        
        optimized_region = (focus_x1, focus_y1, focus_x2, focus_y2)
        
        # 计算实际的优化效果 (基于边界调整后的真实宽度)
        actual_focus_width = focus_x2 - focus_x1
        reduction_ratio = (1 - (actual_focus_width / orig_width)) * 100
        print(f"🎯 dHash区域优化: {orig_width}×{orig_height} → {actual_focus_width}×{orig_height} "
              f"(减少{reduction_ratio:.1f}%背景干扰)")
        
        return optimized_region

    def _extract_dhash_region_from_cache(self, cached_frame: np.ndarray, 
                                       dhash_region: Tuple[int, int, int, int],
                                       subtitle_area: Tuple[int, int, int, int]) -> np.ndarray:
        """
        从缓存的完整字幕条中提取dHash分析区域
        
        Args:
            cached_frame: 缓存的完整字幕条图像 (H, W, C)
            dhash_region: dHash分析区域坐标 (x1, y1, x2, y2)
            subtitle_area: 完整字幕区域坐标 (x1, y1, x2, y2)
            
        Returns:
            提取的dHash区域图像 (灰度图)
        """
        dhash_x1, dhash_y1, dhash_x2, dhash_y2 = dhash_region
        sub_x1, sub_y1, sub_x2, sub_y2 = subtitle_area
        
        # 计算dHash区域在缓存图像中的相对位置
        rel_x1 = dhash_x1 - sub_x1
        rel_y1 = dhash_y1 - sub_y1
        rel_x2 = dhash_x2 - sub_x1
        rel_y2 = dhash_y2 - sub_y1
        
        # 边界检查
        rel_x1 = max(0, rel_x1)
        rel_y1 = max(0, rel_y1)
        rel_x2 = min(cached_frame.shape[1], rel_x2)
        rel_y2 = min(cached_frame.shape[0], rel_y2)
        
        # 提取dHash区域
        dhash_region_img = cached_frame[rel_y1:rel_y2, rel_x1:rel_x2]
        
        # 转换为灰度图 (与dHash计算保持一致)
        if len(dhash_region_img.shape) == 3:
            # RGB转灰度: 0.299*R + 0.587*G + 0.114*B
            dhash_gray = cv2.cvtColor(dhash_region_img, cv2.COLOR_RGB2GRAY)
        else:
            dhash_gray = dhash_region_img
            
        return dhash_gray

    def detect_keyframes(self, video_path: str, decoder: GPUDecoder, 
                        subtitle_area: Tuple[int, int, int, int]) -> List[int]:
        """
        检测视频中所有关键帧 (简化版本，只使用dHash)
        
        实现逻辑:
        1. 第一帧默认为关键帧
        2. 逐帧比对: 1vs0, 2vs1, 3vs2...
        3. dHash相似度低于阈值 → 新关键帧
        
        Args:
            video_path: 视频文件路径
            decoder: GPU解码器实例
            subtitle_area: 字幕区域坐标 (x1, y1, x2, y2)
            
        Returns:
            关键帧索引列表 [0, 45, 89, 156, ...]
        """
        # 🆕 优化dHash分析区域，聚焦字幕中心部分  
        dhash_region = self._optimize_dhash_region(subtitle_area)
        keyframes, _ = self._compute_frame_features_and_detect(video_path, decoder, dhash_region)
        return keyframes
    
    def _compute_frame_features_and_detect(self, video_path: str, decoder: GPUDecoder, 
                                         dhash_region: Tuple[int, int, int, int]) -> Tuple[List[int], List[np.ndarray]]:
        """
        计算帧特征并检测关键帧 (简化版本，不带缓存)
        
        Args:
            video_path: 视频文件路径
            decoder: GPU解码器实例
            dhash_region: dHash分析区域
            
        Returns:
            Tuple[List[int], List[np.ndarray]]: 关键帧索引列表和所有hash
        """
        all_hashes = self._compute_frame_features(video_path, decoder, dhash_region)
        keyframes = self._detect_keyframes_sequential(all_hashes)
        return keyframes, all_hashes

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

        # 🆕 优化dHash分析区域，聚焦字幕中心部分  
        dhash_region = self._optimize_dhash_region(subtitle_area)

        # 1. 批量计算所有帧的特征 + 同步缓存
        all_hashes, keyframe_cache = self._compute_frame_features_with_cache(
            video_path, decoder, dhash_region, subtitle_area
        )
        print(f"📊 完成特征计算: {len(all_hashes)} 帧")

        # 2. 关键帧逐帧检测 - 只使用dHash
        keyframes = self._detect_keyframes_sequential_with_logging(all_hashes, keyframe_cache, video_path, dhash_region, subtitle_area)
        
        # 4. 只保留检测到的关键帧缓存，释放其他缓存
        final_keyframe_cache = {k: keyframe_cache[k] for k in keyframes if k in keyframe_cache}
        
        # 5. 🆕 内存优化: 显式删除临时缓存并强制垃圾回收
        del keyframe_cache
        gc.collect()
        
        # 6. 显示缓存统计信息 (使用配置的内存估算)
        cache_size_mb = len(final_keyframe_cache) * self.frame_memory_estimate_mb  
        print(f"✅ 检测到 {len(keyframes)} 个关键帧")
        print(f"🗂️  关键帧缓存: {len(final_keyframe_cache)} 帧，约 {cache_size_mb:.1f}MB")
        
        return keyframes, final_keyframe_cache
    
    def _detect_keyframes_sequential_with_logging(self, hashes: List[np.ndarray], 
                                                keyframe_cache: Dict[int, np.ndarray],
                                                video_path: str,
                                                dhash_region: Tuple[int, int, int, int],
                                                subtitle_area: Tuple[int, int, int, int]) -> List[int]:
        """
        按照新逻辑进行关键帧检测 + 详细日志记录
        实现用户需求的具体算法 + 保存dHash对比数据和字幕条图片
        
        Args:
            hashes: 所有帧的dHash特征列表
            keyframe_cache: 关键帧图像缓存 (完整字幕区域)
            video_path: 视频文件路径，用于生成日志文件名
            dhash_region: dHash分析区域 (用于截图保存)
            subtitle_area: 完整字幕区域 (用于参考)
            
        Returns:
            关键帧索引列表
        """
        # 边界情况检查
        if not hashes or len(hashes) == 0:
            print("⚠️ 警告: 没有帧数据，返回空列表")
            return []
        
        if len(hashes) == 1:
            print("📌 单帧视频，返回第0帧作为关键帧")
            return [0]
        
        keyframes = []
        dhash_log_data = []  # 用于保存详细的dHash对比数据
        
        # 统计数据初始化 - 使用动态变量名
        similarity_stats = {
            'gte_threshold': 0,  # >=阈值的帧数
            'lt_threshold': 0,   # <阈值的帧数
        }
        
        # 1. 第一帧默认为关键帧
        keyframes.append(0)
        print(f"📌 关键帧 0: 默认第一帧")
        
        # 记录第一帧的日志数据
        dhash_log_data.append({
            "frame_index": 0,
            "threshold": self.similarity_threshold,
            "similarity_with_previous": None,  # 第一帧没有前一帧
            "is_keyframe": True,
            "subtitle_frame_path": None
        })
        
        print(f"🔄 正在分析 {len(hashes)} 帧的相似度...")
        
        # 2. 从第1帧开始逐帧比对
        for curr_frame in range(1, len(hashes)):
            prev_frame = curr_frame - 1
            
            # 计算相似度 - 只使用dHash
            similarity = self._calculate_similarity(
                hashes[prev_frame], hashes[curr_frame]
            )
            
            # 统计相似度分布 - 使用动态阈值
            if similarity >= self.similarity_threshold:
                similarity_stats['gte_threshold'] += 1
            else:
                similarity_stats['lt_threshold'] += 1
            
            # 3. 相似度低于阈值 → 新关键帧
            is_keyframe = similarity < self.similarity_threshold
            if is_keyframe:
                keyframes.append(curr_frame)
            
            # 记录详细的dHash对比数据
            dhash_log_data.append({
                "frame_index": curr_frame,
                "threshold": self.similarity_threshold,
                "similarity_with_previous": round(similarity, 4),
                "is_keyframe": is_keyframe,
                "subtitle_frame_path": None
            })
            
            # 进度显示 (按配置间隔显示)
            if curr_frame % self.progress_interval_frames == 0:
                progress = (curr_frame / len(hashes)) * 100
                threshold_percent = int(self.similarity_threshold * 100)
                print(f"  🔍 检测进度: {curr_frame}/{len(hashes)} ({progress:.1f}%) | "
                      f"相似度分布: >={threshold_percent}%帧:{similarity_stats['gte_threshold']}/"
                      f"<{threshold_percent}%帧:{similarity_stats['lt_threshold']} | "
                      f"关键帧:{len(keyframes)}个")
        
        # # 任务1: 注释日志保存功能
        # # 保存dHash对比日志文件
        # video_name = os.path.splitext(os.path.basename(video_path))[0]
        # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # log_filename = f'./logs/dhash_analysis_{video_name}_{timestamp}.json'
        
        # log_summary = {
        #     "video_path": video_path,
        #     "total_frames": len(hashes),
        #     "similarity_threshold": self.similarity_threshold,
        #     "detected_keyframes": len(keyframes),
        #     "keyframe_ratio": len(keyframes) / len(hashes),
        #     "analysis_timestamp": datetime.now().isoformat(),
        #     "frames_data": dhash_log_data
        # }
        
        # # 确保logs目录存在
        # os.makedirs('./logs', exist_ok=True)
        # with open(log_filename, 'w', encoding='utf-8') as f:
        #     json.dump(log_summary, f, indent=2, ensure_ascii=False)
        
        # 输出最终统计 - 使用动态变量名
        total_compared = len(hashes) - 1  # 第一帧不参与比较
        threshold_percent = int(self.similarity_threshold * 100)
        print(f"📊 相似度统计(总计{total_compared}帧): >={threshold_percent}%帧:{similarity_stats['gte_threshold']}/"
              f"<{threshold_percent}%帧:{similarity_stats['lt_threshold']}")
        print(f"✅ 关键帧检测完成: 共找到 {len(keyframes)} 个关键帧")
        # print(f"📝 详细日志已保存: {log_filename}") # 任务1: 注释日志保存功能
        
        return keyframes
    
    def _detect_keyframes_sequential(self, hashes: List[np.ndarray]) -> List[int]:
        """
        按照新逻辑进行关键帧检测
        实现用户需求的具体算法
        """
        # 边界情况检查
        if not hashes or len(hashes) == 0:
            print("⚠️ 警告: 没有帧数据，返回空列表")
            return []
        
        if len(hashes) == 1:
            print("📌 单帧视频，返回第0帧作为关键帧")
            return [0]
        
        keyframes = []
        
        # 统计数据初始化 - 使用动态变量名
        similarity_stats = {
            'gte_threshold': 0,  # >=阈值的帧数
            'lt_threshold': 0,   # <阈值的帧数
        }
        
        # 1. 第一帧默认为关键帧
        keyframes.append(0)
        print(f"📌 关键帧 0: 默认第一帧")
        
        print(f"🔄 正在分析 {len(hashes)} 帧的相似度...")
        
        # 2. 从第1帧开始逐帧比对
        for curr_frame in range(1, len(hashes)):
            prev_frame = curr_frame - 1
            
            # 计算相似度 - 只使用dHash
            similarity = self._calculate_similarity(
                hashes[prev_frame], hashes[curr_frame]
            )
            
            # 统计相似度分布 - 使用动态阈值
            if similarity >= self.similarity_threshold:
                similarity_stats['gte_threshold'] += 1
            else:
                similarity_stats['lt_threshold'] += 1
            
            # 3. 相似度低于阈值 → 新关键帧
            if similarity < self.similarity_threshold:
                keyframes.append(curr_frame)
            
            # 进度显示 (按配置间隔显示)
            if curr_frame % self.progress_interval_frames == 0:
                progress = (curr_frame / len(hashes)) * 100
                threshold_percent = int(self.similarity_threshold * 100)
                print(f"  🔍 检测进度: {curr_frame}/{len(hashes)} ({progress:.1f}%) | "
                      f"相似度分布: >={threshold_percent}%帧:{similarity_stats['gte_threshold']}/"
                      f"<{threshold_percent}%帧:{similarity_stats['lt_threshold']} | "
                      f"关键帧:{len(keyframes)}个")
        
        # 输出最终统计 - 使用动态变量名
        total_compared = len(hashes) - 1  # 第一帧不参与比较
        threshold_percent = int(self.similarity_threshold * 100)
        print(f"📊 相似度统计(总计{total_compared}帧): >={threshold_percent}%帧:{similarity_stats['gte_threshold']}/"
              f"<{threshold_percent}%帧:{similarity_stats['lt_threshold']}")
        print(f"✅ 关键帧检测完成: 共找到 {len(keyframes)} 个关键帧")
        return keyframes
    
    def _calculate_similarity(self, hash1: np.ndarray, hash2: np.ndarray) -> float:
        """
        计算两帧之间的相似度
        
        相似度计算规则:
        - 基于dHash的汉明距离计算
        
        基于行业标准Dr. Neal Krawetz的研究成果
        """
        # 边界情况检查
        if hash1 is None or hash2 is None:
            return 0.0
        
        if hash1.size == 0 or hash2.size == 0:
            return 0.0
            
        if hash1.size != hash2.size:
            print(f"⚠️ 警告: hash尺寸不匹配: {hash1.size} vs {hash2.size}")
            return 0.0
        
        # 直接基于dHash计算相似度
        hamming_distance = np.count_nonzero(hash1 != hash2)
        max_possible_distance = hash1.size  # 64 for 8x8 dHash
        
        # 防止除零错误
        if max_possible_distance == 0:
            return 1.0  # 如果两个都是空数组，认为相同
        
        # 相似度 = 1 - (汉明距离 / 最大可能距离)
        similarity = 1.0 - (hamming_distance / max_possible_distance)
        
        return similarity
    
    def _compute_frame_features(self, video_path: str, decoder: GPUDecoder, 
                               dhash_region: Tuple[int, int, int, int]) -> List[np.ndarray]:
        """
        批量计算所有帧的dHash (使用优化后的中心区域)
        """
        all_hashes = []
        x1, y1, x2, y2 = dhash_region

        frame_count = 0
        batch_count = 0
        
        print("🔄 正在计算视频特征 (使用优化的dHash区域)...")
        
        for batch_tensor, _ in decoder.decode_gpu(video_path):
            # 裁剪优化后的dHash区域  
            dhash_cropped_batch = batch_tensor[:, :, y1:y2, x1:x2]

            # 计算dHash (带GPU内存保护)
            batch_hashes = None  # 初始化避免未定义错误
            try:
                grayscale_batch = dhash_cropped_batch.float().mean(dim=1, keepdim=True)
                resized_batch = torch.nn.functional.interpolate(
                    grayscale_batch, 
                    size=(self.hash_size, self.hash_size + 1), 
                    mode='bilinear', align_corners=False
                )
                diff = resized_batch[:, :, :, 1:] > resized_batch[:, :, :, :-1]
                hashes_np = diff.cpu().numpy().astype(np.uint8).reshape(diff.shape[0], -1)
                all_hashes.extend(hashes_np)
                
                # 显式清理中间GPU变量，释放显存
                del grayscale_batch, resized_batch, diff, hashes_np
                
            except RuntimeError as e:
                if "out of memory" in str(e).lower():
                    print(f"⚠️ GPU内存不足，跳过batch {batch_count}: {e}")
                    # 跳过当前batch，但仍需更新计数器
                    frame_count += batch_tensor.size(0)
                    batch_count += 1
                    continue
                else:
                    raise e
            
            frame_count += batch_tensor.size(0)
            batch_count += 1
            
            # 显式删除批次tensor，释放GPU内存
            del batch_tensor, dhash_cropped_batch
            
            # 每配置间隔显示一次进度
            if batch_count % self.progress_interval_batches == 0:
                print(f"  📊 已处理 {frame_count} 帧...")
                # 间隔性强制垃圾回收
                import gc
                gc.collect()
            
        print(f"✅ 特征计算完成: 共处理 {frame_count} 帧")
        
        # GPU 资源释放
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
        # 强制垃圾回收
        import gc
        gc.collect()
            
        return all_hashes
    
    def _compute_frame_features_with_cache(self, video_path: str, decoder: GPUDecoder, 
                                          dhash_region: Tuple[int, int, int, int],
                                          cache_region: Tuple[int, int, int, int]) -> Tuple[List[np.ndarray], Dict[int, np.ndarray]]:
        """
        批量计算所有帧的dHash + 智能缓存关键帧图像
        
        🆕 区域分离策略:
        - dhash_region: 用于dHash计算的优化区域(聚焦中心，减少背景干扰)  
        - cache_region: 用于图像缓存的完整字幕区域(OCR识别需要)
        
        Args:
            video_path: 视频文件路径
            decoder: GPU解码器实例 
            dhash_region: dHash分析区域 (x1, y1, x2, y2) - 中心焦点区域
            cache_region: 图像缓存区域 (x1, y1, x2, y2) - 完整字幕区域
            
        Returns:
            Tuple[List[np.ndarray], Dict[int, np.ndarray]]:
            - all_hashes: 所有帧的dHash特征列表
            - keyframe_cache: 候选关键帧的图像缓存字典
        """
        all_hashes = []
        keyframe_cache = {}
        
        # dHash计算区域
        dhash_x1, dhash_y1, dhash_x2, dhash_y2 = dhash_region
        # 图像缓存区域  
        cache_x1, cache_y1, cache_x2, cache_y2 = cache_region

        frame_count = 0
        batch_count = 0
        prev_hash = None
        cached_frames_count = 0
        
        print("🔄 正在计算视频特征并智能缓存...")
        
        for batch_tensor, _ in decoder.decode_gpu(video_path):
            # 🎯 先裁剪dHash计算区域 (优先处理，减少内存占用)
            dhash_cropped = batch_tensor[:, :, dhash_y1:dhash_y2, dhash_x1:dhash_x2]

            # 计算dHash (带GPU内存保护) - 使用优化后的中心区域
            batch_hashes = None  # 初始化避免未定义错误
            try:
                grayscale_batch = dhash_cropped.float().mean(dim=1, keepdim=True)
                resized_batch = torch.nn.functional.interpolate(
                    grayscale_batch, 
                    size=(self.hash_size, self.hash_size + 1), 
                    mode='bilinear', align_corners=False
                )
                diff = resized_batch[:, :, :, 1:] > resized_batch[:, :, :, :-1]
                batch_hashes = diff.cpu().numpy().astype(np.uint8).reshape(diff.shape[0], -1)
                all_hashes.extend(batch_hashes)
                
                # 显式清理中间GPU变量，释放显存
                del grayscale_batch, resized_batch, diff
                
            except RuntimeError as e:
                if "out of memory" in str(e).lower():
                    print(f"⚠️ GPU内存不足，跳过batch {batch_count}: {e}")
                    # 跳过当前batch，但仍需更新计数器
                    frame_count += batch_tensor.size(0)
                    batch_count += 1
                    continue
                else:
                    raise e
            
            # 🆕 智能缓存候选关键帧 (只有在GPU计算成功时才执行)
            # 优化策略：只在需要缓存时才裁剪cache区域，减少不必要的GPU操作
            if batch_hashes is not None:
                cache_cropped = None  # 延迟初始化
                
                for i, curr_hash in enumerate(batch_hashes):
                    frame_idx = frame_count + i
                    
                    # 第一帧默认缓存
                    if frame_idx == 0:
                        if cache_cropped is None:
                            cache_cropped = batch_tensor[:, :, cache_y1:cache_y2, cache_x1:cache_x2]
                        # 缓存完整字幕条区域 (用于OCR识别)
                        frame_np = cache_cropped[i].permute(1, 2, 0).cpu().numpy().astype(np.uint8)
                        keyframe_cache[frame_idx] = frame_np
                        prev_hash = curr_hash
                        cached_frames_count += 1
                        continue
                    
                    # 快速相似度预判断 (粗筛) - 无条件更新prev_hash
                    if prev_hash is not None:
                        hamming_distance = np.count_nonzero(curr_hash != prev_hash)
                        rough_similarity = 1.0 - (hamming_distance / curr_hash.size)
                        
                        # 缓存可能是关键帧的帧 (使用相同的相似度阈值)
                        if rough_similarity < self.similarity_threshold:
                            if cache_cropped is None:
                                cache_cropped = batch_tensor[:, :, cache_y1:cache_y2, cache_x1:cache_x2]
                            # 缓存完整字幕条区域 (用于OCR识别)
                            frame_np = cache_cropped[i].permute(1, 2, 0).cpu().numpy().astype(np.uint8)
                            keyframe_cache[frame_idx] = frame_np
                            cached_frames_count += 1
                        
                        # 无条件更新prev_hash以保持连续性
                        prev_hash = curr_hash
            
            frame_count += batch_tensor.size(0)
            batch_count += 1
            
            # 显式删除批次数据，释放内存
            del batch_tensor
            if cache_cropped is not None:
                del cache_cropped
            if batch_hashes is not None:
                del batch_hashes
            
            # 每配置间隔显示一次进度 + 缓存统计
            if batch_count % self.progress_interval_batches == 0:
                cache_mb = cached_frames_count * self.frame_memory_estimate_mb
                cache_ratio = (cached_frames_count / frame_count) * 100
                print(f"  📊 已处理 {frame_count} 帧，预缓存 {cached_frames_count} 帧 ({cache_ratio:.1f}%, ~{cache_mb:.1f}MB)")
                # 间隔性强制垃圾回收
                import gc
                gc.collect()
            
        # 最终统计 (使用配置的内存估算)
        final_cache_mb = cached_frames_count * self.frame_memory_estimate_mb
        cache_ratio = (cached_frames_count / frame_count) * 100
        print(f"✅ 特征计算完成: 共处理 {frame_count} 帧")
        print(f"🗂️  预缓存统计: {cached_frames_count} 帧 ({cache_ratio:.1f}%), 约 {final_cache_mb:.1f}MB")
        
        # GPU 资源释放
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
        # 强制垃圾回收
        import gc
        gc.collect()
        
        return all_hashes, keyframe_cache
    
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
        # 输入验证
        if not keyframes:
            print("⚠️ 警告: 关键帧列表为空，返回空段落列表")
            return []
        
        if fps <= 0:
            raise ValueError(f"fps必须大于0，当前值: {fps}")
        
        if total_frames <= 0:
            raise ValueError(f"total_frames必须大于0，当前值: {total_frames}")
        
        if not isinstance(keyframes, list):
            raise TypeError(f"keyframes必须是列表类型，当前类型: {type(keyframes)}")
        
        # 验证关键帧索引的有效性
        if any(frame < 0 or frame >= total_frames for frame in keyframes):
            invalid_frames = [frame for frame in keyframes if frame < 0 or frame >= total_frames]
            raise ValueError(f"关键帧索引超出有效范围[0, {total_frames-1}]: {invalid_frames}")
        
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

    def detect(self, video_path: str, decoder, subtitle_area: Tuple[int, int, int], **kwargs) -> List[int]:
        """
        实现基类的抽象检测方法

        Args:
            video_path: 视频文件路径
            decoder: GPU解码器实例
            subtitle_area: 字幕区域坐标
            **kwargs: 其他参数

        Returns:
            关键帧索引列表
        """
        self._start_processing()
        try:
            keyframes = self.detect_keyframes(video_path, decoder, subtitle_area)
            return keyframes
        finally:
            self._finish_processing()

    def get_detector_name(self) -> str:
        """
        获取检测器名称

        Returns:
            检测器名称
        """
        return "KeyFrameDetector"
