#!/usr/bin/env python3
"""
字幕断句优化器
基于词级时间戳进行智能字幕断句，遵循行业标准
"""

import re
import json
from typing import List, Dict, Tuple
from dataclasses import dataclass
from services.common.logger import get_logger

logger = get_logger('subtitle_segmenter')

@dataclass
class SubtitleConfig:
    """字幕断句配置"""
    # 时间相关配置（基于行业标准）
    max_subtitle_duration: float = 8.0  # 最大字幕时长（秒），适当放宽
    min_subtitle_duration: float = 2.5  # 最小字幕时长（秒），避免过短字幕
    min_gap_between_subtitles: float = 0.5  # 字幕间最小间隔（秒）

    # 文本相关配置
    max_chars_per_line: int = 42  # 每行最大字符数（Netflix标准）
    max_lines_per_subtitle: int = 2  # 每个字幕最大行数
    max_words_per_subtitle: int = 25  # 每个字幕最大词数，适当增加

    # 断句相关配置
    word_gap_threshold: float = 2.0  # 词间间隔阈值（秒），提高阈值避免过度断句
    sentence_break_punctuation: List[str] = None  # 句末标点符号
    clause_break_punctuation: List[str] = None  # 分句标点符号
    semantic_min_words: int = 6  # 语义单元最小词数
    prefer_complete_phrases: bool = True  # 优先保持短语完整性

    def __post_init__(self):
        if self.sentence_break_punctuation is None:
            self.sentence_break_punctuation = ['.', '!', '?', '。', '！', '？']
        if self.clause_break_punctuation is None:
            self.clause_break_punctuation = [',', ';', ':', '，', '；', '：', '-', '—']

