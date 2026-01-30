"""
字幕提取器

从 faster-whisper 输出格式加载和提取字幕数据。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import SubtitleSegment, WordTimestamp


class SubtitleExtractor:
    """
    字幕提取器

    负责从 faster-whisper 输出格式加载字幕数据，
    并提供格式化的提取功能。

    Attributes:
        _data: 原始字幕数据字典
        _segments: 解析后的字幕段列表
        _metadata: 元数据信息
    """

    def __init__(self):
        """初始化提取器"""
        self._data: Dict[str, Any] = {}
        self._segments: List[SubtitleSegment] = []
        self._metadata: Dict[str, Any] = {}

    def load_from_file(self, file_path: str) -> "SubtitleExtractor":
        """
        从JSON文件加载字幕数据

        Args:
            file_path: JSON文件路径

        Returns:
            self: 支持链式调用

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: JSON格式无效
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"字幕文件不存在: {file_path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"无效的JSON格式: {e}")

        return self.load_from_dict(data)

    def load_from_dict(self, data: Dict[str, Any]) -> "SubtitleExtractor":
        """
        从字典加载字幕数据

        Args:
            data: 包含字幕数据的字典

        Returns:
            self: 支持链式调用

        Raises:
            ValueError: 数据格式无效
        """
        if not isinstance(data, dict):
            raise ValueError("数据必须是字典类型")

        self._data = data
        self._metadata = data.get("metadata", {})
        self._segments = self._parse_segments(data.get("segments", []))

        return self

    def _parse_segments(self, segments_data: List[Dict[str, Any]]) -> List[SubtitleSegment]:
        """
        解析字幕段数据

        Args:
            segments_data: 字幕段原始数据列表

        Returns:
            解析后的 SubtitleSegment 列表
        """
        segments = []
        for seg_data in segments_data:
            try:
                words = None
                if "words" in seg_data and seg_data["words"]:
                    words = [
                        WordTimestamp(
                            word=w.get("word", ""),
                            start=w.get("start", 0.0),
                            end=w.get("end", 0.0),
                            probability=w.get("probability", 1.0),
                        )
                        for w in seg_data["words"]
                    ]

                segment = SubtitleSegment(
                    id=seg_data.get("id", 0),
                    start=seg_data.get("start", 0.0),
                    end=seg_data.get("end", 0.0),
                    text=seg_data.get("text", "").strip(),
                    words=words,
                )
                segments.append(segment)
            except (ValueError, TypeError) as e:
                # 跳过无效的字幕段
                continue

        return segments

    def extract_formatted_lines(self) -> List[str]:
        """
        提取格式化的字幕行

        格式: [ID]文本

        Returns:
            格式化后的字幕行列表
        """
        return [f"[{seg.id}]{seg.text}" for seg in self._segments]

    def get_segment_by_id(self, segment_id: int) -> Optional[SubtitleSegment]:
        """
        通过ID获取字幕段

        Args:
            segment_id: 字幕段ID

        Returns:
            找到的字幕段，未找到返回None
        """
        for segment in self._segments:
            if segment.id == segment_id:
                return segment
        return None

    def get_all_segments(self) -> List[SubtitleSegment]:
        """
        获取所有字幕段

        Returns:
            字幕段列表
        """
        return self._segments.copy()

    def get_metadata(self) -> Dict[str, Any]:
        """
        获取元数据

        Returns:
            元数据字典
        """
        return self._metadata.copy()

    def get_total_lines(self) -> int:
        """
        获取总行数

        Returns:
            字幕段数量
        """
        return len(self._segments)
