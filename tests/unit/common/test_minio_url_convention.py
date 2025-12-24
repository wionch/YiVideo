# tests/unit/common/test_minio_url_convention.py
# -*- coding: utf-8 -*-

"""MinIO URL 命名约定单元测试"""

import pytest
from services.common.minio_url_convention import (
    MinioUrlNamingConvention,
    apply_minio_url_convention,
    validate_minio_url_naming
)


class TestMinioUrlNamingConvention:
    """MinIO URL 命名约定测试"""

    def test_standard_field_naming(self):
        """测试标准字段命名"""
        convention = MinioUrlNamingConvention()

        assert convention.get_minio_url_field_name("audio_path") == "audio_path_minio_url"
        assert convention.get_minio_url_field_name("keyframe_dir") == "keyframe_dir_minio_url"
        assert convention.get_minio_url_field_name("segments_file") == "segments_file_minio_url"

    def test_array_field_naming(self):
        """测试数组字段命名"""
        convention = MinioUrlNamingConvention()

        assert convention.get_minio_url_field_name("all_audio_files") == "all_audio_files_minio_urls"

    def test_path_field_detection(self):
        """测试路径字段识别"""
        convention = MinioUrlNamingConvention()

        assert convention.is_path_field("audio_path") == True
        assert convention.is_path_field("keyframe_dir") == True
        assert convention.is_path_field("segments_file") == True
        assert convention.is_path_field("model_name") == False
        assert convention.is_path_field("duration") == False

    def test_apply_convention_disabled(self):
        """测试全局上传开关关闭时不生成 MinIO URL"""
        output = {"audio_path": "/share/audio.wav"}
        result = apply_minio_url_convention(output, auto_upload_enabled=False)

        assert "audio_path_minio_url" not in result
        assert result["audio_path"] == "/share/audio.wav"

    def test_apply_convention_enabled(self):
        """测试全局上传开关启用时生成 MinIO URL"""
        output = {"audio_path": "/share/audio.wav"}
        result = apply_minio_url_convention(output, auto_upload_enabled=True)

        assert "audio_path_minio_url" in result
        assert result["audio_path"] == "/share/audio.wav"  # 原始字段保留

    def test_original_field_preservation(self):
        """测试原始字段保留"""
        output = {"audio_path": "/share/audio.wav"}
        result = apply_minio_url_convention(output, auto_upload_enabled=True)

        assert output["audio_path"] == "/share/audio.wav"  # 原始值不变
        assert "audio_path_minio_url" in result

    def test_validate_correct_naming(self):
        """测试正确命名的验证"""
        output = {
            "audio_path": "/share/audio.wav",
            "audio_path_minio_url": "http://..."
        }
        errors = validate_minio_url_naming(output)

        assert len(errors) == 0

    def test_validate_incorrect_naming(self):
        """测试错误命名的验证"""
        output = {
            "keyframe_dir": "/share/keyframes",
            "keyframe_minio_url": "http://..."  # 错误：缺少 _dir
        }
        errors = validate_minio_url_naming(output)

        assert len(errors) > 0
        # 错误消息可能是 "corresponding local field" 或 "naming convention"
        assert any("corresponding local field" in err or "naming convention" in err for err in errors)

    def test_validate_missing_local_field(self):
        """测试缺少本地字段的验证"""
        output = {
            "audio_path_minio_url": "http://..."  # 缺少对应的 audio_path
        }
        errors = validate_minio_url_naming(output)

        assert len(errors) > 0
        assert "corresponding local field" in errors[0]
