"""
纯文本字幕优化器

将字幕片段合并为全文文本，调用 AI 服务进行纠错优化。
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from services.common.config_loader import get_config

from .ai_providers import AIProviderFactory
from .prompt_loader import PromptLoader
from .ai_providers_config import AIProvidersConfig
from .subtitle_extractor import SubtitleExtractor

logger = logging.getLogger(__name__)


class SubtitleTextOptimizer:
    """纯文本字幕优化器"""

    def __init__(
        self,
        provider: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        dump_tag: Optional[str] = None
    ):
        config_data = config or get_config().get("ai_providers", {})
        self.config = AIProvidersConfig(config_data)
        self.provider_name = provider or self.config.default_provider
        self.prompt_loader = PromptLoader()
        self.extractor = SubtitleExtractor()
        self.dump_tag = dump_tag

    def optimize_text(
        self,
        segments: Optional[List[Dict[str, Any]]] = None,
        segments_file: Optional[str] = None,
        prompt_file_path: Optional[str] = None
    ) -> Dict[str, Any]:
        start_time = time.time()

        try:
            if segments is None:
                if not segments_file:
                    return {"success": False, "error": "缺少必需参数: segments 或 segments_file"}
                segments = self.extractor.extract_subtitles(segments_file)

            merged_text = self._merge_segments_text(segments)
            if not merged_text:
                return {"success": False, "error": "字幕文本为空"}

            system_prompt = self.prompt_loader.load_prompt(prompt_file_path)
            optimized_text = self._call_ai(system_prompt, merged_text)

            return {
                "success": True,
                "optimized_text": optimized_text,
                "stats": {
                    "provider": self.provider_name,
                    "segments_count": len(segments),
                    "input_chars": len(merged_text),
                    "output_chars": len(optimized_text),
                    "processing_time": round(time.time() - start_time, 2)
                }
            }
        except Exception as e:
            logger.error(f"纯文本字幕优化失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _merge_segments_text(self, segments: List[Dict[str, Any]]) -> str:
        texts = [str(segment.get("text", "")).strip() for segment in segments]
        return " ".join(texts)

    def _call_ai(self, system_prompt: str, user_text: str) -> str:
        provider_config = self.config.get_provider_config(self.provider_name)
        provider = AIProviderFactory.create_provider(self.provider_name, provider_config)
        provider.enable_request_dump = True
        provider.request_dump_tag = self.dump_tag
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ]
        return asyncio.run(
            provider.chat_completion(
                messages,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature
            )
        )
