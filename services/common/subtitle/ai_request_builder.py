"""
AI优化请求构建器

构建发送给AI模型的请求数据，包括系统提示和字幕内容。

作者: Claude Code
日期: 2025-11-06
版本: v1.0.0
"""

import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class AIRequestBuilder:
    """AI优化请求构建器

    构建符合AI模型API要求的请求格式。
    """

    def __init__(self):
        """初始化请求构建器"""
        pass

    def build_request(self,
                     subtitles: List[Dict[str, Any]],
                     system_prompt: str,
                     provider: str = "deepseek") -> Dict[str, Any]:
        """构建AI API请求

        Args:
            subtitles: 字幕数组
            system_prompt: 系统提示词
            provider: AI提供商

        Returns:
            符合AI API格式的请求字典
        """
        logger.info(f"构建AI请求 - 提供商: {provider}, 字幕数: {len(subtitles)}")

        # 根据提供商构建不同的请求格式
        if provider == "deepseek" or provider == "openai_compatible":
            return self._build_openai_format(subtitles, system_prompt)
        elif provider == "gemini":
            return self._build_gemini_format(subtitles, system_prompt)
        elif provider == "zhipu" or provider == "volcengine":
            return self._build_chatglm_format(subtitles, system_prompt)
        else:
            logger.warning(f"未知提供商: {provider}，使用默认格式")
            return self._build_openai_format(subtitles, system_prompt)

    def _build_openai_format(self,
                           subtitles: List[Dict[str, Any]],
                           system_prompt: str) -> Dict[str, Any]:
        """构建OpenAI兼容格式

        Args:
            subtitles: 字幕数组
            system_prompt: 系统提示词

        Returns:
            OpenAI格式的请求
        """
        # 格式化字幕内容
        subtitle_text = json.dumps(subtitles, ensure_ascii=False, indent=2)

        messages = [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": f"请优化以下字幕内容:\n{subtitle_text}\n\n请返回JSON格式的优化指令。"
            }
        ]

        request = {
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 4000,
            "response_format": {"type": "json_object"}
        }

        return request

    def _build_gemini_format(self,
                           subtitles: List[Dict[str, Any]],
                           system_prompt: str) -> Dict[str, Any]:
        """构建Gemini格式

        Args:
            subtitles: 字幕数组
            system_prompt: 系统提示词

        Returns:
            Gemini格式的请求
        """
        subtitle_text = json.dumps(subtitles, ensure_ascii=False, indent=2)

        contents = [
            {
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n{subtitle_text}"}]
            }
        ]

        generation_config = {
            "temperature": 0.3,
            "maxOutputTokens": 4000,
            "response_mime_type": "application/json"
        }

        request = {
            "contents": contents,
            "generationConfig": generation_config
        }

        return request

    def _build_chatglm_format(self,
                            subtitles: List[Dict[str, Any]],
                            system_prompt: str) -> Dict[str, Any]:
        """构建ChatGLM格式

        Args:
            subtitles: 字幕数组
            system_prompt: 系统提示词

        Returns:
            ChatGLM格式的请求
        """
        subtitle_text = json.dumps(subtitles, ensure_ascii=False, indent=2)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请优化以下字幕内容:\n{subtitle_text}\n\n请返回JSON格式的优化指令。"}
        ]

        request = {
            "model": "glm-4",
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 4000
        }

        return request

    def format_subtitle_content(self, subtitles: List[Dict[str, Any]]) -> str:
        """格式化字幕内容为可读文本

        Args:
            subtitles: 字幕数组

        Returns:
            格式化的文本内容
        """
        lines = []
        for subtitle in subtitles:
            lines.append(f"[{subtitle['id']}] {subtitle['text']}")

        return "\n".join(lines)