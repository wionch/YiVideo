"""
WService AI 字幕优化执行器。
"""

import os
import time
from typing import Dict, Any, List

from services.common.base_node_executor import BaseNodeExecutor
from services.common.logger import get_logger
from services.common.parameter_resolver import get_param_with_fallback
from services.common.subtitle.subtitle_optimizer import SubtitleOptimizer
from services.common.subtitle.metrics import metrics_collector

logger = get_logger(__name__)


class WServiceAIOptimizeSubtitlesExecutor(BaseNodeExecutor):
    """
    WService AI 字幕优化执行器。

    通过 AI 大模型对转录后的字幕进行智能优化和校正，包括：
    1. 修正错别字和语法错误
    2. 添加适当的标点符号
    3. 删除口头禅和填充词
    4. 支持大体积字幕的并发处理

    输入参数:
        - segments_file (str, 可选): 转录文件路径
        - subtitle_optimization (dict, 可选): 优化配置
            - enabled (bool): 是否启用优化 (默认False)
            - provider (str): AI 提供商 (默认'deepseek')
            - batch_size (int): 批次大小 (默认50)
            - overlap_size (int): 重叠大小 (默认10)

    输出字段:
        - optimized_file_path (str): 优化后的文件路径
        - original_file_path (str): 原始文件路径
        - provider_used (str): 使用的 AI 提供商
        - processing_time (float): 处理时间（秒）
        - subtitles_count (int): 字幕条目数量
        - commands_applied (int): 应用的优化命令数
        - batch_mode (str): 批处理模式
        - batches_count (int): 批次数量
        - statistics (dict): 优化统计信息
    """

    def __init__(self, stage_name: str, context):
        super().__init__(stage_name, context)
        self.optimization_params = None
        self.provider = None
        self.start_time = None

    def validate_input(self) -> None:
        """
        验证输入参数。

        字幕优化是可选功能，如果未启用则跳过验证。
        """
        input_data = self.get_input_data()

        # 获取优化配置
        self.optimization_params = get_param_with_fallback(
            "subtitle_optimization",
            input_data,
            self.context
        )

        # 如果没有配置，尝试从全局参数获取
        if not self.optimization_params:
            self.optimization_params = self.context.input_params.get('params', {}).get(
                'subtitle_optimization', {}
            )

        # 如果未启用，不需要验证
        is_enabled = self.optimization_params.get('enabled', False) if self.optimization_params else False
        if not is_enabled:
            logger.info(f"[{self.context.workflow_id}] 字幕优化未启用，将跳过处理")
            return

        # 验证转录文件路径
        segments_file = self._get_segments_file(input_data)
        if not segments_file:
            raise ValueError("缺少必需参数: segments_file (转录文件路径)")

    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行字幕优化核心逻辑。

        Returns:
            包含优化结果的字典
        """
        self.start_time = time.time()
        workflow_id = self.context.workflow_id
        input_data = self.get_input_data()

        # 检查是否启用
        is_enabled = self.optimization_params.get('enabled', False) if self.optimization_params else False
        if not is_enabled:
            logger.info(f"[{workflow_id}] 字幕优化未启用，跳过处理")
            return {"_skipped": True}

        # 获取配置参数
        self.provider = self.optimization_params.get('provider', 'deepseek')
        batch_size = self.optimization_params.get('batch_size', 50)
        overlap_size = self.optimization_params.get('overlap_size', 10)

        logger.info(
            f"[{workflow_id}] 开始AI字幕优化 - 提供商: {self.provider}, "
            f"批次大小: {batch_size}, 重叠大小: {overlap_size}"
        )

        # 获取转录文件路径
        segments_file = self._get_segments_file(input_data)

        if not segments_file or not os.path.exists(segments_file):
            raise FileNotFoundError(f"未找到转录文件: {segments_file}")

        logger.info(f"[{workflow_id}] 转录文件: {segments_file}")

        # 初始化字幕优化器
        optimizer = SubtitleOptimizer(
            batch_size=batch_size,
            overlap_size=overlap_size,
            provider=self.provider
        )

        # 执行优化
        result = optimizer.optimize_subtitles(
            transcribe_file_path=segments_file,
            output_file_path=None,  # 自动生成输出路径
            prompt_file_path=None   # 使用默认提示词
        )

        if not result['success']:
            raise RuntimeError(f"AI字幕优化失败: {result.get('error', '未知错误')}")

        # 记录指标
        metrics_collector.record_request(
            provider=self.provider,
            status='success',
            duration=time.time() - self.start_time
        )
        metrics_collector.set_processing_time(self.provider, result['processing_time'])
        metrics_collector.set_batch_size(self.provider, batch_size)
        metrics_collector.record_subtitle_count(
            result['subtitles_count'],
            result['batch_mode']
        )

        logger.info(
            f"[{workflow_id}] 字幕优化完成 - 文件: {result['file_path']}, "
            f"处理时间: {result['processing_time']:.2f}秒"
        )

        return {
            "optimized_file_path": result['file_path'],
            "original_file_path": segments_file,
            "provider_used": self.provider,
            "processing_time": result['processing_time'],
            "subtitles_count": result['subtitles_count'],
            "commands_applied": result['commands_applied'],
            "batch_mode": result['batch_mode'],
            "batches_count": result.get('batches_count', 1),
            "statistics": {
                "total_commands": result['commands_applied'],
                "optimization_rate": result['commands_applied'] / max(result['subtitles_count'], 1)
            }
        }

    def _get_segments_file(self, input_data: Dict[str, Any]) -> str:
        """
        获取转录文件路径。

        优先级:
        1. optimization_params 中的 segments_file
        2. 参数/input_data 中的 segments_file
        3. faster_whisper.transcribe_audio 节点的 segments_file

        Args:
            input_data: 输入数据

        Returns:
            转录文件路径或 None
        """
        workflow_id = self.context.workflow_id

        # 优先从 optimization_params 获取
        if self.optimization_params:
            segments_file = self.optimization_params.get('segments_file')
            if segments_file:
                logger.info(
                    f"[{workflow_id}] 从 optimization_params 获取转录文件: {segments_file}"
                )
                return segments_file

        # 从参数获取
        segments_file = get_param_with_fallback(
            "segments_file",
            input_data,
            self.context
        )
        if segments_file:
            logger.info(
                f"[{workflow_id}] 从参数/input_data获取转录文件: {segments_file}"
            )
            return segments_file

        # 从 faster_whisper.transcribe_audio 获取
        faster_whisper_stage = self.context.stages.get('faster_whisper.transcribe_audio')
        if faster_whisper_stage and faster_whisper_stage.output:
            segments_file = faster_whisper_stage.output.get('segments_file')
            if segments_file:
                logger.info(
                    f"[{workflow_id}] 从 faster_whisper.transcribe_audio "
                    f"获取转录文件: {segments_file}"
                )
                return segments_file

        return None

    def handle_error(self, error: Exception) -> None:
        """
        处理错误。

        记录错误指标。
        """
        # 记录错误指标
        if self.provider and self.start_time:
            metrics_collector.record_request(
                provider=self.provider,
                status='failure',
                duration=time.time() - self.start_time
            )

        super().handle_error(error)

    def get_cache_key_fields(self) -> List[str]:
        """
        返回用于生成缓存键的字段列表。

        字幕优化结果依赖于转录文件和优化配置。
        """
        return ["segments_file", "subtitle_optimization"]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段列表。

        字幕优化的核心输出是 optimized_file_path。
        """
        return ["optimized_file_path"]

    def format_output(self, core_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化输出数据。

        处理跳过状态的特殊情况。
        """
        # 检查是否跳过
        if core_output.get("_skipped"):
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
