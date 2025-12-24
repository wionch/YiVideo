# tests/unit/common/test_cache_key_strategy.py
# -*- coding: utf-8 -*-

"""CacheKeyStrategy 单元测试"""

import pytest
from services.common.cache_key_strategy import (
    CacheKeyStrategy,
    can_reuse_cache,
    is_pending_state
)


class ConcreteCacheKeyStrategy(CacheKeyStrategy):
    """用于测试的具体缓存键策略"""

    def __init__(self, cache_fields):
        self.cache_fields = cache_fields

    def get_cache_key_fields(self):
        return self.cache_fields


class TestCacheKeyStrategy:
    """CacheKeyStrategy 测试"""

    def test_single_field_cache_key(self):
        """测试单字段缓存键生成"""
        strategy = ConcreteCacheKeyStrategy(["video_path"])
        cache_key = strategy.generate_cache_key(
            "ffmpeg.extract_audio",
            {"video_path": "/share/video.mp4"}
        )

        assert cache_key.startswith("ffmpeg.extract_audio:")
        assert len(cache_key.split(":")) == 2

    def test_multiple_fields_cache_key(self):
        """测试多字段缓存键生成"""
        strategy = ConcreteCacheKeyStrategy(["audio_path", "model_name"])
        cache_key = strategy.generate_cache_key(
            "faster_whisper.transcribe",
            {
                "audio_path": "/share/audio.wav",
                "model_name": "large-v3"
            }
        )

        assert cache_key.startswith("faster_whisper.transcribe:")

    def test_cache_key_stability(self):
        """测试缓存键稳定性(相同输入生成相同键)"""
        strategy = ConcreteCacheKeyStrategy(["audio_path", "model_name"])

        cache_key1 = strategy.generate_cache_key(
            "faster_whisper.transcribe",
            {
                "audio_path": "/share/audio.wav",
                "model_name": "large-v3"
            }
        )

        cache_key2 = strategy.generate_cache_key(
            "faster_whisper.transcribe",
            {
                "audio_path": "/share/audio.wav",
                "model_name": "large-v3"
            }
        )

        assert cache_key1 == cache_key2

    def test_cache_key_order_independence(self):
        """测试缓存键与字段顺序无关"""
        strategy = ConcreteCacheKeyStrategy(["field_a", "field_b"])

        cache_key1 = strategy.generate_cache_key(
            "test.node",
            {"field_a": "value_a", "field_b": "value_b"}
        )

        cache_key2 = strategy.generate_cache_key(
            "test.node",
            {"field_b": "value_b", "field_a": "value_a"}
        )

        assert cache_key1 == cache_key2

    def test_cache_key_different_values(self):
        """测试不同输入生成不同缓存键"""
        strategy = ConcreteCacheKeyStrategy(["video_path"])

        cache_key1 = strategy.generate_cache_key(
            "ffmpeg.extract_audio",
            {"video_path": "/share/video1.mp4"}
        )

        cache_key2 = strategy.generate_cache_key(
            "ffmpeg.extract_audio",
            {"video_path": "/share/video2.mp4"}
        )

        assert cache_key1 != cache_key2

    def test_cache_key_missing_field(self):
        """测试缺失字段时的缓存键生成"""
        strategy = ConcreteCacheKeyStrategy(["audio_path", "model_name"])

        # 只提供部分字段
        cache_key = strategy.generate_cache_key(
            "faster_whisper.transcribe",
            {"audio_path": "/share/audio.wav"}
        )

        # 应该只使用存在的字段
        assert cache_key.startswith("faster_whisper.transcribe:")

    def test_cache_key_extra_fields_ignored(self):
        """测试额外字段被忽略"""
        strategy = ConcreteCacheKeyStrategy(["audio_path"])

        cache_key1 = strategy.generate_cache_key(
            "faster_whisper.transcribe",
            {"audio_path": "/share/audio.wav"}
        )

        cache_key2 = strategy.generate_cache_key(
            "faster_whisper.transcribe",
            {
                "audio_path": "/share/audio.wav",
                "extra_field": "ignored"
            }
        )

        # 额外字段不应影响缓存键
        assert cache_key1 == cache_key2


