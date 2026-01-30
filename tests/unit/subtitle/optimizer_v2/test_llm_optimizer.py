"""
LLM优化器单元测试
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from services.common.subtitle.optimizer_v2.llm_optimizer import (
    LLMOptimizer,
    LLMOptimizerConfig,
)
from services.common.subtitle.optimizer_v2.models import (
    SubtitleSegment,
    SegmentTask,
    OptimizationStatus,
    SegmentType,
)
from services.common.subtitle.optimizer_v2.config import LLMConfig


@pytest.fixture
def mock_provider():
    """提供模拟的AI提供商"""
    provider = Mock()
    provider.chat_completion = AsyncMock()
    return provider


@pytest.fixture
def optimizer(mock_provider):
    """提供使用模拟提供商的优化器"""
    return LLMOptimizer(provider=mock_provider)


class TestBuildSystemPrompt:
    """测试构建System Prompt"""

    def test_system_prompt_contains_key_instructions(self, optimizer):
        """测试系统提示词包含关键指令"""
        prompt = optimizer._build_system_prompt()

        assert "字幕优化" in prompt
        assert "行数不变" in prompt
        assert "ID" in prompt
        assert "格式" in prompt

    def test_system_prompt_contains_input_format(self, optimizer):
        """测试系统提示词包含输入格式说明"""
        prompt = optimizer._build_system_prompt()

        assert "ID|时间范围|文本内容" in prompt
        assert "ID|开始时间-结束时间|优化后的文本" in prompt

    def test_system_prompt_contains_example(self, optimizer):
        """测试系统提示词包含示例"""
        prompt = optimizer._build_system_prompt()

        assert "示例" in prompt or "示例输出" in prompt


class TestBuildUserPrompt:
    """测试构建User Prompt"""

    @pytest.fixture
    def sample_task(self):
        """提供示例任务"""
        segments = [
            SubtitleSegment(id=1, start=0.0, end=2.5, text="第一段字幕"),
            SubtitleSegment(id=2, start=2.5, end=5.0, text="第二段字幕"),
        ]
        return SegmentTask(
            task_id="test_task_001",
            segments=segments,
            segment_type=SegmentType.NORMAL,
        )

    def test_basic_prompt_structure(self, optimizer, sample_task):
        """测试基本提示词结构"""
        prompt = optimizer._build_user_prompt(sample_task)

        assert "需要优化的字幕" in prompt
        assert "1|0.0-2.5|第一段字幕" in prompt
        assert "2|2.5-5.0|第二段字幕" in prompt

    def test_prompt_with_context_before(self, optimizer, sample_task):
        """测试带前文的提示词"""
        context = "这是前文内容"
        prompt = optimizer._build_user_prompt(sample_task, context_before=context)

        assert "【前文】" in prompt
        assert context in prompt

    def test_prompt_with_context_after(self, optimizer, sample_task):
        """测试带后文的提示词"""
        context = "这是后文内容"
        prompt = optimizer._build_user_prompt(sample_task, context_after=context)

        assert "【后文】" in prompt
        assert context in prompt

    def test_prompt_with_both_contexts(self, optimizer, sample_task):
        """测试带前后文的提示词"""
        prompt = optimizer._build_user_prompt(
            sample_task,
            context_before="前文",
            context_after="后文",
        )

        assert "【前文】" in prompt
        assert "【后文】" in prompt
        assert "前文" in prompt
        assert "后文" in prompt

    def test_prompt_format_consistency(self, optimizer, sample_task):
        """测试提示词格式一致性"""
        prompt = optimizer._build_user_prompt(sample_task)

        lines = prompt.split("\n")
        content_started = False
        for line in lines:
            if "需要优化的字幕" in line:
                content_started = True
                continue
            if content_started and line.strip() and "|" in line:
                parts = line.split("|")
                assert len(parts) == 3, f"格式错误: {line}"
                # 验证ID是数字
                assert parts[0].strip().isdigit()
                # 验证时间范围包含-
                assert "-" in parts[1]


class TestParseResponse:
    """测试解析响应"""

    @pytest.fixture
    def sample_task(self):
        """提供示例任务"""
        segments = [
            SubtitleSegment(id=1, start=0.0, end=2.5, text="第一段字幕"),
            SubtitleSegment(id=2, start=2.5, end=5.0, text="第二段字幕"),
        ]
        return SegmentTask(
            task_id="test_task_001",
            segments=segments,
            segment_type=SegmentType.NORMAL,
        )

    def test_parse_valid_response(self, optimizer, sample_task):
        """测试解析有效响应"""
        response = """1|0.0-2.5|优化后的第一段字幕
