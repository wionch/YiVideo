"""
字幕优化器V2配置加载器

提供从YAML配置文件加载字幕优化器配置的功能，支持默认值和配置覆盖。
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import yaml


@dataclass
class DebugConfig:
    """调试配置"""
    enabled: bool = True
    log_dir: str = "tmp/subtitle_optimizer_logs"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "log_dir": self.log_dir,
        }

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "DebugConfig":
        return cls(
            enabled=config_dict.get("enabled", True),
            log_dir=config_dict.get("log_dir", "tmp/subtitle_optimizer_logs"),
        )


@dataclass
class LLMConfig:
    """LLM配置"""
    model: str = "gemini-pro"
    max_tokens: int = 4096
    temperature: float = 0.1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "LLMConfig":
        return cls(
            model=config_dict.get("model", "gemini-pro"),
            max_tokens=config_dict.get("max_tokens", 4096),
            temperature=config_dict.get("temperature", 0.1),
        )


@dataclass
class SubtitleOptimizerConfig:
    """
    字幕优化器V2配置

    包含字幕优化器的所有配置参数。

    Attributes:
        segment_size: 分段大小（字幕行数）
        overlap_lines: 重叠行数
        max_concurrent: 最大并发数
        max_retries: 最大重试次数
        retry_backoff_base: 重试退避基数
        diff_threshold: 差异阈值（用于检测修改）
        max_overlap_expand: 最大重叠扩展行数
        debug: 调试配置
        llm: LLM配置
    """
    segment_size: int = 100
    overlap_lines: int = 20
    max_concurrent: int = 3
    max_retries: int = 3
    retry_backoff_base: int = 1
    diff_threshold: float = 0.3
    max_overlap_expand: int = 50
    debug: DebugConfig = field(default_factory=DebugConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)

    def __post_init__(self):
        """验证配置有效性"""
        if self.segment_size <= 0:
            raise ValueError(f"分段大小必须大于0: {self.segment_size}")
        if self.overlap_lines < 0:
            raise ValueError(f"重叠行数不能为负数: {self.overlap_lines}")
        if self.overlap_lines >= self.segment_size:
            raise ValueError(f"重叠行数必须小于分段大小: {self.overlap_lines} >= {self.segment_size}")
        if self.max_concurrent <= 0:
            raise ValueError(f"最大并发数必须大于0: {self.max_concurrent}")
        if self.max_retries < 0:
            raise ValueError(f"最大重试次数不能为负数: {self.max_retries}")
        if self.retry_backoff_base < 0:
            raise ValueError(f"重试退避基数不能为负数: {self.retry_backoff_base}")
        if not 0.0 <= self.diff_threshold <= 1.0:
            raise ValueError(f"差异阈值必须在0-1之间: {self.diff_threshold}")
        if self.max_overlap_expand < 0:
            raise ValueError(f"最大重叠扩展行数不能为负数: {self.max_overlap_expand}")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "segment_size": self.segment_size,
            "overlap_lines": self.overlap_lines,
            "max_concurrent": self.max_concurrent,
            "max_retries": self.max_retries,
            "retry_backoff_base": self.retry_backoff_base,
            "diff_threshold": self.diff_threshold,
            "max_overlap_expand": self.max_overlap_expand,
            "debug": self.debug.to_dict(),
            "llm": self.llm.to_dict(),
        }

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "SubtitleOptimizerConfig":
        """从字典创建配置"""
        debug_config = DebugConfig.from_dict(config_dict.get("debug", {}))
        llm_config = LLMConfig.from_dict(config_dict.get("llm", {}))

        return cls(
            segment_size=config_dict.get("segment_size", 100),
            overlap_lines=config_dict.get("overlap_lines", 20),
            max_concurrent=config_dict.get("max_concurrent", 3),
            max_retries=config_dict.get("max_retries", 3),
            retry_backoff_base=config_dict.get("retry_backoff_base", 1),
            diff_threshold=config_dict.get("diff_threshold", 0.3),
            max_overlap_expand=config_dict.get("max_overlap_expand", 50),
            debug=debug_config,
            llm=llm_config,
        )


class OptimizerConfigLoader:
    """
    优化器配置加载器

    负责从YAML配置文件加载字幕优化器配置。
    """

    # 默认配置文件路径（相对于项目根目录）
    DEFAULT_CONFIG_PATH = "config.yml"

    # 配置在YAML中的键名
    CONFIG_KEY = "subtitle_optimizer"

    @classmethod
    def load(
        cls,
        config_path: Optional[str] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> SubtitleOptimizerConfig:
        """
        加载配置

        从YAML配置文件加载字幕优化器配置，支持默认值和配置覆盖。

        Args:
            config_path: 配置文件路径，默认为项目根目录下的config.yml
            overrides: 配置覆盖字典，用于覆盖配置文件中的值

        Returns:
            SubtitleOptimizerConfig: 加载的配置对象

        Raises:
            ValueError: 配置验证失败时
        """
        # 确定配置文件路径
        if config_path is None:
            config_path = cls._get_default_config_path()

        # 从文件加载配置字典
        file_config = cls._load_from_file(config_path)

        # 应用覆盖
        if overrides:
            file_config = cls._deep_merge(file_config, overrides)

        # 创建配置对象
        return SubtitleOptimizerConfig.from_dict(file_config)

    @classmethod
    def _get_default_config_path(cls) -> str:
        """
        获取默认配置文件路径

        Returns:
            str: 默认配置文件绝对路径
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # 从 services/common/subtitle/optimizer_v2/ 到项目根目录
        config_path = os.path.join(
            current_dir, "..", "..", "..", "..", cls.DEFAULT_CONFIG_PATH
        )
        return os.path.abspath(config_path)

    @classmethod
    def _load_from_file(cls, config_path: str) -> Dict[str, Any]:
        """
        从YAML文件加载配置

        Args:
            config_path: 配置文件路径

        Returns:
            Dict[str, Any]: 配置字典，如果文件不存在返回空字典
        """
        if not os.path.exists(config_path):
            return {}

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            if config is None:
                return {}

            # 提取subtitle_optimizer配置段
            return config.get(cls.CONFIG_KEY, {})

        except yaml.YAMLError:
            return {}
        except Exception:
            return {}

    @classmethod
    def _deep_merge(
        cls, base: Dict[str, Any], override: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        深度合并两个字典

        Args:
            base: 基础字典
            override: 覆盖字典

        Returns:
            Dict[str, Any]: 合并后的字典
        """
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = cls._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    @classmethod
    def get_default_config(cls) -> SubtitleOptimizerConfig:
        """
        获取默认配置

        Returns:
            SubtitleOptimizerConfig: 默认配置对象
        """
        return SubtitleOptimizerConfig()
