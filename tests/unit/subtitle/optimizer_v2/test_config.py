"""
字幕优化器V2配置加载器测试

测试配置加载器的各项功能，包括默认值、YAML加载和配置覆盖。
"""

import os
import tempfile
import pytest
from services.common.subtitle.optimizer_v2.config import (
    DebugConfig,
    LLMConfig,
    SubtitleOptimizerConfig,
    OptimizerConfigLoader,
)


class TestDebugConfig:
    """测试调试配置"""

    def test_default_values(self):
        """测试默认值"""
        config = DebugConfig()
        assert config.enabled is True
        assert config.log_dir == "tmp/subtitle_optimizer_logs"

    def test_custom_values(self):
        """测试自定义值"""
        config = DebugConfig(enabled=False, log_dir="/custom/log/path")
        assert config.enabled is False
        assert config.log_dir == "/custom/log/path"

    def test_to_dict(self):
        """测试转换为字典"""
        config = DebugConfig(enabled=False, log_dir="/custom/path")
        result = config.to_dict()
        assert result == {"enabled": False, "log_dir": "/custom/path"}

    def test_from_dict(self):
        """测试从字典创建"""
        config = DebugConfig.from_dict({"enabled": False, "log_dir": "/custom/path"})
        assert config.enabled is False
        assert config.log_dir == "/custom/path"

    def test_from_dict_partial(self):
        """测试从部分字典创建"""
        config = DebugConfig.from_dict({"log_dir": "/custom/path"})
        assert config.enabled is True  # 默认值
        assert config.log_dir == "/custom/path"

    def test_from_dict_empty(self):
        """测试从空字典创建"""
        config = DebugConfig.from_dict({})
        assert config.enabled is True
        assert config.log_dir == "tmp/subtitle_optimizer_logs"


class TestLLMConfig:
    """测试LLM配置"""

    def test_default_values(self):
        """测试默认值"""
        config = LLMConfig()
        assert config.model == "gemini-pro"
        assert config.max_tokens == 4096
        assert config.temperature == 0.1

    def test_custom_values(self):
        """测试自定义值"""
        config = LLMConfig(model="deepseek-chat", max_tokens=8000, temperature=0.5)
        assert config.model == "deepseek-chat"
        assert config.max_tokens == 8000
        assert config.temperature == 0.5

    def test_to_dict(self):
        """测试转换为字典"""
        config = LLMConfig(model="custom-model")
        result = config.to_dict()
        assert result == {
            "model": "custom-model",
            "max_tokens": 4096,
            "temperature": 0.1,
        }

    def test_from_dict(self):
        """测试从字典创建"""
        config = LLMConfig.from_dict({"model": "deepseek-chat", "max_tokens": 8000})
        assert config.model == "deepseek-chat"
        assert config.max_tokens == 8000
        assert config.temperature == 0.1  # 默认值


