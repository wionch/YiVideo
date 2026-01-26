"""
逐行翻译装词模块

按字幕分段逐行提交给大模型翻译，要求行数一致并控制字符预算。
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from services.common.config_loader import get_config

from .prompt_loader import PromptLoader
from .subtitle_correction_config import SubtitleCorrectionConfig
from .subtitle_text_optimizer import SubtitleTextOptimizer

logger = logging.getLogger(__name__)


class SubtitleLineTranslator:
    """逐行翻译装词执行器"""

    def __init__(
        self,
        provider: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        dump_tag: Optional[str] = None
    ):
        config_data = config or get_config().get("subtitle_correction", {})
        self.config = SubtitleCorrectionConfig(config_data)
        self.provider_name = provider or self.config.default_provider
        self.prompt_loader = PromptLoader()
        self.dump_tag = dump_tag
        self._config_data = config_data

    def translate_lines(
        self,
        segments: Optional[List[Dict[str, Any]]] = None,
        segments_file: Optional[str] = None,
        target_language: Optional[str] = None,
        source_language: Optional[str] = None,
        prompt_file_path: Optional[str] = None,
        provider: Optional[str] = None,
        cps_limit: int = 18,
        cpl_limit: int = 42,
        max_lines: int = 1,
        max_retries: Optional[int] = None,
        ai_call: Optional[Callable[[str, str], str]] = None
    ) -> Dict[str, Any]:
        if not target_language:
            return {"success": False, "error": "缺少必需参数: target_language"}

        if segments is None:
            if not segments_file:
                return {"success": False, "error": "缺少必需参数: segments 或 segments_file"}
            segments = self._load_segments_from_file(segments_file)

        if not segments:
            return {"success": False, "error": "字幕片段为空"}

        prompt_path = prompt_file_path or "/app/config/system_prompt/subtitle_translation_fitting.md"
        system_prompt = self.prompt_loader.load_prompt(prompt_path)

        retry_limit = max_retries if max_retries is not None else self.config.max_retry_attempts
        retry_limit = max(1, int(retry_limit))

        budgets = self._build_budgets(segments, cps_limit, cpl_limit, max_lines)
        user_prompt = self._build_user_prompt(
            segments,
            budgets,
            target_language,
            source_language,
            cps_limit,
            cpl_limit,
            max_lines
        )

        empty_allowed = self._should_allow_empty_output(budgets)

        last_error = ""
        last_output = ""
        for attempt in range(1, retry_limit + 1):
            output_text = self._call_ai(
                system_prompt,
                user_prompt,
                provider=provider,
                ai_call=ai_call
            ).strip()
            last_output = output_text
            if not output_text:
                if empty_allowed:
                    lines = ["" for _ in budgets]
                    translated_segments = self._apply_translated_lines(segments, lines)
                    return {
                        "success": True,
                        "translated_lines": lines,
                        "translated_segments": translated_segments
                    }
                last_error = "翻译结果为空"
                logger.warning("逐行翻译输出为空，尝试重试: %s/%s", attempt, retry_limit)
                continue

            lines = [line.rstrip("\r") for line in output_text.splitlines()]
            error = self._validate_output_lines(lines, budgets)
            if error:
                last_error = error
                logger.warning("逐行翻译校验失败: %s, 尝试重试: %s/%s", error, attempt, retry_limit)
                continue

            translated_segments = self._apply_translated_lines(segments, lines)
            return {
                "success": True,
                "translated_lines": lines,
                "translated_segments": translated_segments
            }

        return {
            "success": False,
            "error": last_error or "逐行翻译失败",
            "raw_output": last_output
        }

    def _call_ai(
        self,
        system_prompt: str,
        user_prompt: str,
        provider: Optional[str] = None,
        ai_call: Optional[Callable[[str, str], str]] = None
    ) -> str:
        if ai_call:
            return ai_call(system_prompt, user_prompt)

        optimizer = SubtitleTextOptimizer(
            provider=provider or self.provider_name,
            config=self._config_data,
            dump_tag=self.dump_tag
        )
        return optimizer._call_ai(system_prompt, user_prompt)

    def _build_budgets(
        self,
        segments: List[Dict[str, Any]],
        cps_limit: int,
        cpl_limit: int,
        max_lines: int
    ) -> List[int]:
        line_cap = max(1, int(cpl_limit))
        max_chars = line_cap * max(1, int(max_lines))
        budgets: List[int] = []
        for segment in segments:
            start = float(segment.get("start", 0.0))
            end = float(segment.get("end", 0.0))
            duration = max(0.0, end - start)
            budget = int(duration * max(1, int(cps_limit)))
            budgets.append(min(budget, max_chars))
        return budgets

    def _build_user_prompt(
        self,
        segments: List[Dict[str, Any]],
        budgets: List[int],
        target_language: str,
        source_language: Optional[str],
        cps_limit: int,
        cpl_limit: int,
        max_lines: int
    ) -> str:
        source_language = source_language or "自动识别"
        lines: List[str] = []
        for index, (segment, budget) in enumerate(zip(segments, budgets), start=1):
            start = float(segment.get("start", 0.0))
            end = float(segment.get("end", 0.0))
            duration = max(0.0, end - start)
            text = str(segment.get("text", "")).strip()
            lines.append(f"{index} | {duration:.2f} | {budget} | {text}")

        line_items = "\n".join(lines)
        return (
            "任务：字幕逐行翻译装词（行对行回填）\n"
            f"目标语言: {target_language} （可为 ISO 码或语言名称）\n"
            f"源语言: {source_language}\n"
            f"CPS 上限: {cps_limit}\n"
            f"CPL 上限: {cpl_limit}\n"
            f"行数上限: {max_lines}\n"
            "字符预算说明：每行字符预算包含空格与标点；行内禁止换行符。\n\n"
            "输出要求：\n"
            "- 仅输出翻译后的字幕文本行\n"
            "- 行数必须与输入一致\n"
            "- 不要输出序号、时长、预算或任何说明\n\n"
            "逐行字幕（格式: 序号 | 时长秒 | 字符预算 | 原文）:\n"
            f"{line_items}"
        )

    def _validate_output_lines(self, lines: List[str], budgets: List[int]) -> Optional[str]:
        if len(lines) != len(budgets):
            return "行数不一致"

        for index, (line, budget) in enumerate(zip(lines, budgets), start=1):
            text = line.strip()
            if budget <= 0:
                if text:
                    return f"第 {index} 行超出字符预算"
                continue
            if not text:
                return f"第 {index} 行为空"
            if "\n" in text:
                return f"第 {index} 行包含换行符"
            if len(text) > budget:
                return f"第 {index} 行超出字符预算"
        return None

    def _apply_translated_lines(
        self,
        segments: List[Dict[str, Any]],
        lines: List[str]
    ) -> List[Dict[str, Any]]:
        translated_segments: List[Dict[str, Any]] = []
        for segment, line in zip(segments, lines):
            updated = segment.copy()
            updated["text"] = line.strip()
            translated_segments.append(updated)
        return translated_segments

    def _should_allow_empty_output(self, budgets: List[int]) -> bool:
        return any(budget <= 0 for budget in budgets)

    def _load_segments_from_file(self, segments_file: str) -> List[Dict[str, Any]]:
        import json
        import os

        if not segments_file or not os.path.exists(segments_file):
            return []
        try:
            with open(segments_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "segments" in data:
                return data["segments"]
        except Exception as e:
            logger.error("加载 segments 文件失败: %s", e)
        return []