class SubtitleSegmenter:
    """字幕断句优化器"""

    def __init__(self, config: SubtitleConfig = None):
        self.config = config or SubtitleConfig()
        logger.info("字幕断句优化器初始化完成")
        logger.info(f"配置信息：最大时长={self.config.max_subtitle_duration}s, "
                   f"最大字符数={self.config.max_chars_per_line}/行, "
                   f"词间间隔阈值={self.config.word_gap_threshold}s")

    def segment_by_word_timestamps(self, word_timestamps_data: Dict) -> List[Dict]:
        """
        基于词级时间戳进行字幕断句优化

        Args:
            word_timestamps_data: 词级时间戳JSON数据

        Returns:
            优化后的字幕断句列表
        """
        logger.info("开始基于词级时间戳的字幕断句优化")

        if not isinstance(word_timestamps_data, dict) or "segments" not in word_timestamps_data:
            raise ValueError("输入数据格式错误，缺少segments字段")

        # 提取所有词的数据
        all_words = []
        for segment in word_timestamps_data["segments"]:
            if "words" in segment and segment["words"]:
                for word_data in segment["words"]:
                    all_words.append(word_data)

        if not all_words:
            logger.warning("未找到词级时间戳数据，返回原始字幕")
            return self._fallback_to_original_segments(word_timestamps_data)

        logger.info(f"总共处理 {len(all_words)} 个词")

        # 执行断句算法
        optimized_segments = self._perform_segmentation(all_words)

        logger.info(f"断句优化完成：原始 {word_timestamps_data['total_segments']} 段 -> 优化后 {len(optimized_segments)} 段")

        return optimized_segments

    def _perform_segmentation(self, words: List[Dict]) -> List[Dict]:
        """执行断句算法"""
        segments = []
        current_segment_words = []
        segment_start_time = None

        for i, word in enumerate(words):
            word_text = word["word"].strip()
            word_start = word["start"]
            word_end = word["end"]

            # 初始化第一个segment
            if not current_segment_words:
                current_segment_words = [word]
                segment_start_time = word_start
                continue

            # 检查当前segment中的最后一个词是否需要断句
            last_word = current_segment_words[-1]
            last_word_text = last_word["word"].strip()

            # 计算当前segment的时长（到最后一个词）
            current_segment_duration = last_word["end"] - segment_start_time

            # 获取词间间隔
            word_gap = word_start - last_word["end"]

            # 检查是否应该在最后一个词处断句（基于最后一个词的标点符号等）
            should_break_at_last_word = self._should_break_at_word(
                last_word_text,
                current_segment_duration,
                word_gap,
                len(current_segment_words),
                i < len(words) - 1  # 是否还有更多词
            )

            # 如果应该在最后一个词处断句，完成当前segment并开始新segment
            if should_break_at_last_word:
                self._finalize_current_segment(
                    current_segment_words,
                    segment_start_time,
                    last_word["end"],
                    segments
                )

                # 开始新的segment，包含当前词
                current_segment_words = [word]
                segment_start_time = word_start
            else:
                # 继续当前segment，添加当前词
                current_segment_words.append(word)

        # 处理最后一个segment
        if current_segment_words:
            last_word = current_segment_words[-1]
            self._finalize_current_segment(
                current_segment_words,
                segment_start_time,
                last_word["end"],
                segments
            )

        return segments

    def _should_break_at_word(self, word_text: str, duration: float,
                           word_gap: float, word_count: int, has_more_words: bool) -> bool:
        """判断是否应该在当前词处断句 - 修正版本，基于当前词的标点符号"""

        logger.debug(f"断句分析: 词数={word_count}, 时长={duration:.2f}s, 当前词={word_text}, 间隔={word_gap:.2f}s")

        # 按照指定优先级顺序执行断句规则

        # 优先级1: 词间间隔分析 (最高优先级)
        if word_gap > self.config.word_gap_threshold and word_count >= 3:
            logger.debug(f"断句(优先级1): 词间间隔过大 ({word_gap:.2f}s > {self.config.word_gap_threshold}s)")
            return True

        # 优先级2: 标点符号断句 - 检查当前词是否以标点结尾
        has_sentence_end = any(word_text.endswith(punct) for punct in self.config.sentence_break_punctuation)
        has_clause_end = any(word_text.endswith(punct) for punct in self.config.clause_break_punctuation)

        # 句末标点符号断句 (最高优先级)
        if (has_sentence_end and
            duration >= self.config.min_subtitle_duration * 0.8 and
            word_count >= 3):
            logger.debug(f"断句(优先级2a): 当前词以句末标点结尾 ({word_text})")
            return True

        # 分句标点符号断句
        if (has_clause_end and
            duration >= self.config.min_subtitle_duration * 1.5 and
            word_count >= 4):
            logger.debug(f"断句(优先级2b): 当前词以分句标点结尾 ({word_text})")
            return True

        # 优先级3: 语义完整性考虑
        if word_count < self.config.semantic_min_words and has_more_words:
            # 语义单元过短，优先继续而不是断句
            logger.debug(f"不断句(优先级3): 语义单元过短 ({word_count} < {self.config.semantic_min_words})")
            return False

        # 优先级4: 最大时长限制 (5秒，按您的要求)
        max_duration = 5.0  # 使用您指定的5秒
        if duration > max_duration:
            logger.debug(f"断句(优先级4): 超过最大时长限制 ({duration:.2f}s > {max_duration}s)")
            return True

        # 优先级5: 最小时长检查 (1.2秒，按您的要求)
        min_duration = 1.2  # 使用您指定的1.2秒
        if has_more_words and duration < min_duration:
            logger.debug(f"不断句(优先级5): 时长过短 ({duration:.2f}s < {min_duration}s)")
            return False

        # 优先级6: 字符数限制 (40字符/行，按您的要求) - 最低优先级
        # 需要计算当前segment的字符数
        segment_chars = len(word_text) + (word_count - 1) * 1  # 粗略估算
        max_chars = 40  # 使用您指定的40字符/行
        if segment_chars > max_chars * self.config.max_lines_per_subtitle:
            logger.debug(f"断句(优先级6): 字符数过多 ({segment_chars} > {max_chars * self.config.max_lines_per_subtitle})")
            return True

        # 默认情况：不断句
        logger.debug(f"不断句: 未满足任何断句条件")
        return False

    def _finalize_current_segment(self, words: List[Dict], start_time: float,
                                end_time: float, segments: List[Dict]):
        """完成当前segment的处理"""
        # 合并词文本
        text = " ".join([w["word"].strip() for w in words])

        # 计算平均置信度
        avg_confidence = sum(w.get("confidence", 0.0) for w in words) / len(words)

        # 创建segment数据
        segment = {
            "start": start_time,
            "end": end_time,
            "text": text,
            "words": words,
            "confidence": avg_confidence,
            "word_count": len(words),
            "character_count": len(text),
            "duration": end_time - start_time
        }

        segments.append(segment)

        logger.debug(f"生成segment: {text[:30]}... ({start_time:.2f}-{end_time:.2f}s, {len(words)}词)")

    def _fallback_to_original_segments(self, word_timestamps_data: Dict) -> List[Dict]:
        """回退到原始segment数据"""
        logger.warning("使用原始segment数据作为回退方案")

        segments = []
        for segment in word_timestamps_data["segments"]:
            segment_data = {
                "start": segment["start"],
                "end": segment["end"],
                "text": segment["text"],
                "words": segment.get("words", []),
                "confidence": 1.0,
                "word_count": len(segment.get("words", [])),
                "character_count": len(segment["text"]),
                "duration": segment["end"] - segment["start"]
            }
            segments.append(segment_data)

        return segments

    def generate_optimized_srt(self, segments: List[Dict]) -> str:
        """生成优化后的SRT格式字幕"""
        srt_content = ""

        for i, segment in enumerate(segments):
            start_time = segment["start"]
            end_time = segment["end"]
            text = segment["text"]

            # 格式化时间
            start_str = self._format_srt_time(start_time)
            end_str = self._format_srt_time(end_time)

            srt_content += f"{i + 1}\n"
            srt_content += f"{start_str} --> {end_str}\n"
            srt_content += f"{text}\n\n"

        return srt_content

    def _format_srt_time(self, seconds: float) -> str:
        """格式化时间为SRT格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)

        return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"

    def save_optimized_subtitles(self, segments: List[Dict], output_path: str,
                               format_type: str = "both"):
        """
        保存优化后的字幕文件

        Args:
            segments: 优化后的字幕断句
            output_path: 输出文件路径（不含扩展名）
            format_type: 输出格式 ("srt", "json", "both")
        """
        base_path = output_path

        if format_type in ["srt", "both"]:
            # 生成SRT文件
            srt_content = self.generate_optimized_srt(segments)
            srt_path = f"{base_path}_optimized.srt"
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
            logger.info(f"优化SRT字幕已保存: {srt_path}")

        if format_type in ["json", "both"]:
            # 生成JSON文件
            json_data = {
                "format": "optimized_subtitles",
                "total_segments": len(segments),
                "config": {
                    "max_subtitle_duration": self.config.max_subtitle_duration,
                    "max_chars_per_line": self.config.max_chars_per_line,
                    "word_gap_threshold": self.config.word_gap_threshold
                },
                "segments": segments
            }

            json_path = f"{base_path}_optimized.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            logger.info(f"优化JSON字幕已保存: {json_path}")

    def analyze_segmentation_quality(self, original_segments: List[Dict],
                                   optimized_segments: List[Dict]) -> Dict:
        """分析断句优化质量"""
        original_count = len(original_segments)
        optimized_count = len(optimized_segments)

        # 计算原始和优化后的平均时长
        original_avg_duration = sum(s["duration"] for s in original_segments) / original_count if original_count > 0 else 0
        optimized_avg_duration = sum(s["duration"] for s in optimized_segments) / optimized_count if optimized_count > 0 else 0

        # 计算符合时长要求的segment比例
        valid_duration_original = sum(1 for s in original_segments
                                    if self.config.min_subtitle_duration <= s["duration"] <= self.config.max_subtitle_duration)
        valid_duration_optimized = sum(1 for s in optimized_segments
                                     if self.config.min_subtitle_duration <= s["duration"] <= self.config.max_subtitle_duration)

        # 计算符合字符数要求的segment比例
        valid_chars_original = sum(1 for s in original_segments
                                 if s["character_count"] <= self.config.max_chars_per_line * self.config.max_lines_per_subtitle)
        valid_chars_optimized = sum(1 for s in optimized_segments
                                  if s["character_count"] <= self.config.max_chars_per_line * self.config.max_lines_per_subtitle)

        analysis = {
            "segment_counts": {
                "original": original_count,
                "optimized": optimized_count,
                "reduction_ratio": (original_count - optimized_count) / original_count if original_count > 0 else 0
            },
            "average_durations": {
                "original": original_avg_duration,
                "optimized": optimized_avg_duration
            },
            "quality_metrics": {
                "duration_compliance": {
                    "original": valid_duration_original / original_count if original_count > 0 else 0,
                    "optimized": valid_duration_optimized / optimized_count if optimized_count > 0 else 0
                },
                "character_compliance": {
                    "original": valid_chars_original / original_count if original_count > 0 else 0,
                    "optimized": valid_chars_optimized / optimized_count if optimized_count > 0 else 0
                }
            }
        }

        logger.info(f"断句质量分析完成:")
        logger.info(f"  原始段数: {original_count}, 优化段数: {optimized_count}")
        logger.info(f"  平均时长: {original_avg_duration:.2f}s -> {optimized_avg_duration:.2f}s")
        logger.info(f"  时长合规率: {analysis['quality_metrics']['duration_compliance']['original']:.1%} -> {analysis['quality_metrics']['duration_compliance']['optimized']:.1%}")
        logger.info(f"  字符合规率: {analysis['quality_metrics']['character_compliance']['original']:.1%} -> {analysis['quality_metrics']['character_compliance']['optimized']:.1%}")

        return analysis

# 工具函数
def optimize_subtitles_from_json(json_path: str, output_path: str = None,
                               config: SubtitleConfig = None) -> Tuple[List[Dict], Dict]:
    """
    从JSON文件优化字幕断句的便捷函数

    Args:
        json_path: 词级时间戳JSON文件路径
        output_path: 输出文件路径（可选）
        config: 断句配置（可选）

    Returns:
        (优化后的segments, 质量分析结果)
    """
    # 加载词级时间戳数据
    with open(json_path, "r", encoding="utf-8") as f:
        word_timestamps_data = json.load(f)

    # 创建断句器
    segmenter = SubtitleSegmenter(config or SubtitleConfig())

    # 执行断句优化
    optimized_segments = segmenter.segment_by_word_timestamps(word_timestamps_data)

    # 获取原始segments用于对比
    original_segments = []
    for segment in word_timestamps_data["segments"]:
        segment_data = {
            "start": segment["start"],
            "end": segment["end"],
            "text": segment["text"],
            "words": segment.get("words", []),
            "confidence": 1.0,
            "word_count": len(segment.get("words", [])),
            "character_count": len(segment["text"]),
            "duration": segment["end"] - segment["start"]
        }
        original_segments.append(segment_data)

    # 质量分析
    quality_analysis = segmenter.analyze_segmentation_quality(original_segments, optimized_segments)

    # 保存优化结果
    if output_path:
        segmenter.save_optimized_subtitles(optimized_segments, output_path)

    return optimized_segments, quality_analysis