2|2.5-5.0|优化后的第二段字幕"""

        lines = optimizer._parse_response(response, sample_task)

        assert len(lines) == 2
        assert lines[0].text == "优化后的第一段字幕"
        assert lines[0].start == 0.0
        assert lines[0].end == 2.5
        assert lines[1].text == "优化后的第二段字幕"

    def test_parse_response_with_extra_whitespace(self, optimizer, sample_task):
        """测试解析带额外空白的响应"""
        response = """1|0.0-2.5|  优化后的第一段字幕  
2|2.5-5.0|优化后的第二段字幕"""

        lines = optimizer._parse_response(response, sample_task)

        assert len(lines) == 2
        assert lines[0].text == "优化后的第一段字幕"

    def test_parse_response_with_empty_lines(self, optimizer, sample_task):
        """测试解析带空行的响应"""
        response = """1|0.0-2.5|优化后的第一段字幕

2|2.5-5.0|优化后的第二段字幕
"""

        lines = optimizer._parse_response(response, sample_task)

        assert len(lines) == 2

    def test_parse_response_with_unexpected_id(self, optimizer, sample_task):
        """测试解析包含意外ID的响应"""
        response = """1|0.0-2.5|优化后的第一段字幕
2|2.5-5.0|优化后的第二段字幕
3|5.0-7.5|意外的第三段"""

        lines = optimizer._parse_response(response, sample_task)

        # 应该只解析出预期的ID
        assert len(lines) == 2
        assert all(line.start < 5.0 for line in lines)

    def test_parse_response_with_duplicate_id(self, optimizer, sample_task):
        """测试解析包含重复ID的响应"""
        response = """1|0.0-2.5|优化后的第一段字幕
1|0.0-2.5|重复的第一段字幕
2|2.5-5.0|优化后的第二段字幕"""

        lines = optimizer._parse_response(response, sample_task)

        # 应该只保留第一个
        assert len(lines) == 2
        assert lines[0].text == "优化后的第一段字幕"

    def test_parse_empty_response_raises_error(self, optimizer, sample_task):
        """测试解析空响应抛出错误"""
        with pytest.raises(ValueError, match="响应为空"):
            optimizer._parse_response("", sample_task)

    def test_parse_whitespace_only_response_raises_error(self, optimizer, sample_task):
        """测试解析仅空白响应抛出错误"""
        with pytest.raises(ValueError, match="响应为空"):
            optimizer._parse_response("   \n  \n  ", sample_task)

    def test_parse_invalid_format_lines(self, optimizer, sample_task):
        """测试解析无效格式行"""
        response = """1|0.0-2.5|有效行
无效行格式
2|2.5-5.0|另一个有效行"""

        lines = optimizer._parse_response(response, sample_task)

        assert len(lines) == 2

    def test_parse_response_detects_modification(self, optimizer, sample_task):
        """测试解析响应检测修改状态"""
        response = """1|0.0-2.5|第一段字幕
