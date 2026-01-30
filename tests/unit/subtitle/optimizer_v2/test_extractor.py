"""
字幕提取器测试
"""

import json
import tempfile
from pathlib import Path

import pytest

from services.common.subtitle.optimizer_v2.extractor import SubtitleExtractor
from services.common.subtitle.optimizer_v2.models import SubtitleSegment


class TestSubtitleExtractor:
    """字幕提取器测试类"""

    @pytest.fixture
    def sample_data(self):
        """提供示例字幕数据"""
        return {
            "metadata": {
                "language": "zh",
                "duration": 120.5,
                "source": "faster-whisper"
            },
            "segments": [
                {
                    "id": 0,
                    "start": 0.0,
                    "end": 3.5,
                    "text": "  第一段字幕  ",
                    "words": [
                        {"word": "第一", "start": 0.0, "end": 1.5, "probability": 0.95},
                        {"word": "段", "start": 1.5, "end": 2.0, "probability": 0.98},
                        {"word": "字幕", "start": 2.0, "end": 3.5, "probability": 0.92}
                    ]
                },
                {
                    "id": 1,
                    "start": 4.0,
                    "end": 7.5,
                    "text": "第二段字幕",
                    "words": [
                        {"word": "第二", "start": 4.0, "end": 5.5, "probability": 0.94},
                        {"word": "段", "start": 5.5, "end": 6.0, "probability": 0.97},
                        {"word": "字幕", "start": 6.0, "end": 7.5, "probability": 0.93}
                    ]
                },
                {
                    "id": 2,
                    "start": 8.0,
                    "end": 10.0,
                    "text": "第三段字幕"
                }
            ]
        }

    @pytest.fixture
    def extractor(self, sample_data):
        """提供已加载的提取器实例"""
        extractor = SubtitleExtractor()
        extractor.load_from_dict(sample_data)
        return extractor

    def test_load_from_dict(self, sample_data):
        """测试从字典加载"""
        extractor = SubtitleExtractor()
        result = extractor.load_from_dict(sample_data)

        # 验证链式调用返回自身
        assert result is extractor
        # 验证数据已加载
        assert extractor.get_total_lines() == 3

    def test_load_from_dict_invalid_type(self):
        """测试加载非字典类型"""
        extractor = SubtitleExtractor()
        with pytest.raises(ValueError, match="必须是字典类型"):
            extractor.load_from_dict("invalid")

    def test_load_from_dict_empty(self):
        """测试加载空字典"""
        extractor = SubtitleExtractor()
        extractor.load_from_dict({})
        assert extractor.get_total_lines() == 0
        assert extractor.get_metadata() == {}

    def test_load_from_file(self, sample_data):
        """测试从文件加载"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(sample_data, f)
            temp_path = f.name

        try:
            extractor = SubtitleExtractor()
            result = extractor.load_from_file(temp_path)

            # 验证链式调用返回自身
            assert result is extractor
            # 验证数据已加载
            assert extractor.get_total_lines() == 3
            assert extractor.get_metadata()["language"] == "zh"
        finally:
            Path(temp_path).unlink()

    def test_load_from_file_not_found(self):
        """测试加载不存在的文件"""
        extractor = SubtitleExtractor()
        with pytest.raises(FileNotFoundError, match="字幕文件不存在"):
            extractor.load_from_file("/nonexistent/file.json")

    def test_load_from_file_invalid_json(self):
        """测试加载无效的JSON文件"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write("invalid json content")
            temp_path = f.name

        try:
            extractor = SubtitleExtractor()
            with pytest.raises(ValueError, match="无效的JSON格式"):
                extractor.load_from_file(temp_path)
        finally:
            Path(temp_path).unlink()

    def test_extract_formatted_lines(self, extractor):
        """测试提取格式化行"""
        lines = extractor.extract_formatted_lines()

        assert len(lines) == 3
        assert lines[0] == "[0]第一段字幕"
        assert lines[1] == "[1]第二段字幕"
        assert lines[2] == "[2]第三段字幕"

    def test_extract_formatted_lines_empty(self):
        """测试空数据提取格式化行"""
        extractor = SubtitleExtractor()
        extractor.load_from_dict({})
        lines = extractor.extract_formatted_lines()
        assert lines == []

    def test_get_segment_by_id(self, extractor):
        """测试通过ID获取段"""
        segment = extractor.get_segment_by_id(1)

        assert segment is not None
        assert segment.id == 1
        assert segment.text == "第二段字幕"
        assert segment.start == 4.0
        assert segment.end == 7.5

    def test_get_segment_by_id_not_found(self, extractor):
        """测试获取不存在的段"""
        segment = extractor.get_segment_by_id(999)
        assert segment is None

    def test_get_segment_by_id_negative(self, extractor):
        """测试获取负ID"""
        segment = extractor.get_segment_by_id(-1)
        assert segment is None

    def test_get_all_segments(self, extractor):
        """测试获取所有段"""
        segments = extractor.get_all_segments()

        assert len(segments) == 3
        assert all(isinstance(seg, SubtitleSegment) for seg in segments)
        # 验证返回的是副本
        segments.pop()
        assert extractor.get_total_lines() == 3

    def test_get_all_segments_empty(self):
        """测试空数据获取所有段"""
        extractor = SubtitleExtractor()
        extractor.load_from_dict({})
        segments = extractor.get_all_segments()
        assert segments == []

    def test_get_metadata(self, extractor):
        """测试获取元数据"""
        metadata = extractor.get_metadata()

        assert metadata["language"] == "zh"
        assert metadata["duration"] == 120.5
        assert metadata["source"] == "faster-whisper"
        # 验证返回的是副本
        metadata["new_key"] = "new_value"
        assert "new_key" not in extractor.get_metadata()

    def test_get_metadata_empty(self):
        """测试空数据获取元数据"""
        extractor = SubtitleExtractor()
        extractor.load_from_dict({})
        metadata = extractor.get_metadata()
        assert metadata == {}

    def test_get_total_lines(self, extractor):
        """测试获取总行数"""
        assert extractor.get_total_lines() == 3

    def test_get_total_lines_empty(self):
        """测试空数据获取总行数"""
        extractor = SubtitleExtractor()
        extractor.load_from_dict({})
        assert extractor.get_total_lines() == 0

    def test_segment_words_parsing(self, extractor):
        """测试词级时间戳解析"""
        segment = extractor.get_segment_by_id(0)

        assert segment.words is not None
        assert len(segment.words) == 3
        assert segment.words[0].word == "第一"
        assert segment.words[0].start == 0.0
        assert segment.words[0].probability == 0.95

    def test_segment_without_words(self, extractor):
        """测试无词级时间戳的段"""
        segment = extractor.get_segment_by_id(2)

        assert segment.words is None
        assert segment.text == "第三段字幕"

    def test_text_stripping(self, extractor):
        """测试文本去空格"""
        segment = extractor.get_segment_by_id(0)
        # 原始文本 "  第一段字幕  " 应该被去除首尾空格
        assert segment.text == "第一段字幕"

    def test_invalid_segment_skipped(self):
        """测试无效段被跳过"""
        data = {
            "segments": [
                {
                    "id": 0,
                    "start": 0.0,
                    "end": 3.5,
                    "text": "有效段"
                },
                {
                    "id": 1,
                    "start": 5.0,
                    "end": 3.0,  # 无效: 结束时间小于开始时间
                    "text": "无效段"
                },
                {
                    "id": 2,
                    "start": 4.0,
                    "end": 7.5,
                    "text": "另一个有效段"
                }
            ]
        }
        extractor = SubtitleExtractor()
        extractor.load_from_dict(data)

        # 无效段应该被跳过
        assert extractor.get_total_lines() == 2
        assert extractor.get_segment_by_id(0) is not None
        assert extractor.get_segment_by_id(1) is None
        assert extractor.get_segment_by_id(2) is not None

    def test_chained_loading(self, sample_data):
        """测试链式加载"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(sample_data, f)
            temp_path = f.name

        try:
            extractor = SubtitleExtractor()
            # 测试链式调用
            lines = extractor.load_from_file(temp_path).extract_formatted_lines()

            assert len(lines) == 3
            assert lines[0] == "[0]第一段字幕"
        finally:
            Path(temp_path).unlink()
