#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PySBD + LangChain 字幕分句测试脚本

两阶段处理：
1. PySBD 语义分句
2. LangChain RecursiveCharacterTextSplitter 字符限制处理（保护语义边界）
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class SubtitleSegment:
    """字幕片段"""
    id: int  # 片段唯一标识（从1开始）
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

        Args:
            text: 完整文本（包含标点和空格）
            timestamps: 词级时间戳列表 [{text, start, end}, ...]

        Returns:
            {char_index: {word, start, end, word_index}, ...}
        """
        char_map = {}
        text_idx = 0

        for word_idx, ts in enumerate(timestamps):
            word = ts["text"]
            start = ts["start"]
            end = ts["end"]

            # 跳过前导空格和标点（但不跳过撇号）
            while text_idx < len(text) and text[text_idx] in ' \t\n.,!?;:"':
                text_idx += 1

            if text_idx >= len(text):
                break

            word_len = len(word)

            # 尝试直接匹配
            if text_idx + word_len <= len(text) and \
               text[text_idx:text_idx+word_len].lower() == word.lower():
                for i in range(text_idx, text_idx + word_len):
                    char_map[i] = {
                        "word": word,
                        "start": start,
                        "end": end,
                        "word_index": word_idx
                    }
                text_idx += word_len
            else:
                # 匹配失败，尝试在附近范围内查找
                search_end = min(text_idx + 100, len(text))
                search_text = text[text_idx:search_end]
                found_offset = search_text.lower().find(word.lower())

                if found_offset != -1:
                    found_pos = text_idx + found_offset
                    for i in range(found_pos, found_pos + word_len):
                        char_map[i] = {
                            "word": word,
                            "start": start,
                            "end": end,
                            "word_index": word_idx
                        }
                    text_idx = found_pos + word_len

        return char_map


class PySBDLangChainSubtitleSegmenter:
    """PySBD + LangChain 字幕分句器"""

    def __init__(self, max_chars: int = 42):
        """
        初始化分句器

        Args:
            max_chars: 单行字幕最大字符数
        """
        try:
            import pysbd
            self.pysbd_seg = pysbd.Segmenter(language="en", clean=False)
        except ImportError:
            raise ImportError("请先安装 pysbd: pip install pysbd")

        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            # 字幕专用配置：优先在标点处断开
            self.langchain_splitter = RecursiveCharacterTextSplitter(
                chunk_size=max_chars,
                chunk_overlap=0,
                keep_separator="end",  # 🔑 关键：分隔符保留在前一个块的结尾
                separators=[
                    ", ",   # 优先级1：逗号后断开（自然停顿）
                    "; ",   # 优先级2：分号后断开
                    ". ",   # 优先级3：句号后断开
                    "! ",   # 优先级4：感叹号后断开
                    "? ",   # 优先级5：问号后断开
                    " ",    # 优先级6：空格
                    ""      # 优先级7：强制按字符切（最后手段）
                ]
            )
        except ImportError:
            raise ImportError("请先安装 langchain-text-splitters: pip install langchain-text-splitters")

        self.max_chars = max_chars

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
        print("开始两阶段分句处理")
        print("=" * 80)
        print(f"文本长度: {len(text)} 字符")
        print(f"时间戳数量: {len(time_stamps)} 个词")
        print(f"字符限制: {self.max_chars} 字符/行")
        print()

        # 阶段 1: PySBD 语义分句
        print("阶段 1: PySBD 语义分句...")
        pysbd_sentences = self.pysbd_seg.segment(text)
        print(f"✓ 分句完成，共 {len(pysbd_sentences)} 个句子\n")

        # 构建字符映射
        print("阶段 2: 构建字符到时间戳的映射...")
        char_map = ASRDataLoader.build_char_to_timestamp_map(text, time_stamps)
        print(f"✓ 映射完成，覆盖 {len(char_map)} 个字符\n")

        # 阶段 3: LangChain 字符限制处理 + 时间戳映射
        print("阶段 3: LangChain 字符限制处理...")
        segments = self._process_with_langchain(
            pysbd_sentences, text, char_map, time_stamps
        )
        print(f"✓ 处理完成，最终生成 {len(segments)} 个字幕片段\n")

        execution_time = time.time() - start_time

        # 计算统计数据
        stats = self._calculate_statistics(segments, pysbd_sentences)

        return {
            "segments": segments,
            "total_segments": len(segments),
            "execution_time": execution_time,
            "statistics": stats
        }

    def _process_with_langchain(self,
                                sentences: List[str],
                                full_text: str,
                                char_map: Dict[int, Dict],
                                timestamps: List[Dict]) -> List[SubtitleSegment]:
        """
        使用 LangChain 处理字符限制并映射时间戳

        Args:
            sentences: PySBD 分句结果
            full_text: 完整文本
            char_map: 字符到时间戳的映射
            timestamps: 原始词级时间戳列表

        Returns:
            List[SubtitleSegment]
        """
        segments = []
        char_offset = 0
        over_limit_count = 0
        segment_id = 1  # 从 1 开始计数

        for idx, sentence in enumerate(sentences, 1):
            sentence = sentence.strip()
            if not sentence:
                continue

            # 在原文中找到句子位置
            sent_start = full_text.find(sentence, char_offset)
            if sent_start == -1:
                print(f"  ⚠ 句子 {idx} 无法在原文中定位，跳过")
                continue

            sent_end = sent_start + len(sentence) - 1

            # 检查是否超过字符限制
            if len(sentence) <= self.max_chars:
                # 不超限，直接创建片段
                seg = self._create_segment(
                    segment_id, sentence, sent_start, sent_end, char_map, timestamps
                )
                if seg:
                    segments.append(seg)
                    segment_id += 1
            else:
                # 超限，使用 LangChain 分割
                over_limit_count += 1

                # LangChain 分割
                lines = self.langchain_splitter.split_text(sentence)

                # 为每行分配时间戳
                line_char_offset = sent_start
                for line_text in lines:
                    line_text = line_text.strip()
                    if not line_text:
                        continue

                    # 在原句中找到这一行的位置
                    line_start = full_text.find(line_text, line_char_offset)
                    if line_start == -1:
                        # 尝试模糊匹配（去除标点）
                        clean_line = line_text.strip('.,!?;: ')
                        line_start = full_text.find(clean_line, line_char_offset)

                    if line_start != -1:
                        line_end = line_start + len(line_text) - 1
                        seg = self._create_segment(
                            segment_id, line_text, line_start, line_end, char_map, timestamps
                        )
                        if seg:
                            segments.append(seg)
                            segment_id += 1
                        line_char_offset = line_end + 1

            char_offset = sent_end + 1

        if over_limit_count > 0:
            print(f"  📊 共 {over_limit_count} 个句子超过 {self.max_chars} 字符限制，已使用 LangChain 分割")

        return segments

    def _create_segment(self,
                       segment_id: int,
                       text: str,
                       start_pos: int,
                       end_pos: int,
                       char_map: Dict[int, Dict],
                       timestamps: List[Dict]) -> SubtitleSegment:
        """
        创建字幕片段

        Args:
            segment_id: 片段唯一标识（从1开始）
            text: 片段文本
            start_pos: 在原文中的起始位置
            end_pos: 在原文中的结束位置
            char_map: 字符映射表
            timestamps: 原始时间戳列表

        Returns:
            SubtitleSegment or None
        """
        # 获取起始和结束时间戳
        start_ts = char_map.get(start_pos, {}).get("start")
        end_ts = char_map.get(end_pos, {}).get("end")

        # 如果直接找不到，向后/向前搜索
        if start_ts is None:
            for i in range(start_pos, min(end_pos + 1, start_pos + 100)):
                if i in char_map:
                    start_ts = char_map[i]["start"]
                    break

        if end_ts is None:
            for i in range(end_pos, max(start_pos - 1, end_pos - 100), -1):
                if i in char_map:
                    end_ts = char_map[i]["end"]
                    break

        if start_ts is None or end_ts is None:
            return None

        # 提取词级时间戳
        word_indices = set()
        for char_pos in range(start_pos, end_pos + 1):
            if char_pos in char_map:
                word_idx = char_map[char_pos].get("word_index")
                if word_idx is not None:
                    word_indices.add(word_idx)

        word_indices = sorted(word_indices)
        segment_words = []
        for word_idx in word_indices:
            ts = timestamps[word_idx]
            segment_words.append({
                "text": ts["text"],
                "start": ts["start"],
                "end": ts["end"]
            })

        return SubtitleSegment(
            id=segment_id,
            text=text,
            start=start_ts,
            end=end_ts,
            duration=end_ts - start_ts,
            word_count=len(segment_words),
            char_count=len(text),
            words=segment_words
        )

    def _calculate_statistics(self,
                             segments: List[SubtitleSegment],
                             pysbd_sentences: List[str]) -> Dict[str, Any]:
        """计算统计数据"""
        if not segments:
            return {}

        # 检查字符限制合规性
        over_limit = [s for s in segments if s.char_count > self.max_chars]
        compliance_rate = (len(segments) - len(over_limit)) / len(segments) * 100

        total_duration = sum(s.duration for s in segments)
        total_words = sum(s.word_count for s in segments)
        total_chars = sum(s.char_count for s in segments)

        durations = [s.duration for s in segments]
        word_counts = [s.word_count for s in segments]
        char_counts = [s.char_count for s in segments]

        return {
            "pysbd_sentences": len(pysbd_sentences),
            "final_segments": len(segments),
            "expansion_ratio": len(segments) / len(pysbd_sentences),
            "character_limit": {
                "max_allowed": self.max_chars,
                "compliance_rate": compliance_rate,
                "over_limit_count": len(over_limit),
                "max_char_count": max(char_counts) if char_counts else 0
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
    print("PySBD + LangChain 字幕分句测试".center(80))
    print("=" * 80)
    print()

    # 加载数据
    print(f"数据源: {asr_file}\n")
    asr_data = ASRDataLoader.load(asr_file)

    # 创建分句器
    segmenter = PySBDLangChainSubtitleSegmenter(max_chars=42)

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
    print(f"PySBD 分句数: {stats['pysbd_sentences']}")
    print(f"最终字幕片段数: {stats['final_segments']}")
    print(f"扩展比例: {stats['expansion_ratio']:.2f}x")
    print()
    print("字符限制合规性:")
    print(f"  最大允许: {stats['character_limit']['max_allowed']} 字符")
    print(f"  合规率: {stats['character_limit']['compliance_rate']:.1f}%")
    print(f"  超限数量: {stats['character_limit']['over_limit_count']}")
    print(f"  最长片段: {stats['character_limit']['max_char_count']} 字符")
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
    print("片段字符数统计:")
    print(f"  总字符: {stats['char_count']['total']}")
    print(f"  平均: {stats['char_count']['average']:.1f}")
    print(f"  最少: {stats['char_count']['min']}")
    print(f"  最多: {stats['char_count']['max']}")
    print()

    # 展示前 10 个片段
    print("=" * 80)
    print("前 10 个字幕片段（含词级时间戳）")
    print("=" * 80)
    for i, seg in enumerate(result["segments"][:10], 1):
        marker = "⚠" if seg.char_count > 42 else "✓"
        print(f"\n{marker} {i}. [{seg.start:.2f}s - {seg.end:.2f}s] ({seg.duration:.2f}s, {seg.char_count}字符, {seg.word_count}词)")
        print(f"   {seg.text}")
        if seg.words:
            print(f"   词级时间戳 ({len(seg.words)} 个词):")
            for j in range(0, len(seg.words), 5):
                words_slice = seg.words[j:j+5]
                words_str = " | ".join([f"{w['text']}[{w['start']:.2f}-{w['end']:.2f}]"
                                       for w in words_slice])
                print(f"      {words_str}")

    # 如果有超限片段，展示它们
    over_limit_segs = [s for s in result["segments"] if s.char_count > 42]
    if over_limit_segs:
        print("\n" + "=" * 80)
        print(f"⚠ 超过 42 字符的片段 ({len(over_limit_segs)} 个)")
        print("=" * 80)
        for i, seg in enumerate(over_limit_segs[:5], 1):
            print(f"\n{i}. [{seg.start:.2f}s - {seg.end:.2f}s] ({seg.char_count} 字符)")
            print(f"   {seg.text}")

    # 保存结果
    output_dir = Path("/app/tmp")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "pysbd_langchain_subtitle_result.json"
    output_data = {
        "method": "PySBD + LangChain",
        "max_chars": 42,
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
