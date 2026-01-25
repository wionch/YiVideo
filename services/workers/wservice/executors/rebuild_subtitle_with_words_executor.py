"""
WService 词级重构字幕执行器。
"""

import json
import logging
import os
from typing import Any, Dict, List

from services.common.base_node_executor import BaseNodeExecutor
from services.common.path_builder import build_node_output_path, ensure_directory
from services.common.subtitle.word_level_aligner import align_words_to_text

logger = logging.getLogger(__name__)


class WServiceRebuildSubtitleWithWordsExecutor(BaseNodeExecutor):
    """
    词级重构字幕执行器。

    输入参数:
        - segments_file (str, 可选): 原始片段文件路径
        - segments_data (list, 可选): 原始片段数据
        - optimized_text (str, 可选): 优化后的全文文本
        - optimized_text_file (str, 可选): 优化后的全文文本文件
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

        optimized_segments_file = self._save_optimized_segments(segments, input_data)
        return {"optimized_segments_file": optimized_segments_file}

    def get_cache_key_fields(self) -> List[str]:
        return ["segments_file", "segments_data", "optimized_text", "optimized_text_file"]

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
