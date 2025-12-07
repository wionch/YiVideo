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
        required_fields = ['speaker_enhanced_segments', 'diarization_segments']
        for field in required_fields:
            if field not in data:
                # This is a soft warning, data might still be usable
                pass
        return data
    except Exception as e:
        logger.error(f"加载说话人分离文件失败: {e}")
        return {}

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
    独立字幕文件生成任务节点
    
    支持单任务模式调用，通过input_data传入参数：
    - segments_file: 转录数据文件路径（JSON格式，包含segments数组）
    - audio_duration: 音频时长（可选）
    - language: 语言代码（可选，默认'unknown'）
    - output_filename: 输出文件名前缀（可选，默认'subtitle'）
    """
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        # --- Parameter Resolution (采用项目标准模式) ---
        from services.common.parameter_resolver import resolve_parameters, get_param_with_fallback
        
        resolved_params = {}
        node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})
        if node_params:
            try:
                resolved_params = resolve_parameters(node_params, workflow_context.model_dump())
                logger.info(f"[{stage_name}] 参数解析完成: {resolved_params}")
            except ValueError as e:
                logger.error(f"[{stage_name}] 参数解析失败: {e}")
                raise e
        
        # 记录实际使用的输入参数
        recorded_input_params = resolved_params.copy() if resolved_params else {}
        
        # --- 文件下载准备 ---
        file_service = get_file_service()
        
        # --- 智能参数获取：支持单任务模式和工作流模式 ---
        segments = None
        audio_path = None
        audio_duration = 0
        language = 'unknown'
        enable_word_timestamps = True
        data_source = None
        
        # 1. 优先从 input_data / node_params 获取 segments_file（单任务模式）
        segments_file = get_param_with_fallback(
            'segments_file',
            resolved_params,
            workflow_context,
            fallback_from_input_data=True
        )
        
        if segments_file:
            # 单任务模式：从文件加载segments
            logger.info(f"[{stage_name}] 单任务模式：从 segments_file 加载数据: {segments_file}")
            # 下载文件（支持MinIO URL）
            segments_file = file_service.resolve_and_download(segments_file, workflow_context.shared_storage_path)
            segments = load_segments_from_file(segments_file)
            
            if not segments:
                raise ValueError(f"无法从文件加载segments数据: {segments_file}")
            
            # 从参数获取其他可选信息
            audio_duration = get_param_with_fallback('audio_duration', resolved_params, workflow_context) or 0
            language = get_param_with_fallback('language', resolved_params, workflow_context) or 'unknown'
            enable_word_timestamps = any('words' in seg and seg['words'] for seg in segments)
            
            # 生成输出文件名：优先使用参数，其次从segments_file提取
            output_filename = get_param_with_fallback('output_filename', resolved_params, workflow_context)
            if not output_filename:
                output_filename = os.path.splitext(os.path.basename(segments_file))[0]
                # 清理常见后缀
                for suffix in ['_segments', '_transcribe_data', '_transcription']:
                    if output_filename.endswith(suffix):
                        output_filename = output_filename[:-len(suffix)]
                        break
            
            audio_path = output_filename  # 用于生成文件名
            data_source = 'input_data.segments_file'
            recorded_input_params['segments_file'] = segments_file
            recorded_input_params['data_source'] = data_source
        else:
            # 2. 回退到工作流模式：从 faster_whisper.transcribe_audio 阶段获取
            transcribe_stage = workflow_context.stages.get('faster_whisper.transcribe_audio')
            if not transcribe_stage or transcribe_stage.status not in ['SUCCESS', 'COMPLETED']:
                raise ValueError("无法获取转录结果：请提供 segments_file 参数，或确保 faster_whisper.transcribe_audio 任务已成功完成")

            transcribe_output = transcribe_stage.output
            if not transcribe_output or not isinstance(transcribe_output, dict):
                raise ValueError("转录结果数据格式错误")

            segments = get_segments_data(transcribe_output, 'segments')
            audio_path = transcribe_output.get('audio_path')
            audio_duration = transcribe_output.get('audio_duration', 0)
            language = transcribe_output.get('language', 'unknown')
            enable_word_timestamps = transcribe_output.get('enable_word_timestamps', True)
            data_source = 'faster_whisper.transcribe_audio'
            recorded_input_params['data_source'] = data_source

            if not segments or not audio_path:
                raise ValueError("转录结果中缺少必要的数据（segments 或 audio_path）")
        
        # 记录输入参数
        workflow_context.stages[stage_name].input_params = recorded_input_params
        
        logger.info(f"[{stage_name}] 数据来源: {data_source}, segments数量: {len(segments)}")
        
        # --- 说话人信息处理（仅工作流模式） ---
        diarize_stage = workflow_context.stages.get('pyannote_audio.diarize_speakers')
        has_speaker_info = False

        service_config = CONFIG.get('faster_whisper_service', {})
        speaker_segments = None
        speaker_enhanced_segments = None
        detected_speakers = []
        speaker_statistics = {}

        if diarize_stage and diarize_stage.status in ['SUCCESS', 'COMPLETED']:
            diarize_output = diarize_stage.output
            if diarize_output and isinstance(diarize_output, dict):
                speaker_data = get_speaker_data(diarize_output)
                speaker_segments = speaker_data.get('speaker_enhanced_segments')
                detected_speakers = speaker_data.get('detected_speakers', [])
                speaker_statistics = speaker_data.get('speaker_statistics', {})

                if speaker_segments and segments and enable_word_timestamps:
                    try:
                        merge_config = service_config.get('subtitle_merge', {})
                        merger = create_word_level_merger(speaker_segments, merge_config)
                        speaker_enhanced_segments = merger.merge(segments)
                        has_speaker_info = True
                    except Exception as e:
                        logger.warning(f"[{stage_name}] 说话人信息合并失败: {e}")
                        has_speaker_info = False
                        speaker_enhanced_segments = None
                else:
                    has_speaker_info = bool(speaker_segments)

        subtitles_dir = os.path.join(workflow_context.shared_storage_path, "subtitles")
        os.makedirs(subtitles_dir, exist_ok=True)
        base_filename = os.path.splitext(os.path.basename(audio_path))[0]
        subtitle_filename = f"{base_filename}.srt"
        subtitle_path = os.path.join(subtitles_dir, subtitle_filename)

        with open(subtitle_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(segments):
                start_str = f"{int(segment['start']//3600):02d}:{int((segment['start']%3600)//60):02d}:{int(segment['start']%60):02d},{int((segment['start']%1)*1000):03d}"
                end_str = f"{int(segment['end']//3600):02d}:{int((segment['end']%3600)//60):02d}:{int(segment['end']%60):02d},{int((segment['end']%1)*1000):03d}"
                f.write(f"{i+1}\n{start_str} --> {end_str}\n{segment['text'].strip()}\n\n")

        # 构建精简的输出数据，避免重复的路径信息
        output_data = {
            # 核心字幕文件：作为主要输出字段
            "subtitle_path": subtitle_path,
            # 统一文件引用：通过subtitle_files对象提供所有文件的统一访问
            "subtitle_files": {
                "basic": subtitle_path
            }
        }

        if has_speaker_info and speaker_enhanced_segments:
            speaker_srt_filename = f"{base_filename}_with_speakers.srt"
            speaker_srt_path = os.path.join(subtitles_dir, speaker_srt_filename)
            with open(speaker_srt_path, "w", encoding="utf-8") as f:
                for i, segment in enumerate(speaker_enhanced_segments):
                    start_str = f"{int(segment['start']//3600):02d}:{int((segment['start']%3600)//60):02d}:{int(segment['start']%60):02d},{int((segment['start']%1)*1000):03d}"
                    end_str = f"{int(segment['end']//3600):02d}:{int((segment['end']%3600)//60):02d}:{int(segment['end']%60):02d},{int((segment['end']%1)*1000):03d}"
                    speaker = segment.get("speaker", "UNKNOWN")
                    f.write(f"{i+1}\n{start_str} --> {end_str}\n[{speaker}] {segment['text'].strip()}\n\n")
            # 移除重复的speaker_srt_path字段，统一通过subtitle_files访问
            output_data["subtitle_files"]["with_speakers"] = speaker_srt_path

        if enable_word_timestamps and segments:
            word_timestamps_filename = f"{base_filename}_word_timestamps.json"
            word_timestamps_json_path = os.path.join(subtitles_dir, word_timestamps_filename)
            json_content = segments_to_word_timestamp_json(segments, include_segment_info=True)
            with open(word_timestamps_json_path, "w", encoding="utf-8") as f:
                f.write(json_content)
            # 移除重复的word_timestamps_json_path字段，统一通过subtitle_files访问
            output_data["subtitle_files"]["word_timestamps"] = word_timestamps_json_path

        # 始终生成完整的JSON格式字幕文件（包含所有元数据）
        json_subtitle_filename = f"{base_filename}_subtitle.json"
        json_subtitle_path = os.path.join(subtitles_dir, json_subtitle_filename)
        json_subtitle_content = {
            "format": "yivideo_subtitle",
            "version": "1.0",
            "metadata": {
                "language": language,
                "audio_duration": audio_duration,
                "total_segments": len(segments),
                "has_word_timestamps": enable_word_timestamps,
                "data_source": data_source
            },
            "segments": segments
        }
        with open(json_subtitle_path, "w", encoding="utf-8") as f:
            json.dump(json_subtitle_content, f, ensure_ascii=False, indent=2)
        output_data["json_path"] = json_subtitle_path
        output_data["subtitle_files"]["json"] = json_subtitle_path

        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)

    return workflow_context.model_dump()


@celery_app.task(name='wservice.merge_speaker_segments', bind=True)
def merge_speaker_segments(self, context: dict) -> dict:
    """
    合并转录字幕与说话人时间段(片段级)
    
    新增input_data参数支持，支持单任务模式调用：
    - segments_data: 直接传入转录片段数据
    - speaker_segments_data: 直接传入说话人片段数据  
    - segments_file: 转录数据文件路径
    - diarization_file: 说话人分离数据文件路径
    """
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)
    
    try:
        # --- Parameter Resolution (采用项目标准模式) ---
        resolved_params = {}
        node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})
        if node_params:
            try:
                from services.common.parameter_resolver import resolve_parameters, get_param_with_fallback
                resolved_params = resolve_parameters(node_params, workflow_context.model_dump())
                logger.info(f"[{stage_name}] 参数解析完成: {resolved_params}")
            except ValueError as e:
                logger.error(f"[{stage_name}] 参数解析失败: {e}")
                raise e
        
        # 记录实际使用的输入参数到input_params
        recorded_input_params = resolved_params.copy() if resolved_params else {}
        
        # 1. 尝试直接获取片段数据（最高优先级）
        transcript_segments = get_param_with_fallback("segments_data", resolved_params, workflow_context)
        speaker_segments = get_param_with_fallback("speaker_segments_data", resolved_params, workflow_context)
        
        # 2. 如果没有直接数据，尝试文件路径
        if not transcript_segments:
            segments_file = get_param_with_fallback("segments_file", resolved_params, workflow_context)
            if segments_file:
                transcript_segments = load_segments_from_file(segments_file)
                recorded_input_params['segments_file'] = segments_file
        
        if not speaker_segments:
            diarization_file = get_param_with_fallback("diarization_file", resolved_params, workflow_context)
            if diarization_file:
                speaker_data = load_speaker_data_from_file(diarization_file)
                speaker_segments = speaker_data.get('speaker_enhanced_segments')
                recorded_input_params['diarization_file'] = diarization_file
        
        # 3. 最后回退到原有逻辑（向后兼容）
        if not transcript_segments:
            transcribe_stage = workflow_context.stages.get('faster_whisper.transcribe_audio')
            if transcribe_stage and transcribe_stage.output:
                transcript_segments = get_segments_data(transcribe_stage.output, 'segments')
                recorded_input_params['fallback_source'] = 'faster_whisper.transcribe_audio'
            else:
                raise ValueError("无法获取转录片段数据：请提供segments_data/segments_file参数，或确保faster_whisper.transcribe_audio已完成")
        
        if not speaker_segments:
            diarize_stage = workflow_context.stages.get('pyannote_audio.diarize_speakers')
            if diarize_stage and diarize_stage.output:
                speaker_segments = get_speaker_data(diarize_stage.output).get('speaker_enhanced_segments')
                if recorded_input_params.get('fallback_source'):
                    recorded_input_params['fallback_source'] += ' + pyannote_audio.diarize_speakers'
                else:
                    recorded_input_params['fallback_source'] = 'pyannote_audio.diarize_speakers'
            else:
                raise ValueError("无法获取说话人片段数据：请提供speaker_segments_data/diarization_file参数，或确保pyannote_audio.diarize_speakers已完成")
        
        # 记录最终使用的参数
        workflow_context.stages[stage_name].input_params = recorded_input_params
        
        # 验证数据格式
        if not transcript_segments:
            raise ValueError("转录片段数据为空")
        if not validate_speaker_segments(speaker_segments):
            raise ValueError("说话人时间段数据格式无效")
        
        # 执行合并逻辑
        service_config = CONFIG.get('faster_whisper_service', {})
        merge_config = service_config.get('subtitle_merge', {})
        merger = create_subtitle_merger(merge_config)
        merged_segments = merger.merge(transcript_segments, speaker_segments)
        
        output_data = {
            'merged_segments': merged_segments,
            'input_summary': {
                'transcript_segments_count': len(transcript_segments),
                'speaker_segments_count': len(speaker_segments),
                'merged_segments_count': len(merged_segments),
                'data_source': recorded_input_params.get('fallback_source', 'input_data')
            }
        }
        
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data
        
    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)
    
    return workflow_context.model_dump()


@celery_app.task(name='wservice.merge_with_word_timestamps', bind=True)
def merge_with_word_timestamps(self, context: dict) -> dict:
    """
    使用词级时间戳进行精确字幕合并
    
    新增input_data参数支持，支持单任务模式调用：
    - segments_data: 直接传入包含词级时间戳的转录片段数据
    - speaker_segments_data: 直接传入说话人片段数据
    - segments_file: 包含词级时间戳的转录数据文件路径
    - diarization_file: 说话人分离数据文件路径
    """
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)
    
    try:
        # --- Parameter Resolution (采用项目标准模式) ---
        resolved_params = {}
        node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})
        if node_params:
            try:
                from services.common.parameter_resolver import resolve_parameters, get_param_with_fallback
                resolved_params = resolve_parameters(node_params, workflow_context.model_dump())
                logger.info(f"[{stage_name}] 参数解析完成: {resolved_params}")
            except ValueError as e:
                logger.error(f"[{stage_name}] 参数解析失败: {e}")
                raise e
        
        # 记录实际使用的输入参数到input_params
        recorded_input_params = resolved_params.copy() if resolved_params else {}
        
        # 1. 尝试直接获取片段数据（最高优先级）
        transcript_segments = get_param_with_fallback("segments_data", resolved_params, workflow_context)
        speaker_segments = get_param_with_fallback("speaker_segments_data", resolved_params, workflow_context)
        
        # 2. 如果没有直接数据，尝试文件路径
        if not transcript_segments:
            segments_file = get_param_with_fallback("segments_file", resolved_params, workflow_context)
            if segments_file:
                transcript_segments = load_segments_from_file(segments_file)
                recorded_input_params['segments_file'] = segments_file
        
        if not speaker_segments:
            diarization_file = get_param_with_fallback("diarization_file", resolved_params, workflow_context)
            if diarization_file:
                speaker_data = load_speaker_data_from_file(diarization_file)
                speaker_segments = speaker_data.get('speaker_enhanced_segments')
                recorded_input_params['diarization_file'] = diarization_file
        
        # 3. 最后回退到原有逻辑（向后兼容）
        if not transcript_segments:
            transcribe_stage = workflow_context.stages.get('faster_whisper.transcribe_audio')
            if transcribe_stage and transcribe_stage.output:
                transcript_segments = get_segments_data(transcribe_stage.output, 'segments')
                recorded_input_params['fallback_source'] = 'faster_whisper.transcribe_audio'
            else:
                raise ValueError("无法获取转录片段数据：请提供segments_data/segments_file参数，或确保faster_whisper.transcribe_audio已完成")
        
        if not speaker_segments:
            diarize_stage = workflow_context.stages.get('pyannote_audio.diarize_speakers')
            if diarize_stage and diarize_stage.output:
                speaker_segments = get_speaker_data(diarize_stage.output).get('speaker_enhanced_segments')
                if recorded_input_params.get('fallback_source'):
                    recorded_input_params['fallback_source'] += ' + pyannote_audio.diarize_speakers'
                else:
                    recorded_input_params['fallback_source'] = 'pyannote_audio.diarize_speakers'
            else:
                raise ValueError("无法获取说话人片段数据：请提供speaker_segments_data/diarization_file参数，或确保pyannote_audio.diarize_speakers已完成")
        
        # 记录最终使用的参数
        workflow_context.stages[stage_name].input_params = recorded_input_params
        
        # 验证数据格式
        if not transcript_segments:
            raise ValueError("转录片段数据为空")
        
        # 特别验证词级时间戳
        if not any('words' in seg and seg['words'] for seg in transcript_segments):
            raise ValueError("转录结果不包含词级时间戳，无法执行词级合并")
        
        if not validate_speaker_segments(speaker_segments):
            raise ValueError("说话人时间段数据格式无效")
        
        # 执行词级合并逻辑
        service_config = CONFIG.get('faster_whisper_service', {})
        merge_config = service_config.get('subtitle_merge', {})
        merger = create_word_level_merger(speaker_segments, merge_config)
        merged_segments = merger.merge(transcript_segments)
        
        output_data = {
            'merged_segments': merged_segments,
            'input_summary': {
                'transcript_segments_count': len(transcript_segments),
                'speaker_segments_count': len(speaker_segments),
                'merged_segments_count': len(merged_segments),
                'data_source': recorded_input_params.get('fallback_source', 'input_data'),
                'word_timestamps_required': True
            }
        }
        
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data
        
    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)
    
    return workflow_context.model_dump()


@celery_app.task(bind=True, name='wservice.correct_subtitles')
def correct_subtitles(self, context: dict) -> dict:
    """
    字幕AI校正任务节点
    """
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)
    try:
        # --- Parameter Resolution ---
        resolved_params = {}
        node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})
        if node_params:
            try:
                from services.common.parameter_resolver import resolve_parameters, get_param_with_fallback
                resolved_params = resolve_parameters(node_params, workflow_context.model_dump())
                logger.info(f"[{stage_name}] 参数解析完成: {resolved_params}")
            except ValueError as e:
                logger.error(f"[{stage_name}] 参数解析失败: {e}")
                raise e
        
        # 记录实际使用的输入参数到input_params
        recorded_input_params = resolved_params.copy() if resolved_params else {}
        
        # 优先从 resolved_params 获取参数，回退到 global params
        correction_params = resolved_params.get('subtitle_correction', 
                                              workflow_context.input_params.get('params', {}).get('subtitle_correction', {}))
        
        # 获取待校正的字幕文件路径
        subtitle_to_correct = get_param_with_fallback(
            "subtitle_path", 
            resolved_params, 
            workflow_context
        )
        
        # 如果参数中没有，尝试从上游节点获取
        if not subtitle_to_correct:
            # 尝试从 generate_subtitle_files 获取带说话人SRT
            subtitle_to_correct = get_param_with_fallback(
                "speaker_srt_path",
                resolved_params,
                workflow_context,
                fallback_from_stage="wservice.generate_subtitle_files",
                fallback_from_input_data=False
            )
        
        if not subtitle_to_correct:
            # 尝试从 generate_subtitle_files 获取基础SRT
            subtitle_to_correct = get_param_with_fallback(
                "subtitle_path",
                resolved_params,
                workflow_context,
                fallback_from_stage="wservice.generate_subtitle_files",
                fallback_from_input_data=False
            )
            
        if subtitle_to_correct:
            recorded_input_params['subtitle_path'] = subtitle_to_correct
        
        workflow_context.stages[stage_name].input_params = recorded_input_params

        is_enabled = correction_params.get('enabled', False)
        if not is_enabled:
            workflow_context.stages[stage_name].status = 'SKIPPED'
            return workflow_context.model_dump()
        
        provider = correction_params.get('provider', None)
        
        if not subtitle_to_correct or not os.path.exists(subtitle_to_correct):
            raise FileNotFoundError(f"未找到可供校正的字幕文件")
        
        corrector = SubtitleCorrector(provider=provider)
        corrected_filename = os.path.basename(subtitle_to_correct).replace('.srt', '_corrected_by_ai.srt')
        corrected_path = os.path.join(os.path.dirname(subtitle_to_correct), corrected_filename)
        correction_result = asyncio.run(corrector.correct_subtitle_file(subtitle_path=subtitle_to_correct, output_path=corrected_path))
        if not correction_result.success:
            raise RuntimeError(f"AI字幕校正失败: {correction_result.error_message}")
        output_data = {
            "corrected_subtitle_path": correction_result.corrected_subtitle_path,
            "original_subtitle_path": correction_result.original_subtitle_path,
            "provider_used": correction_result.provider_used,
            "statistics": correction_result.statistics,
        }
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data
    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)
    return workflow_context.model_dump()


@celery_app.task(bind=True, name='wservice.ai_optimize_subtitles')
def ai_optimize_subtitles(self, context: dict) -> dict:
    """
    AI字幕优化任务节点

    通过AI大模型对转录后的字幕进行智能优化和校正，包括：
    1. 修正错别字和语法错误
    2. 添加适当的标点符号
    3. 删除口头禅和填充词
    4. 支持大体积字幕的并发处理
    """
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        # 获取节点特定参数
        node_params = workflow_context.input_params.get('node_params', {})
        stage_params = node_params.get(stage_name, {})
        # 向后兼容：也检查params.subtitle_optimization格式
        optimization_params = stage_params.get('subtitle_optimization',
                                               workflow_context.input_params.get('params', {}).get('subtitle_optimization', {}))

        # 使用参数解析器处理动态引用
        from services.common.parameter_resolver import resolve_parameters
        resolved_params = resolve_parameters(stage_params, workflow_context.model_dump())
        
        # 记录实际使用的输入参数到input_params
        recorded_input_params = resolved_params.copy() if resolved_params else {}
        
        # 如果没有显式参数，记录依赖的前置阶段信息
        if not recorded_input_params:
            generate_stage = workflow_context.stages.get('wservice.generate_subtitle_files')
            if generate_stage:
                recorded_input_params['input_source'] = 'wservice.generate_subtitle_files'
                recorded_input_params['subtitle_path'] = generate_stage.output.get('speaker_srt_path') or generate_stage.output.get('subtitle_path')
        
        workflow_context.stages[stage_name].input_params = recorded_input_params
        
        optimization_params = resolved_params.get('subtitle_optimization', optimization_params)

        is_enabled = optimization_params.get('enabled', False)

        if not is_enabled:
            logger.info(f"[{stage_name}] 字幕优化未启用，跳过处理")
            workflow_context.stages[stage_name].status = 'SKIPPED'
            return workflow_context.model_dump()

        # 获取AI提供商
        provider = optimization_params.get('provider', 'deepseek')

        # 获取批处理配置
        batch_size = optimization_params.get('batch_size', 50)
        overlap_size = optimization_params.get('overlap_size', 10)

        logger.info(f"[{stage_name}] 开始AI字幕优化 - 提供商: {provider}, "
                   f"批次大小: {batch_size}, 重叠大小: {overlap_size}")

        # 获取转录文件路径（支持动态引用或自定义路径）
        segments_file = optimization_params.get('segments_file')
        if not segments_file:
            # 尝试从参数中获取，支持动态引用
            segments_file = resolved_params.get('segments_file')

        if not segments_file:
            # 回退到从faster_whisper阶段自动获取
            faster_whisper_stage = workflow_context.stages.get('faster_whisper.transcribe_audio')
            if not faster_whisper_stage:
                raise FileNotFoundError("未找到faster_whisper转录阶段")
            segments_file = faster_whisper_stage.output.get('segments_file')

        if not segments_file or not os.path.exists(segments_file):
            raise FileNotFoundError(f"未找到转录文件: {segments_file}")

        # 初始化字幕优化器
        optimizer = SubtitleOptimizer(
            batch_size=batch_size,
            overlap_size=overlap_size,
            provider=provider
        )

        # 执行优化
        result = optimizer.optimize_subtitles(
            transcribe_file_path=segments_file,
            output_file_path=None,  # 自动生成输出路径
            prompt_file_path=None   # 使用默认提示词
        )

        if not result['success']:
            raise RuntimeError(f"AI字幕优化失败: {result.get('error', '未知错误')}")

        # 记录指标
        metrics_collector.record_request(
            provider=provider,
            status='success',
            duration=time.time() - start_time
        )
        metrics_collector.set_processing_time(provider, result['processing_time'])
        metrics_collector.set_batch_size(provider, batch_size)
        metrics_collector.record_subtitle_count(
            result['subtitles_count'],
            result['batch_mode']
        )

        # 构造输出数据
        output_data = {
            "optimized_file_path": result['file_path'],
            "original_file_path": segments_file,
            "provider_used": provider,
            "processing_time": result['processing_time'],
            "subtitles_count": result['subtitles_count'],
            "commands_applied": result['commands_applied'],
            "batch_mode": result['batch_mode'],
            "batches_count": result.get('batches_count', 1),
            "statistics": {
                "total_commands": result['commands_applied'],
                "optimization_rate": result['commands_applied'] / max(result['subtitles_count'], 1)
            }
        }

        # 更新工作流状态
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

        logger.info(f"[{stage_name}] 字幕优化完成 - 文件: {result['file_path']}, "
                   f"处理时间: {result['processing_time']:.2f}秒")

    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)

        # 记录错误指标
        if 'provider' in locals():
            metrics_collector.record_request(
                provider=provider,
                status='failure',
                duration=time.time() - start_time
            )

        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)

    finally:
        # 记录持续时间
        duration = time.time() - start_time
        workflow_context.stages[stage_name].duration = duration
        state_manager.update_workflow_state(workflow_context)
        logger.info(f"[{stage_name}] 任务完成 - 状态: {workflow_context.stages[stage_name].status}, "
                   f"耗时: {duration:.2f}秒")

    return workflow_context.model_dump()


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
    segments_file = source_stage.output.get('segments_file') or source_stage.output.get('optimized_file_path')
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
    为TTS参考音准备和优化字幕片段。
    
    新增input_data参数支持，支持单任务模式调用：
    - segments_data: 直接传入字幕片段数据
    - segments_file: 字幕片段数据文件路径
    - source_stage_names: 自定义源阶段名称列表（替代默认搜索列表）
    """
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        # --- Parameter Resolution (采用项目标准模式) ---
        resolved_params = {}
        node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})
        if node_params:
            try:
                from services.common.parameter_resolver import resolve_parameters, get_param_with_fallback
                resolved_params = resolve_parameters(node_params, workflow_context.model_dump())
                logger.info(f"[{stage_name}] 参数解析完成: {resolved_params}")
            except ValueError as e:
                logger.error(f"[{stage_name}] 参数解析失败: {e}")
                raise e
        
        # 记录实际使用的输入参数到input_params
        recorded_input_params = resolved_params.copy() if resolved_params else {}
        
        # 1. 尝试直接获取片段数据（最高优先级）
        segments = get_param_with_fallback("segments_data", resolved_params, workflow_context)
        
        # 2. 如果没有直接数据，尝试文件路径
        if not segments:
            segments_file = get_param_with_fallback("segments_file", resolved_params, workflow_context)
            if segments_file:
                segments = load_segments_from_file(segments_file)
                recorded_input_params['segments_file'] = segments_file
        
        # 3. 使用自定义源阶段列表（如果提供）
        source_stage_names = get_param_with_fallback("source_stage_names", resolved_params, workflow_context)
        
        # 4. 最后回退到原有逻辑（向后兼容）
        if not segments:
            # 默认的源阶段列表
            default_source_stage_names = [
                'wservice.merge_with_word_timestamps',
                'wservice.merge_speaker_segments', 
                'wservice.generate_subtitle_files',
                'wservice.ai_optimize_subtitles', # AI优化后也可能作为源
                'faster_whisper.transcribe_audio' # 最终回退到原始转录
            ]
            
            # 使用自定义或默认源阶段列表
            source_stage_names = source_stage_names if source_stage_names else default_source_stage_names
            segments, source_name = _get_segments_from_source_stages(workflow_context, source_stage_names)
            recorded_input_params['fallback_source'] = source_name
            recorded_input_params['source_stage_names_used'] = source_stage_names
        else:
            source_name = 'input_data'
        
        # 记录最终使用的参数
        workflow_context.stages[stage_name].input_params = recorded_input_params
        
        # 验证数据
        if not segments:
            raise ValueError("无法获取字幕片段数据：请提供segments_data/segments_file参数，或确保有有效的上游节点")
        
        # 执行TTS准备逻辑
        service_config = CONFIG.get('wservice', {})
        merger_config = service_config.get('tts_merger_settings', {})
        
        merger = TtsMerger(config=merger_config)
        prepared_segments = merger.merge_segments(segments)

        output_data = {
            'prepared_segments': prepared_segments,
            'source_stage': source_name,
            'total_segments': len(prepared_segments),
            'input_summary': {
                'original_segments_count': len(segments),
                'prepared_segments_count': len(prepared_segments),
                'data_source': recorded_input_params.get('fallback_source', 'input_data')
            }
        }

        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
    finally:
        duration = time.time() - start_time
        workflow_context.stages[stage_name].duration = duration
        state_manager.update_workflow_state(workflow_context)
        logger.info(f"[{stage_name}] 任务完成 - 状态: {workflow_context.stages[stage_name].status}, 耗时: {duration:.2f}秒")

    return workflow_context.model_dump()
