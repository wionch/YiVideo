"""LLM Provider Adapters

提供统一的LLM API适配器，支持多种AI服务提供商。

Classes:
    LLMProvider: LLM提供商抽象基类
    GeminiProvider: Google Gemini API适配器
    DeepSeekProvider: DeepSeek API适配器
    LLMProviderFactory: LLM提供商工厂类
"""

import os
import json
import time
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit

import aiohttp


class LLMProvider(ABC):
    """LLM提供商抽象基类

    定义统一的LLM调用接口，所有具体提供商必须继承此类。

    Attributes:
        config: 提供商配置字典
        api_key: API密钥
        model: 模型名称
        max_tokens: 最大token数
        temperature: 温度参数
    """

    def __init__(self, config: Dict[str, Any]):
        """初始化LLM提供商

        Args:
            config: 提供商配置，包含api_key, model, max_tokens等
        """
        self.config = config
        self.api_key = self._get_api_key()
        self.model = config.get("model", "")
        self.max_tokens = config.get("max_tokens", 4096)
        self.temperature = config.get("temperature", 0.1)
        self.enable_request_dump = config.get("enable_request_dump", False)
        self.request_dump_tag = config.get("request_dump_tag")

    def _get_api_key(self) -> str:
        """从环境变量或配置中获取API密钥

        Returns:
            API密钥字符串

        Raises:
            ValueError: 当API密钥未配置时
        """
        api_key = self.config.get("api_key") or os.getenv(
            self.config.get("api_key_env", "")
        )

        if not api_key:
            raise ValueError(
                f"API密钥未配置，请设置环境变量 {self.config.get('api_key_env', '')}"
            )

        return api_key

    def _is_sensitive_key(self, key: str) -> bool:
        """检查是否为敏感字段

        Args:
            key: 字段名

        Returns:
            是否为敏感字段
        """
        lowered = key.lower()
        return lowered in {"api_key", "apikey", "token", "authorization", "secret", "password", "key"}

    def _mask_sensitive_data(self, data: Any) -> Any:
        """脱敏敏感数据

        Args:
            data: 原始数据

        Returns:
            脱敏后的数据
        """
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
        """清理URL中的敏感信息

        Args:
            url: 原始URL

        Returns:
            清理后的URL
        """
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

    def _dump_request(self, url: str, headers: Dict[str, str], data: Dict[str, Any]) -> None:
        """转储请求数据到文件（用于调试）

        Args:
            url: 请求URL
            headers: 请求头
            data: 请求数据
        """
        dump_dir = "/app/tmp/llm_requests"
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
            "data": self._mask_sensitive_data(data),
        }
        try:
            with open(request_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # 忽略转储失败

    async def _make_http_request(
        self, url: str, headers: Dict[str, str], data: Dict[str, Any], timeout: int = 300
    ) -> Dict[str, Any]:
        """发送HTTP POST请求

        Args:
            url: 请求URL
            headers: 请求头
            data: 请求数据
            timeout: 超时时间（秒）

        Returns:
            响应数据字典

        Raises:
            aiohttp.ClientError: HTTP请求失败
            asyncio.TimeoutError: 请求超时
        """
        if self.enable_request_dump:
            self._dump_request(url, headers, data)

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as session:
            async with session.post(url, headers=headers, json=data) as response:
                response.raise_for_status()
                return await response.json()

    @abstractmethod
    async def call(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """调用LLM

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）
            **kwargs: 额外参数（max_tokens, temperature等）

        Returns:
            LLM响应文本
        """
        pass

    @abstractmethod
    def get_provider_info(self) -> Dict[str, Any]:
        """获取提供商信息

        Returns:
            提供商信息字典
        """
        pass


class GeminiProvider(LLMProvider):
    """Google Gemini API适配器

    支持Google Gemini系列模型的API调用。

    Attributes:
        api_base_url: Gemini API基础URL
    """

    DEFAULT_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
    DEFAULT_MODEL = "gemini-pro"

    def __init__(self, config: Dict[str, Any]):
        """初始化Gemini提供商

        Args:
            config: 提供商配置
        """
        super().__init__(config)
        self.api_base_url = config.get("api_base_url", self.DEFAULT_API_URL)
        self.model = self.model or self.DEFAULT_MODEL

        # 更新URL中的模型名称
        if self.model != self.DEFAULT_MODEL and self.DEFAULT_MODEL in self.api_base_url:
            self.api_base_url = self.api_base_url.replace(self.DEFAULT_MODEL, self.model)

    async def call(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """调用Gemini API

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            **kwargs: 额外参数

        Returns:
            LLM响应文本

        Raises:
            aiohttp.ClientError: API调用失败
            ValueError: 响应解析失败
        """
        contents = []

        # 构建内容列表
        if system_prompt:
            # Gemini将system prompt作为用户消息的一部分
            contents.append({
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n{prompt}"}]
            })
        else:
            contents.append({
                "role": "user",
                "parts": [{"text": prompt}]
            })

        headers = {"Content-Type": "application/json"}

        data = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": kwargs.get("max_tokens", self.max_tokens),
                "temperature": kwargs.get("temperature", self.temperature),
            },
        }

        # Gemini API需要在URL中包含API密钥
        url = f"{self.api_base_url}?key={self.api_key}"

        response = await self._make_http_request(url, headers, data)

        try:
            content = response["candidates"][0]["content"]["parts"][0]["text"]
            return content
        except (KeyError, IndexError) as e:
            raise ValueError(f"解析Gemini响应失败: {e}")

    def get_provider_info(self) -> Dict[str, Any]:
        """获取提供商信息

        Returns:
            提供商信息字典
        """
        return {
            "name": "Google Gemini",
            "model": self.model,
            "api_base_url": self.api_base_url,
            "supported_features": ["text_completion", "chat_completion"],
            "language_support": ["中文", "英文", "多语言"],
            "max_tokens": self.max_tokens,
        }


class DeepSeekProvider(LLMProvider):
    """DeepSeek API适配器

    支持DeepSeek系列模型的API调用。

    Attributes:
        api_base_url: DeepSeek API基础URL
    """

    DEFAULT_API_URL = "https://api.deepseek.com/chat/completions"
    DEFAULT_MODEL = "deepseek-chat"

    def __init__(self, config: Dict[str, Any]):
        """初始化DeepSeek提供商

        Args:
            config: 提供商配置
        """
        super().__init__(config)
        self.api_base_url = config.get("api_base_url", self.DEFAULT_API_URL)
        self.model = self.model or self.DEFAULT_MODEL

    async def call(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """调用DeepSeek API

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            **kwargs: 额外参数

        Returns:
            LLM响应文本

        Raises:
            aiohttp.ClientError: API调用失败
            ValueError: 响应解析失败
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        data = {
            "model": self.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "stream": False,
        }

        response = await self._make_http_request(self.api_base_url, headers, data)

        try:
            content = response["choices"][0]["message"]["content"]
            return content
        except (KeyError, IndexError) as e:
            raise ValueError(f"解析DeepSeek响应失败: {e}")

    def get_provider_info(self) -> Dict[str, Any]:
        """获取提供商信息

        Returns:
            提供商信息字典
        """
        return {
            "name": "DeepSeek",
            "model": self.model,
            "api_base_url": self.api_base_url,
            "supported_features": ["text_completion", "chat_completion"],
            "language_support": ["中文", "英文"],
            "max_tokens": self.max_tokens,
        }


class LLMProviderFactory:
    """LLM提供商工厂类

    用于创建和管理LLM提供商实例。

    Class Attributes:
        _providers: 注册的提供商类字典
    """

    _providers: Dict[str, type] = {
        "gemini": GeminiProvider,
        "deepseek": DeepSeekProvider,
    }

    @classmethod
    def create_provider(cls, provider_name: str, config: Dict[str, Any]) -> LLMProvider:
        """创建LLM提供商实例

        Args:
            provider_name: 提供商名称（gemini/deepseek）
            config: 提供商配置

        Returns:
            LLMProvider实例

        Raises:
            ValueError: 不支持的提供商名称
        """
        provider_name = provider_name.lower()

        if provider_name not in cls._providers:
            supported = list(cls._providers.keys())
            raise ValueError(
                f"不支持的LLM提供商: {provider_name}，支持的提供商: {supported}"
            )

        provider_class = cls._providers[provider_name]
        return provider_class(config)

    @classmethod
    def get_supported_providers(cls) -> List[str]:
        """获取支持的提供商列表

        Returns:
            支持的提供商名称列表
        """
        return list(cls._providers.keys())

    @classmethod
    def get_provider_info(cls, provider_name: str) -> Dict[str, Any]:
        """获取指定提供商的信息

        Args:
            provider_name: 提供商名称

        Returns:
            提供商信息字典

        Raises:
            ValueError: 不支持的提供商名称
        """
        provider_name = provider_name.lower()

        if provider_name not in cls._providers:
            raise ValueError(f"不支持的LLM提供商: {provider_name}")

        # 创建临时实例获取信息
        try:
            temp_config = {
                "api_key": "temp",
                "api_key_env": "TEMP_KEY",
            }
            provider = cls.create_provider(provider_name, temp_config)
            return provider.get_provider_info()
        except Exception:
            return {
                "name": provider_name,
                "error": "无法获取详细信息",
            }

    @classmethod
    def register_provider(cls, name: str, provider_class: type) -> None:
        """注册新的LLM提供商

        Args:
            name: 提供商名称
            provider_class: 提供商类（必须继承LLMProvider）

        Raises:
            TypeError: 当provider_class不是LLMProvider的子类时
        """
        if not issubclass(provider_class, LLMProvider):
            raise TypeError("provider_class必须继承LLMProvider")

        cls._providers[name.lower()] = provider_class
