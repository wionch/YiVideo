# services/workers/ffmpeg_service/app/modules/subtitle_parser.py
# -*- coding: utf-8 -*-

"""
字幕文件解析模块 - 专为音频分割功能设计

提供通用的字幕文件解析功能，支持多种字幕格式和时间戳提取。
为音频分割功能提供时间戳数据和文本信息。

注意：此模块与 services/common/subtitle/subtitle_parser.py 功能类似但用途不同：
- 本模块：主要用于音频分割，支持多种格式（SRT、JSON），包含说话人信息处理
- common模块：主要用于字幕校正和文本处理，专注于SRT格式，包含高级文本处理功能
"""

import os
import re
import json
import logging
from typing import List, Dict, Optional, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SubtitleSegment:
    """字幕片段数据结构"""
    id: int
    start_time: float  # 开始时间（秒）
    end_time: float    # 结束时间（秒）
    duration: float    # 持续时间（秒）
    text: str          # 字幕文本
    speaker: Optional[str] = None  # 说话人（可选）
    confidence: Optional[float] = None  # 置信度（可选）
    words: Optional[List[Dict]] = None  # 词级时间戳（可选）


class SubtitleParser:
    """字幕文件解析器"""

    @staticmethod
    def parse_srt_time(time_str: str) -> float:
        """
        将SRT时间格式转换为秒数

        Args:
            time_str: SRT时间格式字符串，如 "00:01:23,456"

        Returns:
            float: 转换后的秒数
        """
        try:
            # 分离时间部分和毫秒部分
            time_part, ms_part = time_str.split(',')

            # 解析时间部分 (HH:MM:SS)
            hours, minutes, seconds = map(int, time_part.split(':'))

            # 解析毫秒部分
            milliseconds = int(ms_part)

            # 转换为总秒数
            total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0

            return total_seconds

        except Exception as e:
            logger.error(f"解析时间格式失败: {time_str}, 错误: {e}")
            return 0.0

    @staticmethod
    def parse_srt_file(file_path: str) -> List[SubtitleSegment]:
        """
        解析标准SRT字幕文件

        Args:
            file_path: SRT文件路径

        Returns:
            List[SubtitleSegment]: 字幕片段列表
        """
        if not os.path.exists(file_path):
            logger.error(f"SRT文件不存在: {file_path}")
            return []

        segments = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 按空行分割字幕块
            subtitle_blocks = content.strip().split('\n\n')

            for block in subtitle_blocks:
                lines = block.strip().split('\n')

                if len(lines) < 3:
                    continue

                try:
                    # 第一行：序号
                    segment_id = int(lines[0].strip())

                    # 第二行：时间范围
                    time_line = lines[1].strip()
                    start_str, end_str = time_line.split(' --> ')

                    start_time = SubtitleParser.parse_srt_time(start_str.strip())
                    end_time = SubtitleParser.parse_srt_time(end_str.strip())
                    duration = end_time - start_time

                    # 剩余行：字幕文本
                    text = '\n'.join(lines[2:]).strip()

                    # 创建字幕片段对象
                    segment = SubtitleSegment(
                        id=segment_id,
                        start_time=start_time,
                        end_time=end_time,
                        duration=duration,
                        text=text
                    )

                    segments.append(segment)

                except Exception as e:
                    logger.warning(f"解析字幕块失败: {block}, 错误: {e}")
                    continue

            logger.info(f"成功解析SRT文件: {file_path}, 共 {len(segments)} 个片段")
            return segments

        except Exception as e:
            logger.error(f"读取SRT文件失败: {file_path}, 错误: {e}")
            return []

    @staticmethod
    def parse_speaker_srt_file(file_path: str) -> List[SubtitleSegment]:
        """
        解析带说话人信息的SRT字幕文件

        格式示例:
        1
        00:01:23,456 --> 00:01:26,789
        [SPEAKER_00] 这是字幕文本

        Args:
            file_path: 带说话人信息的SRT文件路径

        Returns:
            List[SubtitleSegment]: 字幕片段列表
        """
        if not os.path.exists(file_path):
            logger.error(f"带说话人信息的SRT文件不存在: {file_path}")
            return []

        segments = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 按空行分割字幕块
            subtitle_blocks = content.strip().split('\n\n')

            for block in subtitle_blocks:
                lines = block.strip().split('\n')

                if len(lines) < 3:
                    continue

                try:
                    # 第一行：序号
                    segment_id = int(lines[0].strip())

                    # 第二行：时间范围
                    time_line = lines[1].strip()
                    start_str, end_str = time_line.split(' --> ')

                    start_time = SubtitleParser.parse_srt_time(start_str.strip())
                    end_time = SubtitleParser.parse_srt_time(end_str.strip())
                    duration = end_time - start_time

                    # 第三行：带说话人信息的字幕文本
                    text_line = lines[2].strip()

                    # 提取说话人信息
                    speaker = None
                    text = text_line

                    # 匹配 [SPEAKER_XX] 格式
                    speaker_match = re.match(r'^\[([^\]]+)\]\s*(.*)$', text_line)
                    if speaker_match:
                        speaker = speaker_match.group(1)
                        text = speaker_match.group(2).strip()

                    # 创建字幕片段对象
                    segment = SubtitleSegment(
                        id=segment_id,
                        start_time=start_time,
                        end_time=end_time,
                        duration=duration,
                        text=text,
                        speaker=speaker
                    )

                    segments.append(segment)

                except Exception as e:
                    logger.warning(f"解析带说话人信息的字幕块失败: {block}, 错误: {e}")
                    continue

            logger.info(f"成功解析带说话人信息的SRT文件: {file_path}, 共 {len(segments)} 个片段")
            return segments

        except Exception as e:
            logger.error(f"读取带说话人信息的SRT文件失败: {file_path}, 错误: {e}")
            return []

    @staticmethod
    def parse_subtitle_json_file(file_path: str) -> List[SubtitleSegment]:
        """
        解析JSON格式的字幕文件

        Args:
            file_path: JSON字幕文件路径

        Returns:
            List[SubtitleSegment]: 字幕片段列表
        """
        if not os.path.exists(file_path):
            logger.error(f"JSON字幕文件不存在: {file_path}")
            return []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            segments = []

            # 处理不同的JSON格式
            if isinstance(data, dict) and 'segments' in data:
                # WhisperX带说话人信息的JSON格式
                segment_data = data['segments']

                for seg in segment_data:
                    try:
                        segment = SubtitleSegment(
                            id=seg.get('id', 0),
                            start_time=seg.get('start', 0.0),
                            end_time=seg.get('end', 0.0),
                            duration=seg.get('duration', 0.0),
                            text=seg.get('text', ''),
                            speaker=seg.get('speaker'),
                            confidence=seg.get('speaker_confidence'),
                            words=seg.get('words')
                        )
                        segments.append(segment)

                    except Exception as e:
                        logger.warning(f"解析JSON字幕片段失败: {seg}, 错误: {e}")
                        continue

            logger.info(f"成功解析JSON字幕文件: {file_path}, 共 {len(segments)} 个片段")
            return segments

        except Exception as e:
            logger.error(f"读取JSON字幕文件失败: {file_path}, 错误: {e}")
            return []

    @staticmethod
    def parse_subtitle_file(file_path: str) -> List[SubtitleSegment]:
        """
        自动识别字幕文件格式并解析

        Args:
            file_path: 字幕文件路径

        Returns:
            List[SubtitleSegment]: 字幕片段列表
        """
        if not os.path.exists(file_path):
            logger.error(f"字幕文件不存在: {file_path}")
            return []

        # 根据文件扩展名选择解析方法
        _, ext = os.path.splitext(file_path.lower())

        if ext == '.srt':
            # 检查是否包含说话人信息
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    first_lines = f.read(500)  # 读取前500个字符

                if '[' in first_lines and ']' in first_lines:
                    # 可能包含说话人信息
                    segments = SubtitleParser.parse_speaker_srt_file(file_path)
                    if segments:
                        return segments
                else:
                    # 标准SRT文件
                    return SubtitleParser.parse_srt_file(file_path)

            except Exception as e:
                logger.warning(f"尝试解析SRT文件失败，回退到标准解析: {e}")
                return SubtitleParser.parse_srt_file(file_path)

        elif ext == '.json':
            return SubtitleParser.parse_subtitle_json_file(file_path)

        else:
            logger.error(f"不支持的字幕文件格式: {ext}")
            return []

    @staticmethod
    def filter_segments_by_duration(
        segments: List[SubtitleSegment],
        min_duration: float = 1.0,
        max_duration: float = 30.0
    ) -> List[SubtitleSegment]:
        """
        根据时长过滤字幕片段

        Args:
            segments: 字幕片段列表
            min_duration: 最小时长（秒）
            max_duration: 最大时长（秒）

        Returns:
            List[SubtitleSegment]: 过滤后的字幕片段列表
        """
        filtered_segments = []

        for segment in segments:
            if min_duration <= segment.duration <= max_duration:
                filtered_segments.append(segment)
            else:
                logger.debug(f"跳过时长不符合要求的片段: {segment.id}, 时长: {segment.duration:.2f}s")

        logger.info(f"时长过滤: {len(segments)} -> {len(filtered_segments)} 个片段")
        return filtered_segments

    @staticmethod
    def group_segments_by_speaker(segments: List[SubtitleSegment]) -> Dict[str, List[SubtitleSegment]]:
        """
        按说话人分组字幕片段

        Args:
            segments: 字幕片段列表

        Returns:
            Dict[str, List[SubtitleSegment]]: 按说话人分组的字典
        """
        grouped = {}

        for segment in segments:
            speaker = segment.speaker or "UNKNOWN"

            if speaker not in grouped:
                grouped[speaker] = []

            grouped[speaker].append(segment)

        # 统计信息
        for speaker, segs in grouped.items():
            total_duration = sum(seg.duration for seg in segs)
            logger.info(f"说话人 {speaker}: {len(segs)} 个片段, 总时长: {total_duration:.2f}s")

        return grouped


def parse_subtitle_segments(file_path: str, **kwargs) -> List[SubtitleSegment]:
    """
    便捷函数：解析字幕文件并返回片段列表

    Args:
        file_path: 字幕文件路径
        **kwargs: 额外参数
            - min_duration: 最小时长过滤
            - max_duration: 最大时长过滤

    Returns:
        List[SubtitleSegment]: 字幕片段列表
    """
    segments = SubtitleParser.parse_subtitle_file(file_path)

    # 应用时长过滤
    if 'min_duration' in kwargs or 'max_duration' in kwargs:
        min_duration = kwargs.get('min_duration', 0.0)
        max_duration = kwargs.get('max_duration', float('inf'))
        segments = SubtitleParser.filter_segments_by_duration(segments, min_duration, max_duration)

    return segments