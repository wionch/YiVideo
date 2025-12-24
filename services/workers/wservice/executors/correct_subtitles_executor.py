"""
WService 字幕校正执行器。
"""

import os
import asyncio
from typing import Dict, Any, List

from services.common.base_node_executor import BaseNodeExecutor
from services.common.logger import get_logger
from services.common.parameter_resolver import get_param_with_fallback
from services.common.subtitle.subtitle_correction import SubtitleCorrector

logger = get_logger(__name__)


class WServiceCorrectSubtitlesExecutor(BaseNodeExecutor):
    """
    WService 字幕校正执行器。

    使用 AI 大模型对字幕进行智能校正，包括修正错别字、语法错误等。

    输入参数:
        - subtitle_path (str, 可选): 待校正的字幕文件路径
        - subtitle_correction (dict, 可选): 校正配置
            - enabled (bool): 是否启用校正 (默认False)
            - provider (str): AI 提供商 (默认None)

    输出字段:
        - corrected_subtitle_path (str): 校正后的字幕文件路径
        - original_subtitle_path (str): 原始字幕文件路径
        - provider_used (str): 使用的 AI 提供商
        - statistics (dict): 校正统计信息
    """

    def __init__(self, stage_name: str, context):
        super().__init__(stage_name, context)
        self.correction_params = None

    def validate_input(self) -> None:
        """
        验证输入参数。

        字幕校正是可选功能，如果未启用则跳过验证。
        """
        input_data = self.get_input_data()

        # 获取校正配置
        self.correction_params = get_param_with_fallback(
            "subtitle_correction",
            input_data,
            self.context
        )

        # 如果没有配置，尝试从全局参数获取
        if not self.correction_params:
            self.correction_params = self.context.input_params.get('params', {}).get(
                'subtitle_correction', {}
            )

        # 如果未启用，不需要验证
        is_enabled = self.correction_params.get('enabled', False) if self.correction_params else False
        if not is_enabled:
            logger.info(f"[{self.context.workflow_id}] 字幕校正未启用，将跳过处理")
            return

        # 验证字幕文件路径
        subtitle_path = self._get_subtitle_path(input_data)
        if not subtitle_path:
            raise ValueError("缺少必需参数: subtitle_path (字幕文件路径)")

    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行字幕校正核心逻辑。

        Returns:
            包含校正结果的字典
        """
        workflow_id = self.context.workflow_id
        input_data = self.get_input_data()

        # 检查是否启用
        is_enabled = self.correction_params.get('enabled', False) if self.correction_params else False
        if not is_enabled:
            logger.info(f"[{workflow_id}] 字幕校正未启用，跳过处理")
            # 返回特殊状态表示跳过
            return {"_skipped": True}

        # 获取字幕文件路径
        subtitle_to_correct = self._get_subtitle_path(input_data)

        if not subtitle_to_correct or not os.path.exists(subtitle_to_correct):
            raise FileNotFoundError(f"未找到可供校正的字幕文件: {subtitle_to_correct}")

        # 获取 AI 提供商
        provider = self.correction_params.get('provider', None)

        logger.info(f"[{workflow_id}] 开始字幕校正")
        logger.info(f"[{workflow_id}] 字幕文件: {subtitle_to_correct}")
        logger.info(f"[{workflow_id}] AI 提供商: {provider}")

        # 创建校正器
        corrector = SubtitleCorrector(provider=provider)

        # 生成输出文件路径
        corrected_filename = os.path.basename(subtitle_to_correct).replace(
            '.srt', '_corrected_by_ai.srt'
        )
        corrected_path = os.path.join(
            os.path.dirname(subtitle_to_correct),
            corrected_filename
        )

        # 执行异步校正
        correction_result = asyncio.run(
            corrector.correct_subtitle_file(
                subtitle_path=subtitle_to_correct,
                output_path=corrected_path
            )
        )

        if not correction_result.success:
            raise RuntimeError(
                f"AI字幕校正失败: {correction_result.error_message}"
            )

        logger.info(f"[{workflow_id}] 字幕校正完成: {corrected_path}")

        return {
            "corrected_subtitle_path": correction_result.corrected_subtitle_path,
            "original_subtitle_path": correction_result.original_subtitle_path,
            "provider_used": correction_result.provider_used,
            "statistics": correction_result.statistics
        }

    def _get_subtitle_path(self, input_data: Dict[str, Any]) -> str:
        """
        获取待校正的字幕文件路径。

        优先级:
        1. 参数/input_data 中的 subtitle_path
        2. wservice.generate_subtitle_files 节点的 speaker_srt_path
        3. wservice.generate_subtitle_files 节点的 subtitle_path

        Args:
            input_data: 输入数据

        Returns:
            字幕文件路径或 None
        """
        workflow_id = self.context.workflow_id

        # 优先从参数获取
        subtitle_path = get_param_with_fallback(
            "subtitle_path",
            input_data,
            self.context
        )
        if subtitle_path:
            logger.info(
                f"[{workflow_id}] 从参数/input_data获取字幕路径: {subtitle_path}"
            )
            return subtitle_path

        # 尝试从 generate_subtitle_files 获取带说话人的 SRT
        generate_stage = self.context.stages.get('wservice.generate_subtitle_files')
        if generate_stage and generate_stage.output:
            # 优先使用带说话人的字幕
            speaker_srt_path = generate_stage.output.get('subtitle_files', {}).get('with_speakers')
            if not speaker_srt_path:
                # 向后兼容旧字段名
                speaker_srt_path = generate_stage.output.get('speaker_srt_path')

            if speaker_srt_path:
                logger.info(
                    f"[{workflow_id}] 从 wservice.generate_subtitle_files "
                    f"获取带说话人字幕: {speaker_srt_path}"
                )
                return speaker_srt_path

            # 回退到基础字幕
            basic_subtitle_path = generate_stage.output.get('subtitle_files', {}).get('basic')
            if not basic_subtitle_path:
                # 向后兼容旧字段名
                basic_subtitle_path = generate_stage.output.get('subtitle_path')

            if basic_subtitle_path:
                logger.info(
                    f"[{workflow_id}] 从 wservice.generate_subtitle_files "
                    f"获取基础字幕: {basic_subtitle_path}"
                )
                return basic_subtitle_path

        return None

    def get_cache_key_fields(self) -> List[str]:
        """
        返回用于生成缓存键的字段列表。

        字幕校正结果依赖于字幕文件和 AI 提供商。
        """
        return ["subtitle_path", "subtitle_correction"]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段列表。

        字幕校正的核心输出是 corrected_subtitle_path。
        """
        return ["corrected_subtitle_path"]

    def format_output(self, core_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化输出数据。

        处理跳过状态的特殊情况。
        """
        # 检查是否跳过
        if core_output.get("_skipped"):
            # 跳过状态不需要格式化
            return {}

        return super().format_output(core_output)

    def update_context(self, output_data: Dict[str, Any]) -> None:
        """
        更新工作流上下文。

        处理跳过状态的特殊情况。
        """
        # 检查是否跳过
        if output_data.get("_skipped") or not output_data:
            self.context.stages[self.stage_name].status = "SKIPPED"
            self.context.stages[self.stage_name].output = {}
        else:
            super().update_context(output_data)
