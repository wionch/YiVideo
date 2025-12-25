# tests/unit/common/subtitle/test_speaker_based_merger.py
# -*- coding: utf-8 -*-

"""
基于说话人时间区间的字幕合并模块单元测试
"""

import pytest
from services.common.subtitle.speaker_based_merger import (
    merge_speaker_based_subtitles,
    match_words_to_speaker_segments,
    calculate_match_quality
)
from services.common.subtitle.word_timestamp_utils import (
    flatten_word_timestamps,
    calculate_overlap_ratio
)


class TestWordTimestampUtils:
    """词级时间戳工具函数测试"""

    def test_flatten_word_timestamps(self):
        """测试词级时间戳扁平化"""
        transcript_segments = [
            {
                'start': 10.0,
                'end': 12.0,
                'text': 'Hello world',
                'speaker': 'SPEAKER_00',
                'words': [
                    {'word': 'Hello', 'start': 10.0, 'end': 10.5, 'probability': 0.9},
                    {'word': 'world', 'start': 10.6, 'end': 11.0, 'probability': 0.95}
                ]
            },
            {
                'start': 12.5,
                'end': 14.0,
                'text': 'Test',
                'speaker': 'SPEAKER_01',
                'words': [
                    {'word': 'Test', 'start': 12.5, 'end': 13.0, 'probability': 0.85}
                ]
            }
        ]

        all_words = flatten_word_timestamps(transcript_segments)

        assert len(all_words) == 3
        assert all_words[0]['word'] == 'Hello'
        assert all_words[0]['speaker'] == 'SPEAKER_00'
        assert all_words[2]['word'] == 'Test'
        assert all_words[2]['speaker'] == 'SPEAKER_01'

    def test_calculate_overlap_ratio_full_match(self):
        """测试完全包含的重叠比例"""
        ratio = calculate_overlap_ratio(12.0, 13.0, 11.0, 14.0)
        assert ratio == 1.0

    def test_calculate_overlap_ratio_partial(self):
        """测试部分重叠的重叠比例"""
        ratio = calculate_overlap_ratio(12.0, 14.0, 13.0, 15.0)
        assert ratio == 0.5

    def test_calculate_overlap_ratio_no_overlap(self):
        """测试无重叠"""
        ratio = calculate_overlap_ratio(10.0, 11.0, 12.0, 13.0)
        assert ratio == 0.0


class TestMatchQuality:
    """匹配质量计算测试"""

    def test_calculate_match_quality_full_matches(self):
        """测试全部完全匹配的情况"""
        matched_words = [
            {'word': 'Hello', 'start': 12.0, 'end': 12.5},
            {'word': 'world', 'start': 12.6, 'end': 13.0}
        ]

        quality = calculate_match_quality(matched_words, 12.0, 13.0)

        assert quality['matched_words'] == 2
        assert quality['full_matches'] == 2
        assert quality['partial_overlaps'] == 0
        assert quality['coverage_ratio'] > 0.8

    def test_calculate_match_quality_no_matches(self):
        """测试无匹配词的情况"""
        quality = calculate_match_quality([], 12.0, 13.0)

        assert quality['matched_words'] == 0
        assert quality['coverage_ratio'] == 0.0


class TestSpeakerBasedMerger:
    """基于说话人的字幕合并测试"""

    def test_merge_speaker_based_subtitles_basic(self):
        """测试基本的合并功能"""
        transcript_segments = [
            {
                'start': 10.0,
                'end': 15.0,
                'text': 'Hello world test',
                'words': [
                    {'word': 'Hello', 'start': 10.0, 'end': 10.5, 'probability': 0.9},
                    {'word': 'world', 'start': 12.0, 'end': 12.5, 'probability': 0.95},
                    {'word': 'test', 'start': 14.0, 'end': 14.5, 'probability': 0.85}
                ]
            }
        ]

        diarization_segments = [
            {'start': 9.5, 'end': 11.0, 'speaker': 'SPEAKER_00'},
            {'start': 11.5, 'end': 13.0, 'speaker': 'SPEAKER_01'},
            {'start': 13.5, 'end': 15.0, 'speaker': 'SPEAKER_00'}
        ]

        merged = merge_speaker_based_subtitles(
            transcript_segments,
            diarization_segments,
            overlap_threshold=0.5
        )

        # 应该生成 3 个 segments（与 diarization 一致）
        assert len(merged) == 3

        # 第一个 segment 应该匹配到 "Hello"
        assert merged[0]['speaker'] == 'SPEAKER_00'
        assert 'Hello' in merged[0]['text']

        # 第二个 segment 应该匹配到 "world"
        assert merged[1]['speaker'] == 'SPEAKER_01'
        assert 'world' in merged[1]['text']

        # 第三个 segment 应该匹配到 "test"
        assert merged[2]['speaker'] == 'SPEAKER_00'
        assert 'test' in merged[2]['text']

    def test_merge_speaker_based_subtitles_empty_segment(self):
        """测试处理无匹配词的 segment"""
        transcript_segments = [
            {
                'start': 10.0,
                'end': 11.0,
                'text': 'Hello',
                'words': [
                    {'word': 'Hello', 'start': 10.0, 'end': 10.5, 'probability': 0.9}
                ]
            }
        ]

        diarization_segments = [
            {'start': 9.0, 'end': 11.0, 'speaker': 'SPEAKER_00'},
            {'start': 15.0, 'end': 20.0, 'speaker': 'SPEAKER_01'}  # 无匹配词
        ]

        merged = merge_speaker_based_subtitles(
            transcript_segments,
            diarization_segments,
            overlap_threshold=0.5
        )

        assert len(merged) == 2

        # 第一个 segment 有匹配词
        assert merged[0]['word_count'] > 0
        assert merged[0]['text'] != ''

        # 第二个 segment 无匹配词
        assert merged[1]['word_count'] == 0
        assert merged[1]['text'] == ''
        assert merged[1]['match_quality']['matched_words'] == 0

    def test_merge_speaker_based_subtitles_validation(self):
        """测试输入验证"""
        # 测试空转录片段
        with pytest.raises(ValueError, match="转录片段列表不能为空"):
            merge_speaker_based_subtitles([], [{'start': 1, 'end': 2, 'speaker': 'S'}])

        # 测试空说话人片段
        with pytest.raises(ValueError, match="说话人片段列表不能为空"):
            merge_speaker_based_subtitles(
                [{'start': 1, 'end': 2, 'words': []}],
                []
            )

        # 测试缺少词级时间戳
        with pytest.raises(ValueError, match="不包含词级时间戳"):
            merge_speaker_based_subtitles(
                [{'start': 1, 'end': 2, 'text': 'test'}],  # 无 words 字段
                [{'start': 1, 'end': 2, 'speaker': 'S'}]
            )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
