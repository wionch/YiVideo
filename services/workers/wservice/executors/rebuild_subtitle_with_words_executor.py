"""
WService 词级重构字幕执行器。
"""

import json
import logging
import os
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Tuple

from services.common.base_node_executor import BaseNodeExecutor
from services.common.path_builder import build_node_output_path, ensure_directory
from services.common.subtitle.word_level_aligner import (
    align_words_to_text,
    rebuild_segments_by_words,
)

logger = logging.getLogger(__name__)


class WServiceRebuildSubtitleWithWordsExecutor(BaseNodeExecutor):
    """
    词级重构字幕执行器。

    输入参数:
        - segments_file (str, 可选): 原始片段文件路径
        - segments_data (list, 可选): 原始片段数据
        - optimized_text (str, 可选): 优化后的全文文本
        - optimized_text_file (str, 可选): 优化后的全文文本文件
        - report (bool, 可选): 是否生成重构报告
    """

    def validate_input(self) -> None:
        input_data = self.get_input_data()
        has_segments = bool(input_data.get("segments_file") or input_data.get("segments_data"))
        has_text = bool(input_data.get("optimized_text") or input_data.get("optimized_text_file"))
        if not has_segments:
            raise ValueError("缺少必需参数: segments_file 或 segments_data")
        if not has_text:
            raise ValueError("缺少必需参数: optimized_text 或 optimized_text_file")

    def execute_core_logic(self) -> Dict[str, Any]:
        input_data = self.get_input_data()
        segments = self._load_segments(input_data)
        if not segments:
            raise ValueError("未找到可用的字幕片段数据")

        segment_texts = self._collect_segment_texts(segments)
        segment_ids = self._extract_segment_ids(segments)
        original_text = self._merge_texts(segment_texts)

        optimized_text = self._load_optimized_text(input_data)
        if not optimized_text:
            raise ValueError("优化文本为空")

        flat_words, word_index_map = self._flatten_words(segments)
        if not flat_words:
            raise ValueError("字幕片段缺少词级时间戳数据")

        aligned_words, error = align_words_to_text(
            flat_words,
            optimized_text,
            return_error=True
        )
        if error:
            raise ValueError(error)
        self._apply_aligned_words(segments, aligned_words, word_index_map)

        rebuilt_segments = rebuild_segments_by_words(
            segments,
            max_cpl=42,
            max_cps=18.0,
            min_duration=1.0,
            max_duration=7.0
        )
        optimized_segments = rebuilt_segments or segments
        optimized_segments_file = self._save_optimized_segments(optimized_segments, input_data)
        output = {"optimized_segments_file": optimized_segments_file}

        if self._should_generate_report(input_data):
            report_file = self._generate_report(
                original_text,
                optimized_text,
                segment_texts,
                segment_ids,
                input_data
            )
            output["report_file"] = report_file

        return output

    def get_cache_key_fields(self) -> List[str]:
        return ["segments_file", "segments_data", "optimized_text", "optimized_text_file", "report"]

    def _should_generate_report(self, input_data: Dict[str, Any]) -> bool:
        value = input_data.get("report", False)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        return False

    def _extract_segment_ids(self, segments: List[Dict[str, Any]]) -> List[int]:
        segment_ids: List[int] = []
        for index, segment in enumerate(segments):
            segment_id = segment.get("id")
            if isinstance(segment_id, int) and segment_id > 0:
                segment_ids.append(segment_id)
            else:
                segment_ids.append(index + 1)
        return segment_ids

    def _load_segments(self, input_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        if isinstance(input_data.get("segments_data"), list):
            return input_data["segments_data"]

        segments_file = input_data.get("segments_file")
        if not segments_file:
            return []

        if not os.path.exists(segments_file):
            logger.warning(f"Segments 文件不存在: {segments_file}")
            return []

        try:
            with open(segments_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "segments" in data:
                return data["segments"]
        except Exception as e:
            logger.error(f"加载 segments 文件失败: {e}")
        return []

    def _load_optimized_text(self, input_data: Dict[str, Any]) -> str:
        optimized_text = input_data.get("optimized_text")
        if optimized_text:
            return str(optimized_text)

        optimized_text_file = input_data.get("optimized_text_file")
        if not optimized_text_file:
            return ""
        if not os.path.exists(optimized_text_file):
            logger.warning(f"优化文本文件不存在: {optimized_text_file}")
            return ""

        try:
            with open(optimized_text_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"读取优化文本文件失败: {e}")
            return ""

    def _flatten_words(self, segments: List[Dict[str, Any]]) -> tuple:
        flat_words: List[Dict[str, Any]] = []
        index_map: List[tuple] = []
        for segment_index, segment in enumerate(segments):
            words = segment.get("words") or []
            if not isinstance(words, list):
                continue
            for word_index, word in enumerate(words):
                if isinstance(word, dict):
                    flat_words.append(word)
                    index_map.append((segment_index, word_index))
        return flat_words, index_map

    def _apply_aligned_words(
        self,
        segments: List[Dict[str, Any]],
        aligned_words: List[Dict[str, Any]],
        index_map: List[tuple]
    ) -> None:
        for aligned_word, (segment_index, word_index) in zip(aligned_words, index_map):
            segments[segment_index]["words"][word_index] = aligned_word

    def _save_optimized_segments(self, segments: List[Dict[str, Any]], input_data: Dict[str, Any]) -> str:
        workflow_id = self.context.workflow_id
        segments_file = input_data.get("segments_file")
        base_name = (
            os.path.splitext(os.path.basename(segments_file))[0]
            if segments_file
            else "segments"
        )
        output_path = build_node_output_path(
            task_id=workflow_id,
            node_name=self.stage_name,
            file_type="data",
            filename=f"{base_name}_optimized_words.json"
        )
        ensure_directory(output_path)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(segments, f, ensure_ascii=False, indent=2)

        logger.info(f"[{workflow_id}] 词级重构结果已保存: {output_path}")
        return output_path

    def _collect_segment_texts(self, segments: List[Dict[str, Any]]) -> List[str]:
        return [self._build_segment_text(segment) for segment in segments]

    def _merge_texts(self, texts: List[str]) -> str:
        texts = [text for text in texts if text]
        return " ".join(texts)

    def _build_segment_text(self, segment: Dict[str, Any]) -> str:
        text = str(segment.get("text", "")).strip()
        if text:
            return text
        words = segment.get("words") or []
        word_texts = [str(word.get("word", "")) for word in words if word.get("word")]
        if not word_texts:
            return ""
        if any(self._has_edge_space(word) for word in word_texts):
            return "".join(word_texts).strip()
        if all(self._is_ascii_text(word) for word in word_texts):
            return " ".join(word_texts).strip()
        return "".join(word_texts).strip()

    def _generate_report(
        self,
        original_text: str,
        optimized_text: str,
        segment_texts: List[str],
        segment_ids: List[int],
        input_data: Dict[str, Any]
    ) -> str:
        workflow_id = self.context.workflow_id
        segments_file = input_data.get("segments_file")
        base_name = (
            os.path.splitext(os.path.basename(segments_file))[0]
            if segments_file
            else "segments"
        )
        report_path = build_node_output_path(
            task_id=workflow_id,
            node_name=self.stage_name,
            file_type="data",
            filename=f"{base_name}_rebuild_report.txt"
        )
        ensure_directory(report_path)

        details = self._build_change_details(
            original_text,
            optimized_text,
            segment_texts,
            segment_ids
        )
        lines = [
            "原字幕文本:",
            original_text,
            "",
            "优化后的字幕文本:",
            optimized_text,
            "",
            "变化明细:",
        ]
        for detail in details:
            lines.append(detail)
        content = "\n".join(lines).strip() + "\n"

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"[{workflow_id}] 词级重构报告已生成: {report_path}")
        return report_path

    def _build_change_details(
        self,
        original_text: str,
        optimized_text: str,
        segment_texts: List[str],
        segment_ids: List[int]
    ) -> List[str]:
        original_tokens, original_joiner = self._tokenize_for_diff(original_text)
        optimized_tokens, optimized_joiner = self._tokenize_for_diff(optimized_text)
        use_word_split = original_joiner == " "
        token_segment_ids = self._map_tokens_to_segment_ids(
            segment_texts,
            segment_ids,
            use_word_split
        )
        if len(token_segment_ids) != len(original_tokens):
            token_segment_ids = [None] * len(original_tokens)
        matcher = SequenceMatcher(None, original_tokens, optimized_tokens, autojunk=False)

        details: List[str] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            segment_range = self._format_segment_id_range(
                self._collect_segment_ids_for_range(token_segment_ids, i1, i2, tag)
            )
            if tag == "delete":
                details.append(
                    f"字幕ID: {segment_range} 删除: "
                    f"{self._join_tokens(original_tokens[i1:i2], original_joiner)}"
                )
            elif tag == "insert":
                details.append(
                    f"字幕ID: {segment_range} 新增: "
                    f"{self._join_tokens(optimized_tokens[j1:j2], optimized_joiner)}"
                )
            elif tag == "replace":
                original_part = self._join_tokens(original_tokens[i1:i2], original_joiner)
                optimized_part = self._join_tokens(optimized_tokens[j1:j2], optimized_joiner)
                details.append(f"字幕ID: {segment_range} 替换: {original_part} -> {optimized_part}")

        if not details:
            details.append("无变化")

        return details

    def _tokenize_for_diff(self, text: str) -> Tuple[List[str], str]:
        text = text.strip()
        if not text:
            return [], ""
        if re.search(r"\s", text):
            return text.split(), " "
        tokens = [char for char in text if not char.isspace()]
        return tokens, ""

    def _join_tokens(self, tokens: List[str], joiner: str) -> str:
        if not tokens:
            return ""
        if joiner:
            return joiner.join(tokens).strip()
        return "".join(tokens).strip()

    def _map_tokens_to_segment_ids(
        self,
        segment_texts: List[str],
        segment_ids: List[int],
        use_word_split: bool
    ) -> List[int]:
        token_segment_ids: List[int] = []
        for segment_text, segment_id in zip(segment_texts, segment_ids):
            tokens = self._split_text_for_mapping(segment_text, use_word_split)
            token_segment_ids.extend([segment_id] * len(tokens))
        return token_segment_ids

    def _split_text_for_mapping(self, text: str, use_word_split: bool) -> List[str]:
        text = text.strip()
        if not text:
            return []
        if use_word_split:
            return text.split()
        return [char for char in text if not char.isspace()]

    def _collect_segment_ids_for_range(
        self,
        token_segment_ids: List[int],
        start: int,
        end: int,
        tag: str
    ) -> List[int]:
        if tag == "insert":
            if start > 0:
                anchor = start - 1
            elif start < len(token_segment_ids):
                anchor = start
            else:
                anchor = None
            if anchor is None or anchor >= len(token_segment_ids):
                return []
            return [token_segment_ids[anchor]]

        if start >= end or start >= len(token_segment_ids):
            return []
        end = min(end, len(token_segment_ids))
        return [segment_id for segment_id in token_segment_ids[start:end] if segment_id]

    def _format_segment_id_range(self, segment_ids: List[int]) -> str:
        if not segment_ids:
            return "未知"
        min_id = min(segment_ids)
        max_id = max(segment_ids)
        if min_id == max_id:
            return str(min_id)
        return f"{min_id}-{max_id}"

    def _has_edge_space(self, text: str) -> bool:
        return bool(text and (text[0].isspace() or text[-1].isspace()))

    def _is_ascii_text(self, text: str) -> bool:
        return bool(text) and all(ord(char) < 128 for char in text)
