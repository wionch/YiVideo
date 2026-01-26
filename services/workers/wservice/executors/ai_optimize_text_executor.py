"""
WService 纯文本 AI 优化执行器。
"""

import logging
import os
from typing import Any, Dict, List

from services.common.base_node_executor import BaseNodeExecutor
from services.common.path_builder import build_node_output_path, ensure_directory
from services.common.subtitle.subtitle_text_optimizer import SubtitleTextOptimizer

logger = logging.getLogger(__name__)


class WServiceAIOptimizeTextExecutor(BaseNodeExecutor):
    """
    纯文本 AI 优化执行器。

    输入参数:
        - segments_file (str): 转录片段文件路径
    """

    def validate_input(self) -> None:
        input_data = self.get_input_data()
        segments_file = input_data.get("segments_file")
        if not segments_file:
            raise ValueError("缺少必需参数: segments_file (转录片段文件路径)")

    def execute_core_logic(self) -> Dict[str, Any]:
        workflow_id = self.context.workflow_id
        input_data = self.get_input_data()

        segments_file = input_data.get("segments_file")
        if not os.path.exists(segments_file):
            raise FileNotFoundError(f"未找到转录文件: {segments_file}")

        provider = input_data.get("provider")
        prompt_file_path = input_data.get("prompt_file_path")

        optimizer = SubtitleTextOptimizer(provider=provider, dump_tag=workflow_id or "unknown")
        result = optimizer.optimize_text(
            segments_file=segments_file,
            prompt_file_path=prompt_file_path
        )

        if not result.get("success"):
            raise RuntimeError(f"纯文本纠错失败: {result.get('error', '未知错误')}")

        optimized_text = result.get("optimized_text", "")

        base_name = os.path.splitext(os.path.basename(segments_file))[0] or "segments"
        output_path = build_node_output_path(
            task_id=workflow_id,
            node_name=self.stage_name,
            file_type="data",
            filename=f"{base_name}_optimized_text.txt"
        )
        ensure_directory(output_path)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(optimized_text)

        logger.info(f"[{workflow_id}] 纯文本纠错完成: {output_path}")

        return {
            "optimized_text_file": output_path
        }

    def get_cache_key_fields(self) -> List[str]:
        return ["segments_file", "provider", "prompt_file_path"]