2|2.5-5.0|已修改的第二段"""

        lines = optimizer._parse_response(response, sample_task)

        assert lines[0].is_modified is False  # 文本相同
        assert lines[1].is_modified is True   # 文本不同


class TestValidateIdRange:
    """测试校验ID范围"""

    @pytest.fixture
    def sample_task(self):
        """提供示例任务"""
        segments = [
            SubtitleSegment(id=1, start=0.0, end=2.5, text="第一段"),
            SubtitleSegment(id=2, start=2.5, end=5.0, text="第二段"),
            SubtitleSegment(id=3, start=5.0, end=7.5, text="第三段"),
        ]
        return SegmentTask(
            task_id="test_task_001",
            segments=segments,
            segment_type=SegmentType.NORMAL,
        )

    def test_valid_id_range(self, optimizer, sample_task):
        """测试有效的ID范围"""
        from services.common.subtitle.optimizer_v2.models import OptimizedLine

        optimized_lines = [
            OptimizedLine(text="优化1", start=0.0, end=2.5),
            OptimizedLine(text="优化2", start=2.5, end=5.0),
            OptimizedLine(text="优化3", start=5.0, end=7.5),
        ]

        is_valid, error = optimizer._validate_id_range(optimized_lines, sample_task)

        assert is_valid is True
        assert error is None

    def test_missing_id(self, optimizer, sample_task):
        """测试缺少ID"""
        from services.common.subtitle.optimizer_v2.models import OptimizedLine

        optimized_lines = [
            OptimizedLine(text="优化1", start=0.0, end=2.5),
            OptimizedLine(text="优化2", start=2.5, end=5.0),
            # 缺少ID 3
        ]

        is_valid, error = optimizer._validate_id_range(optimized_lines, sample_task)

        assert is_valid is False
        assert "缺少" in error or "不一致" in error

    def test_extra_id(self, optimizer, sample_task):
        """测试多余ID"""
        from services.common.subtitle.optimizer_v2.models import OptimizedLine

        optimized_lines = [
            OptimizedLine(text="优化1", start=0.0, end=2.5),
            OptimizedLine(text="优化2", start=2.5, end=5.0),
            OptimizedLine(text="优化3", start=5.0, end=7.5),
            OptimizedLine(text="优化4", start=7.5, end=10.0),  # 多余的
        ]

        is_valid, error = optimizer._validate_id_range(optimized_lines, sample_task)

        assert is_valid is False
        assert "多余" in error or "不一致" in error or "行数不一致" in error

    def test_line_count_mismatch(self, optimizer, sample_task):
        """测试行数不匹配"""
        from services.common.subtitle.optimizer_v2.models import OptimizedLine

        optimized_lines = [
            OptimizedLine(text="合并后的", start=0.0, end=7.5),
        ]

        is_valid, error = optimizer._validate_id_range(optimized_lines, sample_task)

        assert is_valid is False
        assert "行数不一致" in error


class TestCalculateBackoffDelay:
    """测试指数退避计算"""

    def test_first_attempt_delay(self, optimizer):
        """测试第一次尝试延迟"""
        delay = optimizer._calculate_backoff_delay(0)

        assert delay == 1.0  # base_delay * 2^0 = 1.0

    def test_second_attempt_delay(self, optimizer):
        """测试第二次尝试延迟"""
        delay = optimizer._calculate_backoff_delay(1)

        assert delay == 2.0  # base_delay * 2^1 = 2.0

    def test_third_attempt_delay(self, optimizer):
        """测试第三次尝试延迟"""
        delay = optimizer._calculate_backoff_delay(2)

        assert delay == 4.0  # base_delay * 2^2 = 4.0

    def test_max_delay_cap(self, optimizer):
        """测试最大延迟上限"""
        # 使用一个大的attempt值
        delay = optimizer._calculate_backoff_delay(10)

        assert delay <= 30.0  # max_delay

    def test_custom_config(self, mock_provider):
        """测试自定义配置"""
        config = LLMOptimizerConfig(
            base_delay=2.0,
            exponential_base=3.0,
            max_delay=50.0,
        )
        optimizer = LLMOptimizer(provider=mock_provider, retry_config=config)

        delay = optimizer._calculate_backoff_delay(2)

        assert delay == 18.0  # 2.0 * 3^2 = 18.0


class TestOptimizeSegment:
    """测试优化单个段（带重试）"""

    @pytest.fixture
    def sample_task(self):
        """提供示例任务"""
        segments = [
            SubtitleSegment(id=1, start=0.0, end=2.5, text="第一段字幕"),
            SubtitleSegment(id=2, start=2.5, end=5.0, text="第二段字幕"),
        ]
        return SegmentTask(
            task_id="test_task_001",
            segments=segments,
            segment_type=SegmentType.NORMAL,
        )

    @pytest.mark.asyncio
    async def test_successful_optimization(self, optimizer, mock_provider, sample_task):
        """测试成功优化"""
        mock_provider.chat_completion.return_value = """1|0.0-2.5|优化后的第一段字幕
2|2.5-5.0|优化后的第二段字幕"""

        result = await optimizer.optimize_segment(sample_task)

        assert result.is_success is True
        assert result.status == OptimizationStatus.COMPLETED
        assert len(result.optimized_lines) == 2
        assert result.task_id == "test_task_001"
        assert result.metadata["attempts"] == 1

    @pytest.mark.asyncio
    async def test_successful_optimization_with_context(self, optimizer, mock_provider, sample_task):
        """测试带上下文的成功优化"""
        mock_provider.chat_completion.return_value = """1|0.0-2.5|优化后的第一段字幕
2|2.5-5.0|优化后的第二段字幕"""

        result = await optimizer.optimize_segment(
            sample_task,
            context_before="前文内容",
            context_after="后文内容",
        )

        assert result.is_success is True
        assert len(result.optimized_lines) == 2

    @pytest.mark.asyncio
    async def test_retry_on_parse_error(self, optimizer, mock_provider, sample_task):
        """测试解析错误时重试"""
        # 第一次返回无效格式，第二次返回有效格式
        mock_provider.chat_completion.side_effect = [
            "无效格式响应",
            """1|0.0-2.5|优化后的第一段字幕