class TestCanReuseCache:
    """can_reuse_cache 函数测试"""

    def test_valid_cache_reuse(self):
        """测试有效缓存可复用"""
        stage_output = {"audio_path": "/share/audio.wav"}
        stage_status = "SUCCESS"
        required_fields = ["audio_path"]

        assert can_reuse_cache(stage_output, stage_status, required_fields)

    def test_failed_status_no_reuse(self):
        """测试失败状态不可复用"""
        stage_output = {"audio_path": "/share/audio.wav"}
        stage_status = "FAILED"
        required_fields = ["audio_path"]

        assert not can_reuse_cache(stage_output, stage_status, required_fields)

    def test_pending_status_no_reuse(self):
        """测试等待状态不可复用"""
        stage_output = {"audio_path": "/share/audio.wav"}
        stage_status = "PENDING"
        required_fields = ["audio_path"]

        assert not can_reuse_cache(stage_output, stage_status, required_fields)

    def test_empty_output_no_reuse(self):
        """测试空输出不可复用"""
        stage_output = {}
        stage_status = "SUCCESS"
        required_fields = ["audio_path"]

        assert not can_reuse_cache(stage_output, stage_status, required_fields)

    def test_missing_required_field_no_reuse(self):
        """测试缺失必需字段不可复用"""
        stage_output = {"other_field": "value"}
        stage_status = "SUCCESS"
        required_fields = ["audio_path"]

        assert not can_reuse_cache(stage_output, stage_status, required_fields)

    def test_empty_required_field_no_reuse(self):
        """测试必需字段为空不可复用"""
        stage_output = {"audio_path": ""}
        stage_status = "SUCCESS"
        required_fields = ["audio_path"]

        assert not can_reuse_cache(stage_output, stage_status, required_fields)

    def test_none_required_field_no_reuse(self):
        """测试必需字段为 None 不可复用"""
        stage_output = {"audio_path": None}
        stage_status = "SUCCESS"
        required_fields = ["audio_path"]

        assert not can_reuse_cache(stage_output, stage_status, required_fields)

    def test_multiple_required_fields(self):
        """测试多个必需字段"""
        stage_output = {
            "audio_path": "/share/audio.wav",
            "subtitle_path": "/share/subtitle.srt"
        }
        stage_status = "SUCCESS"
        required_fields = ["audio_path", "subtitle_path"]

        assert can_reuse_cache(stage_output, stage_status, required_fields)

    def test_multiple_required_fields_one_missing(self):
        """测试多个必需字段其中一个缺失"""
        stage_output = {"audio_path": "/share/audio.wav"}
        stage_status = "SUCCESS"
        required_fields = ["audio_path", "subtitle_path"]

        assert not can_reuse_cache(stage_output, stage_status, required_fields)

    def test_extra_fields_allowed(self):
        """测试允许额外字段"""
        stage_output = {
            "audio_path": "/share/audio.wav",
            "extra_field": "extra_value"
        }
        stage_status = "SUCCESS"
        required_fields = ["audio_path"]

        assert can_reuse_cache(stage_output, stage_status, required_fields)

    def test_zero_value_is_valid(self):
        """测试数字 0 是有效值"""
        stage_output = {"count": 0}
        stage_status = "SUCCESS"
        required_fields = ["count"]

        assert can_reuse_cache(stage_output, stage_status, required_fields)

    def test_false_value_is_valid(self):
        """测试布尔值 False 是有效值"""
        stage_output = {"flag": False}
        stage_status = "SUCCESS"
        required_fields = ["flag"]

        assert can_reuse_cache(stage_output, stage_status, required_fields)

    def test_empty_list_is_valid(self):
        """测试空列表是有效值"""
        stage_output = {"files": []}
        stage_status = "SUCCESS"
        required_fields = ["files"]

        assert can_reuse_cache(stage_output, stage_status, required_fields)


class TestIsPendingState:
    """is_pending_state 函数测试"""

    def test_pending_status(self):
        """测试 PENDING 状态"""
        assert is_pending_state("PENDING")

    def test_running_status(self):
        """测试 RUNNING 状态"""
        assert is_pending_state("RUNNING")

    def test_success_not_pending(self):
        """测试 SUCCESS 不是等待态"""
        assert not is_pending_state("SUCCESS")

    def test_failed_not_pending(self):
        """测试 FAILED 不是等待态"""
        assert not is_pending_state("FAILED")

    def test_case_sensitive(self):
        """测试状态值大小写敏感"""
        assert not is_pending_state("pending")
        assert not is_pending_state("running")
