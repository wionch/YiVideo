"""
Pyannote Audio 获取说话人片段执行器。
"""

import os
import json
from typing import Dict, Any, List

from services.common.base_node_executor import BaseNodeExecutor
from services.common.logger import get_logger
from services.common.file_service import get_file_service
from services.common.parameter_resolver import get_param_with_fallback

logger = get_logger(__name__)


class PyannoteAudioGetSpeakerSegmentsExecutor(BaseNodeExecutor):
    """
    Pyannote Audio 获取说话人片段执行器。

    从说话人分离结果文件中提取指定说话人的片段，
    或返回所有说话人的统计信息。

    输入参数:
        - diarization_file (str, 可选): 说话人分离结果文件路径，如果不提供则从前置节点获取
        - speaker (str, 可选): 目标说话人标签，不指定则返回所有说话人统计

    输出字段:
        - segments (list): 说话人片段列表
        - summary (str): 片段摘要
        - total_segments (int): 片段总数
        - speaker_filter (str, 可选): 过滤的说话人标签
    """

    def validate_input(self) -> None:
        """
        验证输入参数。

        diarization_file 可以从参数获取，也可以从前置节点获取，
        因此这里不强制要求。
        """
        # 不强制要求 diarization_file，因为可以从前置节点获取
        pass

    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行获取说话人片段核心逻辑。

        Returns:
            包含说话人片段的字典
        """
        workflow_id = self.context.workflow_id
        input_data = self.get_input_data()
        file_service = get_file_service()

        # 获取说话人分离结果文件路径
        diarization_file = self._get_diarization_file(input_data)

        if not diarization_file:
            raise ValueError(
                "无法获取说话人分离结果文件：请提供 diarization_file 参数，"
                "或确保 pyannote_audio.diarize_speakers 任务已成功完成"
            )

        logger.info(f"[{workflow_id}] 说话人分离文件: {diarization_file}")

        # 下载文件（如果需要）
        if not os.path.exists(diarization_file):
            logger.info(f"[{workflow_id}] 开始下载说话人分离文件: {diarization_file}")
            diarization_file = file_service.resolve_and_download(
                diarization_file,
                self.context.shared_storage_path
            )
            logger.info(f"[{workflow_id}] 说话人分离文件下载完成: {diarization_file}")

        # 检查文件是否存在
        if not os.path.exists(diarization_file):
            raise FileNotFoundError(f"说话人分离结果文件不存在: {diarization_file}")

        # 加载结果文件
        with open(diarization_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        segments = data.get('segments', [])

        # 获取目标说话人（可选）
        target_speaker = input_data.get('speaker')

        # 过滤片段
        if target_speaker:
            filtered_segments = [
                seg for seg in segments
                if seg.get('speaker') == target_speaker
            ]
            summary = f"说话人 {target_speaker} 的片段: {len(filtered_segments)} 个"
            output_data = {
                "segments": filtered_segments,
                "summary": summary,
                "total_segments": len(filtered_segments),
                "speaker_filter": target_speaker
            }
        else:
            # 返回所有说话人的片段统计
            speaker_stats = {}
            for seg in segments:
                speaker = seg.get('speaker', 'unknown')
                if speaker not in speaker_stats:
                    speaker_stats[speaker] = []
                speaker_stats[speaker].append(seg)

            summary = f"所有说话人片段统计: {len(speaker_stats)} 个说话人"
            output_data = {
                "segments": segments,
                "summary": summary,
                "total_segments": len(segments),
                "speaker_statistics": {
                    speaker: len(segs)
                    for speaker, segs in speaker_stats.items()
                }
            }

        return output_data

    def _get_diarization_file(self, input_data: Dict[str, Any]) -> str:
        """
        获取说话人分离结果文件路径。

        优先级:
        1. 参数/input_data 中的 diarization_file
        2. pyannote_audio.diarize_speakers 节点的输出

        Args:
            input_data: 输入数据

        Returns:
            diarization_file 路径
        """
        workflow_id = self.context.workflow_id

        # 优先从参数获取
        diarization_file = get_param_with_fallback(
            "diarization_file",
            input_data,
            self.context
        )
        if diarization_file:
            logger.info(f"[{workflow_id}] 从参数/input_data获取分离文件: {diarization_file}")
            return diarization_file

        # 从 pyannote_audio.diarize_speakers 获取
        diarize_stage = self.context.stages.get('pyannote_audio.diarize_speakers')
        if diarize_stage and diarize_stage.output:
            diarization_file = diarize_stage.output.get('diarization_file')
            if diarization_file:
                logger.info(
                    f"[{workflow_id}] 从 pyannote_audio.diarize_speakers "
                    f"获取分离文件: {diarization_file}"
                )
                return diarization_file

        return None

    def get_cache_key_fields(self) -> List[str]:
        """
        返回用于生成缓存键的字段列表。

        说话人片段提取结果依赖于分离文件和目标说话人。
        """
        return ["diarization_file", "speaker"]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段列表。

        说话人片段提取的核心输出是 segments。
        """
        return ["segments"]
