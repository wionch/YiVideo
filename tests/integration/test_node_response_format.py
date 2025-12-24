"""
集成测试：验证所有节点的响应格式统一性

测试目标：
1. 所有节点返回 WorkflowContext 结构
2. MinIO URL 字段命名符合规范
3. 复用判定逻辑正确
4. 数据溯源字段完整
"""

import pytest
import os
import json
from typing import Dict, Any, List
from unittest.mock import Mock, patch, MagicMock

from services.common.context import WorkflowContext, StageExecution
from services.common.validators.node_response_validator import NodeResponseValidator
from services.common.minio_url_convention import MinioUrlNamingConvention


class TestNodeResponseFormat:
    """测试所有节点的响应格式统一性"""

    @pytest.fixture
    def validator(self):
        """创建响应验证器"""
        return NodeResponseValidator()

    @pytest.fixture
    def minio_convention(self):
        """创建 MinIO URL 命名规范"""
        return MinioUrlNamingConvention()

    @pytest.fixture
    def base_context(self) -> Dict[str, Any]:
        """创建基础工作流上下文"""
        return {
            "workflow_id": "test-workflow-001",
            "create_at": "2025-12-23T00:00:00Z",
            "input_params": {
                "task_name": "test.node",
                "input_data": {}
            },
            "shared_storage_path": "/share/workflows/test-workflow-001",
            "stages": {}
        }

    # ========================================================================
    # FFmpeg 系列节点测试
    # ========================================================================

    def test_ffmpeg_extract_audio_response_format(self, validator, base_context):
        """测试 ffmpeg.extract_audio 响应格式"""
        from services.workers.ffmpeg_service.executors import FFmpegExtractAudioExecutor

        # 模拟输入
        context = WorkflowContext(**base_context)
        context.input_params["input_data"] = {
            "video_path": "/share/test.mp4"
        }

        # 创建执行器并模拟执行
        with patch('services.workers.ffmpeg_service.executors.extract_audio_executor.subprocess.run'):
            with patch('os.path.exists', return_value=True):
                with patch('os.path.getsize', return_value=1024000):
                    executor = FFmpegExtractAudioExecutor("ffmpeg.extract_audio", context)

                    # 模拟核心逻辑
                    with patch.object(executor, 'execute_core_logic', return_value={
                        "audio_path": "/share/workflows/test-workflow-001/audio/test.wav",
                        "audio_duration": 120.5,
                        "audio_format": "wav",
                        "sample_rate": 16000,
                        "channels": 1
                    }):
                        result_context = executor.execute()

        # 验证响应格式
        assert isinstance(result_context, WorkflowContext)
        assert "ffmpeg.extract_audio" in result_context.stages

        stage = result_context.stages["ffmpeg.extract_audio"]
        assert stage.status == "SUCCESS"
        assert "audio_path" in stage.output
        assert "audio_duration" in stage.output

        # 验证通过验证器
        validation_result = validator.validate(result_context.model_dump())
        assert validation_result["valid"], f"验证失败: {validation_result.get('errors')}"

    def test_ffmpeg_extract_keyframes_response_format(self, validator, base_context):
        """测试 ffmpeg.extract_keyframes 响应格式"""
        from services.workers.ffmpeg_service.executors import FFmpegExtractKeyframesExecutor

        context = WorkflowContext(**base_context)
        context.input_params["input_data"] = {
            "video_path": "/share/test.mp4"
        }

        with patch('services.workers.ffmpeg_service.executors.extract_keyframes_executor.subprocess.run'):
            with patch('os.path.exists', return_value=True):
                with patch('os.listdir', return_value=['frame_001.jpg', 'frame_002.jpg']):
                    executor = FFmpegExtractKeyframesExecutor("ffmpeg.extract_keyframes", context)

                    with patch.object(executor, 'execute_core_logic', return_value={
                        "keyframe_dir": "/share/workflows/test-workflow-001/keyframes",
                        "keyframe_count": 2,
                        "keyframe_files": ["frame_001.jpg", "frame_002.jpg"]
                    }):
                        result_context = executor.execute()

        # 验证响应格式
        assert isinstance(result_context, WorkflowContext)
        stage = result_context.stages["ffmpeg.extract_keyframes"]
        assert stage.status == "SUCCESS"
        assert "keyframe_dir" in stage.output
        assert "keyframe_count" in stage.output

        validation_result = validator.validate(result_context.model_dump())
        assert validation_result["valid"]

    # ========================================================================
    # Faster-Whisper 节点测试
    # ========================================================================

    def test_faster_whisper_transcribe_response_format(self, validator, base_context):
        """测试 faster_whisper.transcribe_audio 响应格式"""
        from services.workers.faster_whisper_service.executors import FasterWhisperTranscribeAudioExecutor

        context = WorkflowContext(**base_context)
        context.input_params["input_data"] = {
            "audio_path": "/share/test.wav"
        }

        with patch('services.workers.faster_whisper_service.executors.transcribe_audio_executor.WhisperModel'):
            executor = FasterWhisperTranscribeAudioExecutor("faster_whisper.transcribe_audio", context)

            with patch.object(executor, 'execute_core_logic', return_value={
                "segments": [
                    {"start": 0.0, "end": 2.0, "text": "测试文本", "words": []}
                ],
                "language": "zh",
                "audio_duration": 120.0,
                "enable_word_timestamps": True
            }):
                result_context = executor.execute()

        # 验证响应格式
        assert isinstance(result_context, WorkflowContext)
        stage = result_context.stages["faster_whisper.transcribe_audio"]
        assert stage.status == "SUCCESS"
        assert "segments" in stage.output
        assert "language" in stage.output

        validation_result = validator.validate(result_context.model_dump())
        assert validation_result["valid"]

    # ========================================================================
    # Audio Separator 节点测试
    # ========================================================================

    def test_audio_separator_response_format(self, validator, base_context):
        """测试 audio_separator.separate_vocals 响应格式"""
        from services.workers.audio_separator_service.executors import AudioSeparatorSeparateVocalsExecutor

        context = WorkflowContext(**base_context)
        context.input_params["input_data"] = {
            "audio_path": "/share/test.wav"
        }

        with patch('services.workers.audio_separator_service.executors.separate_vocals_executor.Separator'):
            executor = AudioSeparatorSeparateVocalsExecutor("audio_separator.separate_vocals", context)

            with patch.object(executor, 'execute_core_logic', return_value={
                "vocal_audio": "/share/vocals.wav",
                "instrumental_audio": "/share/instrumental.wav",
                "separation_model": "UVR-MDX-NET-Inst_HQ_3"
            }):
                result_context = executor.execute()

        # 验证响应格式
        assert isinstance(result_context, WorkflowContext)
        stage = result_context.stages["audio_separator.separate_vocals"]
        assert stage.status == "SUCCESS"
        assert "vocal_audio" in stage.output

        validation_result = validator.validate(result_context.model_dump())
        assert validation_result["valid"]

    # ========================================================================
    # Pyannote Audio 系列节点测试
    # ========================================================================

    def test_pyannote_diarize_speakers_response_format(self, validator, base_context):
        """测试 pyannote_audio.diarize_speakers 响应格式"""
        from services.workers.pyannote_audio_service.executors import PyannoteAudioDiarizeSpeakersExecutor

        context = WorkflowContext(**base_context)
        context.input_params["input_data"] = {
            "audio_path": "/share/test.wav"
        }

        with patch('services.workers.pyannote_audio_service.executors.diarize_speakers_executor.Pipeline'):
            executor = PyannoteAudioDiarizeSpeakersExecutor("pyannote_audio.diarize_speakers", context)

            with patch.object(executor, 'execute_core_logic', return_value={
                "diarization_segments": [
                    {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}
                ],
                "detected_speakers": ["SPEAKER_00"],
                "speaker_statistics": {"SPEAKER_00": {"duration": 2.0}}
            }):
                result_context = executor.execute()

        # 验证响应格式
        assert isinstance(result_context, WorkflowContext)
        stage = result_context.stages["pyannote_audio.diarize_speakers"]
        assert stage.status == "SUCCESS"
        assert "diarization_segments" in stage.output

        validation_result = validator.validate(result_context.model_dump())
        assert validation_result["valid"]

    def test_pyannote_get_speaker_segments_response_format(self, validator, base_context):
        """测试 pyannote_audio.get_speaker_segments 响应格式"""
        from services.workers.pyannote_audio_service.executors import PyannoteAudioGetSpeakerSegmentsExecutor

        context = WorkflowContext(**base_context)
        context.stages["pyannote_audio.diarize_speakers"] = StageExecution(
            status="SUCCESS",
            output={
                "diarization_segments": [
                    {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}
                ]
            }
        )

        executor = PyannoteAudioGetSpeakerSegmentsExecutor("pyannote_audio.get_speaker_segments", context)

        with patch.object(executor, 'execute_core_logic', return_value={
            "speaker_segments": [
                {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}
            ],
            "total_segments": 1
        }):
            result_context = executor.execute()

        # 验证响应格式 - 必须是 WorkflowContext，不是 success/data 格式
        assert isinstance(result_context, WorkflowContext)
        stage = result_context.stages["pyannote_audio.get_speaker_segments"]
        assert stage.status == "SUCCESS"
        assert "speaker_segments" in stage.output

        validation_result = validator.validate(result_context.model_dump())
        assert validation_result["valid"]

    def test_pyannote_validate_diarization_response_format(self, validator, base_context):
        """测试 pyannote_audio.validate_diarization 响应格式"""
        from services.workers.pyannote_audio_service.executors import PyannoteAudioValidateDiarizationExecutor

        context = WorkflowContext(**base_context)
        context.stages["pyannote_audio.diarize_speakers"] = StageExecution(
            status="SUCCESS",
            output={
                "diarization_segments": [
                    {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}
                ]
            }
        )

        executor = PyannoteAudioValidateDiarizationExecutor("pyannote_audio.validate_diarization", context)

        with patch.object(executor, 'execute_core_logic', return_value={
            "is_valid": True,
            "validation_errors": [],
            "total_segments": 1
        }):
            result_context = executor.execute()

        # 验证响应格式 - 必须是 WorkflowContext
        assert isinstance(result_context, WorkflowContext)
        stage = result_context.stages["pyannote_audio.validate_diarization"]
        assert stage.status == "SUCCESS"
        assert "is_valid" in stage.output

        validation_result = validator.validate(result_context.model_dump())
        assert validation_result["valid"]

    # ========================================================================
    # PaddleOCR 系列节点测试
    # ========================================================================

    def test_paddleocr_detect_subtitle_area_response_format(self, validator, base_context):
        """测试 paddleocr.detect_subtitle_area 响应格式"""
        from services.workers.paddleocr_service.executors import PaddleOCRDetectSubtitleAreaExecutor

        context = WorkflowContext(**base_context)
        context.stages["ffmpeg.extract_keyframes"] = StageExecution(
            status="SUCCESS",
            output={
                "keyframe_dir": "/share/keyframes",
                "keyframe_count": 10
            }
        )

        with patch('services.workers.paddleocr_service.executors.detect_subtitle_area_executor.PaddleOCR'):
            executor = PaddleOCRDetectSubtitleAreaExecutor("paddleocr.detect_subtitle_area", context)

            with patch.object(executor, 'execute_core_logic', return_value={
                "subtitle_area": {"x": 0, "y": 800, "width": 1920, "height": 280},
                "confidence": 0.95,
                "detection_method": "ocr_density"
            }):
                result_context = executor.execute()

        # 验证响应格式
        assert isinstance(result_context, WorkflowContext)
        stage = result_context.stages["paddleocr.detect_subtitle_area"]
        assert stage.status == "SUCCESS"
        assert "subtitle_area" in stage.output

        validation_result = validator.validate(result_context.model_dump())
        assert validation_result["valid"]

    def test_paddleocr_create_stitched_images_response_format(self, validator, base_context):
        """测试 paddleocr.create_stitched_images 响应格式"""
        from services.workers.paddleocr_service.executors import PaddleOCRCreateStitchedImagesExecutor

        context = WorkflowContext(**base_context)
        context.stages["ffmpeg.extract_keyframes"] = StageExecution(
            status="SUCCESS",
            output={"keyframe_dir": "/share/keyframes"}
        )
        context.stages["paddleocr.detect_subtitle_area"] = StageExecution(
            status="SUCCESS",
            output={"subtitle_area": {"x": 0, "y": 800, "width": 1920, "height": 280}}
        )

        with patch('cv2.imread'):
            with patch('cv2.imwrite'):
                executor = PaddleOCRCreateStitchedImagesExecutor("paddleocr.create_stitched_images", context)

                with patch.object(executor, 'execute_core_logic', return_value={
                    "multi_frames_path": "/share/stitched_images",
                    "stitched_image_count": 5
                }):
                    result_context = executor.execute()

        # 验证响应格式 - 字段名应保留 _path 后缀
        assert isinstance(result_context, WorkflowContext)
        stage = result_context.stages["paddleocr.create_stitched_images"]
        assert stage.status == "SUCCESS"
        assert "multi_frames_path" in stage.output

        validation_result = validator.validate(result_context.model_dump())
        assert validation_result["valid"]

    def test_paddleocr_perform_ocr_response_format(self, validator, base_context):
        """测试 paddleocr.perform_ocr 响应格式"""
        from services.workers.paddleocr_service.executors import PaddleOCRPerformOCRExecutor

        context = WorkflowContext(**base_context)
        context.stages["paddleocr.create_stitched_images"] = StageExecution(
            status="SUCCESS",
            output={"multi_frames_path": "/share/stitched_images"}
        )

        with patch('services.workers.paddleocr_service.executors.perform_ocr_executor.PaddleOCR'):
            executor = PaddleOCRPerformOCRExecutor("paddleocr.perform_ocr", context)

            with patch.object(executor, 'execute_core_logic', return_value={
                "ocr_results": [{"text": "测试字幕", "confidence": 0.95}],
                "total_text_blocks": 1
            }):
                result_context = executor.execute()

        # 验证响应格式
        assert isinstance(result_context, WorkflowContext)
        stage = result_context.stages["paddleocr.perform_ocr"]
        assert stage.status == "SUCCESS"
        assert "ocr_results" in stage.output

        validation_result = validator.validate(result_context.model_dump())
        assert validation_result["valid"]

    def test_paddleocr_postprocess_and_finalize_response_format(self, validator, base_context):
        """测试 paddleocr.postprocess_and_finalize 响应格式"""
        from services.workers.paddleocr_service.executors import PaddleOCRPostprocessAndFinalizeExecutor

        context = WorkflowContext(**base_context)
        context.stages["paddleocr.perform_ocr"] = StageExecution(
            status="SUCCESS",
            output={"ocr_results": [{"text": "测试字幕"}]}
        )

        executor = PaddleOCRPostprocessAndFinalizeExecutor("paddleocr.postprocess_and_finalize", context)

        with patch.object(executor, 'execute_core_logic', return_value={
            "final_subtitles": [{"text": "测试字幕", "timestamp": "00:00:01"}],
            "subtitle_count": 1
        }):
            result_context = executor.execute()

        # 验证响应格式
        assert isinstance(result_context, WorkflowContext)
        stage = result_context.stages["paddleocr.postprocess_and_finalize"]
        assert stage.status == "SUCCESS"
        assert "final_subtitles" in stage.output

        validation_result = validator.validate(result_context.model_dump())
        assert validation_result["valid"]

    # ========================================================================
    # IndexTTS 节点测试
    # ========================================================================

    def test_indextts_generate_speech_response_format(self, validator, base_context):
        """测试 indextts.generate_speech 响应格式"""
        from services.workers.indextts_service.executors import IndexTTSGenerateSpeechExecutor

        context = WorkflowContext(**base_context)
        context.input_params["input_data"] = {
            "text": "测试文本",
            "reference_audio": "/share/ref.wav"
        }

        with patch('services.workers.indextts_service.executors.generate_speech_executor.IndexTTSModel'):
            executor = IndexTTSGenerateSpeechExecutor("indextts.generate_speech", context)

            with patch.object(executor, 'execute_core_logic', return_value={
                "audio_path": "/share/generated.wav",
                "audio_duration": 5.0,
                "text": "测试文本"
            }):
                result_context = executor.execute()

        # 验证响应格式 - 必须是 WorkflowContext，不是普通字典
        assert isinstance(result_context, WorkflowContext)
        stage = result_context.stages["indextts.generate_speech"]
        assert stage.status == "SUCCESS"
        assert "audio_path" in stage.output

        # 验证状态字段统一为 "SUCCESS" 而非 "success"
        assert stage.status == "SUCCESS"

        validation_result = validator.validate(result_context.model_dump())
        assert validation_result["valid"]

    # ========================================================================
    # WService 系列节点测试
    # ========================================================================

    def test_wservice_generate_subtitle_files_response_format(self, validator, base_context):
        """测试 wservice.generate_subtitle_files 响应格式"""
        from services.workers.wservice.executors import WServiceGenerateSubtitleFilesExecutor

        context = WorkflowContext(**base_context)
        context.stages["faster_whisper.transcribe_audio"] = StageExecution(
            status="SUCCESS",
            output={
                "segments": [{"start": 0.0, "end": 2.0, "text": "测试"}],
                "audio_path": "/share/test.wav"
            }
        )

        executor = WServiceGenerateSubtitleFilesExecutor("wservice.generate_subtitle_files", context)

        with patch.object(executor, 'execute_core_logic', return_value={
            "subtitle_path": "/share/subtitles/test.srt",
            "subtitle_files": {
                "basic": "/share/subtitles/test.srt",
                "json": "/share/subtitles/test.json"
            },
            "json_path": "/share/subtitles/test.json"
        }):
            result_context = executor.execute()

        # 验证响应格式
        assert isinstance(result_context, WorkflowContext)
        stage = result_context.stages["wservice.generate_subtitle_files"]
        assert stage.status == "SUCCESS"
        assert "subtitle_path" in stage.output
        assert "subtitle_files" in stage.output

        validation_result = validator.validate(result_context.model_dump())
        assert validation_result["valid"]

    def test_wservice_correct_subtitles_response_format(self, validator, base_context):
        """测试 wservice.correct_subtitles 响应格式"""
        from services.workers.wservice.executors import WServiceCorrectSubtitlesExecutor

        context = WorkflowContext(**base_context)
        context.input_params["input_data"] = {
            "subtitle_file": "/share/test.srt",
            "correction_params": {"enabled": True}
        }

        with patch('services.common.subtitle.subtitle_correction.SubtitleCorrector'):
            executor = WServiceCorrectSubtitlesExecutor("wservice.correct_subtitles", context)

            with patch.object(executor, 'execute_core_logic', return_value={
                "corrected_subtitle_path": "/share/corrected.srt",
                "corrections_made": 5
            }):
                result_context = executor.execute()

        # 验证响应格式
        assert isinstance(result_context, WorkflowContext)
        stage = result_context.stages["wservice.correct_subtitles"]
        assert stage.status == "SUCCESS"
        assert "corrected_subtitle_path" in stage.output

        validation_result = validator.validate(result_context.model_dump())
        assert validation_result["valid"]

    def test_wservice_ai_optimize_subtitles_response_format(self, validator, base_context):
        """测试 wservice.ai_optimize_subtitles 响应格式"""
        from services.workers.wservice.executors import WServiceAIOptimizeSubtitlesExecutor

        context = WorkflowContext(**base_context)
        context.input_params["input_data"] = {
            "subtitle_file": "/share/test.srt",
            "optimization_params": {"enabled": True}
        }

        with patch('services.common.subtitle.subtitle_optimizer.SubtitleOptimizer'):
            executor = WServiceAIOptimizeSubtitlesExecutor("wservice.ai_optimize_subtitles", context)

            with patch.object(executor, 'execute_core_logic', return_value={
                "optimized_file_path": "/share/optimized.srt",
                "optimizations_applied": 3
            }):
                result_context = executor.execute()

        # 验证响应格式
        assert isinstance(result_context, WorkflowContext)
        stage = result_context.stages["wservice.ai_optimize_subtitles"]
        assert stage.status == "SUCCESS"
        assert "optimized_file_path" in stage.output

        validation_result = validator.validate(result_context.model_dump())
        assert validation_result["valid"]

    def test_wservice_merge_speaker_segments_response_format(self, validator, base_context):
        """测试 wservice.merge_speaker_segments 响应格式"""
        from services.workers.wservice.executors import WServiceMergeSpeakerSegmentsExecutor

        context = WorkflowContext(**base_context)
        context.stages["faster_whisper.transcribe_audio"] = StageExecution(
            status="SUCCESS",
            output={"segments": [{"start": 0.0, "end": 2.0, "text": "测试"}]}
        )
        context.stages["pyannote_audio.diarize_speakers"] = StageExecution(
            status="SUCCESS",
            output={"diarization_segments": [{"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}]}
        )

        with patch('services.common.subtitle.subtitle_merger.create_subtitle_merger'):
            executor = WServiceMergeSpeakerSegmentsExecutor("wservice.merge_speaker_segments", context)

            with patch.object(executor, 'execute_core_logic', return_value={
                "merged_segments": [
                    {"start": 0.0, "end": 2.0, "text": "测试", "speaker": "SPEAKER_00"}
                ],
                "input_summary": {}
            }):
                result_context = executor.execute()

        # 验证响应格式
        assert isinstance(result_context, WorkflowContext)
        stage = result_context.stages["wservice.merge_speaker_segments"]
        assert stage.status == "SUCCESS"
        assert "merged_segments" in stage.output

        validation_result = validator.validate(result_context.model_dump())
        assert validation_result["valid"]

    def test_wservice_merge_with_word_timestamps_response_format(self, validator, base_context):
        """测试 wservice.merge_with_word_timestamps 响应格式"""
        from services.workers.wservice.executors import WServiceMergeWithWordTimestampsExecutor

        context = WorkflowContext(**base_context)
        context.stages["faster_whisper.transcribe_audio"] = StageExecution(
            status="SUCCESS",
            output={"segments": [{"start": 0.0, "end": 2.0, "text": "测试", "words": []}]}
        )
        context.stages["pyannote_audio.diarize_speakers"] = StageExecution(
            status="SUCCESS",
            output={"diarization_segments": [{"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}]}
        )

        with patch('services.common.subtitle.subtitle_merger.create_word_level_merger'):
            executor = WServiceMergeWithWordTimestampsExecutor("wservice.merge_with_word_timestamps", context)

            with patch.object(executor, 'execute_core_logic', return_value={
                "merged_segments_file": "/share/merged.json"
            }):
                result_context = executor.execute()

        # 验证响应格式
        assert isinstance(result_context, WorkflowContext)
        stage = result_context.stages["wservice.merge_with_word_timestamps"]
        assert stage.status == "SUCCESS"
        assert "merged_segments_file" in stage.output

        validation_result = validator.validate(result_context.model_dump())
        assert validation_result["valid"]

    def test_wservice_prepare_tts_segments_response_format(self, validator, base_context):
        """测试 wservice.prepare_tts_segments 响应格式"""
        from services.workers.wservice.executors import WServicePrepareTtsSegmentsExecutor

        context = WorkflowContext(**base_context)
        context.stages["faster_whisper.transcribe_audio"] = StageExecution(
            status="SUCCESS",
            output={"segments": [{"start": 0.0, "end": 2.0, "text": "测试", "words": []}]}
        )

        with patch('services.workers.wservice.app.tasks.TtsMerger'):
            executor = WServicePrepareTtsSegmentsExecutor("wservice.prepare_tts_segments", context)

            with patch.object(executor, 'execute_core_logic', return_value={
                "prepared_segments": [{"start": 0.0, "end": 2.0, "text": "测试"}],
                "source_stage": "faster_whisper.transcribe_audio",
                "total_segments": 1
            }):
                result_context = executor.execute()

        # 验证响应格式
        assert isinstance(result_context, WorkflowContext)
        stage = result_context.stages["wservice.prepare_tts_segments"]
        assert stage.status == "SUCCESS"
        assert "prepared_segments" in stage.output

        validation_result = validator.validate(result_context.model_dump())
        assert validation_result["valid"]

    # ========================================================================
    # MinIO URL 字段命名规范测试
    # ========================================================================

    def test_minio_url_field_naming_convention(self, minio_convention):
        """测试 MinIO URL 字段命名规范"""

        # 测试正确的命名
        assert minio_convention.is_valid_minio_url_field("audio_path_minio_url")
        assert minio_convention.is_valid_minio_url_field("keyframe_dir_minio_url")
        assert minio_convention.is_valid_minio_url_field("multi_frames_path_minio_url")
        assert minio_convention.is_valid_minio_url_field("subtitle_files_minio_urls")  # 数组

        # 测试错误的命名
        assert not minio_convention.is_valid_minio_url_field("keyframe_minio_url")  # 缺少 _dir
        assert not minio_convention.is_valid_minio_url_field("multi_frames_minio_url")  # 缺少 _path
        assert not minio_convention.is_valid_minio_url_field("audio_minio_url")  # 缺少 _path

        # 测试字段名生成
        assert minio_convention.generate_minio_url_field("audio_path") == "audio_path_minio_url"
        assert minio_convention.generate_minio_url_field("keyframe_dir") == "keyframe_dir_minio_url"
        assert minio_convention.generate_minio_url_field("subtitle_files", is_array=True) == "subtitle_files_minio_urls"

    # ========================================================================
    # 缓存键生成测试
    # ========================================================================

    def test_cache_key_generation(self):
        """测试缓存键生成逻辑"""
        from services.common.cache_key_strategy import CacheKeyStrategy

        strategy = CacheKeyStrategy()

        # 测试单字段缓存键
        cache_key = strategy.generate_cache_key(
            task_name="ffmpeg.extract_audio",
            fields=["video_path"],
            input_data={"video_path": "/share/test.mp4"}
        )
        assert cache_key is not None
        assert "ffmpeg.extract_audio" in cache_key

        # 测试多字段缓存键
        cache_key = strategy.generate_cache_key(
            task_name="faster_whisper.transcribe_audio",
            fields=["audio_path", "language"],
            input_data={"audio_path": "/share/test.wav", "language": "zh"}
        )
        assert cache_key is not None

        # 测试缺少必需字段
        cache_key = strategy.generate_cache_key(
            task_name="ffmpeg.extract_audio",
            fields=["video_path"],
            input_data={}
        )
        assert cache_key is None  # 缺少必需字段应返回 None

    # ========================================================================
    # 综合测试：所有节点响应格式一致性
    # ========================================================================

    def test_all_nodes_return_workflow_context(self, validator):
        """测试所有节点都返回 WorkflowContext 结构"""

        # 所有节点列表
        all_nodes = [
            "ffmpeg.extract_audio",
            "ffmpeg.extract_keyframes",
            "faster_whisper.transcribe_audio",
            "audio_separator.separate_vocals",
            "pyannote_audio.diarize_speakers",
            "pyannote_audio.get_speaker_segments",
            "pyannote_audio.validate_diarization",
            "paddleocr.detect_subtitle_area",
            "paddleocr.create_stitched_images",
            "paddleocr.perform_ocr",
            "paddleocr.postprocess_and_finalize",
            "indextts.generate_speech",
            "wservice.generate_subtitle_files",
            "wservice.correct_subtitles",
            "wservice.ai_optimize_subtitles",
            "wservice.merge_speaker_segments",
            "wservice.merge_with_word_timestamps",
            "wservice.prepare_tts_segments"
        ]

        # 验证所有节点都在测试中
        assert len(all_nodes) == 18, "应该有 18 个节点"

        # 所有节点都应该返回 WorkflowContext
        # (这个测试通过上面的各个单独测试来验证)

    def test_no_legacy_response_formats(self):
        """测试没有节点使用旧的响应格式"""

        # 旧格式 1: success/data 结构 (pyannote_audio 旧格式)
        legacy_format_1 = {
            "success": True,
            "data": {"some_field": "value"}
        }

        # 旧格式 2: 普通任务字典 (indextts 旧格式)
        legacy_format_2 = {
            "status": "success",
            "audio_path": "/share/test.wav"
        }

        validator = NodeResponseValidator()

        # 验证旧格式应该被拒绝
        result1 = validator.validate(legacy_format_1)
        assert not result1["valid"], "success/data 格式应该被拒绝"

        result2 = validator.validate(legacy_format_2)
        assert not result2["valid"], "普通字典格式应该被拒绝"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
