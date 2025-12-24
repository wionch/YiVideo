"""
WService 字幕文件生成执行器。
"""

import os
import json
from typing import Dict, Any, List

from services.common.base_node_executor import BaseNodeExecutor
from services.common.logger import get_logger
from services.common.parameter_resolver import get_param_with_fallback
from services.common.config_loader import CONFIG
from services.common.file_service import get_file_service
from services.common.subtitle.subtitle_merger import create_word_level_merger
from services.common.path_builder import build_node_output_path, ensure_directory

logger = get_logger(__name__)


class WServiceGenerateSubtitleFilesExecutor(BaseNodeExecutor):
    """
    WService 字幕文件生成执行器。

    生成多种格式的字幕文件（SRT、JSON、带说话人标记等）。

    输入参数:
        - segments_file (str, 可选): 转录数据文件路径（JSON格式，包含segments数组）
        - audio_duration (float, 可选): 音频时长
        - language (str, 可选): 语言代码（默认'unknown'）
        - output_filename (str, 可选): 输出文件名前缀（默认'subtitle'）

    输出字段:
        - subtitle_path (str): 基础字幕文件路径
        - subtitle_files (dict): 所有字幕文件的统一访问
            - basic (str): 基础 SRT 文件
            - with_speakers (str, 可选): 带说话人标记的 SRT 文件
            - word_timestamps (str, 可选): 词级时间戳 JSON 文件
            - json (str): 完整 JSON 格式字幕文件
        - json_path (str): JSON 格式字幕文件路径
    """

    def __init__(self, stage_name: str, context):
        super().__init__(stage_name, context)
        self.file_service = get_file_service()

    def validate_input(self) -> None:
        """
        验证输入参数。

        至少需要提供以下之一：
        - segments_file 参数
        - faster_whisper.transcribe_audio 节点已完成
        """
        input_data = self.get_input_data()
        workflow_id = self.context.workflow_id

        # 检查是否有 segments_file
        segments_file = get_param_with_fallback(
            "segments_file",
            input_data,
            self.context
        )

        if not segments_file:
            # 检查上游节点
            transcribe_stage = self.context.stages.get('faster_whisper.transcribe_audio')
            if not transcribe_stage or transcribe_stage.status not in ['SUCCESS', 'COMPLETED']:
                raise ValueError(
                    "缺少必需参数: 请提供 segments_file 参数，"
                    "或确保 faster_whisper.transcribe_audio 已成功完成"
                )

        logger.info(f"[{workflow_id}] 输入参数验证通过")

    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行字幕文件生成核心逻辑。

        Returns:
            包含生成的字幕文件路径的字典
        """
        workflow_id = self.context.workflow_id
        input_data = self.get_input_data()

        logger.info(f"[{workflow_id}] 开始生成字幕文件")

        # 获取数据和参数
        segments, audio_path, audio_duration, language, enable_word_timestamps, data_source = (
            self._get_subtitle_data(input_data)
        )

        if not segments or not audio_path:
            raise ValueError("缺少必要的数据（segments 或 audio_path）")

        logger.info(
            f"[{workflow_id}] 数据来源: {data_source}, segments数量: {len(segments)}"
        )

        # 获取说话人信息（仅工作流模式）
        speaker_enhanced_segments, has_speaker_info = self._get_speaker_info(
            segments,
            enable_word_timestamps
        )

        # 生成字幕文件
        subtitles_dir = build_node_output_path(
            task_id=workflow_id,
            node_name=self.stage_name,
            file_type="subtitle",
            filename=""  # 目录路径
        )
        ensure_directory(subtitles_dir)

        base_filename = os.path.splitext(os.path.basename(audio_path))[0]

        # 生成基础 SRT 文件
        subtitle_path = self._generate_basic_srt(
            segments,
            subtitles_dir,
            base_filename
        )

        # 构建输出数据
        output_data = {
            "subtitle_path": subtitle_path,
            "subtitle_files": {
                "basic": subtitle_path
            }
        }

        # 生成带说话人的 SRT 文件（如果有说话人信息）
        if has_speaker_info and speaker_enhanced_segments:
            speaker_srt_path = self._generate_speaker_srt(
                speaker_enhanced_segments,
                subtitles_dir,
                base_filename
            )
            output_data["subtitle_files"]["with_speakers"] = speaker_srt_path

        # 生成词级时间戳 JSON 文件（如果有词级时间戳）
        if enable_word_timestamps and segments:
            word_timestamps_path = self._generate_word_timestamps_json(
                segments,
                subtitles_dir,
                base_filename
            )
            output_data["subtitle_files"]["word_timestamps"] = word_timestamps_path

        # 生成完整的 JSON 格式字幕文件
        json_subtitle_path = self._generate_json_subtitle(
            segments,
            subtitles_dir,
            base_filename,
            language,
            audio_duration,
            enable_word_timestamps,
            data_source
        )
        output_data["json_path"] = json_subtitle_path
        output_data["subtitle_files"]["json"] = json_subtitle_path

        logger.info(f"[{workflow_id}] 字幕文件生成完成")

        return output_data

    def _get_subtitle_data(self, input_data: Dict[str, Any]) -> tuple:
        """
        获取字幕生成所需的数据。

        Returns:
            (segments, audio_path, audio_duration, language, enable_word_timestamps, data_source) 元组
        """
        workflow_id = self.context.workflow_id

        # 1. 优先从 input_data / node_params 获取 segments_file（单任务模式）
        segments_file = get_param_with_fallback(
            'segments_file',
            input_data,
            self.context,
            fallback_from_input_data=True
        )

        if segments_file:
            # 单任务模式：从文件加载 segments
            logger.info(f"[{workflow_id}] 单任务模式：从 segments_file 加载数据: {segments_file}")

            # 下载文件（支持 MinIO URL）
            segments_file = self.file_service.resolve_and_download(
                segments_file,
                self.context.shared_storage_path
            )
            segments = self._load_segments_from_file(segments_file)

            if not segments:
                raise ValueError(f"无法从文件加载 segments 数据: {segments_file}")

            # 从参数获取其他可选信息
            audio_duration = get_param_with_fallback(
                'audio_duration',
                input_data,
                self.context
            ) or 0
            language = get_param_with_fallback(
                'language',
                input_data,
                self.context
            ) or 'unknown'
            enable_word_timestamps = any('words' in seg and seg['words'] for seg in segments)

            # 生成输出文件名
            output_filename = get_param_with_fallback(
                'output_filename',
                input_data,
                self.context
            )
            if not output_filename:
                output_filename = os.path.splitext(os.path.basename(segments_file))[0]
                # 清理常见后缀
                for suffix in ['_segments', '_transcribe_data', '_transcription']:
                    if output_filename.endswith(suffix):
                        output_filename = output_filename[:-len(suffix)]
                        break

            audio_path = output_filename
            data_source = 'input_data.segments_file'

            return (
                segments,
                audio_path,
                audio_duration,
                language,
                enable_word_timestamps,
                data_source
            )

        # 2. 回退到工作流模式：从 faster_whisper.transcribe_audio 阶段获取
        transcribe_stage = self.context.stages.get('faster_whisper.transcribe_audio')
        if not transcribe_stage or transcribe_stage.status not in ['SUCCESS', 'COMPLETED']:
            raise ValueError(
                "无法获取转录结果：请提供 segments_file 参数，"
                "或确保 faster_whisper.transcribe_audio 任务已成功完成"
            )

        transcribe_output = transcribe_stage.output
        if not transcribe_output or not isinstance(transcribe_output, dict):
            raise ValueError("转录结果数据格式错误")

        segments = self._get_segments_data(transcribe_output, 'segments')
        audio_path = transcribe_output.get('audio_path')
        audio_duration = transcribe_output.get('audio_duration', 0)
        language = transcribe_output.get('language', 'unknown')
        enable_word_timestamps = transcribe_output.get('enable_word_timestamps', True)
        data_source = 'faster_whisper.transcribe_audio'

        if not segments or not audio_path:
            raise ValueError("转录结果中缺少必要的数据（segments 或 audio_path）")

        return (
            segments,
            audio_path,
            audio_duration,
            language,
            enable_word_timestamps,
            data_source
        )

    def _get_speaker_info(
        self,
        segments: List[Dict],
        enable_word_timestamps: bool
    ) -> tuple:
        """
        获取说话人信息（仅工作流模式）。

        Returns:
            (speaker_enhanced_segments, has_speaker_info) 元组
        """
        diarize_stage = self.context.stages.get('pyannote_audio.diarize_speakers')
        has_speaker_info = False
        speaker_enhanced_segments = None

        if diarize_stage and diarize_stage.status in ['SUCCESS', 'COMPLETED']:
            diarize_output = diarize_stage.output
            if diarize_output and isinstance(diarize_output, dict):
                speaker_data = self._get_speaker_data(diarize_output)
                speaker_segments = speaker_data.get('speaker_enhanced_segments')

                if speaker_segments and segments and enable_word_timestamps:
                    try:
                        service_config = CONFIG.get('faster_whisper_service', {})
                        merge_config = service_config.get('subtitle_merge', {})
                        merger = create_word_level_merger(speaker_segments, merge_config)
                        speaker_enhanced_segments = merger.merge(segments)
                        has_speaker_info = True
                    except Exception as e:
                        logger.warning(f"说话人信息合并失败: {e}")
                        has_speaker_info = False
                        speaker_enhanced_segments = None
                else:
                    has_speaker_info = bool(speaker_segments)

        return speaker_enhanced_segments, has_speaker_info

    def _generate_basic_srt(
        self,
        segments: List[Dict],
        subtitles_dir: str,
        base_filename: str
    ) -> str:
        """
        生成基础 SRT 字幕文件。

        Returns:
            SRT 文件路径
        """
        subtitle_filename = f"{base_filename}.srt"
        subtitle_path = os.path.join(subtitles_dir, subtitle_filename)

        with open(subtitle_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(segments):
                start_str = self._format_srt_time(segment['start'])
                end_str = self._format_srt_time(segment['end'])
                f.write(f"{i+1}\n{start_str} --> {end_str}\n{segment['text'].strip()}\n\n")

        logger.info(f"基础 SRT 文件已生成: {subtitle_path}")
        return subtitle_path

    def _generate_speaker_srt(
        self,
        speaker_enhanced_segments: List[Dict],
        subtitles_dir: str,
        base_filename: str
    ) -> str:
        """
        生成带说话人标记的 SRT 字幕文件。

        Returns:
            SRT 文件路径
        """
        speaker_srt_filename = f"{base_filename}_with_speakers.srt"
        speaker_srt_path = os.path.join(subtitles_dir, speaker_srt_filename)

        with open(speaker_srt_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(speaker_enhanced_segments):
                start_str = self._format_srt_time(segment['start'])
                end_str = self._format_srt_time(segment['end'])
                speaker = segment.get("speaker", "UNKNOWN")
                f.write(
                    f"{i+1}\n{start_str} --> {end_str}\n"
                    f"[{speaker}] {segment['text'].strip()}\n\n"
                )

        logger.info(f"带说话人 SRT 文件已生成: {speaker_srt_path}")
        return speaker_srt_path

    def _generate_word_timestamps_json(
        self,
        segments: List[Dict],
        subtitles_dir: str,
        base_filename: str
    ) -> str:
        """
        生成词级时间戳 JSON 文件。

        Returns:
            JSON 文件路径
        """
        word_timestamps_filename = f"{base_filename}_word_timestamps.json"
        word_timestamps_json_path = os.path.join(subtitles_dir, word_timestamps_filename)

        json_content = self._segments_to_word_timestamp_json(segments)
        with open(word_timestamps_json_path, "w", encoding="utf-8") as f:
            f.write(json_content)

        logger.info(f"词级时间戳 JSON 文件已生成: {word_timestamps_json_path}")
        return word_timestamps_json_path

    def _generate_json_subtitle(
        self,
        segments: List[Dict],
        subtitles_dir: str,
        base_filename: str,
        language: str,
        audio_duration: float,
        enable_word_timestamps: bool,
        data_source: str
    ) -> str:
        """
        生成完整的 JSON 格式字幕文件。

        Returns:
            JSON 文件路径
        """
        json_subtitle_filename = f"{base_filename}_subtitle.json"
        json_subtitle_path = os.path.join(subtitles_dir, json_subtitle_filename)

        json_subtitle_content = {
            "format": "yivideo_subtitle",
            "version": "1.0",
            "metadata": {
                "language": language,
                "audio_duration": audio_duration,
                "total_segments": len(segments),
                "has_word_timestamps": enable_word_timestamps,
                "data_source": data_source
            },
            "segments": segments
        }

        with open(json_subtitle_path, "w", encoding="utf-8") as f:
            json.dump(json_subtitle_content, f, ensure_ascii=False, indent=2)

        logger.info(f"JSON 字幕文件已生成: {json_subtitle_path}")
        return json_subtitle_path

    def _format_srt_time(self, seconds: float) -> str:
        """
        将秒数格式化为 SRT 时间格式。

        Args:
            seconds: 秒数

        Returns:
            SRT 时间格式字符串（HH:MM:SS,mmm）
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _segments_to_word_timestamp_json(self, segments: List[Dict]) -> str:
        """
        将 faster-whisper 的 segments 转换为包含词级时间戳的 JSON 格式。

        Args:
            segments: segments 列表

        Returns:
            JSON 字符串
        """
        result = {
            "format": "word_timestamps",
            "total_segments": len(segments),
            "segments": []
        }

        for i, segment in enumerate(segments):
            segment_data = {
                "id": i + 1,
                "start": segment["start"],
                "end": segment["end"],
                "text": segment["text"].strip(),
                "srt_time": (
                    f"{self._format_srt_time(segment['start'])} --> "
                    f"{self._format_srt_time(segment['end'])}"
                )
            }

            if "words" in segment and segment["words"]:
                segment_data["words"] = [
                    {
                        "word": word_info["word"],
                        "start": word_info["start"],
                        "end": word_info["end"],
                        "confidence": word_info.get("confidence", 0.0)
                    }
                    for word_info in segment["words"]
                ]
            else:
                segment_data["words"] = [{
                    "word": segment["text"].strip(),
                    "start": segment["start"],
                    "end": segment["end"],
                    "confidence": 1.0
                }]

            result["segments"].append(segment_data)

        return json.dumps(result, indent=2, ensure_ascii=False)

    def _load_segments_from_file(self, segments_file: str) -> List[Dict]:
        """
        从文件加载 segments 数据。

        Args:
            segments_file: segments 文件路径

        Returns:
            segments 列表
        """
        try:
            if not os.path.exists(segments_file):
                logger.warning(f"Segments 文件不存在: {segments_file}")
                return []

            with open(segments_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and 'segments' in data:
                return data['segments']
            else:
                logger.warning(f"Segments 文件格式无效: {segments_file}")
                return []
        except Exception as e:
            logger.error(f"加载 segments 文件失败: {e}")
            return []

    def _get_segments_data(self, stage_output: Dict, field_name: str = None) -> List[Dict]:
        """
        统一的数据获取接口，支持新旧格式。

        Args:
            stage_output: 阶段输出数据
            field_name: 字段名称

        Returns:
            segments 列表
        """
        if field_name and field_name in stage_output:
            segments = stage_output[field_name]
            if segments and isinstance(segments, list):
                return segments

        segments_file = stage_output.get('segments_file')
        if segments_file:
            return self._load_segments_from_file(segments_file)

        return []

    def _get_speaker_data(self, stage_output: Dict) -> Dict[str, Any]:
        """
        获取说话人分离数据，支持新旧格式。

        Args:
            stage_output: 阶段输出数据

        Returns:
            说话人分离数据字典
        """
        # 新格式：直接包含 speaker_enhanced_segments
        if 'speaker_enhanced_segments' in stage_output:
            return {
                'speaker_enhanced_segments': stage_output.get('speaker_enhanced_segments'),
                'diarization_segments': stage_output.get('diarization_segments'),
                'detected_speakers': stage_output.get('detected_speakers', []),
                'speaker_statistics': stage_output.get('speaker_statistics', {})
            }

        # 旧格式：从 statistics 获取
        if 'statistics' in stage_output and isinstance(stage_output['statistics'], dict):
            statistics = stage_output['statistics']
            speaker_data = {
                'detected_speakers': statistics.get('detected_speakers', []),
                'speaker_statistics': statistics.get('speaker_statistics', {}),
                'diarization_duration': statistics.get('diarization_duration', 0)
            }

            # 从文件加载详细数据
            diarization_file = stage_output.get('diarization_file')
            if diarization_file:
                detailed_data = self._load_speaker_data_from_file(diarization_file)
                speaker_data.update({
                    'speaker_enhanced_segments': detailed_data.get('speaker_enhanced_segments'),
                    'diarization_segments': detailed_data.get('diarization_segments')
                })

            return speaker_data

        # 最后尝试从文件加载
        diarization_file = stage_output.get('diarization_file')
        if diarization_file:
            return self._load_speaker_data_from_file(diarization_file)

        return {}

    def _load_speaker_data_from_file(self, diarization_file: str) -> Dict[str, Any]:
        """
        从文件加载说话人分离数据。

        Args:
            diarization_file: 说话人分离文件路径

        Returns:
            说话人分离数据字典
        """
        try:
            if not os.path.exists(diarization_file):
                logger.warning(f"说话人分离文件不存在: {diarization_file}")
                return {}

            with open(diarization_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, dict):
                # 兼容处理
                speaker_segments = data.get('speaker_enhanced_segments')
                diarization_segments = data.get('diarization_segments')

                if speaker_segments is None and isinstance(data.get('segments'), list):
                    speaker_segments = data.get('segments')
                    data['speaker_enhanced_segments'] = speaker_segments

                if diarization_segments is None and isinstance(data.get('segments'), list):
                    diarization_segments = data.get('segments')
                    data['diarization_segments'] = diarization_segments

            return data
        except Exception as e:
            logger.error(f"加载说话人分离文件失败: {e}")
            return {}

    def get_cache_key_fields(self) -> List[str]:
        """
        返回用于生成缓存键的字段列表。

        字幕文件生成结果依赖于 segments 数据。
        """
        return ["segments_file"]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段列表。

        字幕文件生成的核心输出是 subtitle_path。
        """
        return ["subtitle_path"]
