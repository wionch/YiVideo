"""
SRT字幕格式解析器 - 专为字幕校正功能设计

提供SRT字幕文件的解析、验证和生成功能。
支持字幕条目的增删改查和时间戳处理。

注意：此模块与 services/workers/ffmpeg_service/app/modules/subtitle_parser.py 功能类似但用途不同：
- 本模块：主要用于字幕校正和文本处理，专注于SRT格式，包含高级文本处理功能
- ffmpeg_service模块：主要用于音频分割，支持多种格式（SRT、JSON），包含说话人信息处理
"""

import re
import os
from typing import List, Dict, Optional, Union
from dataclasses import dataclass
import logging

from services.common.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SubtitleEntry:
    """字幕条目数据结构"""
    index: int                           # 序号
    start_time: float                    # 开始时间（秒）
    end_time: float                      # 结束时间（秒）
    text: str                            # 字幕文本
    duration: float = 0.0                # 持续时间（秒），自动计算
    speaker: Optional[str] = None        # 说话人标识

    # 说话人标识正则表达式模式
    SPEAKER_PATTERN = r'\[(SPEAKER_[\w_]+)\]'
    SPEAKER_CLEAN_PATTERN = r'\[SPEAKER_[\w_]+\]\s*'

    def __post_init__(self):
        """自动计算持续时间和说话人信息"""
        self.duration = self.end_time - self.start_time
        self.speaker = self._extract_speaker()

    def _extract_speaker(self) -> Optional[str]:
        """从字幕文本中提取说话人标识"""
        match = re.search(self.SPEAKER_PATTERN, self.text)
        if match:
            return match.group(1)
        return None

    def get_clean_text(self) -> str:
        """获取去除说话人标识的纯文本"""
        # 移除说话人标识
        clean_text = re.sub(self.SPEAKER_CLEAN_PATTERN, '', self.text)
        return clean_text.strip()

    def get_text_length(self) -> int:
        """获取纯文本长度（不包括说话人标识）"""
        return len(self.get_clean_text())

    def is_short_subtitle(self, max_chars: int = 1) -> bool:
        """判断是否为短字幕"""
        return self.get_text_length() <= max_chars

    def __str__(self) -> str:
        """字幕条目的字符串表示"""
        start_str = self._seconds_to_srt_time(self.start_time)
        end_str = self._seconds_to_srt_time(self.end_time)
        return f"{self.index}\n{start_str} --> {end_str}\n{self.text}"

    @staticmethod
    def _seconds_to_srt_time(seconds: float) -> str:
        """将秒数转换为SRT时间格式 (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

    @staticmethod
    def _srt_time_to_seconds(time_str: str) -> float:
        """将SRT时间格式转换为秒数"""
        # 匹配格式: HH:MM:SS,mmm 或 H:MM:SS,mmm
        pattern = r'(\d{1,2}):(\d{2}):(\d{2}),(\d{3})'
        match = re.match(pattern, time_str.strip())

        if not match:
            raise ValueError(f"无效的SRT时间格式: {time_str}")

        hours, minutes, seconds, milliseconds = map(int, match.groups())
        return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000

    def get_start_time_str(self) -> str:
        """获取开始时间的SRT格式字符串"""
        return self._seconds_to_srt_time(self.start_time)

    def get_end_time_str(self) -> str:
        """获取结束时间的SRT格式字符串"""
        return self._seconds_to_srt_time(self.end_time)

    def overlaps_with(self, other: 'SubtitleEntry') -> bool:
        """检查是否与另一个字幕条目重叠"""
        return not (self.end_time <= other.start_time or self.start_time >= other.end_time)

    def merge_with(self, other: 'SubtitleEntry') -> 'SubtitleEntry':
        """与另一个字幕条目合并（时间上合并，文本合并）"""
        if not self.overlaps_with(other):
            raise ValueError("只能合并重叠的字幕条目")

        merged_start = min(self.start_time, other.start_time)
        merged_end = max(self.end_time, other.end_time)
        merged_text = f"{self.text} {other.text}".strip()

        return SubtitleEntry(
            index=min(self.index, other.index),
            start_time=merged_start,
            end_time=merged_end,
            text=merged_text
        )


class SRTParser:
    """SRT字幕解析器"""

    # SRT时间戳正则表达式
    TIME_PATTERN = re.compile(r'(\d{1,2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2},\d{3})')

    def __init__(self):
        """初始化SRT解析器"""
        self.entries: List[SubtitleEntry] = []

    def parse_file(self, file_path: str) -> List[SubtitleEntry]:
        """
        解析SRT字幕文件

        Args:
            file_path: SRT文件路径

        Returns:
            List[SubtitleEntry]: 解析后的字幕条目列表

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件格式错误
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"SRT文件不存在: {file_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            entries = self.parse_text(content)
            logger.info(f"成功解析SRT文件: {file_path}，共 {len(entries)} 条字幕")
            return entries

        except Exception as e:
            logger.error(f"解析SRT文件失败: {file_path}, 错误: {e}")
            raise

    def parse_text(self, content: str) -> List[SubtitleEntry]:
        """
        解析SRT格式文本内容

        Args:
            content: SRT格式文本

        Returns:
            List[SubtitleEntry]: 解析后的字幕条目列表
        """
        entries = []

        # 按空行分割字幕块
        blocks = re.split(r'\n\s*\n', content.strip())

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            entry = self._parse_block(block)
            if entry:
                entries.append(entry)

        # 验证和排序
        entries = self._validate_and_sort_entries(entries)

        logger.debug(f"解析SRT文本完成，共 {len(entries)} 条字幕")
        return entries

    def _parse_block(self, block: str) -> Optional[SubtitleEntry]:
        """
        解析单个字幕块

        Args:
            block: 字幕块文本

        Returns:
            SubtitleEntry: 解析后的字幕条目，如果解析失败返回None
        """
        lines = block.split('\n')
        if len(lines) < 3:
            logger.warning(f"字幕块格式不正确，至少需要3行: {block[:50]}...")
            return None

        try:
            # 第一行：序号
            index = int(lines[0].strip())

            # 第二行：时间戳
            time_line = lines[1].strip()
            time_match = self.TIME_PATTERN.match(time_line)

            if not time_match:
                logger.warning(f"时间戳格式不正确: {time_line}")
                return None

            start_time_str, end_time_str = time_match.groups()
            start_time = SubtitleEntry._srt_time_to_seconds(start_time_str)
            end_time = SubtitleEntry._srt_time_to_seconds(end_time_str)

            if start_time >= end_time:
                logger.warning(f"时间戳无效: 开始时间 >= 结束时间 ({start_time} >= {end_time})")
                return None

            # 剩余行：字幕文本
            text = '\n'.join(lines[2:]).strip()

            if not text:
                logger.warning(f"字幕文本为空: 序号 {index}")
                return None

            return SubtitleEntry(
                index=index,
                start_time=start_time,
                end_time=end_time,
                text=text
            )

        except ValueError as e:
            logger.warning(f"解析字幕块失败: {e}")
            return None
        except Exception as e:
            logger.error(f"解析字幕块时发生未知错误: {e}")
            return None

    def _validate_and_sort_entries(self, entries: List[SubtitleEntry]) -> List[SubtitleEntry]:
        """
        验证和排序字幕条目

        Args:
            entries: 原始字幕条目列表

        Returns:
            List[SubtitleEntry]: 验证和排序后的字幕条目列表
        """
        if not entries:
            return []

        # 按开始时间排序
        entries.sort(key=lambda x: x.start_time)

        # 检查序号连续性
        for i, entry in enumerate(entries):
            if entry.index != i + 1:
                logger.debug(f"修正字幕序号: {entry.index} -> {i + 1}")
                entry.index = i + 1

        # 检查时间重叠
        overlaps = []
        for i in range(len(entries) - 1):
            if entries[i].overlaps_with(entries[i + 1]):
                overlaps.append((entries[i], entries[i + 1]))

        if overlaps:
            logger.warning(f"发现 {len(overlaps)} 个时间重叠的字幕条目")

        return entries

    def write_file(self, entries: List[SubtitleEntry], file_path: str) -> None:
        """
        将字幕条目写入SRT文件

        Args:
            entries: 字幕条目列表
            file_path: 输出文件路径
        """
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, 'w', encoding='utf-8') as f:
                for entry in entries:
                    f.write(str(entry))
                    f.write('\n\n')

            logger.info(f"字幕文件写入成功: {file_path}，共 {len(entries)} 条字幕")

        except Exception as e:
            logger.error(f"写入字幕文件失败: {file_path}, 错误: {e}")
            raise

    def entries_to_text(self, entries: List[SubtitleEntry]) -> str:
        """
        将字幕条目转换为SRT格式文本

        Args:
            entries: 字幕条目列表

        Returns:
            str: SRT格式文本
        """
        lines = []
        for entry in entries:
            lines.append(str(entry))

        return '\n\n'.join(lines)

    def get_statistics(self, entries: List[SubtitleEntry]) -> Dict[str, Union[int, float, str]]:
        """
        获取字幕统计信息

        Args:
            entries: 字幕条目列表

        Returns:
            Dict: 统计信息
        """
        if not entries:
            return {
                'total_entries': 0,
                'total_duration': 0.0,
                'average_duration': 0.0,
                'total_characters': 0,
                'average_characters_per_entry': 0.0,
                'start_time': 0.0,
                'end_time': 0.0
            }

        total_duration = sum(entry.duration for entry in entries)
        total_characters = sum(len(entry.text) for entry in entries)

        return {
            'total_entries': len(entries),
            'total_duration': total_duration,
            'average_duration': total_duration / len(entries),
            'total_characters': total_characters,
            'average_characters_per_entry': total_characters / len(entries),
            'start_time': entries[0].start_time,
            'end_time': entries[-1].end_time
        }

    def filter_entries(self, entries: List[SubtitleEntry],
                      start_time: Optional[float] = None,
                      end_time: Optional[float] = None,
                      min_duration: Optional[float] = None,
                      max_duration: Optional[float] = None) -> List[SubtitleEntry]:
        """
        过滤字幕条目

        Args:
            entries: 原始字幕条目列表
            start_time: 开始时间过滤
            end_time: 结束时间过滤
            min_duration: 最小时长过滤
            max_duration: 最大时长过滤

        Returns:
            List[SubtitleEntry]: 过滤后的字幕条目列表
        """
        filtered = entries

        if start_time is not None:
            filtered = [e for e in filtered if e.start_time >= start_time]

        if end_time is not None:
            filtered = [e for e in filtered if e.end_time <= end_time]

        if min_duration is not None:
            filtered = [e for e in filtered if e.duration >= min_duration]

        if max_duration is not None:
            filtered = [e for e in filtered if e.duration <= max_duration]

        return filtered

    def merge_adjacent_entries(self, entries: List[SubtitleEntry],
                             max_gap: float = 2.0) -> List[SubtitleEntry]:
        """
        合并相邻的字幕条目

        Args:
            entries: 原始字幕条目列表
            max_gap: 最大间隔时间（秒），超过此间隔不合并

        Returns:
            List[SubtitleEntry]: 合并后的字幕条目列表
        """
        if not entries:
            return []

        merged = [entries[0]]

        for current in entries[1:]:
            last = merged[-1]

            # 如果间隔时间小于等于max_gap，则合并
            if (current.start_time - last.end_time) <= max_gap:
                merged_entry = SubtitleEntry(
                    index=last.index,
                    start_time=last.start_time,
                    end_time=current.end_time,
                    text=f"{last.text} {current.text}"
                )
                merged[-1] = merged_entry
            else:
                merged.append(current)

        # 重新编号
        for i, entry in enumerate(merged):
            entry.index = i + 1

        return merged

    def adjust_timestamps(self, entries: List[SubtitleEntry],
                         offset: float,
                         stretch_factor: float = 1.0) -> List[SubtitleEntry]:
        """
        调整时间戳

        Args:
            entries: 原始字幕条目列表
            offset: 时间偏移（秒）
            stretch_factor: 时间拉伸因子（1.0表示不拉伸）

        Returns:
            List[SubtitleEntry]: 调整后的字幕条目列表
        """
        adjusted = []

        for entry in entries:
            new_entry = SubtitleEntry(
                index=entry.index,
                start_time=entry.start_time * stretch_factor + offset,
                end_time=entry.end_time * stretch_factor + offset,
                text=entry.text
            )
            adjusted.append(new_entry)

        return adjusted

    def merge_short_subtitles_locally(self, entries: List[SubtitleEntry],
                                     max_chars: int = 1,
                                     max_line_length: int = 20) -> List[SubtitleEntry]:
        """
        本地短字幕合并功能

        合并规则：
        1. 短字幕只有1个字且时间节点和前后字幕某条是重叠的，可以进行合并
        2. 不同说话人的字幕禁止合并
        3. 合并后每行字幕最多不超过20个字

        Args:
            entries: 原始字幕条目列表
            max_chars: 短字幕的最大字符数（默认为1）
            max_line_length: 每行最大字符数（默认为20）

        Returns:
            List[SubtitleEntry]: 合并后的字幕条目列表
        """
        if not entries:
            return []

        logger.info(f"开始本地短字幕合并，共 {len(entries)} 条字幕")

        merged_entries = []
        i = 0
        merged_count = 0

        while i < len(entries):
            current = entries[i]

            # 如果当前不是短字幕，直接添加到结果中
            if not current.is_short_subtitle(max_chars):
                merged_entries.append(current)
                i += 1
                continue

            # 当前是短字幕，尝试与前后字幕合并
            merged = False

            # 尝试与前一个字幕合并
            if merged_entries and self._can_merge_with_previous(current, merged_entries[-1]):
                merged_entry = self._merge_two_entries(merged_entries[-1], current)
                # 检查合并后是否超过行长度限制
                if merged_entry.get_text_length() <= max_line_length:
                    merged_entries[-1] = merged_entry
                    merged = True
                    merged_count += 1
                    logger.debug(f"短字幕 {current.index} 与前一个字幕合并")

            # 如果没有与前一个合并，尝试与后一个字幕合并
            if not merged and i + 1 < len(entries):
                next_entry = entries[i + 1]
                if self._can_merge_with_next(current, next_entry):
                    merged_entry = self._merge_two_entries(current, next_entry)
                    # 检查合并后是否超过行长度限制
                    if merged_entry.get_text_length() <= max_line_length:
                        merged_entries.append(merged_entry)
                        merged = True
                        merged_count += 1
                        i += 2  # 跳过下一个字幕，因为已经合并了
                        logger.debug(f"短字幕 {current.index} 与后一个字幕合并")

            # 如果都没有合并，直接添加
            if not merged:
                merged_entries.append(current)
                i += 1

        # 重新编号
        for idx, entry in enumerate(merged_entries):
            entry.index = idx + 1

        logger.info(f"本地短字幕合并完成，合并了 {merged_count} 个短字幕，剩余 {len(merged_entries)} 条字幕")
        return merged_entries

    def _can_merge_with_previous(self, current: SubtitleEntry, previous: SubtitleEntry) -> bool:
        """检查当前短字幕是否可以与前一个字幕合并"""
        # 1. 检查说话人是否相同
        if current.speaker and previous.speaker and current.speaker != previous.speaker:
            return False

        # 2. 检查时间重叠
        if current.overlaps_with(previous):
            return True

        # 3. 检查时间间隔是否很小（小于0.5秒）
        if abs(current.start_time - previous.end_time) < 0.5:
            return True

        return False

    def _can_merge_with_next(self, current: SubtitleEntry, next_entry: SubtitleEntry) -> bool:
        """检查当前短字幕是否可以与后一个字幕合并"""
        # 1. 检查说话人是否相同
        if current.speaker and next_entry.speaker and current.speaker != next_entry.speaker:
            return False

        # 2. 检查时间重叠
        if current.overlaps_with(next_entry):
            return True

        # 3. 检查时间间隔是否很小（小于0.5秒）
        if abs(next_entry.start_time - current.end_time) < 0.5:
            return True

        return False

    def _merge_two_entries(self, entry1: SubtitleEntry, entry2: SubtitleEntry) -> SubtitleEntry:
        """合并两个字幕条目"""
        # 确定合并后的时间范围
        start_time = min(entry1.start_time, entry2.start_time)
        end_time = max(entry1.end_time, entry2.end_time)

        # 合并文本，保持说话人标识
        text1_clean = entry1.get_clean_text()
        text2_clean = entry2.get_clean_text()

        # 构建合并后的文本
        if entry1.speaker:
            merged_text = f"[{entry1.speaker}] {text1_clean} {text2_clean}"
        else:
            merged_text = f"{text1_clean} {text2_clean}"

        return SubtitleEntry(
            index=min(entry1.index, entry2.index),
            start_time=start_time,
            end_time=end_time,
            text=merged_text.strip()
        )


# 便捷函数
def parse_srt_file(file_path: str) -> List[SubtitleEntry]:
    """便捷函数：解析SRT文件"""
    parser = SRTParser()
    return parser.parse_file(file_path)


def write_srt_file(entries: List[SubtitleEntry], file_path: str) -> None:
    """便捷函数：写入SRT文件"""
    parser = SRTParser()
    parser.write_file(entries, file_path)


def create_srt_entry(index: int, start_time: str, end_time: str, text: str) -> SubtitleEntry:
    """
    便捷函数：创建字幕条目

    Args:
        index: 序号
        start_time: 开始时间 (SRT格式: HH:MM:SS,mmm)
        end_time: 结束时间 (SRT格式: HH:MM:SS,mmm)
        text: 字幕文本

    Returns:
        SubtitleEntry: 字幕条目
    """
    start_seconds = SubtitleEntry._srt_time_to_seconds(start_time)
    end_seconds = SubtitleEntry._srt_time_to_seconds(end_time)

    return SubtitleEntry(
        index=index,
        start_time=start_seconds,
        end_time=end_seconds,
        text=text
    )