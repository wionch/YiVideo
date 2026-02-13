"""
AI 提供商通用配置类

用于字幕翻译、文本优化等AI功能的统一配置管理。
"""

from typing import Any, Dict, Optional


class AIProvidersConfig:
    """AI 提供商通用配置类"""

    def __init__(self, config_data: Dict[str, Any]):
        """
        初始化配置

        Args:
            config_data: 配置字典，从 config.yml 的 ai_providers 块读取
        """
        self.default_provider = config_data.get("default_provider", "deepseek")
        self.providers = config_data.get("providers", {})

    def get_provider_config(self, provider_name: Optional[str] = None) -> Dict[str, Any]:
        """
        获取指定提供商的配置

        Args:
            provider_name: 提供商名称，如果为None则使用默认提供商

        Returns:
            提供商配置字典
        """
        provider = provider_name or self.default_provider
        return self.providers.get(provider, {})
