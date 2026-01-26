"""
WService 翻译装词执行器。
"""

import json
import logging
import os
from typing import Any, Dict, List

from services.common.base_node_executor import BaseNodeExecutor
from services.common.path_builder import build_node_output_path, ensure_directory
from services.common.subtitle.subtitle_line_translator import SubtitleLineTranslator

logger = logging.getLogger(__name__)


class WServiceTranslateSubtitlesExecutor(BaseNodeExecutor):
    """
    翻译装词执行器。

    输入参数:
        - segments_file (str): 字幕片段文件路径
        - target_language (str): 目标语言
        - source_language (str, 可选): 源语言
        - provider (str, 可选): 模型提供商
        - prompt_file_path (str, 可选): 系统提示词路径
        - cps_limit (int, 可选): 阅读速度上限
        - cpl_limit (int, 可选): 单行字符上限
        - max_lines (int, 可选): 最大行数
        - max_retries (int, 可选): 最大重试次数
    """

    def validate_input(self) -> None:
        input_data = self.get_input_data()
        segments_file = input_data.get("segments_file")
        target_language = input_data.get("target_language")
        if not segments_file:
            raise ValueError("缺少必需参数: segments_file (字幕片段文件路径)")
        if not target_language:
            raise ValueError("缺少必需参数: target_language (目标语言)")

    def execute_core_logic(self) -> Dict[str, Any]:
        workflow_id = self.context.workflow_id
        input_data = self.get_input_data()

        segments_file = input_data.get("segments_file")
        if not os.path.exists(segments_file):
            raise FileNotFoundError(f"未找到字幕文件: {segments_file}")

        target_language = input_data.get("target_language")
        source_language = input_data.get("source_language")
        provider = input_data.get("provider")
        prompt_file_path = input_data.get("prompt_file_path")
        cps_limit = input_data.get("cps_limit", 18)
        cpl_limit = input_data.get("cpl_limit", 42)
        max_lines = input_data.get("max_lines", 2)
        max_retries = input_data.get("max_retries")

        translator = SubtitleLineTranslator(
            provider=provider,
            dump_tag=workflow_id or "unknown"
        )
        result = translator.translate_lines(
            segments_file=segments_file,
            target_language=target_language,
            source_language=source_language,
            prompt_file_path=prompt_file_path,
            provider=provider,
            cps_limit=cps_limit,
            cpl_limit=cpl_limit,
            max_lines=max_lines,
            max_retries=max_retries,
        )

        if not result.get("success"):
            raise RuntimeError(f"翻译装词失败: {result.get('error', '未知错误')}")

        translated_segments = result.get("translated_segments", [])
        if not translated_segments:
            raise RuntimeError("翻译装词失败: 返回字幕为空")

        base_name = os.path.splitext(os.path.basename(segments_file))[0] or "segments"
        output_path = build_node_output_path(
            task_id=workflow_id,
            node_name=self.stage_name,
            file_type="data",
            filename=f"{base_name}_translated_segments.json"
        )
        ensure_directory(output_path)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(translated_segments, f, ensure_ascii=False, indent=2)

        logger.info(f"[{workflow_id}] 翻译装词完成: {output_path}")

        return {"translated_segments_file": output_path}

    def get_cache_key_fields(self) -> List[str]:
        return [
            "segments_file",
            "target_language",
            "source_language",
            "provider",
            "prompt_file_path",
            "cps_limit",
            "cpl_limit",
            "max_lines",
            "max_retries",
        ]
