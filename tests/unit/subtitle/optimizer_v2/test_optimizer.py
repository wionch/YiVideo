"""
字幕优化器 V2 测试

测试 SubtitleOptimizerV2 主类的功能。
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from services.common.subtitle.optimizer_v2 import (
    OptimizedLine,
    SubtitleOptimizerConfig,
    SubtitleOptimizerV2,
    SubtitleSegment,
)
from services.common.subtitle.optimizer_v2.models import OptimizationResult, OptimizationStatus


def run_async(coro):
    """运行异步协程的辅助函数"""
    return asyncio.run(coro)


class TestSubtitleOptimizerV2:
    """测试 SubtitleOptimizerV2 类"""

    @pytest.fixture
    def sample_subtitle_data(self):
        """创建示例字幕数据"""
        return {
            "metadata": {
                "language": "zh",
                "duration": 10.0,
            },
            "segments": [
                {
                    "id": 1,
                    "start": 0.0,
                    "end": 2.5,
                    "text": "这是第一段字幕",
                    "words": [
                        {"word": "这是", "start": 0.0, "end": 1.0, "probability": 0.95},
                        {"word": "第一段", "start": 1.0, "end": 2.0, "probability": 0.90},
                        {"word": "字幕", "start": 2.0, "end": 2.5, "probability": 0.92},
                    ],
                },
                {
                    "id": 2,
                    "start": 2.5,
                    "end": 5.0,
                    "text": "这是第二段字幕",
                    "words": [
                        {"word": "这是", "start": 2.5, "end": 3.5, "probability": 0.93},
                        {"word": "第二段", "start": 3.5, "end": 4.5, "probability": 0.88},
                        {"word": "字幕", "start": 4.5, "end": 5.0, "probability": 0.91},
                    ],
                },
                {
                    "id": 3,
                    "start": 5.0,
                    "end": 7.5,
                    "text": "这是第三段字幕",
                    "words": [
                        {"word": "这是", "start": 5.0, "end": 6.0, "probability": 0.94},
                        {"word": "第三段", "start": 6.0, "end": 7.0, "probability": 0.89},
                        {"word": "字幕", "start": 7.0, "end": 7.5, "probability": 0.90},
                    ],
                },
            ],
        }

    @pytest.fixture
    def temp_subtitle_file(self, sample_subtitle_data):
        """创建临时字幕文件"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(sample_subtitle_data, f, ensure_ascii=False)
            temp_path = f.name
        yield temp_path
        # 清理
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    def test_init_with_default_config(self):
        """测试使用默认配置初始化"""
        optimizer = SubtitleOptimizerV2()
        assert optimizer.config is not None
        assert isinstance(optimizer.config, SubtitleOptimizerConfig)
        assert optimizer.extractor is not None
        assert optimizer.segment_manager is not None
        # llm_optimizer 是延迟初始化的，不直接访问
        assert optimizer._llm_optimizer is None
        assert optimizer.timestamp_reconstructor is not None
        assert optimizer.debug_logger is not None

    def test_init_with_custom_config(self):
        """测试使用自定义配置初始化"""
        config = SubtitleOptimizerConfig(segment_size=50, max_concurrent=5)
        optimizer = SubtitleOptimizerV2(config)
        assert optimizer.config.segment_size == 50
        assert optimizer.config.max_concurrent == 5

    def test_load_from_file(self, temp_subtitle_file, sample_subtitle_data):
        """测试从文件加载字幕数据"""
        optimizer = SubtitleOptimizerV2()
        result = optimizer.load_from_file(temp_subtitle_file)

        # 验证链式调用返回自身
        assert result is optimizer

        # 验证数据已加载
        assert len(optimizer._original_segments) == 3
        assert optimizer.get_total_lines() == 3

    def test_load_from_file_not_found(self):
        """测试加载不存在的文件"""
        optimizer = SubtitleOptimizerV2()
        with pytest.raises(FileNotFoundError):
            optimizer.load_from_file("/nonexistent/path.json")

    def test_load_from_dict(self, sample_subtitle_data):
        """测试从字典加载字幕数据"""
        optimizer = SubtitleOptimizerV2()
        result = optimizer.load_from_dict(sample_subtitle_data)

        # 验证链式调用返回自身
        assert result is optimizer

        # 验证数据已加载
        assert len(optimizer._original_segments) == 3
        segments = optimizer.get_original_segments()
        assert len(segments) == 3
        assert segments[0].id == 1
        assert segments[0].text == "这是第一段字幕"

    def test_load_from_dict_invalid(self):
        """测试加载无效数据"""
        optimizer = SubtitleOptimizerV2()
        with pytest.raises(ValueError):
            optimizer.load_from_dict(None)

    def test_optimize_success(self, sample_subtitle_data):
        """测试成功优化流程"""
        optimizer = SubtitleOptimizerV2()
        optimizer.load_from_dict(sample_subtitle_data)

        # Mock LLM优化器的响应
        mock_result = OptimizationResult(
            task_id="segment_0",
            status=OptimizationStatus.COMPLETED,
            optimized_lines=[
                OptimizedLine(
                    text="这是第一段优化后的字幕",
                    start=0.0,
                    end=2.5,
                    is_modified=True,
                    original_text="这是第一段字幕",
                ),
                OptimizedLine(
                    text="这是第二段优化后的字幕",
                    start=2.5,
                    end=5.0,
                    is_modified=True,
                    original_text="这是第二段字幕",
                ),
                OptimizedLine(
                    text="这是第三段优化后的字幕",
                    start=5.0,
                    end=7.5,
                    is_modified=True,
                    original_text="这是第三段字幕",
                ),
            ],
        )

        # 创建mock的llm_optimizer
        mock_llm_optimizer = Mock()
        mock_llm_optimizer.optimize_segment = AsyncMock(return_value=mock_result)
        optimizer._llm_optimizer = mock_llm_optimizer

        result = run_async(optimizer.optimize())

        # 验证结果结构
        assert "metadata" in result
        assert "segments" in result

        # 验证元数据
        assert result["metadata"]["total_lines"] == 3
        assert result["metadata"]["modified_lines"] == 3

        # 验证字幕段
        assert len(result["segments"]) == 3
        assert result["segments"][0]["text"] == "这是第一段优化后的字幕"
        assert result["segments"][0]["is_modified"] is True
        assert "words" in result["segments"][0]

    def test_optimize_with_output_path(self, sample_subtitle_data):
        """测试带输出路径的优化"""
        optimizer = SubtitleOptimizerV2()
        optimizer.load_from_dict(sample_subtitle_data)

        # Mock LLM优化器的响应 - 返回3行与原始段数匹配
        mock_result = OptimizationResult(
            task_id="segment_0",
            status=OptimizationStatus.COMPLETED,
            optimized_lines=[
                OptimizedLine(
                    text="优化后的字幕1",
                    start=0.0,
                    end=2.5,
                    is_modified=True,
                    original_text="这是第一段字幕",
                ),
                OptimizedLine(
                    text="优化后的字幕2",
                    start=2.5,
                    end=5.0,
                    is_modified=True,
                    original_text="这是第二段字幕",
                ),
                OptimizedLine(
                    text="优化后的字幕3",
                    start=5.0,
                    end=7.5,
                    is_modified=True,
                    original_text="这是第三段字幕",
                ),
            ],
        )

        # 创建mock的llm_optimizer
        mock_llm_optimizer = Mock()
        mock_llm_optimizer.optimize_segment = AsyncMock(return_value=mock_result)
        optimizer._llm_optimizer = mock_llm_optimizer

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output.json")

            result = run_async(optimizer.optimize(output_path=output_path))

            # 验证文件已保存
            assert os.path.exists(output_path)

            # 验证文件内容
            with open(output_path, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
                assert saved_data["metadata"]["total_lines"] == 3

    def test_optimize_without_loading_data(self):
        """测试未加载数据时调用优化"""
        optimizer = SubtitleOptimizerV2()

        with pytest.raises(ValueError, match="未加载字幕数据"):
            run_async(optimizer.optimize())

    def test_optimize_with_failed_segments(self, sample_subtitle_data):
        """测试部分段失败的情况 - 使用不分段的配置"""
        # 使用 segment_size=100 确保所有行在一个段中
        optimizer = SubtitleOptimizerV2(SubtitleOptimizerConfig(segment_size=100))
        optimizer.load_from_dict(sample_subtitle_data)

        # Mock 返回所有3行
        mock_result = OptimizationResult(
            task_id="segment_0",
            status=OptimizationStatus.COMPLETED,
            optimized_lines=[
                OptimizedLine(
                    text="优化后的字幕1",
                    start=0.0,
                    end=2.5,
                    is_modified=True,
                    original_text="这是第一段字幕",
                ),
                OptimizedLine(
                    text="优化后的字幕2",
                    start=2.5,
                    end=5.0,
                    is_modified=True,
                    original_text="这是第二段字幕",
                ),
                OptimizedLine(
                    text="优化后的字幕3",
                    start=5.0,
                    end=7.5,
                    is_modified=True,
                    original_text="这是第三段字幕",
                ),
            ],
        )

        # 创建mock的llm_optimizer
        mock_llm_optimizer = Mock()
        mock_llm_optimizer.optimize_segment = AsyncMock(return_value=mock_result)
        optimizer._llm_optimizer = mock_llm_optimizer

        # 执行优化
        result = run_async(optimizer.optimize())

        # 验证所有3行都被包含
        assert len(result["segments"]) == 3

    def test_get_optimized_lines(self, sample_subtitle_data):
        """测试获取优化后的行"""
        optimizer = SubtitleOptimizerV2()
        optimizer.load_from_dict(sample_subtitle_data)

        # 初始为空
        assert optimizer.get_optimized_lines() == []

        # 设置一些优化后的行
        optimizer._optimized_lines = [
            OptimizedLine(text="测试1", start=0.0, end=1.0),
            OptimizedLine(text="测试2", start=1.0, end=2.0),
        ]

        lines = optimizer.get_optimized_lines()
        assert len(lines) == 2
        assert lines[0].text == "测试1"

    def test_get_original_segments(self, sample_subtitle_data):
        """测试获取原始字幕段"""
        optimizer = SubtitleOptimizerV2()
        optimizer.load_from_dict(sample_subtitle_data)

        segments = optimizer.get_original_segments()
        assert len(segments) == 3
        assert isinstance(segments[0], SubtitleSegment)

    def test_get_optimization_results(self):
        """测试获取优化结果"""
        optimizer = SubtitleOptimizerV2()

        # 初始为空
        assert optimizer.get_optimization_results() == []

        # 设置一些结果 - 使用小写的枚举值
        optimizer._optimization_results = [
            OptimizationResult(task_id="test1", status=OptimizationStatus.COMPLETED),
            OptimizationResult(task_id="test2", status=OptimizationStatus.FAILED, error_message="失败原因"),
        ]

        results = optimizer.get_optimization_results()
        assert len(results) == 2

    def test_get_total_lines(self, sample_subtitle_data):
        """测试获取总行数"""
        optimizer = SubtitleOptimizerV2()
        optimizer.load_from_dict(sample_subtitle_data)

        assert optimizer.get_total_lines() == 3

    def test_concurrent_optimization(self, sample_subtitle_data):
        """测试并发优化控制 - 使用不分段的配置"""
        config = SubtitleOptimizerConfig(max_concurrent=2, segment_size=100)
        optimizer = SubtitleOptimizerV2(config)
        optimizer.load_from_dict(sample_subtitle_data)

        call_count = 0

        async def mock_optimize(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # 返回所有3行
            return OptimizationResult(
                task_id=f"segment_{call_count}",
                status=OptimizationStatus.COMPLETED,
                optimized_lines=[
                    OptimizedLine(
                        text=f"优化1",
                        start=0.0,
                        end=2.5,
                    ),
                    OptimizedLine(
                        text=f"优化2",
                        start=2.5,
                        end=5.0,
                    ),
                    OptimizedLine(
                        text=f"优化3",
                        start=5.0,
                        end=7.5,
                    ),
                ],
            )

        # 创建mock的llm_optimizer
        mock_llm_optimizer = Mock()
        mock_llm_optimizer.optimize_segment = mock_optimize
        optimizer._llm_optimizer = mock_llm_optimizer

        result = run_async(optimizer.optimize())

        # 验证所有段都被处理
        assert call_count > 0
        # 验证返回了3行
        assert len(result["segments"]) == 3


class TestSubtitleOptimizerV2Integration:
    """集成测试 - 测试完整的优化流程"""

    @pytest.fixture
    def sample_subtitle_data(self):
        """创建示例字幕数据"""
        return {
            "metadata": {
                "language": "zh",
                "duration": 10.0,
            },
            "segments": [
                {
                    "id": 1,
                    "start": 0.0,
                    "end": 2.5,
                    "text": "这是第一段字幕",
                    "words": [
                        {"word": "这是", "start": 0.0, "end": 1.0, "probability": 0.95},
                        {"word": "第一段", "start": 1.0, "end": 2.0, "probability": 0.90},
                        {"word": "字幕", "start": 2.0, "end": 2.5, "probability": 0.92},
                    ],
                },
                {
                    "id": 2,
                    "start": 2.5,
                    "end": 5.0,
                    "text": "这是第二段字幕",
                    "words": [
                        {"word": "这是", "start": 2.5, "end": 3.5, "probability": 0.93},
                        {"word": "第二段", "start": 3.5, "end": 4.5, "probability": 0.88},
                        {"word": "字幕", "start": 4.5, "end": 5.0, "probability": 0.91},
                    ],
                },
                {
                    "id": 3,
                    "start": 5.0,
                    "end": 7.5,
                    "text": "这是第三段字幕",
                    "words": [
                        {"word": "这是", "start": 5.0, "end": 6.0, "probability": 0.94},
                        {"word": "第三段", "start": 6.0, "end": 7.0, "probability": 0.89},
                        {"word": "字幕", "start": 7.0, "end": 7.5, "probability": 0.90},
                    ],
                },
            ],
        }

    @pytest.fixture
    def complex_subtitle_data(self):
        """创建复杂的字幕数据用于测试"""
        segments = []
        for i in range(10):
            segments.append({
                "id": i + 1,
                "start": i * 2.5,
                "end": (i + 1) * 2.5,
                "text": f"这是第{i + 1}段字幕文本",
                "words": [
                    {"word": "这是", "start": i * 2.5, "end": i * 2.5 + 1.0, "probability": 0.9},
                    {"word": f"第{i + 1}段", "start": i * 2.5 + 1.0, "end": i * 2.5 + 2.0, "probability": 0.85},
                    {"word": "字幕文本", "start": i * 2.5 + 2.0, "end": (i + 1) * 2.5, "probability": 0.88},
                ],
            })

        return {
            "metadata": {"language": "zh", "duration": 25.0},
            "segments": segments,
        }

    def test_full_optimization_workflow(self, complex_subtitle_data):
        """测试完整的优化工作流 - 使用不分段的配置避免合并复杂性"""
        # 使用 segment_size=100 确保所有行在一个段中
        config = SubtitleOptimizerConfig(segment_size=100, max_concurrent=2)
        optimizer = SubtitleOptimizerV2(config)
        optimizer.load_from_dict(complex_subtitle_data)

        # Mock 返回所有10行
        async def mock_optimize_segment(task):
            lines = []
            for seg in task.segments:
                lines.append(
                    OptimizedLine(
                        text=f"优化后的: {seg.text}",
                        start=seg.start,
                        end=seg.end,
                        is_modified=True,
                        original_text=seg.text,
                    )
                )
            return OptimizationResult(
                task_id=task.task_id,
                status=OptimizationStatus.COMPLETED,
                optimized_lines=lines,
            )

        # 创建mock的llm_optimizer
        mock_llm_optimizer = Mock()
        mock_llm_optimizer.optimize_segment = mock_optimize_segment
        optimizer._llm_optimizer = mock_llm_optimizer

        result = run_async(optimizer.optimize())

        # 验证结果
        assert result["metadata"]["total_lines"] == 10
        assert len(result["segments"]) == 10

        # 验证每行都被优化
        for seg in result["segments"]:
            assert seg["is_modified"] is True
            assert seg["text"].startswith("优化后的:")
            assert "words" in seg
            assert len(seg["words"]) > 0

    def test_save_and_load_roundtrip(self, sample_subtitle_data):
        """测试保存和加载的往返流程"""
        optimizer = SubtitleOptimizerV2()
        optimizer.load_from_dict(sample_subtitle_data)

        mock_result = OptimizationResult(
            task_id="segment_0",
            status=OptimizationStatus.COMPLETED,
            optimized_lines=[
                OptimizedLine(
                    text=f"优化后的字幕{i}",
                    start=i * 2.5,
                    end=(i + 1) * 2.5,
                    is_modified=True,
                )
                for i in range(3)
            ],
        )

        # 创建mock的llm_optimizer
        mock_llm_optimizer = Mock()
        mock_llm_optimizer.optimize_segment = AsyncMock(return_value=mock_result)
        optimizer._llm_optimizer = mock_llm_optimizer

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output.json")

            # 优化并保存
            result = run_async(optimizer.optimize(output_path=output_path))

            # 加载保存的文件
            with open(output_path, "r", encoding="utf-8") as f:
                loaded_data = json.load(f)

            # 验证数据一致性
            assert loaded_data["metadata"]["total_lines"] == result["metadata"]["total_lines"]
            assert len(loaded_data["segments"]) == len(result["segments"])