class TestSubtitleOptimizerConfig:
    """测试字幕优化器配置"""

    def test_default_values(self):
        """测试默认值"""
        config = SubtitleOptimizerConfig()
        assert config.segment_size == 100
        assert config.overlap_lines == 20
        assert config.max_concurrent == 3
        assert config.max_retries == 3
        assert config.retry_backoff_base == 1
        assert config.diff_threshold == 0.3
        assert config.max_overlap_expand == 50
        assert isinstance(config.debug, DebugConfig)
        assert isinstance(config.llm, LLMConfig)

    def test_custom_values(self):
        """测试自定义值"""
        config = SubtitleOptimizerConfig(
            segment_size=50,
            overlap_lines=10,
            max_concurrent=5,
            max_retries=5,
            retry_backoff_base=2,
            diff_threshold=0.5,
            max_overlap_expand=30,
        )
        assert config.segment_size == 50
        assert config.overlap_lines == 10
        assert config.max_concurrent == 5
        assert config.max_retries == 5
        assert config.retry_backoff_base == 2
        assert config.diff_threshold == 0.5
        assert config.max_overlap_expand == 30

    def test_validation_segment_size(self):
        """测试分段大小验证"""
        with pytest.raises(ValueError, match="分段大小必须大于0"):
            SubtitleOptimizerConfig(segment_size=0)
        with pytest.raises(ValueError, match="分段大小必须大于0"):
            SubtitleOptimizerConfig(segment_size=-1)

    def test_validation_overlap_lines(self):
        """测试重叠行数验证"""
        with pytest.raises(ValueError, match="重叠行数不能为负数"):
            SubtitleOptimizerConfig(overlap_lines=-1)

    def test_validation_overlap_lines_greater_than_segment(self):
        """测试重叠行数不能大于等于分段大小"""
        with pytest.raises(ValueError, match="重叠行数必须小于分段大小"):
            SubtitleOptimizerConfig(segment_size=10, overlap_lines=10)
        with pytest.raises(ValueError, match="重叠行数必须小于分段大小"):
            SubtitleOptimizerConfig(segment_size=10, overlap_lines=15)

    def test_validation_max_concurrent(self):
        """测试最大并发数验证"""
        with pytest.raises(ValueError, match="最大并发数必须大于0"):
            SubtitleOptimizerConfig(max_concurrent=0)
        with pytest.raises(ValueError, match="最大并发数必须大于0"):
            SubtitleOptimizerConfig(max_concurrent=-1)

    def test_validation_max_retries(self):
        """测试最大重试次数验证"""
        with pytest.raises(ValueError, match="最大重试次数不能为负数"):
            SubtitleOptimizerConfig(max_retries=-1)

    def test_validation_retry_backoff_base(self):
        """测试重试退避基数验证"""
        with pytest.raises(ValueError, match="重试退避基数不能为负数"):
            SubtitleOptimizerConfig(retry_backoff_base=-1)

    def test_validation_diff_threshold(self):
        """测试差异阈值验证"""
        with pytest.raises(ValueError, match="差异阈值必须在0-1之间"):
            SubtitleOptimizerConfig(diff_threshold=-0.1)
        with pytest.raises(ValueError, match="差异阈值必须在0-1之间"):
            SubtitleOptimizerConfig(diff_threshold=1.1)

    def test_validation_max_overlap_expand(self):
        """测试最大重叠扩展行数验证"""
        with pytest.raises(ValueError, match="最大重叠扩展行数不能为负数"):
            SubtitleOptimizerConfig(max_overlap_expand=-1)

    def test_to_dict(self):
        """测试转换为字典"""
        config = SubtitleOptimizerConfig(segment_size=50)
        result = config.to_dict()
        assert result["segment_size"] == 50
        assert result["overlap_lines"] == 20
        assert "debug" in result
        assert "llm" in result

    def test_from_dict(self):
        """测试从字典创建"""
        config_dict = {
            "segment_size": 50,
            "overlap_lines": 10,
            "max_concurrent": 5,
            "debug": {"enabled": False},
            "llm": {"model": "deepseek-chat"},
        }
        config = SubtitleOptimizerConfig.from_dict(config_dict)
        assert config.segment_size == 50
        assert config.overlap_lines == 10
        assert config.max_concurrent == 5
        assert config.debug.enabled is False
        assert config.llm.model == "deepseek-chat"
        # 其他字段使用默认值
        assert config.max_retries == 3
        assert config.llm.max_tokens == 4096

    def test_from_dict_empty(self):
        """测试从空字典创建"""
        config = SubtitleOptimizerConfig.from_dict({})
        assert config.segment_size == 100
        assert config.overlap_lines == 20
        assert config.debug.enabled is True
        assert config.llm.model == "gemini-pro"


