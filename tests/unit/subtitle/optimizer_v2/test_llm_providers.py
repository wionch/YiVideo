"""LLM Provider适配器测试

测试GeminiProvider、DeepSeekProvider和LLMProviderFactory的功能。
"""

import os
import json
import pytest
from unittest.mock import Mock, patch, AsyncMock

from services.common.subtitle.optimizer_v2.llm_providers import (
    LLMProvider,
    GeminiProvider,
    DeepSeekProvider,
    LLMProviderFactory,
)


class TestGeminiProvider:
    """GeminiProvider测试类"""

    def test_init_with_default_config(self):
        """测试使用默认配置初始化"""
        config = {
            "api_key": "test_key",
        }
        provider = GeminiProvider(config)

        assert provider.api_key == "test_key"
        assert provider.model == "gemini-pro"
        assert provider.max_tokens == 4096
        assert provider.temperature == 0.1
        assert provider.api_base_url == GeminiProvider.DEFAULT_API_URL

    def test_init_with_custom_config(self):
        """测试使用自定义配置初始化"""
        config = {
            "api_key": "custom_key",
            "model": "gemini-1.5-pro",
            "max_tokens": 8192,
            "temperature": 0.5,
            "api_base_url": "https://custom.gemini.api/v1/models",
        }
        provider = GeminiProvider(config)

        assert provider.api_key == "custom_key"
        assert provider.model == "gemini-1.5-pro"
        assert provider.max_tokens == 8192
        assert provider.temperature == 0.5
        assert provider.api_base_url == "https://custom.gemini.api/v1/models"

    def test_init_with_env_api_key(self):
        """测试从环境变量获取API密钥"""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "env_key"}):
            config = {"api_key_env": "GEMINI_API_KEY"}
            provider = GeminiProvider(config)
            assert provider.api_key == "env_key"

    def test_init_missing_api_key(self):
        """测试缺少API密钥时抛出异常"""
        config = {}
        with pytest.raises(ValueError, match="API密钥未配置"):
            GeminiProvider(config)

    @pytest.mark.asyncio
    async def test_call_success(self):
        """测试成功调用Gemini API"""
        config = {"api_key": "test_key"}
        provider = GeminiProvider(config)

        mock_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "优化后的字幕文本"}]
                    }
                }
            ]
        }

        with patch.object(provider, '_make_http_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await provider.call("请优化这段字幕")

        assert result == "优化后的字幕文本"

    @pytest.mark.asyncio
    async def test_call_with_system_prompt(self):
        """测试带系统提示词的调用"""
        config = {"api_key": "test_key"}
        provider = GeminiProvider(config)

        mock_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "响应内容"}]
                    }
                }
            ]
        }

        with patch.object(provider, '_make_http_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await provider.call(
                prompt="用户提示词",
                system_prompt="系统提示词"
            )

            # 验证请求数据
            call_args = mock_request.call_args
            assert call_args is not None
            _, headers, data = call_args[0]

            # 检查system prompt被合并到用户消息中
            contents = data["contents"]
            assert len(contents) == 1
            assert contents[0]["role"] == "user"
            assert "系统提示词" in contents[0]["parts"][0]["text"]
            assert "用户提示词" in contents[0]["parts"][0]["text"]

    @pytest.mark.asyncio
    async def test_call_with_custom_params(self):
        """测试使用自定义参数调用"""
        config = {"api_key": "test_key"}
        provider = GeminiProvider(config)

        mock_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "响应"}]
                    }
                }
            ]
        }

        with patch.object(provider, '_make_http_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            await provider.call(
                "测试",
                max_tokens=2048,
                temperature=0.8
            )

            call_args = mock_request.call_args
            _, headers, data = call_args[0]

            assert data["generationConfig"]["maxOutputTokens"] == 2048
            assert data["generationConfig"]["temperature"] == 0.8

    @pytest.mark.asyncio
    async def test_call_api_error(self):
        """测试API调用失败"""
        config = {"api_key": "test_key"}
        provider = GeminiProvider(config)

        with patch.object(provider, '_make_http_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = Exception("API Error")

            with pytest.raises(Exception, match="API Error"):
                await provider.call("测试")

    @pytest.mark.asyncio
    async def test_call_invalid_response(self):
        """测试无效响应格式"""
        config = {"api_key": "test_key"}
        provider = GeminiProvider(config)

        mock_response = {"invalid": "response"}

        with patch.object(provider, '_make_http_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(ValueError, match="解析Gemini响应失败"):
                await provider.call("测试")

    def test_get_provider_info(self):
        """测试获取提供商信息"""
        config = {
            "api_key": "test_key",
            "model": "gemini-1.5-pro",
            "max_tokens": 8192,
        }
        provider = GeminiProvider(config)
        info = provider.get_provider_info()

        assert info["name"] == "Google Gemini"
        assert info["model"] == "gemini-1.5-pro"
        assert info["max_tokens"] == 8192
        assert "supported_features" in info
        assert "language_support" in info


class TestDeepSeekProvider:
    """DeepSeekProvider测试类"""

    def test_init_with_default_config(self):
        """测试使用默认配置初始化"""
        config = {
            "api_key": "test_key",
        }
        provider = DeepSeekProvider(config)

        assert provider.api_key == "test_key"
        assert provider.model == "deepseek-chat"
        assert provider.max_tokens == 4096
        assert provider.temperature == 0.1
        assert provider.api_base_url == DeepSeekProvider.DEFAULT_API_URL

    def test_init_with_custom_config(self):
        """测试使用自定义配置初始化"""
        config = {
            "api_key": "custom_key",
            "model": "deepseek-coder",
            "max_tokens": 8192,
            "temperature": 0.5,
            "api_base_url": "https://custom.deepseek.api/v1",
        }
        provider = DeepSeekProvider(config)

        assert provider.api_key == "custom_key"
        assert provider.model == "deepseek-coder"
        assert provider.max_tokens == 8192
        assert provider.temperature == 0.5
        assert provider.api_base_url == "https://custom.deepseek.api/v1"

    def test_init_with_env_api_key(self):
        """测试从环境变量获取API密钥"""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "env_key"}):
            config = {"api_key_env": "DEEPSEEK_API_KEY"}
            provider = DeepSeekProvider(config)
            assert provider.api_key == "env_key"

    def test_init_missing_api_key(self):
        """测试缺少API密钥时抛出异常"""
        config = {}
        with pytest.raises(ValueError, match="API密钥未配置"):
            DeepSeekProvider(config)

    @pytest.mark.asyncio
    async def test_call_success(self):
        """测试成功调用DeepSeek API"""
        config = {"api_key": "test_key"}
        provider = DeepSeekProvider(config)

        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": "优化后的字幕文本"
                    }
                }
            ]
        }

        with patch.object(provider, '_make_http_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await provider.call("请优化这段字幕")

        assert result == "优化后的字幕文本"

    @pytest.mark.asyncio
    async def test_call_with_system_prompt(self):
        """测试带系统提示词的调用"""
        config = {"api_key": "test_key"}
        provider = DeepSeekProvider(config)

        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": "响应内容"
                    }
                }
            ]
        }

        with patch.object(provider, '_make_http_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            result = await provider.call(
                prompt="用户提示词",
                system_prompt="系统提示词"
            )

            call_args = mock_request.call_args
            _, headers, data = call_args[0]

            messages = data["messages"]
            assert len(messages) == 2
            assert messages[0]["role"] == "system"
            assert messages[0]["content"] == "系统提示词"
            assert messages[1]["role"] == "user"
            assert messages[1]["content"] == "用户提示词"

    @pytest.mark.asyncio
    async def test_call_with_custom_params(self):
        """测试使用自定义参数调用"""
        config = {"api_key": "test_key"}
        provider = DeepSeekProvider(config)

        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": "响应"
                    }
                }
            ]
        }

        with patch.object(provider, '_make_http_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            await provider.call(
                "测试",
                max_tokens=2048,
                temperature=0.8
            )

            call_args = mock_request.call_args
            _, headers, data = call_args[0]

            assert data["max_tokens"] == 2048
            assert data["temperature"] == 0.8

    @pytest.mark.asyncio
    async def test_call_api_error(self):
        """测试API调用失败"""
        config = {"api_key": "test_key"}
        provider = DeepSeekProvider(config)

        with patch.object(provider, '_make_http_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = Exception("API Error")

            with pytest.raises(Exception, match="API Error"):
                await provider.call("测试")

    @pytest.mark.asyncio
    async def test_call_invalid_response(self):
        """测试无效响应格式"""
        config = {"api_key": "test_key"}
        provider = DeepSeekProvider(config)

        mock_response = {"invalid": "response"}

        with patch.object(provider, '_make_http_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            with pytest.raises(ValueError, match="解析DeepSeek响应失败"):
                await provider.call("测试")

    def test_get_provider_info(self):
        """测试获取提供商信息"""
        config = {
            "api_key": "test_key",
            "model": "deepseek-coder",
            "max_tokens": 8192,
        }
        provider = DeepSeekProvider(config)
        info = provider.get_provider_info()

        assert info["name"] == "DeepSeek"
        assert info["model"] == "deepseek-coder"
        assert info["max_tokens"] == 8192
        assert "supported_features" in info
        assert "language_support" in info


class TestLLMProviderFactory:
    """LLMProviderFactory测试类"""

    def test_create_gemini_provider(self):
        """测试创建GeminiProvider"""
        config = {"api_key": "test_key"}
        provider = LLMProviderFactory.create_provider("gemini", config)

        assert isinstance(provider, GeminiProvider)
        assert provider.api_key == "test_key"

    def test_create_deepseek_provider(self):
        """测试创建DeepSeekProvider"""
        config = {"api_key": "test_key"}
        provider = LLMProviderFactory.create_provider("deepseek", config)

        assert isinstance(provider, DeepSeekProvider)
        assert provider.api_key == "test_key"

    def test_create_provider_case_insensitive(self):
        """测试提供商名称大小写不敏感"""
        config = {"api_key": "test_key"}

        provider1 = LLMProviderFactory.create_provider("GEMINI", config)
        provider2 = LLMProviderFactory.create_provider("Gemini", config)
        provider3 = LLMProviderFactory.create_provider("gemini", config)

        assert isinstance(provider1, GeminiProvider)
        assert isinstance(provider2, GeminiProvider)
        assert isinstance(provider3, GeminiProvider)

    def test_create_unsupported_provider(self):
        """测试创建不支持的提供商"""
        config = {"api_key": "test_key"}

        with pytest.raises(ValueError, match="不支持的LLM提供商"):
            LLMProviderFactory.create_provider("unsupported", config)

    def test_get_supported_providers(self):
        """测试获取支持的提供商列表"""
        providers = LLMProviderFactory.get_supported_providers()

        assert "gemini" in providers
        assert "deepseek" in providers
        assert len(providers) == 2

    def test_get_provider_info_gemini(self):
        """测试获取Gemini提供商信息"""
        with patch.dict(os.environ, {"TEMP_KEY": "temp"}):
            info = LLMProviderFactory.get_provider_info("gemini")

            assert info["name"] == "Google Gemini"
            assert "model" in info
            assert "supported_features" in info

    def test_get_provider_info_deepseek(self):
        """测试获取DeepSeek提供商信息"""
        with patch.dict(os.environ, {"TEMP_KEY": "temp"}):
            info = LLMProviderFactory.get_provider_info("deepseek")

            assert info["name"] == "DeepSeek"
            assert "model" in info
            assert "supported_features" in info

    def test_get_provider_info_unsupported(self):
        """测试获取不支持的提供商信息"""
        with pytest.raises(ValueError, match="不支持的LLM提供商"):
            LLMProviderFactory.get_provider_info("unsupported")

    def test_register_new_provider(self):
        """测试注册新的提供商"""

        class TestProvider(LLMProvider):
            async def call(self, prompt, system_prompt=None, **kwargs):
                return "test"

            def get_provider_info(self):
                return {"name": "Test"}

        LLMProviderFactory.register_provider("test", TestProvider)

        # 验证新提供商已注册
        assert "test" in LLMProviderFactory.get_supported_providers()

        # 验证可以创建实例
        config = {"api_key": "test_key"}
        provider = LLMProviderFactory.create_provider("test", config)
        assert isinstance(provider, TestProvider)

    def test_register_invalid_provider(self):
        """测试注册无效的提供商类"""

        class InvalidProvider:
            pass

        with pytest.raises(TypeError, match="必须继承LLMProvider"):
            LLMProviderFactory.register_provider("invalid", InvalidProvider)


class TestLLMProviderBase:
    """LLMProvider基类测试"""

    def test_mask_sensitive_data(self):
        """测试敏感数据脱敏"""

        class TestProvider(LLMProvider):
            async def call(self, prompt, system_prompt=None, **kwargs):
                return "test"

            def get_provider_info(self):
                return {"name": "Test"}

        config = {"api_key": "secret_key"}
        provider = TestProvider(config)

        data = {
            "api_key": "secret",
            "nested": {"token": "nested_secret"},
            "normal": "value",
        }

        masked = provider._mask_sensitive_data(data)

        assert masked["api_key"] == "***"
        assert masked["nested"]["token"] == "***"
        assert masked["normal"] == "value"

    def test_sanitize_url(self):
        """测试URL清理"""

        class TestProvider(LLMProvider):
            async def call(self, prompt, system_prompt=None, **kwargs):
                return "test"

            def get_provider_info(self):
                return {"name": "Test"}

        config = {"api_key": "test_key"}
        provider = TestProvider(config)

        url = "https://api.example.com/v1?api_key=secret&other=value"
        sanitized = provider._sanitize_url(url)

        # URL编码后的***是%2A%2A%2A
        assert "api_key=" in sanitized
        assert "other=value" in sanitized
        assert "secret" not in sanitized
        assert "%2A%2A%2A" in sanitized or "***" in sanitized

    def test_is_sensitive_key(self):
        """测试敏感字段检测"""

        class TestProvider(LLMProvider):
            async def call(self, prompt, system_prompt=None, **kwargs):
                return "test"

            def get_provider_info(self):
                return {"name": "Test"}

        config = {"api_key": "test_key"}
        provider = TestProvider(config)

        assert provider._is_sensitive_key("api_key")
        assert provider._is_sensitive_key("API_KEY")
        assert provider._is_sensitive_key("token")
        assert provider._is_sensitive_key("Authorization")
        assert not provider._is_sensitive_key("model")
        assert not provider._is_sensitive_key("temperature")