2|2.5-5.0|优化后的第二段字幕""",
        ]

        result = await optimizer.optimize_segment(sample_task)

        assert result.is_success is True
        assert result.metadata["attempts"] == 2
        assert mock_provider.chat_completion.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_validation_error(self, optimizer, mock_provider, sample_task):
        """测试验证错误时重试"""
        # 第一次返回缺少一行，第二次返回完整
        mock_provider.chat_completion.side_effect = [
            "1|0.0-2.5|只有第一段",
            """1|0.0-2.5|优化后的第一段字幕
2|2.5-5.0|优化后的第二段字幕""",
        ]

        result = await optimizer.optimize_segment(sample_task)

        assert result.is_success is True
        assert result.metadata["attempts"] == 2

    @pytest.mark.asyncio
    async def test_all_retries_fail(self, optimizer, mock_provider, sample_task):
        """测试所有重试都失败"""
        mock_provider.chat_completion.return_value = "始终无效的响应"

        result = await optimizer.optimize_segment(sample_task)

        assert result.is_success is False
        assert result.status == OptimizationStatus.FAILED
        assert result.error_message is not None
        assert result.metadata["attempts"] == 3  # 默认重试3次

    @pytest.mark.asyncio
    async def test_max_retries_respected(self, mock_provider, sample_task):
        """测试最大重试次数被尊重"""
        config = LLMOptimizerConfig(max_retries=5)
        optimizer = LLMOptimizer(provider=mock_provider, retry_config=config)
        mock_provider.chat_completion.return_value = "无效响应"

        result = await optimizer.optimize_segment(sample_task)

        assert result.is_success is False
        assert result.metadata["attempts"] == 5
        assert mock_provider.chat_completion.call_count == 5

    @pytest.mark.asyncio
    async def test_llm_call_parameters(self, optimizer, mock_provider, sample_task):
        """测试LLM调用参数"""
        mock_provider.chat_completion.return_value = """1|0.0-2.5|优化后的第一段字幕
2|2.5-5.0|优化后的第二段字幕"""

        await optimizer.optimize_segment(sample_task)

        # 验证调用参数
        call_args = mock_provider.chat_completion.call_args
        assert "messages" in call_args.kwargs
        messages = call_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert call_args.kwargs["max_tokens"] == optimizer.llm_config.max_tokens
        assert call_args.kwargs["temperature"] == optimizer.llm_config.temperature


class TestLLMOptimizerConfig:
    """测试LLM优化器配置"""

    def test_default_config(self):
        """测试默认配置"""
        config = LLMOptimizerConfig()

        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0
        assert config.exponential_base == 2.0

    def test_custom_config(self):
        """测试自定义配置"""
        config = LLMOptimizerConfig(
            max_retries=5,
            base_delay=2.0,
            max_delay=60.0,
            exponential_base=3.0,
        )

        assert config.max_retries == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 3.0


class TestLLMOptimizerInitialization:
    """测试LLM优化器初始化"""

    def test_default_initialization(self):
        """测试默认初始化"""
        with patch(
            "services.common.subtitle.optimizer_v2.llm_optimizer.AIProviderFactory"
        ) as mock_factory:
            mock_factory.create_provider.return_value = Mock()
            optimizer = LLMOptimizer()

            assert optimizer.llm_config is not None
            assert optimizer.retry_config is not None
            mock_factory.create_provider.assert_called_once()

    def test_initialization_with_custom_config(self, mock_provider):
        """测试使用自定义配置初始化"""
        llm_config = LLMConfig(model="custom-model", max_tokens=2048)
        retry_config = LLMOptimizerConfig(max_retries=5)

        optimizer = LLMOptimizer(
            provider=mock_provider,
            llm_config=llm_config,
            retry_config=retry_config,
        )

        assert optimizer.llm_config.model == "custom-model"
        assert optimizer.llm_config.max_tokens == 2048
        assert optimizer.retry_config.max_retries == 5
        assert optimizer.provider == mock_provider

    def test_initialization_with_provider_only(self, mock_provider):
        """测试仅提供provider初始化"""
        optimizer = LLMOptimizer(provider=mock_provider)

        assert optimizer.provider == mock_provider
        assert optimizer.llm_config is not None
        assert optimizer.retry_config is not None
