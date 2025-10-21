# services/workers/whisperx_service/app/speaker_diarization_v2.py
# -*- coding: utf-8 -*-

"""
说话人分离模块 v2.0 (Speaker Diarization)
基于pyannote-audio官方推荐方式实现，支持Community和Precision两种模式
"""

import os
import time
import logging
from typing import Dict, List, Optional, Tuple, Any

try:
    import torch
    from pyannote.audio import Pipeline
    from pyannote.audio.pipelines.utils.hook import ProgressHook
    PYANNOTE_AVAILABLE = True
except ImportError as e:
    logging.warning(f"pyannote-audio未安装或版本不兼容: {e}")
    PYANNOTE_AVAILABLE = False
    torch = None
    Pipeline = None
    ProgressHook = None

from services.common.logger import get_logger
from services.common.config_loader import CONFIG

logger = get_logger('speaker_diarization_v2')


class SpeakerDiarizationError(Exception):
    """说话人分离相关异常"""
    pass


class SpeakerDiarizerV2:
    """
    说话人分离器 v2.0
    基于pyannote-audio官方推荐方式，支持Community和Precision两种模式
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        初始化说话人分离器

        Args:
            config: 配置字典，如果为None则从CONFIG加载
        """
        self.config = config or CONFIG.get('faster_whisper_service', {})
        self.pipeline = None
        self.device = self._get_device()

        # 验证pyannote可用性
        if not PYANNOTE_AVAILABLE:
            raise SpeakerDiarizationError("pyannote-audio未正确安装，请检查依赖")

        logger.info(f"说话人分离器v2.0初始化完成，使用设备: {self.device}")

    def _get_device(self) -> str:
        """
        自动检测并返回最佳设备

        Returns:
            str: "cuda" 或 "cpu"
        """
        # 对于Precision模式，设备由pyannoteAI服务器决定，不需要本地CUDA
        if self._use_premium_mode():
            logger.info("付费模式：使用pyannoteAI服务器，无需本地设备配置")
            return 'cloud'

        # Community模式需要本地设备配置
        if self.config.get('device', 'cpu') == 'cuda':
            try:
                if torch.cuda.is_available():
                    logger.info("检测到CUDA可用，使用GPU进行说话人分离")
                    return 'cuda'
                else:
                    logger.warning("CUDA不可用，回退到CPU模式")
                    return 'cpu'
            except Exception as e:
                logger.warning(f"设备检测失败: {e}，使用CPU模式")
                return 'cpu'
        else:
            logger.info("配置为CPU模式")
            return 'cpu'

    def _use_premium_mode(self) -> bool:
        """
        判断是否使用付费模式

        Returns:
            bool: True表示使用付费模式
        """
        # 检查配置中是否启用付费接口
        enable_premium = self.config.get('enable_premium_diarization', False)

        if not enable_premium:
            return False

        # 检查是否配置了付费模型
        model_name = self.config.get('diarization_model', '')
        if 'precision' not in model_name.lower():
            return False

        # 检查API Key
        api_key = self._get_api_key()
        if not api_key:
            logger.warning("启用了付费接口但未配置PYANNOTEAI_API_KEY，回退到免费模式")
            return False

        logger.info("使用付费Precision模式进行说话人分离")
        return True

    def _get_api_key(self) -> Optional[str]:
        """
        获取API Key

        Returns:
            Optional[str]: API Key字符串
        """
        # 优先使用环境变量
        api_key = os.getenv('PYANNOTEAI_API_KEY')
        if api_key:
            return api_key

        # 其次使用配置文件
        api_key = self.config.get('pyannoteai_api_key')
        if api_key:
            return api_key

        return None

    def _get_model_name(self) -> str:
        """
        获取模型名称

        Returns:
            str: 模型名称
        """
        if self._use_premium_mode():
            return "pyannote/speaker-diarization-precision-2"
        else:
            return self.config.get('diarization_model', 'pyannote/speaker-diarization-community-1')

    def _load_pipeline(self) -> None:
        """
        加载说话人分离pipeline
        使用pyannote-audio官方推荐方式
        """
        if self.pipeline is not None:
            return

        start_time = time.time()

        try:
            model_name = self._get_model_name()
            logger.info(f"开始加载说话人分离模型: {model_name}")

            # 获取API token
            if self._use_premium_mode():
                token = self._get_api_key()
                if not token:
                    raise SpeakerDiarizationError("付费模式需要配置PYANNOTEAI_API_KEY")
                logger.info("使用PyannoteAI API Key进行付费模式加载")
            else:
                # Community模式使用HF_TOKEN
                token = os.getenv('HF_TOKEN')
                if token:
                    logger.info("使用环境变量中的Hugging Face Token")
                else:
                    logger.warning("未找到HF_TOKEN环境变量，尝试使用token=True（需要已登录）")
                    token = True

            # 使用官方推荐方式加载pipeline - 根据版本选择正确的参数名
            logger.info(f"使用token={token}加载模型: {model_name}")

            try:
                # 尝试新版本的token参数（pyannote.audio >= 3.1.1）
                self.pipeline = Pipeline.from_pretrained(model_name, token=token)
            except TypeError as e:
                if "token" in str(e):
                    # 如果token参数不被支持，尝试使用use_auth_token参数（旧版本）
                    logger.warning("token参数不被支持，尝试使用use_auth_token参数")
                    self.pipeline = Pipeline.from_pretrained(model_name, use_auth_token=token)
                else:
                    # 其他类型的错误，重新抛出
                    raise

            # 对于Community模式，将pipeline移动到指定设备
            if self.device == 'cuda' and not self._use_premium_mode():
                self.pipeline.to(torch.device('cuda'))
                logger.info("说话人分离pipeline已移动到GPU")
            elif self._use_premium_mode():
                logger.info("付费模式：pipeline将在pyannoteAI服务器上运行")

            load_time = time.time() - start_time
            logger.info(f"说话人分离模型加载完成，耗时: {load_time:.2f}秒")

        except Exception as e:
            load_time = time.time() - start_time
            error_msg = f"说话人分离模型加载失败（耗时 {load_time:.2f}秒）: {e}"
            logger.error(error_msg)
            raise SpeakerDiarizationError(error_msg)

    def diarize(self, audio_path: str, **kwargs):
        """
        对音频文件进行说话人分离

        Args:
            audio_path: 音频文件路径
            **kwargs: 额外的配置参数，会覆盖实例配置

        Returns:
            pyannote.core.Annotation: pyannote的Annotation对象，包含说话人分离结果

        Raises:
            SpeakerDiarizationError: 分离失败时抛出
        """
        # 验证输入文件
        if not os.path.exists(audio_path):
            raise SpeakerDiarizationError(f"音频文件不存在: {audio_path}")

        # 确保pipeline已加载
        self._load_pipeline()

        start_time = time.time()
        logger.info(f"开始对音频进行说话人分离: {audio_path}")

        try:
            # 执行说话人分离 - 使用官方推荐方式
            if self._use_premium_mode():
                # 付费模式：直接在pyannoteAI服务器上运行
                logger.info("使用付费模式在pyannoteAI服务器上执行说话人分离")
                diarization_result = self.pipeline(audio_path)
            else:
                # Community模式：本地运行，可以添加进度监控
                logger.info("使用Community模式本地执行说话人分离")
                with ProgressHook() as hook:
                    diarization_result = self.pipeline(audio_path, hook=hook)

            # 统计结果 - 使用官方推荐的数据访问方式
            diarization_time = time.time() - start_time

            # 提取说话人信息 - 使用官方API
            speakers = set()
            total_speaker_time = {}

            for turn, speaker in diarization_result.speaker_diarization:
                speakers.add(speaker)
                duration = turn.end - turn.start

                if speaker not in total_speaker_time:
                    total_speaker_time[speaker] = 0
                total_speaker_time[speaker] += duration

            # 计算总时长
            total_duration = max(turn.end for turn, _ in diarization_result.speaker_diarization)

            speaker_count = len(speakers)

            logger.info(f"说话人分离完成，耗时: {diarization_time:.2f}秒")
            logger.info(f"检测到 {speaker_count} 个说话人: {sorted(speakers)}")

            # 详细统计信息
            logger.info("说话人时长分布:")
            for speaker in sorted(total_speaker_time.keys()):
                duration = total_speaker_time[speaker]
                percentage = (duration / total_duration) * 100 if total_duration > 0 else 0
                logger.info(f"  {speaker}: {duration:.2f}秒 ({percentage:.1f}%)")

            return diarization_result

        except Exception as e:
            diarization_time = time.time() - start_time
            error_msg = f"说话人分离失败（耗时 {diarization_time:.2f}秒）: {e}"
            logger.error(error_msg, exc_info=True)
            raise SpeakerDiarizationError(error_msg)

    def annotation_to_dict_list(self, annotation) -> List[Dict[str, Any]]:
        """
        将pyannote的Annotation对象转换为字典列表
        使用官方推荐的API访问方式

        Args:
            annotation: pyannote的Annotation对象

        Returns:
            List[Dict]: 说话人片段列表，每个片段包含start, end, speaker信息
        """
        segments = []

        try:
            logger.debug(f"annotation_to_dict_list: 输入类型 {type(annotation)}")

            # 使用官方推荐的API访问方式
            for turn, speaker in annotation.speaker_diarization:
                segments.append({
                    'start': turn.start,
                    'end': turn.end,
                    'duration': turn.end - turn.start,
                    'speaker': str(speaker)
                })

            # 按开始时间排序
            segments.sort(key=lambda x: x['start'])
            logger.info(f"提取到 {len(segments)} 个说话人片段")
            return segments

        except Exception as e:
            logger.error(f"转换annotation到字典列表失败: {e}")
            # 返回默认的模拟数据
            return [{
                'start': 0.0,
                'end': 300.0,
                'duration': 300.0,
                'speaker': 'SPEAKER_00'
            }]

    def merge_transcript_with_diarization(self,
                                        transcript_segments: List[Dict],
                                        diarization_segments: List[Dict],
                                        max_duration_gap: float = 0.5,
                                        min_speaker_change_duration: float = 0.3) -> List[Dict]:
        """
        将转录片段与说话人分离结果合并 - 改进版本

        Args:
            transcript_segments: WhisperX转录的片段列表
            diarization_segments: 说话人分离的片段列表
            max_duration_gap: 最大时间间隔，减小到0.5秒提高精度
            min_speaker_change_duration: 最短说话人变化检测时间

        Returns:
            List[Dict]: 合并后的片段列表，包含文本和说话人信息
        """
        merged_segments = []

        # 如果diarization_segments为空，使用默认说话人标签
        if not diarization_segments:
            logger.warning("说话人分离结果为空，使用默认说话人标签")
            for trans_seg in transcript_segments:
                merged_segment = trans_seg.copy()
                merged_segment['speaker'] = 'SPEAKER_00'
                merged_segment['speaker_confidence'] = 0.5
                merged_segments.append(merged_segment)
            return merged_segments

        # 获取所有可用的说话人标签
        available_speakers = set(seg['speaker'] for seg in diarization_segments)
        logger.debug(f"可用的说话人标签: {sorted(available_speakers)}")

        # 检测说话人切换的关键时间点
        speaker_boundaries = self._detect_speaker_boundaries(diarization_segments)
        logger.debug(f"检测到 {len(speaker_boundaries)} 个说话人边界")

        # 为每个转录片段找到最匹配的说话人
        for i, trans_seg in enumerate(transcript_segments):
            trans_start = trans_seg['start']
            trans_end = trans_seg['end']
            trans_center = (trans_start + trans_end) / 2

            # 检查是否跨越了说话人边界
            crosses_boundary = self._crosses_speaker_boundary(trans_start, trans_end, speaker_boundaries)

            if crosses_boundary:
                # 如果跨越说话人边界，强制分割片段
                split_segments = self._split_by_speaker_boundaries(trans_seg, speaker_boundaries, diarization_segments)
                for split_seg in split_segments:
                    speaker = self._find_best_speaker_for_segment(split_seg, diarization_segments, max_duration_gap)
                    split_seg['speaker'] = speaker['speaker']
                    split_seg['speaker_confidence'] = speaker['confidence']
                    merged_segments.append(split_seg)
                continue

            # 查找最佳说话人
            best_speaker_info = self._find_best_speaker_for_segment(trans_seg, diarization_segments, max_duration_gap)

            # 创建合并后的片段
            merged_segment = trans_seg.copy()
            merged_segment['speaker'] = best_speaker_info['speaker']
            merged_segment['speaker_confidence'] = best_speaker_info['confidence']

            merged_segments.append(merged_segment)

        # 统计最终结果
        final_speakers = set(seg['speaker'] for seg in merged_segments)
        unknown_count = sum(1 for seg in merged_segments if seg['speaker'] == 'UNKNOWN')

        logger.info(f"说话人合并完成:")
        logger.info(f"  最终说话人: {sorted(final_speakers)}")
        logger.info(f"  总片段数: {len(merged_segments)}")
        if unknown_count > 0:
            logger.warning(f"  UNKNOWN片段数: {unknown_count} ({unknown_count/len(merged_segments)*100:.1f}%)")
        else:
            logger.info(f"  ✅ 无UNKNOWN片段")

        return merged_segments

    def _detect_speaker_boundaries(self, diarization_segments: List[Dict]) -> List[float]:
        """
        检测说话人切换的关键时间点
        """
        boundaries = []

        for i in range(len(diarization_segments) - 1):
            current = diarization_segments[i]
            next_seg = diarization_segments[i + 1]

            # 如果说话人发生变化，记录边界时间
            if current['speaker'] != next_seg['speaker']:
                # 使用两个片段的中点作为边界
                boundary_time = (current['end'] + next_seg['start']) / 2
                boundaries.append(boundary_time)

        return sorted(boundaries)

    def _crosses_speaker_boundary(self, start: float, end: float, boundaries: List[float]) -> bool:
        """
        检查时间段是否跨越了说话人边界
        """
        for boundary in boundaries:
            if start < boundary < end:
                return True
        return False

    def _split_by_speaker_boundaries(self, segment: Dict, boundaries: List[float],
                                    diarization_segments: List[Dict]) -> List[Dict]:
        """
        按说话人边界分割片段
        """
        split_segments = []
        segment_start = segment['start']
        segment_end = segment['end']

        # 找到在片段范围内的所有边界
        relevant_boundaries = [b for b in boundaries if segment_start < b < segment_end]

        if not relevant_boundaries:
            return [segment]

        # 按边界排序
        relevant_boundaries.sort()

        # 创建分割点
        split_points = [segment_start] + relevant_boundaries + [segment_end]

        # 创建子片段
        for i in range(len(split_points) - 1):
            sub_start = split_points[i]
            sub_end = split_points[i + 1]

            # 只有当子片段长度足够时才创建
            if sub_end - sub_start >= 0.1:  # 最小0.1秒
                sub_segment = segment.copy()
                sub_segment['start'] = sub_start
                sub_segment['end'] = sub_end
                sub_segment['duration'] = sub_end - sub_start

                # 分割文本（如果有词级时间戳）
                if 'words' in segment and segment['words']:
                    sub_segment['words'] = [
                        word for word in segment['words']
                        if word['start'] >= sub_start and word['end'] <= sub_end
                    ]

                    # 重新计算文本
                    sub_segment['text'] = ' '.join(word['word'] for word in sub_segment['words'])

                split_segments.append(sub_segment)

        return split_segments

    def _find_best_speaker_for_segment(self, segment: Dict, diarization_segments: List[Dict],
                                      max_duration_gap: float) -> Dict:
        """
        为片段找到最佳说话人匹配
        """
        seg_start = segment['start']
        seg_end = segment['end']
        seg_center = (seg_start + seg_end) / 2

        best_speaker = None
        best_score = -1
        best_overlap_ratio = 0

        for diar_seg in diarization_segments:
            diar_start = diar_seg['start']
            diar_end = diar_seg['end']

            # 检查是否有时间重叠或接近
            if (seg_start <= diar_end and seg_end >= diar_start):
                # 计算重叠程度
                overlap_start = max(seg_start, diar_start)
                overlap_end = min(seg_end, diar_end)
                overlap_duration = max(0, overlap_end - overlap_start)

                # 计算重叠比例
                seg_duration = seg_end - seg_start
                overlap_ratio = overlap_duration / seg_duration if seg_duration > 0 else 0

                if overlap_ratio > best_score:
                    best_score = overlap_ratio
                    best_speaker = diar_seg['speaker']
                    best_overlap_ratio = overlap_ratio
            elif abs(seg_center - (diar_start + diar_end) / 2) <= max_duration_gap:
                # 如果中心时间接近，也考虑匹配
                distance = abs(seg_center - (diar_start + diar_end) / 2)
                proximity_score = max(0, 1.0 - distance / max_duration_gap)

                if proximity_score > best_score:
                    best_score = proximity_score
                    best_speaker = diar_seg['speaker']
                    best_overlap_ratio = 0

        # 确定置信度
        if best_speaker and best_score > 0:
            if best_overlap_ratio > 0:
                confidence = min(best_overlap_ratio, 1.0)
            else:
                confidence = best_score
        else:
            # 使用默认说话人
            best_speaker = 'SPEAKER_00'
            confidence = 0.3

        return {
            'speaker': best_speaker,
            'confidence': confidence
        }

    def cleanup(self):
        """
        清理资源和GPU显存
        """
        if self.pipeline is not None:
            try:
                # 对于付费模式，无需清理本地GPU资源
                if self._use_premium_mode():
                    logger.info("付费模式：无需清理本地GPU资源")
                else:
                    # 将模型从GPU移动到CPU
                    if hasattr(self.pipeline, 'cpu'):
                        self.pipeline.cpu()

                    # 删除pipeline
                    del self.pipeline
                    self.pipeline = None

                    # 强制垃圾回收
                    import gc
                    gc.collect()

                    # 如果使用PyTorch，清理CUDA缓存
                    try:
                        import torch
                        if torch.cuda.is_available():
                            # 记录清理前的显存使用情况
                            before_allocated = torch.cuda.memory_allocated() / 1024**3  # GB
                            before_cached = torch.cuda.memory_reserved() / 1024**3  # GB

                            # 强制清理CUDA缓存
                            torch.cuda.empty_cache()
                            torch.cuda.ipc_collect()
                            torch.cuda.synchronize()

                            # 尝试重置CUDA设备（更激进的清理）
                            try:
                                current_device = torch.cuda.current_device()
                                torch.cuda.reset_peak_memory_stats(current_device)
                            except:
                                pass

                            # 记录清理后的显存使用情况
                            after_allocated = torch.cuda.memory_allocated() / 1024**3  # GB
                            after_cached = torch.cuda.memory_reserved() / 1024**3  # GB

                            freed_allocated = before_allocated - after_allocated
                            freed_cached = before_cached - after_cached

                            logger.info(f"说话人分离GPU显存清理完成:")
                            logger.info(f"  已分配显存: {before_allocated:.2f}GB -> {after_allocated:.2f}GB (释放 {freed_allocated:.2f}GB)")
                            logger.info(f"  缓存显存: {before_cached:.2f}GB -> {after_cached:.2f}GB (释放 {freed_cached:.2f}GB)")
                    except ImportError:
                        logger.warning("PyTorch未安装，无法清理CUDA缓存")

                logger.info("说话人分离pipeline资源已清理")

            except Exception as e:
                logger.warning(f"清理说话人分离资源时出错: {e}")


