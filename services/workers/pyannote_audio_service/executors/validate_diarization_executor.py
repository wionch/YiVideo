"""
Pyannote Audio 验证说话人分离结果执行器。
"""

import os
import json
from typing import Dict, Any, List

from services.common.base_node_executor import BaseNodeExecutor
from services.common.logger import get_logger
from services.common.file_service import get_file_service
from services.common.parameter_resolver import get_param_with_fallback

logger = get_logger(__name__)


class PyannoteAudioValidateDiarizationExecutor(BaseNodeExecutor):
    """
    Pyannote Audio 验证说话人分离结果执行器。

    对说话人分离结果进行质量检查，包括：
    - 片段数量和时长检查
    - 说话人数量检查
    - 片段分布检查

    输入参数:
        - diarization_file (str, 可选): 说话人分离结果文件路径，如果不提供则从前置节点获取

    输出字段:
        - valid (bool): 验证结果是否有效
        - total_segments (int): 片段总数
        - total_speakers (int): 说话人总数
        - total_duration (float): 总时长
        - avg_segment_duration (float): 平均片段时长
        - issues (list): 发现的问题列表
        - summary (str): 验证结果摘要
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
        执行验证说话人分离结果核心逻辑。

        Returns:
            包含验证结果的字典
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

        # 如果没有片段，返回无效结果
        if not segments:
            return {
                "valid": False,
                "total_segments": 0,
                "total_speakers": 0,
                "total_duration": 0,
                "avg_segment_duration": 0,
                "issues": ["没有检测到任何说话人片段"],
                "summary": "说话人分离结果无效"
            }

        # 执行质量检查
        validation_results = self._validate_segments(segments, data)

        return validation_results

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

    def _validate_segments(
        self,
        segments: List[Dict[str, Any]],
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        验证说话人片段质量。

        Args:
            segments: 说话人片段列表
            data: 完整的分离结果数据

        Returns:
            验证结果字典
        """
        issues = []
        total_speakers = data.get('total_speakers', 0)

        # 计算总时长和平均时长
        total_duration = 0
        segment_durations = []

        for segment in segments:
            duration = segment.get('duration', 0)
            segment_durations.append(duration)
            total_duration += duration

            # 检查片段时长
            if duration < 0.5:  # 片段过短
                issues.append(f"片段过短 ({duration:.2f}s)")
            elif duration > 30:  # 片段过长
                issues.append(f"片段过长 ({duration:.2f}s)")

        avg_segment_duration = total_duration / len(segments) if segments else 0

        # 检查说话人数量
        if total_speakers < 1:
            issues.append("没有检测到说话人")
        elif total_speakers > 10:  # 说话人过多可能是问题
            issues.append(f"检测到过多说话人 ({total_speakers})")

        # 检查片段分布
        unique_speakers = len(set(seg.get('speaker', 'unknown') for seg in segments))
        if unique_speakers < total_speakers:
            issues.append("部分说话人片段不完整")

        # 构建验证结果
        valid = len(issues) == 0
        summary = "说话人分离结果有效" if valid else "说话人分离结果存在问题"

        return {
            "valid": valid,
            "total_segments": len(segments),
            "total_speakers": total_speakers,
            "total_duration": total_duration,
            "avg_segment_duration": avg_segment_duration,
            "issues": issues,
            "summary": summary
        }

    def get_cache_key_fields(self) -> List[str]:
        """
        返回用于生成缓存键的字段列表。

        验证结果仅依赖于分离文件。
        """
        return ["diarization_file"]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段列表。

        验证的核心输出是 valid 和 summary。
        """
        return ["valid", "summary"]
