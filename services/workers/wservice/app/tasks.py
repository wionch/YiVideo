# services/workers/wservice/app/tasks.py
# -*- coding: utf-8 -*-

"""
wservice - 通用工作流服务

负责与GPU无关的、可复用的工作流任务节点，例如字幕文件生成、合并与校正。
"""

import os
import time
import json
import asyncio
from collections import defaultdict
from typing import List, Dict, Any, Tuple

from services.common.logger import get_logger
from services.common import state_manager
from services.common.context import StageExecution, WorkflowContext
from services.common.config_loader import CONFIG
from services.common.file_service import get_file_service
from services.common.parameter_resolver import resolve_parameters, get_param_with_fallback

# 导入 wservice 自己的 Celery app (将在下一步创建)
from .celery_app import celery_app

# 导入重构后的公共字幕合并模块
from services.common.subtitle.subtitle_merger import (
    create_subtitle_merger,
    create_word_level_merger,
    validate_speaker_segments
)
# 导入公共字幕校正模块
from services.common.subtitle.subtitle_correction import SubtitleCorrector
# 导入AI字幕优化模块
from services.common.subtitle.subtitle_optimizer import SubtitleOptimizer
from services.common.subtitle.metrics import metrics_collector

logger = get_logger('wservice_tasks')


class TtsMerger:
    """
    根据TTS参考音的要求，对字幕片段进行智能合并与分割。
    """
    def __init__(self, config: Dict[str, Any]):
        """
        初始化合并器。

        Args:
            config (Dict[str, Any]): 节点的配置参数。
        """
        self.min_duration = config.get('min_duration', 3.0)
        self.max_duration = config.get('max_duration', 10.0)
        self.max_gap = config.get('max_gap', 1.0)
        self.split_on_punctuation = config.get('split_on_punctuation', False)
        self.PUNCTUATION = set("。！？.”")
        logger.info(f"TtsMerger 初始化: min_duration={self.min_duration}, max_duration={self.max_duration}, max_gap={self.max_gap}, split_on_punctuation={self.split_on_punctuation}")

    def merge_segments(self, segments: List[Dict]) -> List[Dict]:
        """
        主入口函数，执行完整的合并与优化流程。

        Args:
            segments (List[Dict]): 原始字幕片段列表。

        Returns:
            List[Dict]: 处理后的字幕片段列表。
        """
        if not segments:
            return []

        # 1. 按说话人对所有片段进行分组
        speaker_groups = self._group_by_speaker(segments)

        final_segments = []
        for speaker, speaker_segments in speaker_groups.items():
            logger.debug(f"正在处理说话人 '{speaker}' 的 {len(speaker_segments)} 个片段...")
            # 2. 对每个说话人的片段执行初步合并
            preliminary_merged = self._preliminary_merge(speaker_segments)

            # 3. 对合并后的片段进行优化调整
            optimized_segments = self._optimize_segments(preliminary_merged)
            final_segments.extend(optimized_segments)

        # 4. 按开始时间对最终结果排序
        final_segments.sort(key=lambda x: x['start'])

        # 5. 为所有最终片段重新分配唯一的、从1开始的ID
        for i, segment in enumerate(final_segments):
            segment['id'] = i + 1

        logger.info(f"合并与优化完成，共生成 {len(final_segments)} 个片段。")
        return final_segments

    def _group_by_speaker(self, segments: List[Dict]) -> Dict[str, List[Dict]]:
        """按说话人对片段进行分组。"""
        groups = defaultdict(list)
        for segment in segments:
            speaker = segment.get('speaker', 'SPEAKER_UNKNOWN')
            groups[speaker].append(segment)
        return groups

    def _preliminary_merge(self, segments: List[Dict]) -> List[Dict]:
        """阶段一：初步迭代合并。"""
        if not segments:
            return []

        merged_groups = []
        current_group = [segments[0]]

        for i in range(1, len(segments)):
            current_segment = segments[i]
            last_segment_in_group = current_group[-1]

            # 条件检查
            gap = current_segment['start'] - last_segment_in_group['end']

            # 计算当前组的总时长
            group_start = current_group[0]['start']
            group_end = last_segment_in_group['end']
            current_group_duration = group_end - group_start

            new_total_duration = (current_segment['end'] - group_start)

            # 检查标点
            ends_with_punctuation = False
            if self.split_on_punctuation:
                if last_segment_in_group['text'].strip() and last_segment_in_group['text'].strip()[-1] in self.PUNCTUATION:
                    ends_with_punctuation = True

            # 决策
            if gap <= self.max_gap and new_total_duration <= self.max_duration and not ends_with_punctuation:
                current_group.append(current_segment)
            else:
                merged_groups.append(self._finalize_group(current_group))
                current_group = [current_segment]

        # 处理最后一组
        if current_group:
            merged_groups.append(self._finalize_group(current_group))

        return merged_groups

    def _finalize_group(self, group: List[Dict]) -> Dict:
        """将一个片段组固化成一个合并后的片段。"""
        if not group:
            return {}

        start_time = group[0]['start']
        end_time = group[-1]['end']
        text = " ".join(s['text'].strip() for s in group)

        # 合并 words 列表
        words = []
        for s in group:
            if 'words' in s:
                words.extend(s['words'])

        return {
            'start': start_time,
            'end': end_time,
            'duration': end_time - start_time,
            'text': text,
            'speaker': group[0].get('speaker', 'SPEAKER_UNKNOWN'),
            'words': words
        }

    def _optimize_segments(self, segments: List[Dict]) -> List[Dict]:
        """阶段二：优化调整，处理过长和过短的片段。"""
        optimized = []
        for segment in segments:
            if segment['duration'] > self.max_duration:
                optimized.extend(self._split_long_segment(segment))
            else:
                optimized.append(segment)

        # 注意：二次合并逻辑较为复杂，此处暂时简化为直接过滤，后续可根据需求增强
        final_segments = self._handle_short_segments(optimized)
        return final_segments

    def _split_long_segment(self, segment: Dict) -> List[Dict]:
        """智能分割过长片段，利用词级时间戳和标点符号。"""
        logger.warning(f"检测到过长片段 (时长: {segment['duration']:.2f}s > {self.max_duration:.2f}s)，将进行智能分割。")

        words = segment.get('words')
        if not words:
            # 如果没有词级时间戳，回退到暴力分割
            return self._split_long_segment_fallback(segment)

        split_segments = []
        current_split_words = []

        for i, word in enumerate(words):
            current_split_words.append(word)

            current_duration = word['end'] - current_split_words[0]['start']

            # 寻找分割点
            # 条件1: 当前时长已接近max_duration
            # 条件2: 遇到句末标点
            # 条件3: 是最后一个词
            is_last_word = (i == len(words) - 1)
            is_punctuation_stop = word['word'].strip() and word['word'].strip()[-1] in self.PUNCTUATION
            is_duration_exceeded = current_duration >= self.max_duration

            if is_duration_exceeded or is_punctuation_stop or is_last_word:
                if current_split_words:
                    new_seg = self._finalize_group(current_split_words)
                    # 只有当新片段时长有效时才添加
                    if new_seg['duration'] > 0.1:
                        split_segments.append(new_seg)
                    current_split_words = []

        # 如果循环结束后仍有剩余的词，处理最后一部分
        if current_split_words:
            new_seg = self._finalize_group(current_split_words)
            if new_seg['duration'] > 0.1:
                split_segments.append(new_seg)

        return split_segments

    def _split_long_segment_fallback(self, segment: Dict) -> List[Dict]:
        """没有词级时间戳时的暴力分割方法。"""
        num_splits = int(segment['duration'] // self.max_duration) + 1
        split_duration = segment['duration'] / num_splits

        split_segments = []
        current_start = segment['start']

        for i in range(num_splits):
            split_end = min(current_start + split_duration, segment['end'])
            if split_end > current_start:
                new_seg = segment.copy()
                new_seg['start'] = current_start
                new_seg['end'] = split_end
                new_seg['duration'] = split_end - current_start
                new_seg['text'] = f"[SPLIT {i+1}/{num_splits}] {segment['text']}"
                new_seg['words'] = [] # 清空words，因为无法准确分割
                split_segments.append(new_seg)
            current_start = split_end

        return split_segments

    def _handle_short_segments(self, segments: List[Dict]) -> List[Dict]:
        """处理过短的片段，尝试与相邻片段进行二次合并。"""
        if not segments:
            return []

        # 创建一个可变列表用于操作
        mutable_segments = list(segments)
        i = 0
        while i < len(mutable_segments):
            current_seg = mutable_segments[i]

            if current_seg['duration'] < self.min_duration:
                # 尝试与后一个片段合并
                if i + 1 < len(mutable_segments):
                    next_seg = mutable_segments[i+1]
                    # 检查说话人是否一致，以及合并后是否超长
                    if current_seg['speaker'] == next_seg['speaker']:
                        merged_duration = (next_seg['end'] - current_seg['start'])
                        if merged_duration <= self.max_duration:
                            logger.debug(f"二次合并：将短片段 {i} 与后一个片段 {i+1} 合并。")
                            merged_seg = self._finalize_group([current_seg, next_seg])
                            mutable_segments[i] = merged_seg
                            del mutable_segments[i+1]
                            # 合并后，停在当前位置，再次检查新合并的片段是否仍然过短
                            continue

                # 如果无法向后合并，尝试与前一个片段合并
                if i > 0:
                    prev_seg = mutable_segments[i-1]
                    if current_seg['speaker'] == prev_seg['speaker']:
                        merged_duration = (current_seg['end'] - prev_seg['start'])
                        if merged_duration <= self.max_duration:
                            logger.debug(f"二次合并：将短片段 {i} 与前一个片段 {i-1} 合并。")
                            merged_seg = self._finalize_group([prev_seg, current_seg])
                            mutable_segments[i-1] = merged_seg
                            del mutable_segments[i]
                            # 合并后，回退一个索引，以便再次检查新合并的片段
                            i -= 1
                            continue

            i += 1

        # 最后，过滤掉仍然过短的片段
        final_segments = [seg for seg in mutable_segments if seg['duration'] >= self.min_duration]

        if len(final_segments) < len(mutable_segments):
            logger.info(f"经过二次合并后，仍过滤掉 {len(mutable_segments) - len(final_segments)} 个无法合并的短片段。")

        return final_segments




# ============================================================================
# 数据读取辅助函数 (从 faster_whisper_service 迁移)
# ============================================================================

def convert_annotation_to_segments(annotation) -> List[Dict]:
    """
    将pyannote的DiarizeOutput或Annotation对象转换为说话人片段列表

    Args:
        annotation: pyannote的DiarizeOutput或Annotation对象

    Returns:
        List[Dict]: 说话人片段列表，每个片段包含start, end, speaker信息
    """
    segments = []

    try:
        logger.debug(f"convert_annotation_to_segments: 输入类型 {type(annotation)}")

        # 检查是否是DiarizeOutput类型
        if hasattr(annotation, 'speaker_diarization'):
            # DiarizeOutput对象，使用speaker_diarization属性
            speaker_annotation = annotation.speaker_diarization
            logger.debug("检测到DiarizeOutput对象，使用speaker_diarization属性")
        else:
            # 直接是Annotation对象
            speaker_annotation = annotation
            logger.debug("检测到Annotation对象，直接使用")

        # 遍历说话人分离结果
        segment_count = 0
        for turn, _, speaker in speaker_annotation.itertracks(yield_label=True):
            segments.append({
                'start': float(turn.start),
                'end': float(turn.end),
                'duration': float(turn.end - turn.start),
                'speaker': str(speaker)
            })
            segment_count += 1

            # 调试信息（只显示前5个）
            if segment_count <= 5:
                logger.debug(f"说话人片段 {segment_count}: {turn.start:.2f}s-{turn.end:.2f}s, 说话人: {speaker}")

        # 按开始时间排序
        segments.sort(key=lambda x: x['start'])
        logger.info(f"成功提取到 {len(segments)} 个说话人片段")

        # 显示说话人统计
        speakers = set(seg['speaker'] for seg in segments)
        logger.info(f"识别到的说话人: {sorted(speakers)}")

        return segments

    except Exception as e:
        logger.error(f"转换annotation到字典列表失败: {e}")
        import traceback
        traceback.print_exc()

        # 返回默认的模拟数据
        logger.warning("返回默认说话人片段")
        return [{
            'start': 0.0,
            'end': 300.0,
            'duration': 300.0,
            'speaker': 'SPEAKER_00'
        }]

def load_segments_from_file(segments_file: str) -> list:
    """
    从文件加载segments数据
    """
    try:
        if not os.path.exists(segments_file):
            logger.warning(f"Segments文件不存在: {segments_file}")
            return []
        with open(segments_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and 'segments' in data:
            return data['segments']
        else:
            logger.warning(f"Segments文件格式无效: {segments_file}")
            return []
    except Exception as e:
        logger.error(f"加载segments文件失败: {e}")
        return []

def load_speaker_data_from_file(diarization_file: str) -> dict:
    """
    从文件加载说话人分离数据
    """
    try:
        if not os.path.exists(diarization_file):
            logger.warning(f"说话人分离文件不存在: {diarization_file}")
            return {}
        with open(diarization_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            speaker_segments = data.get('speaker_enhanced_segments')
            diarization_segments = data.get('diarization_segments')
            if speaker_segments is None and isinstance(data.get('segments'), list):
                speaker_segments = data.get('segments')
                data['speaker_enhanced_segments'] = speaker_segments
            if diarization_segments is None and isinstance(data.get('segments'), list):
                diarization_segments = data.get('segments')
                data['diarization_segments'] = diarization_segments
            logger.info(
                f"说话人分离数据加载成功: {diarization_file}, "
                f"keys={list(data.keys())}, "
                f"speaker_enhanced_segments={len(speaker_segments) if isinstance(speaker_segments, list) else 'N/A'}, "
                f"diarization_segments={len(diarization_segments) if isinstance(diarization_segments, list) else 'N/A'}"
            )
        required_fields = ['speaker_enhanced_segments', 'diarization_segments']
        for field in required_fields:
            if field not in data:
                # This is a soft warning, data might still be usable
                pass
        return data
    except Exception as e:
        logger.error(f"加载说话人分离文件失败: {e}")
        return {}

def normalize_local_input_path(file_path: str, shared_storage_path: str) -> str:
    """
    规范化本地文件路径，支持省略开头的 /share 或相对路径。
    """
    if not file_path:
        return file_path
    if file_path.startswith(("http://", "https://", "minio://")):
        return file_path
    if file_path.startswith(("share/", "share\\")):
        candidate = "/" + file_path.lstrip("/\\")
        if os.path.exists(candidate):
            return candidate
    if not os.path.isabs(file_path):
        candidate = os.path.join(shared_storage_path, file_path)
        if os.path.exists(candidate):
            return candidate
    return file_path

def get_segments_data(stage_output: dict, field_name: str = None) -> list:
    """
    统一的数据获取接口，支持新旧格式
    """
    if field_name and field_name in stage_output:
        segments = stage_output[field_name]
        if segments and isinstance(segments, list):
            return segments
    segments_file = stage_output.get('segments_file')
    if segments_file:
        return load_segments_from_file(segments_file)
    return []

def segments_to_word_timestamp_json(segments: list, include_segment_info: bool = True) -> str:
    """
    将faster-whisper的segments转换为包含词级时间戳的JSON格式
    """
    result = {
        "format": "word_timestamps",
        "total_segments": len(segments),
        "segments": []
    }
    for i, segment in enumerate(segments):
        segment_data = {
            "id": i + 1,
            "start": segment["start"],
            "end": segment["end"],
            "text": segment["text"].strip()
        }
        if include_segment_info:
            segment_data["srt_time"] = f"{int(segment['start'] // 3600):02}:{int((segment['start'] % 3600) // 60):02}:{int(segment['start'] % 60):02},{int((segment['start'] * 1000) % 1000):03} --> {int(segment['end'] // 3600):02}:{int((segment['end'] % 3600) // 60):02}:{int(segment['end'] % 60):02},{int((segment['end'] * 1000) % 1000):03}"
        if "words" in segment and segment["words"]:
            segment_data["words"] = []
            for word_info in segment["words"]:
                word_data = {
                    "word": word_info["word"],
                    "start": word_info["start"],
                    "end": word_info["end"],
                    "confidence": word_info.get("confidence", 0.0)
                }
                segment_data["words"].append(word_data)
        else:
            segment_data["words"] = [{
                "word": segment["text"].strip(),
                "start": segment["start"],
                "end": segment["end"],
                "confidence": 1.0
            }]
        result["segments"].append(segment_data)
    return json.dumps(result, indent=2, ensure_ascii=False)

def get_speaker_data(stage_output: dict) -> dict:
    """
    获取说话人分离数据，支持新旧格式
    """
    if 'speaker_enhanced_segments' in stage_output:
        return {
            'speaker_enhanced_segments': stage_output.get('speaker_enhanced_segments'),
            'diarization_segments': stage_output.get('diarization_segments'),
            'detected_speakers': stage_output.get('detected_speakers', []),
            'speaker_statistics': stage_output.get('speaker_statistics', {})
        }
    if 'statistics' in stage_output and isinstance(stage_output['statistics'], dict):
        statistics = stage_output['statistics']
        speaker_data = {
            'detected_speakers': statistics.get('detected_speakers', []),
            'speaker_statistics': statistics.get('speaker_statistics', {}),
            'diarization_duration': statistics.get('diarization_duration', 0)
        }
        diarization_file = stage_output.get('diarization_file')
        if diarization_file:
            detailed_data = load_speaker_data_from_file(diarization_file)
            speaker_data.update({
                'speaker_enhanced_segments': detailed_data.get('speaker_enhanced_segments'),
                'diarization_segments': detailed_data.get('diarization_segments')
            })
        return speaker_data
    diarization_file = stage_output.get('diarization_file')
    if diarization_file:
        return load_speaker_data_from_file(diarization_file)
    return {}

# ============================================================================
# Celery 任务 (从 faster_whisper_service 迁移)
# ============================================================================

@celery_app.task(bind=True, name='wservice.generate_subtitle_files')
def generate_subtitle_files(self, context: dict) -> dict:
    """
    独立字幕文件生成任务节点。
    该任务已迁移到统一的 BaseNodeExecutor 框架。
    """
    from services.workers.wservice.executors import WServiceGenerateSubtitleFilesExecutor

    workflow_context = WorkflowContext(**context)
    executor = WServiceGenerateSubtitleFilesExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()


@celery_app.task(name='wservice.merge_speaker_segments', bind=True)
def merge_speaker_segments(self, context: dict) -> dict:
    """
    合并转录字幕与说话人时间段（片段级）。
    该任务已迁移到统一的 BaseNodeExecutor 框架。
    """
    from services.workers.wservice.executors import WServiceMergeSpeakerSegmentsExecutor

    workflow_context = WorkflowContext(**context)
    executor = WServiceMergeSpeakerSegmentsExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()


@celery_app.task(name='wservice.merge_with_word_timestamps', bind=True)
def merge_with_word_timestamps(self, context: dict) -> dict:
    """
    使用词级时间戳进行精确字幕合并。
    该任务已迁移到统一的 BaseNodeExecutor 框架。
    """
    from services.workers.wservice.executors import WServiceMergeWithWordTimestampsExecutor

    workflow_context = WorkflowContext(**context)
    executor = WServiceMergeWithWordTimestampsExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()


@celery_app.task(bind=True, name='wservice.correct_subtitles')
def correct_subtitles(self, context: dict) -> dict:
    """
    字幕AI校正任务节点。
    该任务已迁移到统一的 BaseNodeExecutor 框架。
    """
    from services.workers.wservice.executors import WServiceCorrectSubtitlesExecutor

    workflow_context = WorkflowContext(**context)
    executor = WServiceCorrectSubtitlesExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()


@celery_app.task(bind=True, name='wservice.ai_optimize_subtitles')
def ai_optimize_subtitles(self, context: dict) -> dict:
    """
    AI字幕优化任务节点。
    该任务已迁移到统一的 BaseNodeExecutor 框架。
    """
    from services.workers.wservice.executors import WServiceAIOptimizeSubtitlesExecutor

    workflow_context = WorkflowContext(**context)
    executor = WServiceAIOptimizeSubtitlesExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()


def _get_segments_from_source_stages(workflow_context: WorkflowContext, source_stage_names: List[str]) -> Tuple[List[Dict], str]:
    """
    从指定的前置阶段列表中安全地获取字幕片段。
    它会按顺序查找，直到找到有效的片段数据为止。

    Args:
        workflow_context (WorkflowContext): 当前工作流的上下文。
        source_stage_names (List[str]): 要搜索的阶段名称列表。

    Returns:
        Tuple[List[Dict], str]: 一个元组，包含找到的片段列表和来源阶段的名称。

    Raises:
        ValueError: 如果在所有指定的阶段中都找不到有效的片段数据。
    """
    source_stage = None
    for name in source_stage_names:
        if name in workflow_context.stages and workflow_context.stages[name].status in ['SUCCESS', 'COMPLETED']:
            source_stage = workflow_context.stages[name]
            logger.info(f"找到潜在的源数据于阶段: '{name}'")
            break

    if not source_stage:
        raise ValueError(f"无法从任何有效的前置节点 {source_stage_names} 获取字幕片段。")

    # 策略1: 尝试从 'merged_segments' 获取 (这是合并任务的典型输出)
    segments = source_stage.output.get('merged_segments')
    if segments and isinstance(segments, list):
        logger.info(f"成功从 '{source_stage.name}' 的 'merged_segments' 字段获取 {len(segments)} 个片段。")
        return segments, source_stage.name

    # 策略2: 回退到从文件加载 (转录或优化任务的输出)
    segments_file = (
        source_stage.output.get('segments_file')
        or source_stage.output.get('optimized_file_path')
        or source_stage.output.get('merged_segments_file')
    )
    if segments_file and os.path.exists(segments_file):
        segments = load_segments_from_file(segments_file)
        if segments:
            logger.info(f"成功从文件 '{segments_file}' 加载 {len(segments)} 个片段。")
            return segments, source_stage.name

    # 策略3: 最后尝试从 'segments' 字段直接获取
    segments = source_stage.output.get('segments')
    if segments and isinstance(segments, list):
        logger.info(f"成功从 '{source_stage.name}' 的 'segments' 字段获取 {len(segments)} 个片段。")
        return segments, source_stage.name

    raise ValueError(f"在源阶段 '{source_stage.name}' 的输出中找不到有效的 'segments', 'merged_segments' 或 'segments_file'。")


@celery_app.task(bind=True, name='wservice.prepare_tts_segments')
def prepare_tts_segments(self, context: dict) -> dict:
    """
    为 TTS 参考音准备和优化字幕片段。
    该任务已迁移到统一的 BaseNodeExecutor 框架。
    """
    from services.workers.wservice.executors import WServicePrepareTtsSegmentsExecutor

    workflow_context = WorkflowContext(**context)
    executor = WServicePrepareTtsSegmentsExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()
