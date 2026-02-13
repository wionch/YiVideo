#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PySBD 字幕分句测试脚本

使用 PySBD 对 Qwen3 ASR 转录结果进行语义分句，
并映射词级时间戳到句子级别。
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class SubtitleSegment:
    """字幕片段"""
    text: str
    start: float
    end: float
    duration: float
    word_count: int
    char_count: int
    words: List[Dict[str, Any]]  # 词级时间戳列表


class ASRDataLoader:
    """加载 Qwen3 ASR 数据"""

    @staticmethod
    def load(file_path: str) -> Dict[str, Any]:
        """加载 ASR JSON 数据"""
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def build_char_to_timestamp_map(text: str, timestamps: List[Dict]) -> Dict[int, Dict]:
        """
        构建字符位置到时间戳的映射

        关键问题：
        1. ASR 时间戳的词不包含标点和空格
        2. 缩写词处理：原文 "you've" vs 时间戳可能是 "you've" 或分开的 "you" + "'ve"

        Args:
            text: 完整文本（包含标点和空格）
            timestamps: 词级时间戳列表 [{text, start, end}, ...]

        Returns:
            {char_index: {word, start, end, word_index}, ...}
            其中 word_index 是该词在原始 timestamps 列表中的索引
        """
        char_map = {}
        text_idx = 0

        for word_idx, ts in enumerate(timestamps):
            word = ts["text"]
            start = ts["start"]
            end = ts["end"]

            # 跳过前导空格和标点（但不跳过撇号，因为它可能是缩写的一部分）
            while text_idx < len(text) and text[text_idx] in ' \t\n.,!?;:"':
                text_idx += 1

            if text_idx >= len(text):
                break

            word_len = len(word)

            # 尝试直接匹配
            if text_idx + word_len <= len(text) and \
               text[text_idx:text_idx+word_len].lower() == word.lower():
                # 精确匹配
                for i in range(text_idx, text_idx + word_len):
                    char_map[i] = {
                        "word": word,
                        "start": start,
                        "end": end,
                        "word_index": word_idx  # 记录词索引
                    }
                text_idx += word_len
            else:
                # 匹配失败，尝试在附近范围内查找
                # 扩大搜索范围到100字符以处理错位情况
                search_end = min(text_idx + 100, len(text))
                search_text = text[text_idx:search_end]

                # 使用不区分大小写的查找
                found_offset = search_text.lower().find(word.lower())

                if found_offset != -1:
                    found_pos = text_idx + found_offset
                    for i in range(found_pos, found_pos + word_len):
                        char_map[i] = {
                            "word": word,
                            "start": start,
                            "end": end,
                            "word_index": word_idx  # 记录词索引
                        }
                    text_idx = found_pos + word_len
                else:
                    # 仍然找不到，可能是数据问题，跳过这个词
                    # 但不移动 text_idx，让下一个词继续尝试从当前位置匹配
                    pass

        return char_map


