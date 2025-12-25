"""
WService 基于说话人时间区间的字幕合并执行器。
"""

import os
import json
from typing import Dict, Any, List

from services.common.base_node_executor import BaseNodeExecutor
from services.common.logger import get_logger
from services.common.parameter_resolver import get_param_with_fallback
from services.common.file_service import get_file_service
from services.common.subtitle.speaker_based_merger import merge_speaker_based_subtitles
from services.common.path_builder import build_node_output_path, ensure_directory

logger = get_logger(__name__)


class WServiceMergeSpeakerBasedSubtitlesExecutor(BaseNodeExecutor):
    """
    WService 基于说话人时间区间的字幕合并执行器。

    基于说话人识别文件的时间区间生成字幕，输出 segments 数量与 Diarization 一致。

    输入参数:
        - segments_data (list, 可选): 直接传入包含词级时间戳的转录片段数据
        - speaker_segments_data (list, 可选): 直接传入说话人片段数据
        - segments_file (str, 可选): 包含词级时间戳的转录数据文件路径
        - diarization_file (str, 可选): 说话人分离数据文件路径
        - overlap_threshold (float, 可选): 重叠阈值（默认 0.5）

    输出字段:
        - merged_segments_file (str): 合并后的片段文件路径
        - total_segments (int): 总片段数量
        - matched_segments (int): 有匹配词的片段数量
        - empty_segments (int): 无匹配词的片段数量
    """

    def __init__(self, stage_name: str, context):
        super().__init__(stage_name, context)
        self.file_service = get_file_service()

    def validate_input(self) -> None:
        """
        验证输入参数。

        至少需要提供以下之一：
        - segments_data 或 segments_file（必须包含词级时间戳）
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
        执行基于说话人时间区间的字幕合并核心逻辑。

        Returns:
            包含合并结果的字典
        """
        workflow_id = self.context.workflow_id
        input_data = self.get_input_data()

        logger.info(f"[{workflow_id}] 开始基于说话人时间区间的字幕合并")

        # 获取转录片段数据
        transcript_segments = self._get_transcript_segments(input_data)
        if not transcript_segments:
            raise ValueError("转录片段数据为空")

        # 验证词级时间戳
        if not any('words' in seg and seg['words'] for seg in transcript_segments):
            raise ValueError("转录结果不包含词级时间戳，无法执行基于说话人的合并")

        # 获取说话人片段数据
        speaker_segments = self._get_speaker_segments(input_data)
        if not speaker_segments:
            raise ValueError("说话人片段数据为空")

        # 验证说话人片段格式
        self._validate_speaker_segments(speaker_segments)

        # 获取重叠阈值参数
        overlap_threshold = get_param_with_fallback(
            "overlap_threshold",
            input_data,
            self.context
        )
        if overlap_threshold is None:
            overlap_threshold = 0.5
        else:
            overlap_threshold = float(overlap_threshold)
            if not 0.0 <= overlap_threshold <= 1.0:
                raise ValueError(f"overlap_threshold 必须在 0.0-1.0 范围内，当前值: {overlap_threshold}")

        logger.info(
            f"[{workflow_id}] 转录片段数量: {len(transcript_segments)}, "
            f"说话人片段数量: {len(speaker_segments)}, "
            f"重叠阈值: {overlap_threshold}"
        )

        # 执行基于说话人的合并逻辑
        merged_segments = merge_speaker_based_subtitles(
            transcript_segments,
            speaker_segments,
            overlap_threshold
        )

        logger.info(f"[{workflow_id}] 基于说话人的合并完成，生成 {len(merged_segments)} 个片段")

        # 统计信息
        matched_segments = sum(1 for seg in merged_segments if seg['word_count'] > 0)
        empty_segments = len(merged_segments) - matched_segments

        logger.info(
            f"[{workflow_id}] 统计: 总片段={len(merged_segments)}, "
            f"有匹配词={matched_segments}, 无匹配词={empty_segments}"
        )

        # 保存合并结果到文件
        merged_file = self._save_merged_segments(merged_segments, input_data)

        return {
            "merged_segments_file": merged_file,
            "total_segments": len(merged_segments),
            "matched_segments": matched_segments,
            "empty_segments": empty_segments
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
            logger.info(f"[{workflow_id}] 解析 segments_file: {segments_file}")
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
            logger.info(f"[{workflow_id}] 解析 diarization_file: {diarization_file}")
            diarization_file = self._download_if_needed(diarization_file)
            if diarization_file:
                speaker_data = self._load_speaker_data_from_file(diarization_file)
                speaker_segments = speaker_data.get('speaker_enhanced_segments')
                if isinstance(speaker_segments, list):
                    logger.info(
                        f"[{workflow_id}] 从文件加载说话人片段: {diarization_file}, "
                        f"数量: {len(speaker_segments)}"
                    )
                    return speaker_segments
                else:
                    logger.warning(
                        f"[{workflow_id}] speaker_segments 类型异常: {type(speaker_segments)}"
                    )

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

    def _validate_speaker_segments(self, speaker_segments: List[Dict]) -> None:
        """
        验证说话人片段格式。

        Args:
            speaker_segments: 说话人片段列表

        Raises:
            ValueError: 如果格式无效
        """
        if not speaker_segments:
            raise ValueError("speaker_segments 为空")

        for idx, seg in enumerate(speaker_segments):
            # 检查必需字段
            missing = [key for key in ['start', 'end', 'speaker'] if key not in seg]
            if missing:
                raise ValueError(f"speaker_segments[{idx}] 缺少字段: {missing}")

            # 检查时间有效性
            if seg['end'] <= seg['start']:
                raise ValueError(
                    f"speaker_segments[{idx}] 时间无效: "
                    f"start={seg.get('start')}, end={seg.get('end')}"
                )

    def _normalize_path(self, file_path: str) -> str:
        """
        规范化文件路径。

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

    def _save_merged_segments(
        self,
        merged_segments: List[Dict],
        input_data: Dict[str, Any]
    ) -> str:
        """
        保存合并后的片段到文件。

        Args:
            merged_segments: 合并后的片段列表
            input_data: 输入数据

        Returns:
            保存的文件路径
        """
        workflow_id = self.context.workflow_id

        # 生成文件名（使用 speaker_based 标识）
        segments_source = get_param_with_fallback(
            "segments_file",
            input_data,
            self.context
        )
        base_name = (
            os.path.splitext(os.path.basename(segments_source))[0]
            if segments_source
            else "merged_segments"
        )

        # 使用标准化路径
        merged_file = build_node_output_path(
            task_id=workflow_id,
            node_name=self.stage_name,
            file_type="data",
            filename=f"{base_name}_speaker_based.json"
        )
        ensure_directory(merged_file)

        # 保存文件
        with open(merged_file, "w", encoding="utf-8") as f:
            json.dump(merged_segments, f, ensure_ascii=False, indent=2)

        logger.info(f"[{workflow_id}] 合并结果已保存: {merged_file}")
        return merged_file

    def get_cache_key_fields(self) -> List[str]:
        """
        返回用于生成缓存键的字段列表。

        基于说话人的合并结果依赖于转录片段、说话人片段和重叠阈值。
        """
        return ["segments_file", "diarization_file", "overlap_threshold"]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段列表。

        基于说话人合并的核心输出是 merged_segments_file。
        """
        return ["merged_segments_file"]
