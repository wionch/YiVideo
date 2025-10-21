"""
字幕校正配置管理模块

负责管理字幕校正相关的配置信息，包括AI服务提供商配置、
处理参数、系统提示词路径等。
"""

import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import logging

from services.common.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ProviderConfig:
    """AI服务提供商配置"""
    name: str                                    # 提供商名称
    api_key: str                                 # API密钥
    api_key_env: str                             # API密钥环境变量名
    api_base_url: str                            # API基础URL
    model: str                                   # 模型名称
    max_tokens: int = 8000                       # 最大令牌数
    temperature: float = 0.1                     # 温度参数
    timeout: int = 300                           # 超时时间（秒）
    enabled: bool = True                         # 是否启用
    additional_params: Dict[str, Any] = field(default_factory=dict)  # 额外参数


@dataclass
class SubtitleCorrectionConfig:
    """字幕校正配置类"""

    # 基础配置（基于DeepSeek API优化）
    default_provider: str = "deepseek"                          # 默认AI提供商
    max_subtitle_length: int = 4000                             # 单次处理最大字符数（考虑token安全边距）
    max_tokens: int = 8000                                      # AI响应最大令牌数
    temperature: float = 0.1                                    # AI响应温度参数
    timeout_seconds: int = 300                                  # 请求超时时间

    # 文件路径配置
    system_prompt_path: str = "/app/config/system_prompt/subtitle_optimization.md"
    output_format: str = "srt"                                  # 输出格式
    backup_original: bool = True                                # 是否备份原始文件

    # 处理配置
    batch_processing: bool = True                               # 是否启用批量处理
    batch_size: int = 5                                         # 批处理大小
    preserve_timestamps: bool = True                            # 是否保持原始时间戳
    max_retry_attempts: int = 3                                 # 最大重试次数
    retry_delay: float = 2.0                                    # 重试延迟（秒）

    # 本地合并配置
    enable_local_merge: bool = True                             # 是否启用本地短字幕合并
    local_merge_max_chars: int = 1                              # 短字幕的最大字符数
    local_merge_max_line_length: int = 20                       # 合并后每行最大字符数

    # AI服务提供商配置
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)

    def __init__(self, config_dict: Optional[Dict[str, Any]] = None):
        """
        初始化配置

        Args:
            config_dict: 配置字典，如果为None则使用默认配置
        """
        # 初始化providers字段为空字典
        self.providers = {}

        if config_dict:
            logger.debug(f"从配置字典加载字幕校正配置: {list(config_dict.keys())}")
            self._load_from_dict(config_dict)

            providers_dict = config_dict.get('providers', {})
            logger.debug(f"加载AI服务提供商配置: {list(providers_dict.keys())}")
            self._load_providers_from_dict(providers_dict)
        else:
            logger.debug("使用默认字幕校正配置")
            self._load_default_config()

        # 验证配置
        self._validate_config()
        logger.debug(f"字幕校正配置初始化完成，默认提供商: {self.default_provider}，已配置提供商: {list(self.providers.keys())}")

    def _load_from_dict(self, config_dict: Dict[str, Any]):
        """从字典加载基础配置"""
        self.default_provider = config_dict.get('default_provider', self.default_provider)
        self.max_subtitle_length = config_dict.get('max_subtitle_length', self.max_subtitle_length)
        self.max_tokens = config_dict.get('max_tokens', self.max_tokens)
        self.temperature = config_dict.get('temperature', self.temperature)
        self.timeout_seconds = config_dict.get('timeout_seconds', self.timeout_seconds)

        self.system_prompt_path = config_dict.get('system_prompt_path', self.system_prompt_path)
        self.output_format = config_dict.get('output_format', self.output_format)
        self.backup_original = config_dict.get('backup_original', self.backup_original)

        self.batch_processing = config_dict.get('batch_processing', self.batch_processing)
        self.batch_size = config_dict.get('batch_size', self.batch_size)
        self.preserve_timestamps = config_dict.get('preserve_timestamps', self.preserve_timestamps)
        self.max_retry_attempts = config_dict.get('max_retry_attempts', self.max_retry_attempts)
        self.retry_delay = config_dict.get('retry_delay', self.retry_delay)

        # 加载本地合并配置
        self.enable_local_merge = config_dict.get('enable_local_merge', self.enable_local_merge)
        self.local_merge_max_chars = config_dict.get('local_merge_max_chars', self.local_merge_max_chars)
        self.local_merge_max_line_length = config_dict.get('local_merge_max_line_length', self.local_merge_max_line_length)

    def _load_providers_from_dict(self, providers_dict: Dict[str, Dict[str, Any]]):
        """从字典加载AI服务提供商配置"""
        logger.debug(f"开始加载 {len(providers_dict)} 个AI服务提供商配置")

        for provider_name, provider_config in providers_dict.items():
            try:
                logger.debug(f"加载AI服务提供商 {provider_name}: {provider_config.get('model', 'unknown')}")

                provider_instance = ProviderConfig(
                    name=provider_name,
                    api_key=provider_config.get('api_key', ''),
                    api_key_env=self._get_api_key_env(provider_name),
                    api_base_url=provider_config.get('api_base_url', ''),
                    model=provider_config.get('model', ''),
                    max_tokens=provider_config.get('max_tokens', self.max_tokens),
                    temperature=provider_config.get('temperature', self.temperature),
                    timeout=provider_config.get('timeout', self.timeout_seconds),
                    enabled=provider_config.get('enabled', True),
                    additional_params=provider_config.get('additional_params', {})
                )

                self.providers[provider_name] = provider_instance
                logger.debug(f"AI服务提供商 {provider_name} 加载成功")

            except Exception as e:
                logger.error(f"加载AI服务提供商 {provider_name} 失败: {e}")
                # 继续加载其他提供商，不中断整个过程
                continue

        logger.debug(f"AI服务提供商配置加载完成，成功加载: {list(self.providers.keys())}")

    def _load_default_config(self):
        """加载默认配置"""
        # 默认AI服务提供商配置
        default_providers = {
            'deepseek': {
                'name': 'deepseek',
                'api_key': '',
                'api_base_url': 'https://api.deepseek.com/chat/completions',
                'model': 'deepseek-chat',
                'max_tokens': 8000,
                'temperature': 0.1,
                'timeout': 300,
                'enabled': True
            },
            'gemini': {
                'name': 'gemini',
                'api_key': '',
                'api_base_url': 'https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent',
                'model': 'gemini-pro',
                'max_tokens': 8000,
                'temperature': 0.1,
                'timeout': 300,
                'enabled': True
            },
            'zhipu': {
                'name': 'zhipu',
                'api_key': '',
                'api_base_url': 'https://open.bigmodel.cn/api/paas/v4/chat/completions',
                'model': 'glm-4',
                'max_tokens': 8000,
                'temperature': 0.1,
                'timeout': 300,
                'enabled': True
            },
            'volcengine': {
                'name': 'volcengine',
                'api_key': '',
                'api_base_url': 'https://ark.cn-beijing.volces.com/api/v3/chat/completions',
                'model': 'doubao-pro-32k',
                'max_tokens': 8000,
                'temperature': 0.1,
                'timeout': 300,
                'enabled': True
            }
        }

        self._load_providers_from_dict(default_providers)

    def _get_api_key_env(self, provider_name: str) -> str:
        """获取API密钥环境变量名"""
        env_mapping = {
            'deepseek': 'DEEPSEEK_API_KEY',
            'gemini': 'GEMINI_API_KEY',
            'zhipu': 'ZHIPU_API_KEY',
            'volcengine': 'VOLCENGINE_API_KEY'
        }
        return env_mapping.get(provider_name, f'{provider_name.upper()}_API_KEY')

    def _validate_config(self):
        """验证配置的有效性"""
        # 验证默认提供商
        if self.default_provider not in self.providers:
            available_providers = list(self.providers.keys())
            if available_providers:
                self.default_provider = available_providers[0]
                logger.warning(f"默认提供商 '{self.default_provider}' 不存在，使用 '{available_providers[0]}' 代替")
            else:
                raise ValueError("没有配置任何AI服务提供商")

        # 验证数值参数
        if self.max_subtitle_length <= 0:
            raise ValueError("max_subtitle_length 必须大于 0")

        if self.max_tokens <= 0:
            raise ValueError("max_tokens 必须大于 0")

        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature 必须在 0.0 到 2.0 之间")

        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须大于 0")

        # 验证系统提示词路径
        if not os.path.exists(self.system_prompt_path):
            logger.warning(f"系统提示词文件不存在: {self.system_prompt_path}")

        # 验证输出格式
        supported_formats = ['srt', 'vtt', 'ass']
        if self.output_format not in supported_formats:
            logger.warning(f"不支持的输出格式 '{self.output_format}'，支持的格式: {supported_formats}")

    def get_provider_config(self, provider_name: str) -> Dict[str, Any]:
        """
        获取指定AI服务提供商的配置

        Args:
            provider_name: 提供商名称

        Returns:
            Dict: 提供商配置字典

        Raises:
            ValueError: 提供商不存在
        """
        if provider_name not in self.providers:
            raise ValueError(f"AI服务提供商 '{provider_name}' 不存在")

        provider = self.providers[provider_name]

        # 从环境变量获取API密钥
        api_key = os.getenv(provider.api_key_env, provider.api_key)

        config = {
            'api_key': api_key,
            'api_key_env': provider.api_key_env,
            'api_base_url': provider.api_base_url,
            'model': provider.model,
            'max_tokens': provider.max_tokens,
            'temperature': provider.temperature,
            'timeout': provider.timeout,
            'enabled': provider.enabled
        }

        # 添加额外参数
        if provider.additional_params:
            config.update(provider.additional_params)

        return config

    def get_enabled_providers(self) -> List[str]:
        """获取所有启用的AI服务提供商列表"""
        return [name for name, provider in self.providers.items() if provider.enabled]

    def is_provider_enabled(self, provider_name: str) -> bool:
        """检查指定的AI服务提供商是否启用"""
        provider = self.providers.get(provider_name)
        return provider is not None and provider.enabled

    def get_system_prompt(self) -> str:
        """
        读取系统提示词内容

        Returns:
            str: 系统提示词内容

        Raises:
            FileNotFoundError: 系统提示词文件不存在
        """
        try:
            with open(self.system_prompt_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except FileNotFoundError:
            logger.error(f"系统提示词文件不存在: {self.system_prompt_path}")
            raise
        except Exception as e:
            logger.error(f"读取系统提示词文件失败: {e}")
            raise

    def update_provider_config(self, provider_name: str, updates: Dict[str, Any]):
        """
        更新AI服务提供商配置

        Args:
            provider_name: 提供商名称
            updates: 要更新的配置项
        """
        if provider_name not in self.providers:
            raise ValueError(f"AI服务提供商 '{provider_name}' 不存在")

        provider = self.providers[provider_name]

        for key, value in updates.items():
            if hasattr(provider, key):
                setattr(provider, key, value)
            else:
                provider.additional_params[key] = value

        logger.info(f"已更新AI服务提供商 '{provider_name}' 的配置")

    def enable_provider(self, provider_name: str):
        """启用指定的AI服务提供商"""
        if provider_name not in self.providers:
            raise ValueError(f"AI服务提供商 '{provider_name}' 不存在")

        self.providers[provider_name].enabled = True
        logger.info(f"已启用AI服务提供商: {provider_name}")

    def disable_provider(self, provider_name: str):
        """禁用指定的AI服务提供商"""
        if provider_name not in self.providers:
            raise ValueError(f"AI服务提供商 '{provider_name}' 不存在")

        self.providers[provider_name].enabled = False
        logger.info(f"已禁用AI服务提供商: {provider_name}")

    def to_dict(self) -> Dict[str, Any]:
        """将配置转换为字典"""
        return {
            'default_provider': self.default_provider,
            'max_subtitle_length': self.max_subtitle_length,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
            'timeout_seconds': self.timeout_seconds,
            'system_prompt_path': self.system_prompt_path,
            'output_format': self.output_format,
            'backup_original': self.backup_original,
            'batch_processing': self.batch_processing,
            'batch_size': self.batch_size,
            'preserve_timestamps': self.preserve_timestamps,
            'max_retry_attempts': self.max_retry_attempts,
            'retry_delay': self.retry_delay,
            'providers': {
                name: {
                    'name': provider.name,
                    'api_key': '***',  # 隐藏API密钥
                    'api_base_url': provider.api_base_url,
                    'model': provider.model,
                    'max_tokens': provider.max_tokens,
                    'temperature': provider.temperature,
                    'timeout': provider.timeout,
                    'enabled': provider.enabled,
                    'additional_params': provider.additional_params
                }
                for name, provider in self.providers.items()
            }
        }

    def __str__(self) -> str:
        """配置的字符串表示"""
        enabled_providers = self.get_enabled_providers()
        return (f"SubtitleCorrectionConfig("
                f"default_provider='{self.default_provider}', "
                f"enabled_providers={enabled_providers}, "
                f"max_subtitle_length={self.max_subtitle_length}, "
                f"system_prompt_path='{self.system_prompt_path}')")


# 全局配置实例
_global_config: Optional[SubtitleCorrectionConfig] = None


def get_subtitle_correction_config(config_dict: Optional[Dict[str, Any]] = None) -> SubtitleCorrectionConfig:
    """
    获取全局字幕校正配置实例

    Args:
        config_dict: 配置字典，仅在首次调用时有效

    Returns:
        SubtitleCorrectionConfig: 配置实例
    """
    global _global_config

    if _global_config is None:
        _global_config = SubtitleCorrectionConfig(config_dict)

    return _global_config


def reset_subtitle_correction_config():
    """重置全局配置实例"""
    global _global_config
    _global_config = None
    logger.info("字幕校正配置已重置")