class PySBDSubtitleSegmenter:
    """PySBD 字幕分句器"""

    def __init__(self):
        try:
            import pysbd
            self.seg = pysbd.Segmenter(language="en", clean=False)
        except ImportError:
            raise ImportError("请先安装 pysbd: pip install pysbd")

    def segment(self, asr_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行分句

        Args:
            asr_data: ASR 数据 {text, time_stamps, ...}

        Returns:
            {
                segments: List[SubtitleSegment],
                total_segments: int,
                execution_time: float,
                statistics: {...}
            }
        """
        start_time = time.time()

        text = asr_data["text"]
        time_stamps = asr_data["time_stamps"]

        print("=" * 80)
        print("开始分句处理")
        print("=" * 80)
        print(f"文本长度: {len(text)} 字符")
        print(f"时间戳数量: {len(time_stamps)} 个词")
        print()

        # PySBD 分句
        print("步骤 1: PySBD 语义分句...")
        sentences = self.seg.segment(text)
        print(f"✓ 分句完成，共 {len(sentences)} 个句子\n")

        # 构建字符映射
        print("步骤 2: 构建字符到时间戳的映射...")
        char_map = ASRDataLoader.build_char_to_timestamp_map(text, time_stamps)
        print(f"✓ 映射完成，覆盖 {len(char_map)} 个字符\n")

        # 映射时间戳到句子
        print("步骤 3: 映射时间戳到句子...")
        segments = self._map_timestamps(sentences, text, char_map, time_stamps)
        print(f"✓ 映射完成，成功处理 {len(segments)} 个片段\n")

        execution_time = time.time() - start_time

        # 计算统计数据
        stats = self._calculate_statistics(segments, text, sentences)

        return {
            "segments": segments,
            "total_segments": len(segments),
            "execution_time": execution_time,
            "statistics": stats
        }

    def _map_timestamps(self,
                       sentences: List[str],
                       full_text: str,
                       char_map: Dict[int, Dict],
                       timestamps: List[Dict]) -> List[SubtitleSegment]:
        """
        将时间戳映射到句子

        Args:
            sentences: 分句列表
            full_text: 完整文本
            char_map: 字符到时间戳的映射
            timestamps: 原始词级时间戳列表

        Returns:
            List[SubtitleSegment]
        """
        segments = []
        char_offset = 0
        unmapped_count = 0

        for idx, sentence in enumerate(sentences, 1):
            sentence = sentence.strip()
            if not sentence:
                continue

            # 在原文中找到句子位置
            sent_start = full_text.find(sentence, char_offset)
            if sent_start == -1:
                # 如果找不到，尝试去除标点再找
                sentence_clean = sentence.strip('.,!?;: ')
                sent_start = full_text.find(sentence_clean, char_offset)

            if sent_start == -1:
                # 仍然找不到，跳过
                print(f"  ⚠ 句子 {idx} 无法在原文中定位: '{sentence[:50]}...'")
                unmapped_count += 1
                continue

            sent_end = sent_start + len(sentence) - 1

            # 获取起始时间戳
            start_ts = char_map.get(sent_start, {}).get("start")
            end_ts = char_map.get(sent_end, {}).get("end")

            # 如果直接找不到，向后/向前搜索最近的有效时间戳
            if start_ts is None or end_ts is None:
                if start_ts is None:
                    # 从句子开始往后找
                    for i in range(sent_start, min(sent_end + 1, len(full_text))):
                        if i in char_map:
                            start_ts = char_map[i]["start"]
                            break

                if end_ts is None:
                    # 从句子结束往前找
                    for i in range(sent_end, max(sent_start - 1, -1), -1):
                        if i in char_map:
                            end_ts = char_map[i]["end"]
                            break

            # 提取句子中的所有词级时间戳
            sentence_words = self._extract_words_for_sentence(
                sent_start, sent_end, char_map, timestamps
            )

            if start_ts is not None and end_ts is not None:
                segments.append(SubtitleSegment(
                    text=sentence,
                    start=start_ts,
                    end=end_ts,
                    duration=end_ts - start_ts,
                    word_count=len(sentence_words),  # 使用实际的词级时间戳数量
                    char_count=len(sentence),
                    words=sentence_words
                ))
            else:
                print(f"  ⚠ 句子 {idx} 缺少时间戳: '{sentence[:50]}...'")
                unmapped_count += 1

            char_offset = sent_start + len(sentence)

        if unmapped_count > 0:
            print(f"\n⚠ 共 {unmapped_count} 个句子未能成功映射时间戳")

        return segments

    def _extract_words_for_sentence(self,
                                    sent_start: int,
                                    sent_end: int,
                                    char_map: Dict[int, Dict],
                                    timestamps: List[Dict]) -> List[Dict[str, Any]]:
        """
        提取句子范围内的所有词级时间戳

        Args:
            sent_start: 句子起始字符位置
            sent_end: 句子结束字符位置
            char_map: 字符映射表
            timestamps: 原始时间戳列表

        Returns:
            List of {text, start, end}
        """
        # 收集句子范围内所有词的索引（去重）
        word_indices = set()

        for char_pos in range(sent_start, sent_end + 1):
            if char_pos in char_map:
                word_idx = char_map[char_pos].get("word_index")
                if word_idx is not None:
                    word_indices.add(word_idx)

        # 按索引排序并提取词信息
        word_indices = sorted(word_indices)
        sentence_words = []

        for word_idx in word_indices:
            ts = timestamps[word_idx]
            sentence_words.append({
                "text": ts["text"],
                "start": ts["start"],
                "end": ts["end"]
            })

        return sentence_words

    def _calculate_statistics(self,
                             segments: List[SubtitleSegment],
                             full_text: str,
                             sentences: List[str]) -> Dict[str, Any]:
        """计算统计数据"""
        if not segments:
            return {}

        total_duration = sum(s.duration for s in segments)
        total_words = sum(s.word_count for s in segments)
        total_chars = sum(s.char_count for s in segments)

        durations = [s.duration for s in segments]
        word_counts = [s.word_count for s in segments]
        char_counts = [s.char_count for s in segments]

        return {
            "total_sentences_detected": len(sentences),
            "total_segments_mapped": len(segments),
            "mapping_success_rate": len(segments) / len(sentences) * 100 if sentences else 0,
            "coverage": {
                "total_chars_in_text": len(full_text),
                "total_chars_in_segments": total_chars,
                "coverage_percentage": total_chars / len(full_text) * 100 if full_text else 0
            },
            "duration": {
                "total": total_duration,
                "average": total_duration / len(segments),
                "min": min(durations),
                "max": max(durations)
            },
            "word_count": {
                "total": total_words,
                "average": total_words / len(segments),
                "min": min(word_counts),
                "max": max(word_counts)
            },
            "char_count": {
                "total": total_chars,
                "average": total_chars / len(segments),
                "min": min(char_counts),
                "max": max(char_counts)
            }
        }


def main():
    """主函数"""
    # ASR 数据文件路径
    asr_file = "/share/workflows/task_id/nodes/qwen3_asr.transcribe_audio/data/raw_transcribe_result_task_id.json"

    print("=" * 80)
    print("PySBD 字幕分句测试".center(80))
    print("=" * 80)
    print()

    # 加载数据
    print(f"数据源: {asr_file}\n")
    asr_data = ASRDataLoader.load(asr_file)

    # 创建分句器
    segmenter = PySBDSubtitleSegmenter()

    # 执行分句
    result = segmenter.segment(asr_data)

    # 打印结果
    print("=" * 80)
    print("测试结果".center(80))
    print("=" * 80)
    print()

    stats = result["statistics"]
    print(f"执行时间: {result['execution_time']:.4f} 秒")
    print()
    print(f"分句数量: {stats['total_sentences_detected']}")
    print(f"成功映射: {result['total_segments']}")
    print(f"映射成功率: {stats['mapping_success_rate']:.1f}%")
    print()
    print(f"文本覆盖率: {stats['coverage']['coverage_percentage']:.1f}%")
    print(f"  原文总字符: {stats['coverage']['total_chars_in_text']}")
    print(f"  片段总字符: {stats['coverage']['total_chars_in_segments']}")
    print()
    print("片段时长统计:")
    print(f"  总时长: {stats['duration']['total']:.2f}s")
    print(f"  平均: {stats['duration']['average']:.2f}s")
    print(f"  最短: {stats['duration']['min']:.2f}s")
    print(f"  最长: {stats['duration']['max']:.2f}s")
    print()
    print("片段词数统计:")
    print(f"  总词数: {stats['word_count']['total']}")
    print(f"  平均: {stats['word_count']['average']:.1f}")
    print(f"  最少: {stats['word_count']['min']}")
    print(f"  最多: {stats['word_count']['max']}")
    print()

    # 展示前5个和后5个片段
    print("=" * 80)
    print("前 5 个字幕片段（含词级时间戳）")
    print("=" * 80)
    for i, seg in enumerate(result["segments"][:5], 1):
        print(f"\n{i}. [{seg.start:.2f}s - {seg.end:.2f}s] ({seg.duration:.2f}s, {seg.word_count}词)")
        print(f"   文本: {seg.text}")
        print(f"   词级时间戳 ({len(seg.words)} 个词):")
        # 每行显示5个词
        for j in range(0, len(seg.words), 5):
            words_slice = seg.words[j:j+5]
            words_str = " | ".join([f"{w['text']}[{w['start']:.2f}-{w['end']:.2f}]"
                                   for w in words_slice])
            print(f"      {words_str}")

    print("\n" + "=" * 80)
    print("后 5 个字幕片段（含词级时间戳）")
    print("=" * 80)
    for i, seg in enumerate(result["segments"][-5:], len(result["segments"]) - 4):
        print(f"\n{i}. [{seg.start:.2f}s - {seg.end:.2f}s] ({seg.duration:.2f}s, {seg.word_count}词)")
        print(f"   文本: {seg.text}")
        print(f"   词级时间戳 ({len(seg.words)} 个词):")
        for j in range(0, len(seg.words), 5):
            words_slice = seg.words[j:j+5]
            words_str = " | ".join([f"{w['text']}[{w['start']:.2f}-{w['end']:.2f}]"
                                   for w in words_slice])
            print(f"      {words_str}")

    # 保存结果
    output_dir = Path("/app/tmp")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "pysbd_subtitle_segmentation_result.json"
    output_data = {
        "execution_time": result["execution_time"],
        "total_segments": result["total_segments"],
        "statistics": stats,
        "segments": [asdict(seg) for seg in result["segments"]]
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(f"✓ 结果已保存: {output_file}")
    print("=" * 80)


if __name__ == "__main__":
    main()