class TestOptimizerConfigLoader:
    """测试配置加载器"""

    def test_get_default_config(self):
        """测试获取默认配置"""
        config = OptimizerConfigLoader.get_default_config()
        assert isinstance(config, SubtitleOptimizerConfig)
        assert config.segment_size == 100
        assert config.overlap_lines == 20

    def test_load_with_nonexistent_file(self):
        """测试加载不存在的文件"""
        config = OptimizerConfigLoader.load(config_path="/nonexistent/path/config.yml")
        assert isinstance(config, SubtitleOptimizerConfig)
        # 应该返回默认配置
        assert config.segment_size == 100
        assert config.overlap_lines == 20

    def test_load_from_yaml_file(self):
        """测试从YAML文件加载"""
        yaml_content = """
subtitle_optimizer:
  segment_size: 200
  overlap_lines: 30
  max_concurrent: 5
  max_retries: 5
  retry_backoff_base: 2
  diff_threshold: 0.5
  max_overlap_expand: 60
  debug:
    enabled: false
    log_dir: "/var/log/optimizer"
  llm:
    model: "deepseek-chat"
    max_tokens: 8000
    temperature: 0.2
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            config = OptimizerConfigLoader.load(config_path=temp_path)
            assert config.segment_size == 200
            assert config.overlap_lines == 30
            assert config.max_concurrent == 5
            assert config.max_retries == 5
            assert config.retry_backoff_base == 2
            assert config.diff_threshold == 0.5
            assert config.max_overlap_expand == 60
            assert config.debug.enabled is False
            assert config.debug.log_dir == "/var/log/optimizer"
            assert config.llm.model == "deepseek-chat"
            assert config.llm.max_tokens == 8000
            assert config.llm.temperature == 0.2
        finally:
            os.unlink(temp_path)

    def test_load_with_partial_yaml(self):
        """测试从部分YAML加载"""
        yaml_content = """
subtitle_optimizer:
  segment_size: 150
  debug:
    enabled: false
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            config = OptimizerConfigLoader.load(config_path=temp_path)
            assert config.segment_size == 150
            assert config.debug.enabled is False
            # 其他字段使用默认值
            assert config.overlap_lines == 20
            assert config.max_concurrent == 3
            assert config.llm.model == "gemini-pro"
        finally:
            os.unlink(temp_path)

    def test_load_with_overrides(self):
        """测试配置覆盖"""
        yaml_content = """
subtitle_optimizer:
  segment_size: 200
  overlap_lines: 30
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            overrides = {
                "segment_size": 50,
                "max_concurrent": 10,
                "debug": {"enabled": False},
            }
            config = OptimizerConfigLoader.load(config_path=temp_path, overrides=overrides)
            # 覆盖的值
            assert config.segment_size == 50
            assert config.max_concurrent == 10
            assert config.debug.enabled is False
            # 未覆盖的值保持原样
            assert config.overlap_lines == 30
            assert config.llm.model == "gemini-pro"
        finally:
            os.unlink(temp_path)

    def test_load_with_nested_overrides(self):
        """测试嵌套配置覆盖"""
        yaml_content = """
subtitle_optimizer:
  debug:
    enabled: true
    log_dir: "/original/log"
  llm:
    model: "gemini-pro"
    max_tokens: 4096
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            overrides = {"debug": {"enabled": False}, "llm": {"model": "deepseek-chat"}}
            config = OptimizerConfigLoader.load(config_path=temp_path, overrides=overrides)
            # debug.enabled 被覆盖
            assert config.debug.enabled is False
            # debug.log_dir 保持原样
            assert config.debug.log_dir == "/original/log"
            # llm.model 被覆盖
            assert config.llm.model == "deepseek-chat"
            # llm.max_tokens 保持原样
            assert config.llm.max_tokens == 4096
        finally:
            os.unlink(temp_path)

    def test_load_without_subtitle_optimizer_section(self):
        """测试YAML中没有subtitle_optimizer配置段"""
        yaml_content = """
other_section:
  some_key: some_value
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            config = OptimizerConfigLoader.load(config_path=temp_path)
            # 应该返回默认配置
            assert config.segment_size == 100
            assert config.overlap_lines == 20
        finally:
            os.unlink(temp_path)

    def test_load_with_invalid_yaml(self):
        """测试无效的YAML文件"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            temp_path = f.name

        try:
            config = OptimizerConfigLoader.load(config_path=temp_path)
            # 应该返回默认配置
            assert config.segment_size == 100
            assert isinstance(config, SubtitleOptimizerConfig)
        finally:
            os.unlink(temp_path)

    def test_deep_merge(self):
        """测试深度合并"""
        base = {"a": 1, "b": {"c": 2, "d": 3}, "e": 4}
        override = {"b": {"c": 20}, "f": 6}
        result = OptimizerConfigLoader._deep_merge(base, override)
        assert result == {"a": 1, "b": {"c": 20, "d": 3}, "e": 4, "f": 6}

    def test_get_default_config_path(self):
        """测试获取默认配置路径"""
        path = OptimizerConfigLoader._get_default_config_path()
        assert path.endswith("config.yml")
        assert os.path.isabs(path)