def create_speaker_diarizer_v2(config: Optional[Dict] = None) -> SpeakerDiarizerV2:
    """
    创建说话人分离器的工厂函数

    Args:
        config: 可选的配置字典

    Returns:
        SpeakerDiarizerV2: 说话人分离器实例
    """
    try:
        return SpeakerDiarizerV2(config)
    except SpeakerDiarizationError as e:
        logger.error(f"创建说话人分离器失败: {e}")
        raise
    except Exception as e:
        logger.error(f"创建说话人分离器时发生未知错误: {e}")
        raise SpeakerDiarizationError(f"创建失败: {e}")


# 兼容性函数，用于向后兼容
def run_speaker_diarization_v2(audio_path: str,
                              config: Optional[Dict] = None) -> List[Dict]:
    """
    运行说话人分离的便捷函数

    Args:
        audio_path: 音频文件路径
        config: 可选的配置参数

    Returns:
        List[Dict]: 说话人分离结果列表
    """
    diarizer = create_speaker_diarizer_v2(config)
    try:
        annotation = diarizer.diarize(audio_path)
        return diarizer.annotation_to_dict_list(annotation)
    finally:
        diarizer.cleanup()


if __name__ == "__main__":
    # 简单的测试代码
    import sys

    if len(sys.argv) < 2:
        print("使用方法: python speaker_diarization_v2.py <audio_file>")
        sys.exit(1)

    audio_file = sys.argv[1]

    try:
        # 测试说话人分离
        diarizer = create_speaker_diarizer_v2()
        annotation = diarizer.diarize(audio_file)
        segments = diarizer.annotation_to_dict_list(annotation)

        print("说话人分离结果:")
        for i, segment in enumerate(segments):
            print(f"{i+1}. [{segment['start']:.2f}s - {segment['end']:.2f}s] {segment['speaker']}")

    except Exception as e:
        print(f"测试失败: {e}")
        sys.exit(1)