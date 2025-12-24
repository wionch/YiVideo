"""
WService 说话人片段合并执行器。
"""

import os
from typing import Dict, Any, List

from services.common.base_node_executor import BaseNodeExecutor
from services.common.logger import get_logger
from services.common.parameter_resolver import get_param_with_fallback
from services.common.config_loader import CONFIG
from services.common.file_service import get_file_service
from services.common.subtitle.subtitle_merger import (
    create_subtitle_merger,
    validate_speaker_segments
)

logger = get_logger(__name__)


class WServiceMergeSpeakerSegmentsExecutor(BaseNodeExecutor):
    """
    WService 说话人片段合并执行器。

    合并转录字幕与说话人时间段（片段级合并）。

    输入参数:
        - segments_data (list, 可选): 直接传入转录片段数据
        - speaker_segments_data (list, 可选): 直接传入说话人片段数据
        - segments_file (str, 可选): 转录数据文件路径
        - diarization_file (str, 可选): 说话人分离数据文件路径

    输出字段:
        - merged_segments (list): 合并后的片段列表
        - input_summary (dict): 输入数据摘要
            - transcript_segments_count (int): 转录片段数量
            - speaker_segments_count (int): 说话人片段数量
            - merged_segments_count (int): 合并后片段数量
            - data_source (str): 数据来源
    """

    def __init__(self, stage_name: str, context):
        super().__init__(stage_name, context)
        self.file_service = get_file_service()

    def validate_input(self) -> None:
        """
        验证输入参数。

        至少需要提供以下之一：
        - segments_data 或 segments_file
        - speaker_segments_data 或 diarization_file
        """
        input_data = self.get_input_data()
        workflow_id = self.context.workflow_id

        # 检查转录片段数据
        has_transcript_data = (
            get_param_with_fallback("segments_data", input_data, self.context) is not None
            or get_param_with_fallback("segments_file", input_data, self.context) is not None
        )

        # 检查说话人片段数据
        has_speaker_data = (
            get_param_with_fallback("speaker_segments_data", input_data, self.context) is not None
            or get_param_with_fallback("diarization_file", input_data, self.context) is not None
        )

        # 如果都没有提供，检查是否有上游节点
        if not has_transcript_data:
            transcribe_stage = self.context.stages.get('faster_whisper.transcribe_audio')
            if not transcribe_stage or transcribe_stage.status not in ['SUCCESS', 'COMPLETED']:
                raise ValueError(
                    "缺少必需参数: 请提供 segments_data/segments_file 参数，"
                    "或确保 faster_whisper.transcribe_audio 已完成"
                )

        if not has_speaker_data:
            diarize_stage = self.context.stages.get('pyannote_audio.diarize_speakers')
            if not diarize_stage or diarize_stage.status not in ['SUCCESS', 'COMPLETED']:
                raise ValueError(
                    "缺少必需参数: 请提供 speaker_segments_data/diarization_file 参数，"
                    "或确保 pyannote_audio.diarize_speakers 已完成"
                )

        logger.info(f"[{workflow_id}] 输入参数验证通过")

    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行说话人片段合并核心逻辑。

        Returns:
            包含合并结果的字典
        """
        workflow_id = self.context.workflow_id
        input_data = self.get_input_data()

        logger.info(f"[{workflow_id}] 开始合并转录片段与说话人片段")

        # 获取转录片段数据
        transcript_segments = self._get_transcript_segments(input_data)
        if not transcript_segments:
            raise ValueError("转录片段数据为空")

        # 获取说话人片段数据
        speaker_segments = self._get_speaker_segments(input_data)
        if not speaker_segments:
            raise ValueError("说话人片段数据为空")

        # 验证说话人片段格式
        if not validate_speaker_segments(speaker_segments):
            raise ValueError("说话人时间段数据格式无效")

        logger.info(
            f"[{workflow_id}] 转录片段数量: {len(transcript_segments)}, "
            f"说话人片段数量: {len(speaker_segments)}"
        )

        # 执行合并逻辑
        service_config = CONFIG.get('faster_whisper_service', {})
        merge_config = service_config.get('subtitle_merge', {})
        merger = create_subtitle_merger(merge_config)
        merged_segments = merger.merge(transcript_segments, speaker_segments)

        logger.info(f"[{workflow_id}] 合并完成，生成 {len(merged_segments)} 个片段")

        return {
            'merged_segments': merged_segments,
            'input_summary': {
                'transcript_segments_count': len(transcript_segments),
                'speaker_segments_count': len(speaker_segments),
                'merged_segments_count': len(merged_segments),
                'data_source': self._get_data_source()
            }
        }

    def _get_transcript_segments(self, input_data: Dict[str, Any]) -> List[Dict]:
        """
        获取转录片段数据。

        优先级:
        1. 直接传入的 segments_data
        2. segments_file 文件路径
        3. faster_whisper.transcribe_audio 节点输出

        Args:
            input_data: 输入数据

        Returns:
            转录片段列表
        """
        workflow_id = self.context.workflow_id

        # 1. 尝试直接获取片段数据
        transcript_segments = get_param_with_fallback(
            "segments_data",
            input_data,
            self.context
        )
        if transcript_segments:
            logger.info(f"[{workflow_id}] 从 segments_data 获取转录片段")
            return transcript_segments

        # 2. 尝试从文件加载
        segments_file = get_param_with_fallback(
            "segments_file",
            input_data,
            self.context
        )
        if segments_file:
            segments_file = self._normalize_path(segments_file)
            segments_file = self._download_if_needed(segments_file)
            if segments_file:
                transcript_segments = self._load_segments_from_file(segments_file)
                if transcript_segments:
                    logger.info(
                        f"[{workflow_id}] 从文件加载转录片段: {segments_file}"
                    )
                    return transcript_segments

        # 3. 从上游节点获取
        transcribe_stage = self.context.stages.get('faster_whisper.transcribe_audio')
        if transcribe_stage and transcribe_stage.output:
            transcript_segments = self._get_segments_data(
                transcribe_stage.output,
                'segments'
            )
            if transcript_segments:
                logger.info(
                    f"[{workflow_id}] 从 faster_whisper.transcribe_audio 获取转录片段"
                )
                return transcript_segments

        return []

    def _get_speaker_segments(self, input_data: Dict[str, Any]) -> List[Dict]:
        """
        获取说话人片段数据。

        优先级:
        1. 直接传入的 speaker_segments_data
        2. diarization_file 文件路径
        3. pyannote_audio.diarize_speakers 节点输出

        Args:
            input_data: 输入数据

        Returns:
            说话人片段列表
        """
        workflow_id = self.context.workflow_id

        # 1. 尝试直接获取片段数据
        speaker_segments = get_param_with_fallback(
            "speaker_segments_data",
            input_data,
            self.context
        )
        if speaker_segments:
            logger.info(f"[{workflow_id}] 从 speaker_segments_data 获取说话人片段")
            return speaker_segments

        # 2. 尝试从文件加载
        diarization_file = get_param_with_fallback(
            "diarization_file",
            input_data,
            self.context
        )
        if diarization_file:
            diarization_file = self._normalize_path(diarization_file)
            diarization_file = self._download_if_needed(diarization_file)
            if diarization_file:
                speaker_data = self._load_speaker_data_from_file(diarization_file)
                speaker_segments = speaker_data.get('speaker_enhanced_segments')
                if speaker_segments:
                    logger.info(
                        f"[{workflow_id}] 从文件加载说话人片段: {diarization_file}"
                    )
                    return speaker_segments

        # 3. 从上游节点获取
        diarize_stage = self.context.stages.get('pyannote_audio.diarize_speakers')
        if diarize_stage and diarize_stage.output:
            speaker_data = self._get_speaker_data(diarize_stage.output)
            speaker_segments = speaker_data.get('speaker_enhanced_segments')
            if speaker_segments:
                logger.info(
                    f"[{workflow_id}] 从 pyannote_audio.diarize_speakers 获取说话人片段"
                )
                return speaker_segments

        return []

    def _normalize_path(self, file_path: str) -> str:
        """
        规范化文件路径。

        支持省略开头的 /share 或相对路径。

        Args:
            file_path: 原始文件路径

        Returns:
            规范化后的文件路径
        """
        if not file_path:
            return file_path

        # URL 直接返回
        if file_path.startswith(("http://", "https://", "minio://")):
            return file_path

        # 处理 share/ 开头的路径
        if file_path.startswith(("share/", "share\\")):
            candidate = "/" + file_path.lstrip("/\\")
            if os.path.exists(candidate):
                return candidate

        # 处理相对路径
        if not os.path.isabs(file_path):
            candidate = os.path.join(
                self.context.shared_storage_path,
                file_path
            )
            if os.path.exists(candidate):
                return candidate

        return file_path

    def _download_if_needed(self, file_path: str) -> str:
        """
        如果是 URL，下载文件到本地。

        Args:
            file_path: 文件路径或 URL

        Returns:
            本地文件路径，如果下载失败则返回 None
        """
        if not file_path:
            return None

        # 如果是本地文件且存在，直接返回
        if not file_path.startswith(("http://", "https://", "minio://")):
            if os.path.exists(file_path):
                return file_path
            return None

        # 下载 URL 文件
        try:
            local_path = self.file_service.resolve_and_download(
                file_path,
                self.context.shared_storage_path
            )
            logger.info(f"文件下载成功: {file_path} -> {local_path}")
            return local_path
        except Exception as e:
            logger.warning(f"文件下载失败: {file_path}, 错误: {e}")
            return None

    def _load_segments_from_file(self, segments_file: str) -> List[Dict]:
        """
        从文件加载 segments 数据。

        Args:
            segments_file: segments 文件路径

        Returns:
            segments 列表
        """
        import json

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

    def _load_speaker_data_from_file(self, diarization_file: str) -> Dict[str, Any]:
        """
        从文件加载说话人分离数据。

        Args:
            diarization_file: 说话人分离文件路径

        Returns:
            说话人分离数据字典
        """
        import json

        try:
            if not os.path.exists(diarization_file):
                logger.warning(f"说话人分离文件不存在: {diarization_file}")
                return {}

            with open(diarization_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, dict):
                # 兼容处理：如果缺少某些字段，尝试从 segments 补充
                speaker_segments = data.get('speaker_enhanced_segments')
                diarization_segments = data.get('diarization_segments')

                if speaker_segments is None and isinstance(data.get('segments'), list):
                    speaker_segments = data.get('segments')
                    data['speaker_enhanced_segments'] = speaker_segments

                if diarization_segments is None and isinstance(data.get('segments'), list):
                    diarization_segments = data.get('segments')
                    data['diarization_segments'] = diarization_segments

                logger.info(
                    f"说话人分离数据加载成功: {diarization_file}, "
                    f"keys={list(data.keys())}"
                )

            return data
        except Exception as e:
            logger.error(f"加载说话人分离文件失败: {e}")
            return {}

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

    def _get_data_source(self) -> str:
        """
        获取数据来源描述。

        Returns:
            数据来源字符串
        """
        input_data = self.get_input_data()

        # 检查是否从参数直接获取
        if get_param_with_fallback("segments_data", input_data, self.context):
            return "input_data.segments_data"
        if get_param_with_fallback("segments_file", input_data, self.context):
            return "input_data.segments_file"

        # 检查是否从上游节点获取
        sources = []
        if self.context.stages.get('faster_whisper.transcribe_audio'):
            sources.append('faster_whisper.transcribe_audio')
        if self.context.stages.get('pyannote_audio.diarize_speakers'):
            sources.append('pyannote_audio.diarize_speakers')

        return ' + '.join(sources) if sources else 'unknown'

    def get_cache_key_fields(self) -> List[str]:
        """
        返回用于生成缓存键的字段列表。

        合并结果依赖于转录片段和说话人片段。
        """
        return ["segments_file", "diarization_file"]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段列表。

        合并的核心输出是 merged_segments。
        """
        return ["merged_segments"]
