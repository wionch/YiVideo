"""
AI服务提供商适配器

支持多个AI服务提供商的统一接口：
- DeepSeek (deepseek-chat)
- Gemini (gemini-pro)
- 智谱AI (glm-4)
- 火山引擎 (doubao-pro)
"""

import os
import json
import time
import asyncio
import aiohttp
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from services.common.logger import get_logger

logger = get_logger(__name__)


@dataclass
class AIResponse:
    """AI响应数据结构"""
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None
    finish_reason: Optional[str] = None


class AIProviderBase(ABC):
    """AI服务提供商抽象基类"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化AI提供商

        Args:
            config: 提供商配置信息
        """
        self.config = config
        self.api_key = self._get_api_key()
        self.api_base_url = config.get('api_base_url', '')
        self.model = config.get('model', '')
        self.max_tokens = config.get('max_tokens', 128000)
        self.temperature = config.get('temperature', 0.1)
        self.enable_request_dump = False
        self.request_dump_tag = None

    def _get_api_key(self) -> str:
        """从环境变量或配置中获取API密钥"""
        api_key = self.config.get('api_key') or os.getenv(self.config.get('api_key_env', ''))

        if not api_key:
            raise ValueError(f"API密钥未配置，请设置环境变量 {self.config.get('api_key_env', '')}")

        return api_key

    def _is_sensitive_key(self, key: str) -> bool:
        lowered = key.lower()
        return lowered in {"api_key", "apikey", "token", "authorization", "secret", "password", "key"}

    def _mask_sensitive_data(self, data: Any) -> Any:
        if isinstance(data, dict):
            masked = {}
            for k, v in data.items():
                if self._is_sensitive_key(str(k)):
                    masked[k] = "***"
                else:
                    masked[k] = self._mask_sensitive_data(v)
            return masked
        if isinstance(data, list):
            return [self._mask_sensitive_data(item) for item in data]
        return data

    def _sanitize_url(self, url: str) -> str:
        try:
            parts = urlsplit(url)
            if not parts.query:
                return url
            query_items = []
            for k, v in parse_qsl(parts.query, keep_blank_values=True):
                if self._is_sensitive_key(k):
                    v = "***"
                query_items.append((k, v))
            sanitized_query = urlencode(query_items)
            return urlunsplit((parts.scheme, parts.netloc, parts.path, sanitized_query, parts.fragment))
        except Exception:
            return url

    def _dump_llm_request(self, url: str, headers: Dict[str, str], data: Dict[str, Any]) -> None:
        dump_dir = "/app/tmp/1"
        os.makedirs(dump_dir, exist_ok=True)
        timestamp_ms = int(time.time() * 1000)
        tag = ""
        if self.request_dump_tag:
            safe_tag = str(self.request_dump_tag).replace(os.sep, "_")
            tag = f"_{safe_tag}"
        filename = f"llm_request_{self.__class__.__name__}{tag}_{timestamp_ms}.json"
        request_path = os.path.join(dump_dir, filename)
        payload = {
            "provider": self.__class__.__name__,
            "model": self.model,
            "url": self._sanitize_url(url),
            "headers": self._mask_sensitive_data(headers),
            "data": self._mask_sensitive_data(data)
        }
        try:
            with open(request_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.exception("保存LLM请求数据失败: %s", request_path)

    @abstractmethod
    async def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        聊天补全接口

        Args:
            messages: 消息列表，格式为 [{"role": "system/user/assistant", "content": "..."}]
            **kwargs: 其他参数（max_tokens, temperature等）

        Returns:
            str: AI响应内容
        """
        pass

    @abstractmethod
    def get_provider_info(self) -> Dict[str, Any]:
        """获取提供商信息"""
        pass

    async def _make_http_request(self, url: str, headers: Dict[str, str],
                                data: Dict[str, Any], timeout: int = 300) -> Dict[str, Any]:
        """
        通用的HTTP请求方法

        Args:
            url: 请求URL
            headers: 请求头
            data: 请求数据
            timeout: 超时时间（秒）

        Returns:
            Dict: 响应数据
        """
        try:
            if self.enable_request_dump:
                self._dump_llm_request(url, headers, data)
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                async with session.post(url, headers=headers, json=data) as response:
                    response.raise_for_status()
                    return await response.json()

        except aiohttp.ClientError as e:
            logger.error(f"HTTP请求失败: {e}")
            raise
        except asyncio.TimeoutError:
            logger.error("HTTP请求超时")
            raise


class DeepSeekProvider(AIProviderBase):
    """DeepSeek AI服务提供商"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_base_url = self.api_base_url or "https://api.deepseek.com/chat/completions"
        self.model = self.model or "deepseek-chat"

    async def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """DeepSeek聊天补全"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": messages,
            "max_tokens": kwargs.get('max_tokens', self.max_tokens),
            "temperature": kwargs.get('temperature', self.temperature),
            "stream": False
        }

        try:
            logger.debug(f"调用DeepSeek API: {self.model}")
            logger.debug(f"url: {self.api_base_url}")
            # 安全：掩码敏感信息
            safe_headers = {k: '***' if 'authorization' in k.lower() or 'apikey' in k.lower() else v
                           for k, v in headers.items()}
            logger.debug(f"headers: {safe_headers}")
            logger.debug(f"data: {data}")
            response = await self._make_http_request(self.api_base_url, headers, data)


            content = response['choices'][0]['message']['content']
            logger.debug("DeepSeek API调用成功")
            return content

        except aiohttp.ClientResponseError as e:
            logger.error(f"DeepSeek API HTTP错误: {e.status} - {e.message}")

            # 针对特定错误类型提供更详细的诊断
            if e.status == 400:
                logger.error("400 Bad Request 错误可能原因:")
                logger.error("- 请求体过大：输入文本可能超过了单次请求的实际限制")
                logger.error("- 参数格式错误：请求参数可能不符合API规范")
                logger.error("- Token限制：输入token可能超出了模型的实际处理能力")
                logger.error(f"- 请求数据大小: {len(str(data))} 字符")

                # 检查输入文本长度并给出建议
                input_text_length = len(str(data.get('messages', [{}])[-1].get('content', '')))
                estimated_tokens = input_text_length * 1.5  # 粗略估算中文token

                logger.error(f"- 输入文本长度: {input_text_length} 字符")
                logger.error(f"- 估算token数: {estimated_tokens} tokens")
                logger.error("- 建议: 减小输入文本长度或启用分批处理")

            raise

        except Exception as e:
            logger.error(f"DeepSeek API调用失败: {e}")
            raise

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "DeepSeek",
            "model": self.model,
            "api_base_url": self.api_base_url,
            "supported_features": ["chat_completion", "text_correction"],
            "language_support": ["中文", "英文"],
            "max_tokens": self.max_tokens
        }


class GeminiProvider(AIProviderBase):
    """Google Gemini AI服务提供商"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_base_url = self.api_base_url or "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
        self.model = self.model or "gemini-pro"

    async def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Gemini聊天补全"""
        # 将消息格式转换为Gemini格式
        contents = []
        system_prompt = ""

        for message in messages:
            if message['role'] == 'system':
                system_prompt = message['content']
            else:
                contents.append({
                    "role": "user" if message['role'] == 'user' else "model",
                    "parts": [{"text": message['content']}]
                })

        # 如果有系统提示词，添加到第一条用户消息
        if system_prompt and contents:
            contents[0]["parts"][0]["text"] = f"{system_prompt}\n\n{contents[0]['parts'][0]['text']}"

        headers = {
            "Content-Type": "application/json"
        }

        data = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": kwargs.get('max_tokens', self.max_tokens),
                "temperature": kwargs.get('temperature', self.temperature)
            }
        }

        try:
            # Gemini API需要在URL中包含API密钥
            url = f"{self.api_base_url}?key={self.api_key}"
            logger.debug(f"调用Gemini API: {self.model}")
            # 安全：掩码URL中的API密钥
            safe_url = f"{self.api_base_url}?key=***"
            logger.debug(f"url: {safe_url}")

            response = await self._make_http_request(url, headers, data)

            content = response['candidates'][0]['content']['parts'][0]['text']
            logger.debug("Gemini API调用成功")
            return content

        except Exception as e:
            logger.error(f"Gemini API调用失败: {e}")
            raise

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "Google Gemini",
            "model": self.model,
            "api_base_url": self.api_base_url,
            "supported_features": ["chat_completion", "text_correction"],
            "language_support": ["中文", "英文", "多语言"],
            "max_tokens": self.max_tokens
        }


class ZhipuProvider(AIProviderBase):
    """智谱AI服务提供商"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_base_url = self.api_base_url or "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        self.model = self.model or "glm-4"

    async def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """智谱AI聊天补全"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": messages,
            "max_tokens": kwargs.get('max_tokens', self.max_tokens),
            "temperature": kwargs.get('temperature', self.temperature)
        }

        try:
            logger.debug(f"调用智谱AI API: {self.model}")
            response = await self._make_http_request(self.api_base_url, headers, data)

            content = response['choices'][0]['message']['content']
            logger.debug("智谱AI API调用成功")
            return content

        except Exception as e:
            logger.error(f"智谱AI API调用失败: {e}")
            raise

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "智谱AI",
            "model": self.model,
            "api_base_url": self.api_base_url,
            "supported_features": ["chat_completion", "text_correction"],
            "language_support": ["中文", "英文"],
            "max_tokens": self.max_tokens
        }


class VolcengineProvider(AIProviderBase):
    """火山引擎（字节跳动）AI服务提供商"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_base_url = self.api_base_url or "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
        self.model = self.model or "doubao-pro-32k"
        self.endpoint_id = config.get('endpoint_id', '')

    async def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """火山引擎聊天补全"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # 如果有endpoint_id，添加到模型名中
        model_name = f"{self.endpoint_id}@{self.model}" if self.endpoint_id else self.model

        data = {
            "model": model_name,
            "messages": messages,
            "max_tokens": kwargs.get('max_tokens', self.max_tokens),
            "temperature": kwargs.get('temperature', self.temperature)
        }

        try:
            logger.debug(f"调用火山引擎API: {model_name}")
            response = await self._make_http_request(self.api_base_url, headers, data)

            content = response['choices'][0]['message']['content']
            logger.debug("火山引擎API调用成功")
            return content

        except Exception as e:
            logger.error(f"火山引擎API调用失败: {e}")
            raise

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "火山引擎",
            "model": self.model,
            "endpoint_id": self.endpoint_id,
            "api_base_url": self.api_base_url,
            "supported_features": ["chat_completion", "text_correction"],
            "language_support": ["中文", "英文", "多语言"],
            "max_tokens": self.max_tokens
        }


class OpenAICompatibleProvider(AIProviderBase):
    """通用OpenAI兼容AI服务提供商"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        # 优先使用配置中的api_base_url，否则使用默认值
        self.api_base_url = self.api_base_url or "https://np.wionch.top/v1/chat/completions"
        self.model = self.model or "流式抗截断/gemini-2.5-pro" # 提供一个默认模型
        logger.info(f"OpenAICompatibleProvider: {self.model}")

    async def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """OpenAI兼容聊天补全"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": messages,
            "max_tokens": kwargs.get('max_tokens', self.max_tokens),
            "temperature": kwargs.get('temperature', self.temperature),
            "stream": False
        }

        try:
            logger.debug(f"调用OpenAI兼容API: {self.model}")
            logger.debug(f"URL: {self.api_base_url}")
            # 安全：掩码敏感信息
            safe_headers = {k: '***' if 'authorization' in k.lower() or 'apikey' in k.lower() else v
                           for k, v in headers.items()}
            logger.debug(f"headers: {safe_headers}")
            response = await self._make_http_request(self.api_base_url, headers, data)

            content = response['choices'][0]['message']['content']
            logger.debug("OpenAI兼容API调用成功")
            return content

        except aiohttp.ClientResponseError as e:
            logger.error(f"OpenAI兼容API HTTP错误: {e.status} - {e.message}")
            if e.status == 401:
                logger.error("401 Unauthorized 错误: API密钥无效或未提供。请检查 `OpenAI_Compatible_KEY` 环境变量。")
            raise

        except Exception as e:
            logger.error(f"OpenAI兼容API调用失败: {e}")
            raise

    def get_provider_info(self) -> Dict[str, Any]:
        return {
            "name": "OpenAI Compatible",
            "model": self.model,
            "api_base_url": self.api_base_url,
            "supported_features": ["chat_completion", "text_correction"],
            "language_support": ["多语言"],
            "max_tokens": self.max_tokens
        }


class AIProviderFactory:
    """AI服务提供商工厂类"""

    _providers = {
        'deepseek': DeepSeekProvider,
        'gemini': GeminiProvider,
        'zhipu': ZhipuProvider,
        'volcengine': VolcengineProvider,
        'openai_compatible': OpenAICompatibleProvider
    }

    @classmethod
    def create_provider(cls, provider_name: str, config: Dict[str, Any]) -> AIProviderBase:
        """
        创建AI服务提供商实例

        Args:
            provider_name: 提供商名称
            config: 提供商配置

        Returns:
            AIProviderBase: AI服务提供商实例

        Raises:
            ValueError: 不支持的提供商名称
        """
        if provider_name not in cls._providers:
            raise ValueError(f"不支持的AI服务提供商: {provider_name}，支持的提供商: {list(cls._providers.keys())}")

        provider_class = cls._providers[provider_name]
        return provider_class(config)

    @classmethod
    def get_supported_providers(cls) -> List[str]:
        """获取支持的AI服务提供商列表"""
        return list(cls._providers.keys())

    @classmethod
    def get_provider_info(cls, provider_name: str) -> Dict[str, Any]:
        """
        获取指定AI服务提供商的信息

        Args:
            provider_name: 提供商名称

        Returns:
            Dict: 提供商信息
        """
        if provider_name not in cls._providers:
            raise ValueError(f"不支持的AI服务提供商: {provider_name}")

        # 创建一个临时实例来获取信息
        try:
            temp_config = {
                'api_key': 'temp',
                'api_key_env': 'TEMP_KEY'
            }
            provider = cls.create_provider(provider_name, temp_config)
            return provider.get_provider_info()
        except Exception as e:
            logger.warning(f"获取提供商信息失败: {e}")
            return {
                "name": provider_name,
                "error": "无法获取详细信息"
            }

    @classmethod
    def register_provider(cls, name: str, provider_class: type):
        """
        注册新的AI服务提供商

        Args:
            name: 提供商名称
            provider_class: 提供商类
        """
        cls._providers[name] = provider_class
        logger.info(f"注册AI服务提供商: {name}")


# 便捷函数
async def get_ai_response(provider_name: str, messages: List[Dict[str, str]],
                         config: Optional[Dict[str, Any]] = None) -> str:
    """
    便捷函数：获取AI响应

    Args:
        provider_name: 提供商名称
        messages: 消息列表
        config: 额外配置

    Returns:
        str: AI响应内容
    """
    factory = AIProviderFactory()
    provider = factory.create_provider(provider_name, config or {})
    return await provider.chat_completion(messages)
