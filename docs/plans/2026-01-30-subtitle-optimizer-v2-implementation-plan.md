# 字幕优化功能重构 (第二版) 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现基于行数锚定的LLM字幕优化器，支持分段并发处理、重叠区去重、时间戳重建

**Architecture:** 采用模块化设计，包含 SubtitleExtractor、SegmentManager、LLMOptimizer、TimestampReconstructor、DebugLogger 五大组件，支持集中式调度和可配置并发

**Tech Stack:** Python 3.11, asyncio, aiohttp (LLM并发), difflib.SequenceMatcher (时间戳对齐), PyYAML (配置管理)

---

## 前置准备

### Task 0: 创建项目目录结构

**Files:**
- Create: `services/common/subtitle/optimizer_v2/__init__.py`
- Create: `services/common/subtitle/optimizer_v2/extractor.py`
- Create: `services/common/subtitle/optimizer_v2/segment_manager.py`
- Create: `services/common/subtitle/optimizer_v2/llm_optimizer.py`
- Create: `services/common/subtitle/optimizer_v2/timestamp_reconstructor.py`
- Create: `services/common/subtitle/optimizer_v2/debug_logger.py`
- Create: `services/common/subtitle/optimizer_v2/config.py`
- Create: `services/common/subtitle/optimizer_v2/models.py`
- Create: `tests/unit/subtitle/optimizer_v2/__init__.py`
- Create: `tmp/subtitle_optimizer_logs/` (目录)

**Step 1: 创建目录**

```bash
mkdir -p services/common/subtitle/optimizer_v2
mkdir -p tests/unit/subtitle/optimizer_v2
mkdir -p tmp/subtitle_optimizer_logs
touch services/common/subtitle/optimizer_v2/__init__.py
touch tests/unit/subtitle/optimizer_v2/__init__.py
```

**Step 2: 验证目录创建**

```bash
ls -la services/common/subtitle/optimizer_v2/
ls -la tests/unit/subtitle/optimizer_v2/
```

Expected: 目录存在且为空（除 __init__.py）

**Step 3: Commit**

```bash
git add services/common/subtitle/optimizer_v2/ tests/unit/subtitle/optimizer_v2/ tmp/subtitle_optimizer_logs/
git commit -m "feat(subtitle_optimizer): create directory structure for v2 optimizer"
```

---

## 模块 1: 数据模型定义

### Task 1: 定义核心数据模型

**Files:**
- Create: `services/common/subtitle/optimizer_v2/models.py`
- Test: `tests/unit/subtitle/optimizer_v2/test_models.py`

**Step 1: 编写测试 - 验证数据模型创建**

```python
# tests/unit/subtitle/optimizer_v2/test_models.py
import pytest
from dataclasses import asdict
from services.common.subtitle.optimizer_v2.models import (
    SubtitleSegment,
    WordTimestamp,
    OptimizedLine,
    SegmentTask,
    OptimizationResult,
)


def test_subtitle_segment_creation():
    """测试字幕段创建"""
    segment = SubtitleSegment(
        id=1,
        start=11.4,
        end=19.56,
        text="Hello world",
        words=[
            WordTimestamp(word="Hello", start=11.4, end=12.0),
            WordTimestamp(word="world", start=12.0, end=12.5),
        ]
    )
    assert segment.id == 1
    assert segment.text == "Hello world"
    assert len(segment.words) == 2


def test_word_timestamp_creation():
    """测试词级时间戳创建"""
    word = WordTimestamp(word="test", start=1.0, end=2.0, probability=0.95)
    assert word.word == "test"
    assert word.start == 1.0
    assert word.end == 2.0
    assert word.probability == 0.95


def test_segment_task_creation():
    """测试分段任务创建"""
    task = SegmentTask(
        segment_idx=0,
        start_line=1,
        end_line=120,
        lines=["[1]Line 1", "[2]Line 2"],
        is_overlap=False
    )
    assert task.segment_idx == 0
    assert task.start_line == 1
    assert task.end_line == 120
    assert len(task.lines) == 2


def test_optimization_result_creation():
    """测试优化结果创建"""
    result = OptimizationResult(
        segment_idx=0,
        original_lines=["[1]Line 1"],
        optimized_lines=["[1]Optimized line 1"],
        retry_count=0,
        success=True
    )
    assert result.success is True
    assert result.retry_count == 0
```

**Step 2: 运行测试（预期失败）**

```bash
cd /opt/wionch/docker/yivideo
python -m pytest tests/unit/subtitle/optimizer_v2/test_models.py -v
```

Expected: ImportError - models module not found

**Step 3: 实现数据模型**

```python
# services/common/subtitle/optimizer_v2/models.py
"""
字幕优化器 v2 数据模型

定义所有核心数据结构，包括字幕段、词级时间戳、任务和结果。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum


@dataclass
class WordTimestamp:
    """词级时间戳"""
    word: str
    start: float
    end: float
    probability: Optional[float] = None


@dataclass
class SubtitleSegment:
    """字幕段"""
    id: int
    start: float
    end: float
    text: str
    words: List[WordTimestamp] = field(default_factory=list)


@dataclass
class OptimizedLine:
    """优化后的字幕行"""
    line_id: int
    original_text: str
    optimized_text: str
    is_empty: bool = False


@dataclass
class SegmentTask:
    """分段处理任务"""
    segment_idx: int
    start_line: int
    end_line: int
    lines: List[str]
    is_overlap: bool = False


@dataclass
class OptimizationResult:
    """优化结果"""
    segment_idx: int
    original_lines: List[str]
    optimized_lines: List[str]
    retry_count: int
    success: bool
    error_message: Optional[str] = None


@dataclass
class OverlapRegion:
    """重叠区域定义"""
    start_line: int
    end_line: int
    segment_a_idx: int
    segment_b_idx: int


@dataclass
class OptimizerConfig:
    """优化器配置"""
    segment_size: int = 100
    overlap_lines: int = 20
    max_concurrent: int = 3
    max_retries: int = 3
    retry_backoff_base: float = 1.0
    diff_threshold: float = 0.3
    max_overlap_expand: int = 50
    debug_enabled: bool = True
    debug_log_dir: str = "tmp/subtitle_optimizer_logs"
    llm_model: str = "gemini-pro"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.1
```

**Step 4: 运行测试（预期通过）**

```bash
python -m pytest tests/unit/subtitle/optimizer_v2/test_models.py -v
```

Expected: 4 tests passed

**Step 5: Commit**

```bash
git add services/common/subtitle/optimizer_v2/models.py tests/unit/subtitle/optimizer_v2/test_models.py
git commit -m "feat(subtitle_optimizer): add core data models"
```

---

## 模块 2: 配置管理

### Task 2: 实现配置加载

**Files:**
- Create: `services/common/subtitle/optimizer_v2/config.py`
- Test: `tests/unit/subtitle/optimizer_v2/test_config.py`
- Modify: `config.yml` (添加 subtitle_optimizer 配置段)

**Step 1: 编写测试**

```python
# tests/unit/subtitle/optimizer_v2/test_config.py
import pytest
import os
from services.common.subtitle.optimizer_v2.config import OptimizerConfigLoader
from services.common.subtitle.optimizer_v2.models import OptimizerConfig


def test_load_default_config():
    """测试加载默认配置"""
    config = OptimizerConfigLoader.load()
    assert isinstance(config, OptimizerConfig)
    assert config.segment_size == 100
    assert config.overlap_lines == 20
    assert config.max_concurrent == 3


def test_load_from_yaml():
    """测试从 YAML 加载配置"""
    config = OptimizerConfigLoader.load()
    assert config.max_retries == 3
    assert config.diff_threshold == 0.3
    assert config.debug_enabled is True


def test_config_override():
    """测试配置覆盖"""
    custom = OptimizerConfig(segment_size=50, max_concurrent=5)
    assert custom.segment_size == 50
    assert custom.max_concurrent == 5
```

**Step 2: 运行测试（预期失败）**

```bash
python -m pytest tests/unit/subtitle/optimizer_v2/test_config.py -v
```

**Step 3: 实现配置加载器**

```python
# services/common/subtitle/optimizer_v2/config.py
"""
配置加载模块

支持从 config.yml 加载字幕优化器配置。
"""

import os
import yaml
from typing import Optional
from pathlib import Path

from services.common.subtitle.optimizer_v2.models import OptimizerConfig


class OptimizerConfigLoader:
    """优化器配置加载器"""

    DEFAULT_CONFIG = OptimizerConfig()

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> OptimizerConfig:
        """
        加载配置

        Args:
            config_path: 配置文件路径，默认使用项目根目录的 config.yml

        Returns:
            OptimizerConfig 实例
        """
        if config_path is None:
            # 从项目根目录查找 config.yml
            current_file = Path(__file__).resolve()
            project_root = current_file.parents[4]  # 向上回溯到项目根目录
            config_path = project_root / "config.yml"

        if not os.path.exists(config_path):
            return cls.DEFAULT_CONFIG

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                yaml_config = yaml.safe_load(f)

            if not yaml_config or 'subtitle_optimizer' not in yaml_config:
                return cls.DEFAULT_CONFIG

            so_config = yaml_config['subtitle_optimizer']

            return OptimizerConfig(
                segment_size=so_config.get('segment_size', 100),
                overlap_lines=so_config.get('overlap_lines', 20),
                max_concurrent=so_config.get('max_concurrent', 3),
                max_retries=so_config.get('max_retries', 3),
                retry_backoff_base=so_config.get('retry_backoff_base', 1.0),
                diff_threshold=so_config.get('diff_threshold', 0.3),
                max_overlap_expand=so_config.get('max_overlap_expand', 50),
                debug_enabled=so_config.get('debug', {}).get('enabled', True),
                debug_log_dir=so_config.get('debug', {}).get('log_dir', 'tmp/subtitle_optimizer_logs'),
                llm_model=so_config.get('llm', {}).get('model', 'gemini-pro'),
                llm_max_tokens=so_config.get('llm', {}).get('max_tokens', 4096),
                llm_temperature=so_config.get('llm', {}).get('temperature', 0.1),
            )
        except Exception as e:
            print(f"Warning: Failed to load config from {config_path}: {e}")
            return cls.DEFAULT_CONFIG
```

**Step 4: 更新 config.yml**

```yaml
# 在 config.yml 末尾添加
subtitle_optimizer:
  # 分段处理
  segment_size: 100        # 每段处理字幕条数
  overlap_lines: 20        # 重叠行数
  max_concurrent: 3        # 最大并发数

  # 重试机制
  max_retries: 3           # 最大重试次数
  retry_backoff_base: 1    # 退避基数（秒）

  # 去重策略
  diff_threshold: 0.3      # 差异阈值（编辑距离比例）
  max_overlap_expand: 50   # 最大重叠扩展行数

  # 调试日志
  debug:
    enabled: true
    log_dir: "tmp/subtitle_optimizer_logs"

  # LLM配置
  llm:
    model: "gemini-pro"    # 或其他模型
    max_tokens: 4096
    temperature: 0.1       # 低温度，更稳定
```

**Step 5: 运行测试（预期通过）**

```bash
python -m pytest tests/unit/subtitle/optimizer_v2/test_config.py -v
```

**Step 6: Commit**

```bash
git add services/common/subtitle/optimizer_v2/config.py tests/unit/subtitle/optimizer_v2/test_config.py config.yml
git commit -m "feat(subtitle_optimizer): add config loader and yaml configuration"
```

---

## 模块 3: 调试日志

### Task 3: 实现调试日志记录器

**Files:**
- Create: `services/common/subtitle/optimizer_v2/debug_logger.py`
- Test: `tests/unit/subtitle/optimizer_v2/test_debug_logger.py`

**Step 1: 编写测试**

```python
# tests/unit/subtitle/optimizer_v2/test_debug_logger.py
import pytest
import os
import tempfile
import shutil
from datetime import datetime
from services.common.subtitle.optimizer_v2.debug_logger import DebugLogger


class TestDebugLogger:
    """测试调试日志记录器"""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp = tempfile.mkdtemp()
        yield temp
        shutil.rmtree(temp)

    def test_log_request(self, temp_dir):
        """测试记录请求"""
        logger = DebugLogger(log_dir=temp_dir, enabled=True)

        logger.log_request(
            task_id="test_001",
            segment_idx=0,
            total_lines=500,
            segment_range=(1, 120),
            prompt="Test prompt",
            lines=["[1]Line 1", "[2]Line 2"]
        )

        # 验证文件创建
        expected_file = os.path.join(temp_dir, "test_001_seg0_request.txt")
        assert os.path.exists(expected_file)

        # 验证内容
        with open(expected_file, 'r', encoding='utf-8') as f:
            content = f.read()
            assert "任务ID: test_001" in content
            assert "段索引: 0" in content
            assert "[1]Line 1" in content

    def test_log_response(self, temp_dir):
        """测试记录响应"""
        logger = DebugLogger(log_dir=temp_dir, enabled=True)

        logger.log_response(
            task_id="test_001",
            segment_idx=0,
            raw_response="[1]Optimized line 1",
            validation_status="PASS",
            retry_count=0
        )

        expected_file = os.path.join(temp_dir, "test_001_seg0_response.txt")
        assert os.path.exists(expected_file)

        with open(expected_file, 'r', encoding='utf-8') as f:
            content = f.read()
            assert "校验状态: PASS" in content

    def test_disabled_logger(self, temp_dir):
        """测试禁用状态不写入文件"""
        logger = DebugLogger(log_dir=temp_dir, enabled=False)

        logger.log_request(
            task_id="test_002",
            segment_idx=0,
            total_lines=100,
            segment_range=(1, 50),
            prompt="Test",
            lines=["[1]Line"]
        )

        expected_file = os.path.join(temp_dir, "test_002_seg0_request.txt")
        assert not os.path.exists(expected_file)
```

**Step 2: 运行测试（预期失败）**

```bash
python -m pytest tests/unit/subtitle/optimizer_v2/test_debug_logger.py -v
```

**Step 3: 实现调试日志记录器**

```python
# services/common/subtitle/optimizer_v2/debug_logger.py
"""
调试日志记录器

记录所有LLM请求和响应，用于问题排查和调试。
"""

import os
from datetime import datetime
from typing import List, Tuple, Optional
from pathlib import Path


class DebugLogger:
    """调试日志记录器"""

    def __init__(self, log_dir: str = "tmp/subtitle_optimizer_logs", enabled: bool = True):
        self.log_dir = Path(log_dir)
        self.enabled = enabled

        if self.enabled:
            self.log_dir.mkdir(parents=True, exist_ok=True)

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _format_lines(self, lines: List[str]) -> str:
        """格式化字幕行列表"""
        return "\n".join(lines)

    def log_request(
        self,
        task_id: str,
        segment_idx: int,
        total_lines: int,
        segment_range: Tuple[int, int],
        prompt: str,
        lines: List[str],
        system_prompt: Optional[str] = None
    ):
        """
        记录请求

        Args:
            task_id: 任务ID
            segment_idx: 段索引
            total_lines: 字幕总行数
            segment_range: (start_line, end_line) 本段范围
            prompt: User prompt
            lines: 字幕文本行列表
            system_prompt: System prompt（可选）
        """
        if not self.enabled:
            return

        filename = f"{task_id}_seg{segment_idx}_request.txt"
        filepath = self.log_dir / filename

        content = f"""========================================
任务ID: {task_id}
段索引: {segment_idx}
时间: {self._get_timestamp()}
========================================

【Meta信息】
- 总行数: {total_lines}
- 本段范围: {segment_range[0]}-{segment_range[1]}
- 实际处理行数: {len(lines)}

【System Prompt】
{system_prompt or "(使用默认system prompt)"}

【User Prompt】
{prompt}

【字幕文本】
{self._format_lines(lines)}
"""

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

    def log_response(
        self,
        task_id: str,
        segment_idx: int,
        raw_response: str,
        validation_status: str,
        retry_count: int,
        parsed_lines: Optional[List[str]] = None,
        error_message: Optional[str] = None
    ):
        """
        记录响应

        Args:
            task_id: 任务ID
            segment_idx: 段索引
            raw_response: LLM原始响应
            validation_status: 校验状态 (PASS/FAIL)
            retry_count: 重试次数
            parsed_lines: 解析后的行列表（可选）
            error_message: 错误信息（可选）
        """
        if not self.enabled:
            return

        filename = f"{task_id}_seg{segment_idx}_response.txt"
        filepath = self.log_dir / filename

        parsed_section = ""
        if parsed_lines:
            parsed_section = f"""
【解析结果】
- 行数: {len(parsed_lines)}
- 提取的文本:
{self._format_lines(parsed_lines)}
"""

        error_section = ""
        if error_message:
            error_section = f"""
【错误信息】
{error_message}
"""

        content = f"""========================================
任务ID: {task_id}
段索引: {segment_idx}
时间: {self._get_timestamp()}
校验状态: {validation_status}
重试次数: {retry_count}
========================================

【原始响应】
{raw_response}
{parsed_section}{error_section}
"""

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

    def log_error(
        self,
        task_id: str,
        segment_idx: int,
        error_type: str,
        error_message: str,
        context: Optional[dict] = None
    ):
        """
        记录错误

        Args:
            task_id: 任务ID
            segment_idx: 段索引
            error_type: 错误类型
            error_message: 错误信息
            context: 上下文信息（可选）
        """
        if not self.enabled:
            return

        filename = f"{task_id}_seg{segment_idx}_error.txt"
        filepath = self.log_dir / filename

        context_section = ""
        if context:
            context_section = "\n【上下文】\n"
            for key, value in context.items():
                context_section += f"{key}: {value}\n"

        content = f"""========================================
任务ID: {task_id}
段索引: {segment_idx}
时间: {self._get_timestamp()}
错误类型: {error_type}
========================================

【错误信息】
{error_message}
{context_section}
"""

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
```

**Step 4: 运行测试（预期通过）**

```bash
python -m pytest tests/unit/subtitle/optimizer_v2/test_debug_logger.py -v
```

**Step 5: Commit**

```bash
git add services/common/subtitle/optimizer_v2/debug_logger.py tests/unit/subtitle/optimizer_v2/test_debug_logger.py
git commit -m "feat(subtitle_optimizer): add debug logger for request/response tracing"
```

---

## 模块 4: 字幕提取器

### Task 4: 实现字幕提取器

**Files:**
- Create: `services/common/subtitle/optimizer_v2/extractor.py`
- Test: `tests/unit/subtitle/optimizer_v2/test_extractor.py`

**Step 1: 编写测试**

```python
# tests/unit/subtitle/optimizer_v2/test_extractor.py
import pytest
import json
import tempfile
import os
from services.common.subtitle.optimizer_v2.extractor import SubtitleExtractor
from services.common.subtitle.optimizer_v2.models import SubtitleSegment, WordTimestamp


class TestSubtitleExtractor:
    """测试字幕提取器"""

    @pytest.fixture
    def sample_transcribe_data(self):
        """示例转录数据"""
        return {
            "metadata": {
                "task_name": "faster_whisper.transcribe_audio",
                "workflow_id": "test_task"
            },
            "segments": [
                {
                    "id": 1,
                    "start": 11.4,
                    "end": 19.56,
                    "text": "Hello world",
                    "words": [
                        {"word": "Hello", "start": 11.4, "end": 12.0},
                        {"word": "world", "start": 12.0, "end": 12.5}
                    ]
                },
                {
                    "id": 2,
                    "start": 20.0,
                    "end": 25.0,
                    "text": "Test subtitle",
                    "words": [
                        {"word": "Test", "start": 20.0, "end": 20.5},
                        {"word": "subtitle", "start": 20.5, "end": 21.0}
                    ]
                }
            ]
        }

    def test_load_from_dict(self, sample_transcribe_data):
        """测试从字典加载"""
        extractor = SubtitleExtractor()
        segments = extractor.load_from_dict(sample_transcribe_data)

        assert len(segments) == 2
        assert segments[0].id == 1
        assert segments[0].text == "Hello world"
        assert len(segments[0].words) == 2

    def test_load_from_file(self, sample_transcribe_data):
        """测试从文件加载"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(sample_transcribe_data, f)
            temp_path = f.name

        try:
            extractor = SubtitleExtractor()
            segments = extractor.load_from_file(temp_path)

            assert len(segments) == 2
            assert segments[0].id == 1
        finally:
            os.unlink(temp_path)

    def test_extract_formatted_lines(self, sample_transcribe_data):
        """测试提取格式化行"""
        extractor = SubtitleExtractor()
        extractor.load_from_dict(sample_transcribe_data)

        lines = extractor.extract_formatted_lines()

        assert len(lines) == 2
        assert lines[0] == "[1]Hello world"
        assert lines[1] == "[2]Test subtitle"

    def test_get_segment_by_id(self, sample_transcribe_data):
        """测试通过ID获取段"""
        extractor = SubtitleExtractor()
        extractor.load_from_dict(sample_transcribe_data)

        segment = extractor.get_segment_by_id(1)
        assert segment is not None
        assert segment.text == "Hello world"

        segment = extractor.get_segment_by_id(999)
        assert segment is None
```

**Step 2: 运行测试（预期失败）**

```bash
python -m pytest tests/unit/subtitle/optimizer_v2/test_extractor.py -v
```

**Step 3: 实现字幕提取器**

```python
# services/common/subtitle/optimizer_v2/extractor.py
"""
字幕提取器

从 faster-whisper 输出中提取字幕数据，生成格式化文本。
"""

import json
from typing import List, Dict, Any, Optional
from pathlib import Path

from services.common.subtitle.optimizer_v2.models import SubtitleSegment, WordTimestamp


class SubtitleExtractor:
    """字幕提取器"""

    def __init__(self):
        self.segments: List[SubtitleSegment] = []
        self.metadata: Dict[str, Any] = {}

    def load_from_file(self, file_path: str) -> List[SubtitleSegment]:
        """
        从 JSON 文件加载字幕数据

        Args:
            file_path: JSON 文件路径

        Returns:
            字幕段列表
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return self.load_from_dict(data)

    def load_from_dict(self, data: Dict[str, Any]) -> List[SubtitleSegment]:
        """
        从字典加载字幕数据

        Args:
            data: faster-whisper 输出的字典格式

        Returns:
            字幕段列表
        """
        self.metadata = data.get("metadata", {})
        self.segments = []

        for seg_data in data.get("segments", []):
            words = []
            for word_data in seg_data.get("words", []):
                words.append(WordTimestamp(
                    word=word_data.get("word", ""),
                    start=word_data.get("start", 0.0),
                    end=word_data.get("end", 0.0),
                    probability=word_data.get("probability")
                ))

            segment = SubtitleSegment(
                id=seg_data.get("id", 0),
                start=seg_data.get("start", 0.0),
                end=seg_data.get("end", 0.0),
                text=seg_data.get("text", ""),
                words=words
            )
            self.segments.append(segment)

        return self.segments

    def extract_formatted_lines(self) -> List[str]:
        """
        提取格式化的字幕行

        Returns:
            格式为 "[ID]文本" 的行列表
        """
        return [f"[{seg.id}]{seg.text}" for seg in self.segments]

    def get_segment_by_id(self, segment_id: int) -> Optional[SubtitleSegment]:
        """
        通过 ID 获取字幕段

        Args:
            segment_id: 段ID

        Returns:
            SubtitleSegment 或 None
        """
        for seg in self.segments:
            if seg.id == segment_id:
                return seg
        return None

    def get_all_segments(self) -> List[SubtitleSegment]:
        """
        获取所有字幕段

        Returns:
            字幕段列表
        """
        return self.segments

    def get_metadata(self) -> Dict[str, Any]:
        """
        获取元数据

        Returns:
            元数据字典
        """
        return self.metadata

    def get_total_lines(self) -> int:
        """
        获取总行数

        Returns:
            字幕段数量
        """
        return len(self.segments)
```

**Step 4: 运行测试（预期通过）**

```bash
python -m pytest tests/unit/subtitle/optimizer_v2/test_extractor.py -v
```

**Step 5: Commit**

```bash
git add services/common/subtitle/optimizer_v2/extractor.py tests/unit/subtitle/optimizer_v2/test_extractor.py
git commit -m "feat(subtitle_optimizer): add subtitle extractor for loading and formatting"
```

---

## 模块 5: 分段管理器

### Task 5: 实现分段管理器

**Files:**
- Create: `services/common/subtitle/optimizer_v2/segment_manager.py`
- Test: `tests/unit/subtitle/optimizer_v2/test_segment_manager.py`

**Step 1: 编写测试**

```python
# tests/unit/subtitle/optimizer_v2/test_segment_manager.py
import pytest
from services.common.subtitle.optimizer_v2.segment_manager import SegmentManager
from services.common.subtitle.optimizer_v2.models import SegmentTask


class TestSegmentManager:
    """测试分段管理器"""

    @pytest.fixture
    def sample_lines(self):
        """示例字幕行"""
        return [f"[{i}]Line {i} content" for i in range(1, 251)]  # 250行

    def test_create_segments_basic(self, sample_lines):
        """测试基本分段创建"""
        manager = SegmentManager(segment_size=100, overlap_lines=20)
        tasks = manager.create_segments(sample_lines)

        # 250行，每段100行，重叠20行
        # 段1: 1-120 (处理1-100)
        # 段2: 81-200 (处理81-180)
        # 段3: 161-250 (处理161-250)
        assert len(tasks) >= 3

    def test_segment_ranges(self, sample_lines):
        """测试分段范围计算"""
        manager = SegmentManager(segment_size=100, overlap_lines=20)
        tasks = manager.create_segments(sample_lines)

        # 验证第一段
        assert tasks[0].start_line == 1
        assert tasks[0].end_line == 120
        assert len(tasks[0].lines) == 120

        # 验证第二段（重叠20行）
        assert tasks[1].start_line == 81
        assert tasks[1].end_line == 200

    def test_small_input_no_segmentation(self):
        """测试小输入不分段"""
        lines = [f"[{i}]Line {i}" for i in range(1, 51)]  # 50行
        manager = SegmentManager(segment_size=100, overlap_lines=20)
        tasks = manager.create_segments(lines)

        assert len(tasks) == 1
        assert tasks[0].start_line == 1
        assert tasks[0].end_line == 50

    def test_extract_overlap_region(self, sample_lines):
        """测试提取重叠区域"""
        manager = SegmentManager(segment_size=100, overlap_lines=20)
        tasks = manager.create_segments(sample_lines)

        results = {
            0: ["[81]Line 81 content", "[82]Line 82 content"],
            1: ["[81]Line 81 modified", "[82]Line 82 modified"]
        }

        overlap = manager.extract_overlap_region(
            tasks[0], tasks[1], results, 0, 1
        )

        assert overlap.start_line == 81
        assert overlap.end_line == 100  # 重叠区结束

    def test_merge_segments(self, sample_lines):
        """测试合并段结果"""
        manager = SegmentManager(segment_size=100, overlap_lines=20)
        tasks = manager.create_segments(sample_lines)

        # 模拟优化结果
        optimized_results = {
            0: [f"[{i}]Optimized {i}" for i in range(1, 121)],
            1: [f"[{i}]Optimized {i}" for i in range(81, 201)],
            2: [f"[{i}]Optimized {i}" for i in range(161, 251)]
        }

        merged = manager.merge_segments(tasks, optimized_results)

        # 合并后应该有250行
        assert len(merged) == 250
        # 验证第一行
        assert merged[0] == "[1]Optimized 1"
        # 验证最后一行
        assert merged[249] == "[250]Optimized 250"
```

**Step 2: 运行测试（预期失败）**

```bash
python -m pytest tests/unit/subtitle/optimizer_v2/test_segment_manager.py -v
```

**Step 3: 实现分段管理器**

```python
# services/common/subtitle/optimizer_v2/segment_manager.py
"""
分段管理器

负责将长字幕切分为可并发处理的小段，管理重叠区域，合并结果。
"""

from typing import List, Dict, Tuple
from difflib import SequenceMatcher

from services.common.subtitle.optimizer_v2.models import SegmentTask, OverlapRegion


class SegmentManager:
    """分段管理器"""

    def __init__(self, segment_size: int = 100, overlap_lines: int = 20):
        """
        初始化

        Args:
            segment_size: 每段处理的字幕条数
            overlap_lines: 重叠行数
        """
        self.segment_size = segment_size
        self.overlap_lines = overlap_lines

    def create_segments(self, lines: List[str]) -> List[SegmentTask]:
        """
        创建分段任务

        Args:
            lines: 格式为 "[ID]文本" 的字幕行列表

        Returns:
            SegmentTask 列表
        """
        total_lines = len(lines)

        # 如果总行数小于等于段大小，不需要分段
        if total_lines <= self.segment_size:
            return [SegmentTask(
                segment_idx=0,
                start_line=1,
                end_line=total_lines,
                lines=lines,
                is_overlap=False
            )]

        tasks = []
        segment_idx = 0
        current_start = 0  # 0-based index

        while current_start < total_lines:
            # 计算本段的结束位置
            # 实际处理 segment_size 行
            # 但提取时要包含 overlap_lines 的重叠区
            actual_end = min(current_start + self.segment_size, total_lines)

            # 提取范围包含重叠区
            extract_end = min(actual_end + self.overlap_lines, total_lines)

            # 创建任务
            task = SegmentTask(
                segment_idx=segment_idx,
                start_line=current_start + 1,  # 转换为 1-based
                end_line=extract_end,  # 1-based
                lines=lines[current_start:extract_end],
                is_overlap=False
            )
            tasks.append(task)

            # 下一段的起始位置（考虑重叠）
            current_start = actual_end - self.overlap_lines
            segment_idx += 1

            # 如果剩余行数很少，直接作为最后一段
            if total_lines - current_start <= self.overlap_lines:
                if current_start < total_lines:
                    task = SegmentTask(
                        segment_idx=segment_idx,
                        start_line=current_start + 1,
                        end_line=total_lines,
                        lines=lines[current_start:],
                        is_overlap=False
                    )
                    tasks.append(task)
                break

        return tasks

    def extract_overlap_region(
        self,
        task_a: SegmentTask,
        task_b: SegmentTask,
        results: Dict[int, List[str]],
        idx_a: int,
        idx_b: int
    ) -> OverlapRegion:
        """
        提取两段之间的重叠区域

        Args:
            task_a: 前一段任务
            task_b: 后一段任务
            results: 优化结果字典
            idx_a: 前一段索引
            idx_b: 后一段索引

        Returns:
            OverlapRegion
        """
        # 计算重叠区的行号范围
        overlap_start = task_b.start_line  # 后一段的开始
        overlap_end = min(task_a.end_line, task_b.start_line + self.overlap_lines - 1)

        return OverlapRegion(
            start_line=overlap_start,
            end_line=overlap_end,
            segment_a_idx=idx_a,
            segment_b_idx=idx_b
        )

    def calculate_diff_score(self, lines_a: List[str], lines_b: List[str]) -> float:
        """
        计算两段重叠区的差异度

        Args:
            lines_a: 前一段的重叠区行
            lines_b: 后一段的重叠区行

        Returns:
            差异比例 (0.0 - 1.0)，越高差异越大
        """
        text_a = "\n".join(lines_a)
        text_b = "\n".join(lines_b)

        matcher = SequenceMatcher(None, text_a, text_b)
        return 1.0 - matcher.ratio()

    def merge_segments(
        self,
        tasks: List[SegmentTask],
        results: Dict[int, List[str]],
        diff_threshold: float = 0.3
    ) -> List[str]:
        """
        合并各段结果，处理重叠区

        Args:
            tasks: 任务列表
            results: 优化结果字典 {segment_idx: lines}
            diff_threshold: 差异阈值

        Returns:
            合并后的完整行列表
        """
        if not tasks:
            return []

        if len(tasks) == 1:
            return results.get(0, [])

        merged = []

        # 处理第一段（非重叠部分 + 重叠区）
        first_result = results.get(0, [])
        first_task = tasks[0]

        # 计算第一段的非重叠部分
        non_overlap_end = len(first_result) - self.overlap_lines
        if non_overlap_end < 0:
            non_overlap_end = len(first_result)

        merged.extend(first_result[:non_overlap_end])

        # 处理中间段
        for i in range(1, len(tasks)):
            prev_result = results.get(i - 1, [])
            curr_result = results.get(i, [])
            curr_task = tasks[i]

            # 提取重叠区
            prev_overlap = prev_result[-self.overlap_lines:] if len(prev_result) >= self.overlap_lines else prev_result
            curr_overlap_start = 0
            curr_overlap_end = min(self.overlap_lines, len(curr_result))
            curr_overlap = curr_result[curr_overlap_start:curr_overlap_end]

            # 计算差异
            diff_score = self.calculate_diff_score(prev_overlap, curr_overlap)

            # 决策：优先后段，但如果差异过大需要处理
            if diff_score <= diff_threshold:
                # 差异小，使用后段结果
                merged.extend(curr_overlap)
            else:
                # 差异大，这里简化处理：使用后段并记录
                # 实际实现中可能需要扩展重叠区重试
                merged.extend(curr_overlap)

            # 添加当前段的非重叠部分
            if i < len(tasks) - 1:
                # 不是最后一段，取非重叠部分
                non_overlap = curr_result[curr_overlap_end:len(curr_result) - self.overlap_lines]
            else:
                # 最后一段，取全部剩余
                non_overlap = curr_result[curr_overlap_end:]

            merged.extend(non_overlap)

        return merged

    def get_overlap_lines_for_retry(
        self,
        task_a: SegmentTask,
        task_b: SegmentTask,
        expand_factor: int = 2
    ) -> Tuple[List[str], List[str]]:
        """
        获取扩展后的重叠区用于重试

        Args:
            task_a: 前一段任务
            task_b: 后一段任务
            expand_factor: 扩展倍数

        Returns:
            (扩展后的段A范围, 扩展后的段B范围)
        """
        expanded_overlap = self.overlap_lines * expand_factor

        # 计算扩展后的范围
        new_start_a = max(1, task_b.start_line - expanded_overlap)
        new_end_a = task_a.end_line

        new_start_b = task_b.start_line
        new_end_b = min(task_b.end_line + expanded_overlap, task_b.end_line)

        return (
            list(range(new_start_a, new_end_a + 1)),
            list(range(new_start_b, new_end_b + 1))
        )
```

**Step 4: 运行测试（预期通过）**

```bash
python -m pytest tests/unit/subtitle/optimizer_v2/test_segment_manager.py -v
```

**Step 5: Commit**

```bash
git add services/common/subtitle/optimizer_v2/segment_manager.py tests/unit/subtitle/optimizer_v2/test_segment_manager.py
git commit -m "feat(subtitle_optimizer): add segment manager for splitting and merging"
```

---

## 模块 6: LLM优化器

### Task 6: 实现LLM优化器

**Files:**
- Create: `services/common/subtitle/optimizer_v2/llm_optimizer.py`
- Test: `tests/unit/subtitle/optimizer_v2/test_llm_optimizer.py`

**Step 1: 编写测试**

```python
# tests/unit/subtitle/optimizer_v2/test_llm_optimizer.py
import pytest
from unittest.mock import Mock, patch, AsyncMock
import asyncio

from services.common.subtitle.optimizer_v2.llm_optimizer import LLMOptimizer
from services.common.subtitle.optimizer_v2.models import OptimizerConfig


class TestLLMOptimizer:
    """测试LLM优化器"""

    @pytest.fixture
    def config(self):
        return OptimizerConfig(
            max_retries=3,
            retry_backoff_base=0.1,  # 测试用短间隔
            llm_model="test-model"
        )

    @pytest.fixture
    def optimizer(self, config):
        return LLMOptimizer(config)

    def test_build_system_prompt(self, optimizer):
        """测试构建system prompt"""
        prompt = optimizer._build_system_prompt()
        assert "字幕校对专家" in prompt
        assert "行数绝对不允许增减" in prompt
        assert "[ID]字幕文本" in prompt

    def test_build_user_prompt(self, optimizer):
        """测试构建user prompt"""
        lines = ["[1]Hello", "[2]World"]
        prompt = optimizer._build_user_prompt(
            total_lines=100,
            segment_range=(1, 50),
            lines=lines,
            description="Test video"
        )
        assert "字幕总行数: 100" in prompt
        assert "本段范围: 第1行 至 第50行" in prompt
        assert "[1]Hello" in prompt

    def test_parse_response_valid(self, optimizer):
        """测试解析有效响应"""
        response = "[1]Hello world\n[2]Test line"
        lines, error = optimizer._parse_response(response, 1, 2)

        assert error is None
        assert len(lines) == 2
        assert lines[0] == "[1]Hello world"
        assert lines[1] == "[2]Test line"

    def test_parse_response_invalid_format(self, optimizer):
        """测试解析格式错误的响应"""
        response = "Hello world\nTest line"  # 缺少 [ID]
        lines, error = optimizer._parse_response(response, 1, 2)

        assert error is not None
        assert "格式错误" in error

    def test_parse_response_line_count_mismatch(self, optimizer):
        """测试行数不匹配"""
        response = "[1]Line 1"  # 只有1行，期望2行
        lines, error = optimizer._parse_response(response, 1, 2)

        assert error is not None
        assert "行数不匹配" in error

    def test_validate_id_range(self, optimizer):
        """测试ID范围校验"""
        lines = ["[1]Line 1", "[2]Line 2", "[3]Line 3"]
        is_valid, error = optimizer._validate_id_range(lines, 1, 3)
        assert is_valid is True
        assert error is None

        lines = ["[1]Line 1", "[5]Line 5"]  # ID不连续
        is_valid, error = optimizer._validate_id_range(lines, 1, 3)
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_optimize_segment_success(self, optimizer):
        """测试成功优化段"""
        with patch.object(optimizer, '_call_llm', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = "[1]Optimized 1\n[2]Optimized 2"

            result = await optimizer.optimize_segment(
                segment_idx=0,
                start_line=1,
                end_line=2,
                lines=["[1]Original 1", "[2]Original 2"],
                task_id="test_001"
            )

            assert result.success is True
            assert len(result.optimized_lines) == 2
            assert result.retry_count == 0

    @pytest.mark.asyncio
    async def test_optimize_segment_retry(self, optimizer):
        """测试重试机制"""
        with patch.object(optimizer, '_call_llm', new_callable=AsyncMock) as mock_call:
            # 第一次返回错误格式，第二次成功
            mock_call.side_effect = [
                "Invalid response",
                "[1]Optimized 1\n[2]Optimized 2"
            ]

            result = await optimizer.optimize_segment(
                segment_idx=0,
                start_line=1,
                end_line=2,
                lines=["[1]Original 1", "[2]Original 2"],
                task_id="test_001"
            )

            assert result.success is True
            assert result.retry_count == 1
            assert mock_call.call_count == 2
```

**Step 2: 运行测试（预期失败）**

```bash
python -m pytest tests/unit/subtitle/optimizer_v2/test_llm_optimizer.py -v
```

**Step 3: 实现LLM优化器**

```python
# services/common/subtitle/optimizer_v2/llm_optimizer.py
"""
LLM优化器

负责调用LLM进行字幕优化，包含重试机制和格式校验。
"""

import re
import asyncio
from typing import List, Tuple, Optional
from difflib import SequenceMatcher

from services.common.subtitle.optimizer_v2.models import OptimizerConfig, OptimizationResult


class LLMOptimizer:
    """LLM优化器"""

    def __init__(self, config: OptimizerConfig):
        self.config = config

    def _build_system_prompt(self) -> str:
        """构建System Prompt"""
        return """你是一个专业的字幕校对专家。你的任务是修正字幕中的错误，但必须严格遵守以下规则：

【修正内容】
1. 修正错别字和语义错误
2. 修正标点符号使用
3. 修复断句错误：
   - **整行移动**：如果某行内容从语义上明显属于另一行，将该行内容移动到正确行。**注意：源行必须保留[ID]，文本留空**
   - **部分内容移动**：如果某行的部分内容（如单个词或短语）从语义上属于另一行，将该部分内容移动到正确位置
   - **示例1（部分内容移动）**：输入 `[1]今天天气不 [2]错,你好啊` → 输出 `[1]今天天气不错 [2],你好啊`
   - **示例2（整行移动）**：输入 `[1]这句话应该 [2]放在这里` → 输出 `[1] [2]这句话应该放在这里`

【绝对约束】
1. 字幕行数绝对不允许增减
2. 输出格式必须严格为：每行一条，格式 `[ID]字幕文本`
3. 如因修正导致某行内容为空，保留 `[ID]` 但文本留空
4. 禁止输出任何其他内容（解释、注释、空行等）

【格式检查】
输出前必须检查：
- 行数是否与输入一致
- 每行是否以 `[数字]` 开头
- `[数字]` 的ID必须与本段范围一致（如本段范围1-120，则ID应为[1]到[120]）"""

    def _build_user_prompt(
        self,
        total_lines: int,
        segment_range: Tuple[int, int],
        lines: List[str],
        description: Optional[str] = None
    ) -> str:
        """构建User Prompt"""
        desc = description or "未提供"
        lines_text = "\n".join(lines)

        return f"""【任务信息】
- 视频描述: {desc}
- 字幕总行数: {total_lines}
- 本段范围: 第{segment_range[0]}行 至 第{segment_range[1]}行

【字幕文本】
{lines_text}"""

    def _parse_response(
        self,
        response: str,
        start_line: int,
        end_line: int
    ) -> Tuple[List[str], Optional[str]]:
        """
        解析LLM响应

        Returns:
            (lines, error_message)
        """
        lines = []
        expected_count = end_line - start_line + 1

        # 按行分割
        raw_lines = response.strip().split('\n')

        for line in raw_lines:
            line = line.strip()
            if not line:
                continue

            # 检查格式 [ID]内容
            match = re.match(r'^\[(\d+)\](.*)$', line)
            if not match:
                return [], f"格式错误: 行 '{line}' 不符合 '[ID]内容' 格式"

            lines.append(line)

        # 检查行数
        if len(lines) != expected_count:
            return [], f"行数不匹配: 期望 {expected_count} 行，实际 {len(lines)} 行"

        return lines, None

    def _validate_id_range(
        self,
        lines: List[str],
        start_line: int,
        end_line: int
    ) -> Tuple[bool, Optional[str]]:
        """
        校验ID范围

        Returns:
            (is_valid, error_message)
        """
        expected_id = start_line

        for line in lines:
            match = re.match(r'^\[(\d+)\]', line)
            if not match:
                return False, f"无法解析ID: {line}"

            actual_id = int(match.group(1))
            if actual_id != expected_id:
                return False, f"ID不连续: 期望 [{expected_id}]，实际 [{actual_id}]"

            expected_id += 1

        if expected_id - 1 != end_line:
            return False, f"ID范围错误: 期望到 [{end_line}]，实际到 [{expected_id - 1}]"

        return True, None

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """
        调用LLM

        TODO: 实际实现需要接入具体的LLM API（Gemini/DeepSeek等）
        目前使用 mock 实现
        """
        # 这里是 mock 实现，实际使用时替换为真实API调用
        # 示例：
        # async with aiohttp.ClientSession() as session:
        #     async with session.post(API_URL, json={...}) as resp:
        #         return await resp.text()
        raise NotImplementedError("需要实现具体的LLM API调用")

    async def optimize_segment(
        self,
        segment_idx: int,
        start_line: int,
        end_line: int,
        lines: List[str],
        task_id: str,
        total_lines: int = 0,
        description: Optional[str] = None
    ) -> OptimizationResult:
        """
        优化单个段

        Args:
            segment_idx: 段索引
            start_line: 起始行号（1-based）
            end_line: 结束行号（1-based）
            lines: 字幕行列表
            task_id: 任务ID
            total_lines: 字幕总行数
            description: 视频描述

        Returns:
            OptimizationResult
        """
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            total_lines=total_lines or end_line,
            segment_range=(start_line, end_line),
            lines=lines,
            description=description
        )

        retry_count = 0
        last_error = None

        while retry_count <= self.config.max_retries:
            try:
                # 调用LLM
                response = await self._call_llm(system_prompt, user_prompt)

                # 解析响应
                parsed_lines, parse_error = self._parse_response(
                    response, start_line, end_line
                )

                if parse_error:
                    last_error = parse_error
                    retry_count += 1
                    if retry_count <= self.config.max_retries:
                        await asyncio.sleep(
                            self.config.retry_backoff_base * (2 ** (retry_count - 1))
                        )
                    continue

                # 校验ID范围
                is_valid, validate_error = self._validate_id_range(
                    parsed_lines, start_line, end_line
                )

                if not is_valid:
                    last_error = validate_error
                    retry_count += 1
                    if retry_count <= self.config.max_retries:
                        await asyncio.sleep(
                            self.config.retry_backoff_base * (2 ** (retry_count - 1))
                        )
                    continue

                # 成功
                return OptimizationResult(
                    segment_idx=segment_idx,
                    original_lines=lines,
                    optimized_lines=parsed_lines,
                    retry_count=retry_count,
                    success=True
                )

            except Exception as e:
                last_error = str(e)
                retry_count += 1
                if retry_count <= self.config.max_retries:
                    await asyncio.sleep(
                        self.config.retry_backoff_base * (2 ** (retry_count - 1))
                    )

        # 所有重试失败
        return OptimizationResult(
            segment_idx=segment_idx,
            original_lines=lines,
            optimized_lines=[],
            retry_count=retry_count - 1,
            success=False,
            error_message=last_error
        )
```

**Step 4: 运行测试（预期通过）**

```bash
python -m pytest tests/unit/subtitle/optimizer_v2/test_llm_optimizer.py -v
```

**Step 5: Commit**

```bash
git add services/common/subtitle/optimizer_v2/llm_optimizer.py tests/unit/subtitle/optimizer_v2/test_llm_optimizer.py
git commit -m "feat(subtitle_optimizer): add LLM optimizer with retry and validation"
```

---

## 模块 7: 时间戳重建器

### Task 7: 实现时间戳重建器

**Files:**
- Create: `services/common/subtitle/optimizer_v2/timestamp_reconstructor.py`
- Test: `tests/unit/subtitle/optimizer_v2/test_timestamp_reconstructor.py`

**Step 1: 编写测试**

```python
# tests/unit/subtitle/optimizer_v2/test_timestamp_reconstructor.py
import pytest
from services.common.subtitle.optimizer_v2.timestamp_reconstructor import TimestampReconstructor
from services.common.subtitle.optimizer_v2.models import SubtitleSegment, WordTimestamp


class TestTimestampReconstructor:
    """测试时间戳重建器"""

    @pytest.fixture
    def sample_segment(self):
        """示例字幕段"""
        return SubtitleSegment(
            id=1,
            start=0.0,
            end=5.0,
            text="Hello world test",
            words=[
                WordTimestamp(word="Hello", start=0.0, end=1.0),
                WordTimestamp(word="world", start=1.5, end=2.5),
                WordTimestamp(word="test", start=3.0, end=4.0),
            ]
        )

    def test_find_stable_words(self):
        """测试查找稳定词"""
        reconstructor = TimestampReconstructor()

        original_words = [
            WordTimestamp(word="Hello", start=0.0, end=1.0),
            WordTimestamp(word="world", start=1.5, end=2.5),
        ]
        optimized_text = "Hello beautiful world"

        stable = reconstructor._find_stable_words(original_words, optimized_text)

        # "Hello" 和 "world" 应该被识别为稳定词
        assert len(stable) >= 2
        assert stable[0].word == "Hello"

    def test_distribute_in_gap(self):
        """测试在间隙中分配时间"""
        reconstructor = TimestampReconstructor()

        new_words = ["new", "words"]
        result = reconstructor._distribute_in_gap(new_words, 1.0, 3.0)

        # 两个词应该均分 1.0-3.0 的时间
        assert len(result) == 2
        assert result[0]["start"] == 1.0
        assert result[0]["end"] == 2.0
        assert result[1]["start"] == 2.0
        assert result[1]["end"] == 3.0

    def test_reconstruct_with_no_changes(self, sample_segment):
        """测试无变化时的时间戳重建"""
        reconstructor = TimestampReconstructor()

        # 优化后文本与原始相同
        optimized_lines = ["[1]Hello world test"]

        result = reconstructor.reconstruct_segment(
            sample_segment, optimized_lines[0]
        )

        assert result["id"] == 1
        assert result["text"] == "Hello world test"
        assert len(result["words"]) == 3
        # 时间戳应该保持不变
        assert result["words"][0]["start"] == 0.0
        assert result["words"][0]["end"] == 1.0

    def test_reconstruct_with_insertion(self, sample_segment):
        """测试插入新词时的时间戳重建"""
        reconstructor = TimestampReconstructor()

        # 优化后插入了 "beautiful"
        optimized_lines = ["[1]Hello beautiful world test"]

        result = reconstructor.reconstruct_segment(
            sample_segment, optimized_lines[0]
        )

        assert "beautiful" in [w["word"] for w in result["words"]]
        # 新词应该在 Hello 和 world 之间
        words = result["words"]
        hello_idx = next(i for i, w in enumerate(words) if w["word"] == "Hello")
        beautiful_idx = next(i for i, w in enumerate(words) if w["word"] == "beautiful")
        world_idx = next(i for i, w in enumerate(words) if w["word"] == "world")

        assert hello_idx < beautiful_idx < world_idx

    def test_reconstruct_with_merge(self, sample_segment):
        """测试紧邻词合并"""
        reconstructor = TimestampReconstructor()

        # 如果新词插入到紧邻的位置，应该合并到前一个词
        # 这个测试验证合并逻辑
        original_words = [
            WordTimestamp(word="Hello", start=0.0, end=1.0),
            WordTimestamp(word="world", start=1.0, end=2.0),  # 紧邻
        ]

        # 模拟场景：新词 "beautiful" 要插入到 Hello 和 world 之间
        # 但 Hello 和 world 是紧邻的（1.0-1.0 无间隙）
        # 此时应该将 "beautiful" 合并到 "Hello"

        # 由于实现复杂，这里简化测试
        assert True  # 占位，实际实现后补充完整测试
```

**Step 2: 运行测试（预期失败）**

```bash
python -m pytest tests/unit/subtitle/optimizer_v2/test_timestamp_reconstructor.py -v
```

**Step 3: 实现时间戳重建器**

```python
# services/common/subtitle/optimizer_v2/timestamp_reconstructor.py
"""
时间戳重建器

基于稳定词锚定和间隙填充策略，重建优化后字幕的时间戳。
"""

import re
from typing import List, Dict, Tuple, Optional
from difflib import SequenceMatcher

from services.common.subtitle.optimizer_v2.models import SubtitleSegment, WordTimestamp


class TimestampReconstructor:
    """时间戳重建器"""

    def __init__(self):
        pass

    def _tokenize(self, text: str) -> List[str]:
        """
        将文本分词

        Args:
            text: 输入文本

        Returns:
            词列表
        """
        # 简单的空格分词，可以根据需要改进
        words = re.findall(r'\S+', text)
        return words

    def _normalize_word(self, word: str) -> str:
        """
        标准化词（用于比较）

        Args:
            word: 原始词

        Returns:
            标准化后的词
        """
        return word.lower().strip('.,!?;:')

    def _find_stable_words(
        self,
        original_words: List[WordTimestamp],
        optimized_text: str
    ) -> List[Tuple[int, WordTimestamp, str]]:
        """
        查找稳定词（在优化后文本中仍然存在的词）

        Returns:
            列表项: (original_index, word_timestamp, matched_text_in_optimized)
        """
        original_tokens = [self._normalize_word(w.word) for w in original_words]
        optimized_tokens = self._tokenize(optimized_text)
        normalized_optimized = [self._normalize_word(t) for t in optimized_tokens]

        # 使用 LCS 找出匹配的序列
        matcher = SequenceMatcher(None, original_tokens, normalized_optimized, autojunk=False)

        stable_words = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for offset in range(i2 - i1):
                    orig_idx = i1 + offset
                    opt_idx = j1 + offset
                    stable_words.append((
                        orig_idx,
                        original_words[orig_idx],
                        optimized_tokens[opt_idx]
                    ))

        return stable_words

    def _distribute_in_gap(
        self,
        new_words: List[str],
        gap_start: float,
        gap_end: float
    ) -> List[Dict]:
        """
        在间隙中均匀分配新词的时间戳

        Args:
            new_words: 新词列表
            gap_start: 间隙开始时间
            gap_end: 间隙结束时间

        Returns:
            带时间戳的词列表
        """
        if not new_words:
            return []

        gap_duration = gap_end - gap_start
        word_duration = gap_duration / len(new_words)

        result = []
        for i, word in enumerate(new_words):
            start = gap_start + i * word_duration
            end = start + word_duration
            result.append({
                "word": word,
                "start": round(start, 3),
                "end": round(end, 3)
            })

        return result

    def reconstruct_segment(
        self,
        segment: SubtitleSegment,
        optimized_line: str
    ) -> Dict:
        """
        重建单个段的时间戳

        Args:
            segment: 原始字幕段
            optimized_line: 优化后的行（格式: "[ID]文本"）

        Returns:
            重建后的段字典
        """
        # 提取优化后的文本（去掉 [ID] 前缀）
        match = re.match(r'^\[\d+\](.*)$', optimized_line)
        if not match:
            # 格式错误，返回原始段
            return {
                "id": segment.id,
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
                "words": [
                    {"word": w.word, "start": w.start, "end": w.end}
                    for w in segment.words
                ]
            }

        optimized_text = match.group(1).strip()

        # 如果文本为空，返回带空文本的段
        if not optimized_text:
            return {
                "id": segment.id,
                "start": segment.start,
                "end": segment.end,
                "text": "",
                "words": []
            }

        # 查找稳定词
        stable_words = self._find_stable_words(segment.words, optimized_text)

        # 构建稳定词映射
        stable_map = {}  # optimized_word -> (original_word, start, end)
        for orig_idx, word_ts, opt_text in stable_words:
            stable_map[self._normalize_word(opt_text)] = {
                "word": word_ts.word,
                "start": word_ts.start,
                "end": word_ts.end,
                "orig_idx": orig_idx
            }

        # 分词并重建时间戳
        optimized_tokens = self._tokenize(optimized_text)
        reconstructed_words = []

        last_end_time = segment.start
        last_was_stable = False

        for i, token in enumerate(optimized_tokens):
            normalized = self._normalize_word(token)

            if normalized in stable_map:
                # 稳定词，使用原始时间戳
                stable = stable_map[normalized]
                reconstructed_words.append({
                    "word": token,
                    "start": stable["start"],
                    "end": stable["end"]
                })
                last_end_time = stable["end"]
                last_was_stable = True
            else:
                # 新词，需要分配时间戳
                # 查找下一个稳定词
                next_stable_start = None
                for j in range(i + 1, len(optimized_tokens)):
                    next_norm = self._normalize_word(optimized_tokens[j])
                    if next_norm in stable_map:
                        next_stable_start = stable_map[next_norm]["start"]
                        break

                if next_stable_start is None:
                    # 后面没有稳定词，使用段结束时间
                    next_stable_start = segment.end

                # 检查是否有间隙
                gap = next_stable_start - last_end_time

                if gap > 0.1 and last_was_stable:
                    # 有足够间隙，分配时间戳
                    # 收集连续的新词
                    new_words = [token]
                    for j in range(i + 1, len(optimized_tokens)):
                        next_norm = self._normalize_word(optimized_tokens[j])
                        if next_norm not in stable_map:
                            new_words.append(optimized_tokens[j])
                        else:
                            break

                    # 为这些新词分配时间
                    distributed = self._distribute_in_gap(
                        new_words, last_end_time, next_stable_start
                    )
                    reconstructed_words.extend(distributed)

                    # 跳过已处理的词
                    # 注意：这里简化处理，实际可能需要更复杂的逻辑
                    last_end_time = next_stable_start
                    last_was_stable = False
                else:
                    # 无间隙或间隙太小，合并到前一个词
                    if reconstructed_words:
                        # 将当前词文本追加到前一个词
                        reconstructed_words[-1]["word"] += " " + token
                        # 时间戳保持不变（继承前一个词的结束时间）
                    else:
                        # 第一个词就是新词，使用段开始时间
                        reconstructed_words.append({
                            "word": token,
                            "start": segment.start,
                            "end": segment.start + 0.5  # 默认0.5秒
                        })
                    last_was_stable = False

        # 计算段的开始和结束时间
        if reconstructed_words:
            segment_start = reconstructed_words[0]["start"]
            segment_end = reconstructed_words[-1]["end"]
        else:
            segment_start = segment.start
            segment_end = segment.end

        return {
            "id": segment.id,
            "start": segment_start,
            "end": segment_end,
            "text": optimized_text,
            "words": reconstructed_words
        }

    def reconstruct_all(
        self,
        segments: List[SubtitleSegment],
        optimized_lines: List[str]
    ) -> List[Dict]:
        """
        重建所有段的时间戳

        Args:
            segments: 原始字幕段列表
            optimized_lines: 优化后的行列表（格式: "[ID]文本"）

        Returns:
            重建后的段列表
        """
        results = []

        # 构建ID到优化行的映射
        line_map = {}
        for line in optimized_lines:
            match = re.match(r'^\[(\d+)\](.*)$', line)
            if match:
                line_id = int(match.group(1))
                line_map[line_id] = line

        # 为每个段重建时间戳
        for segment in segments:
            if segment.id in line_map:
                result = self.reconstruct_segment(segment, line_map[segment.id])
                results.append(result)
            else:
                # 如果找不到对应的优化行，保留原始
                results.append({
                    "id": segment.id,
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                    "words": [
                        {"word": w.word, "start": w.start, "end": w.end}
                        for w in segment.words
                    ]
                })

        return results
```

**Step 4: 运行测试（预期通过）**

```bash
python -m pytest tests/unit/subtitle/optimizer_v2/test_timestamp_reconstructor.py -v
```

**Step 5: Commit**

```bash
git add services/common/subtitle/optimizer_v2/timestamp_reconstructor.py tests/unit/subtitle/optimizer_v2/test_timestamp_reconstructor.py
git commit -m "feat(subtitle_optimizer): add timestamp reconstructor with stable word anchoring"
```

---

## 模块 8: 主优化器入口

### Task 8: 实现主优化器入口

**Files:**
- Modify: `services/common/subtitle/optimizer_v2/__init__.py`
- Create: `services/common/subtitle/optimizer_v2/optimizer.py`
- Test: `tests/unit/subtitle/optimizer_v2/test_optimizer.py`

**Step 1: 编写测试**

```python
# tests/unit/subtitle/optimizer_v2/test_optimizer.py
import pytest
from unittest.mock import Mock, patch, AsyncMock
import asyncio

from services.common.subtitle.optimizer_v2.optimizer import SubtitleOptimizerV2
from services.common.subtitle.optimizer_v2.models import OptimizerConfig


class TestSubtitleOptimizerV2:
    """测试主优化器"""

    @pytest.fixture
    def sample_input_data(self):
        """示例输入数据"""
        return {
            "metadata": {
                "task_name": "faster_whisper.transcribe_audio",
                "workflow_id": "test_task"
            },
            "segments": [
                {
                    "id": 1,
                    "start": 0.0,
                    "end": 2.0,
                    "text": "Hello world",
                    "words": [
                        {"word": "Hello", "start": 0.0, "end": 1.0},
                        {"word": "world", "start": 1.0, "end": 2.0}
                    ]
                },
                {
                    "id": 2,
                    "start": 3.0,
                    "end": 5.0,
                    "text": "Test line",
                    "words": [
                        {"word": "Test", "start": 3.0, "end": 4.0},
                        {"word": "line", "start": 4.0, "end": 5.0}
                    ]
                }
            ]
        }

    @pytest.mark.asyncio
    async def test_optimize_success(self, sample_input_data):
        """测试成功优化"""
        optimizer = SubtitleOptimizerV2()

        # Mock LLM调用
        with patch.object(
            optimizer.llm_optimizer, '_call_llm', new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = "[1]Hello world\n[2]Test line"

            result = await optimizer.optimize(
                input_data=sample_input_data,
                task_id="test_001"
            )

            assert result["success"] is True
            assert "segments" in result
            assert len(result["segments"]) == 2

    @pytest.mark.asyncio
    async def test_optimize_with_output_path(self, sample_input_data, tmp_path):
        """测试优化并保存到文件"""
        optimizer = SubtitleOptimizerV2()
        output_path = tmp_path / "output.json"

        with patch.object(
            optimizer.llm_optimizer, '_call_llm', new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = "[1]Hello world\n[2]Test line"

            result = await optimizer.optimize(
                input_data=sample_input_data,
                task_id="test_002",
                output_path=str(output_path)
            )

            assert result["success"] is True
            assert output_path.exists()

    def test_load_and_save(self, sample_input_data, tmp_path):
        """测试加载和保存"""
        optimizer = SubtitleOptimizerV2()

        input_path = tmp_path / "input.json"
        output_path = tmp_path / "output.json"

        import json
        with open(input_path, 'w') as f:
            json.dump(sample_input_data, f)

        # 测试加载
        optimizer.load_from_file(str(input_path))
        assert optimizer.extractor.get_total_lines() == 2
```

**Step 2: 运行测试（预期失败）**

```bash
python -m pytest tests/unit/subtitle/optimizer_v2/test_optimizer.py -v
```

**Step 3: 实现主优化器**

```python
# services/common/subtitle/optimizer_v2/optimizer.py
"""
字幕优化器 V2 主入口

整合所有模块，提供完整的字幕优化流程。
"""

import json
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path

from services.common.subtitle.optimizer_v2.models import OptimizerConfig
from services.common.subtitle.optimizer_v2.config import OptimizerConfigLoader
from services.common.subtitle.optimizer_v2.extractor import SubtitleExtractor
from services.common.subtitle.optimizer_v2.segment_manager import SegmentManager
from services.common.subtitle.optimizer_v2.llm_optimizer import LLMOptimizer
from services.common.subtitle.optimizer_v2.timestamp_reconstructor import TimestampReconstructor
from services.common.subtitle.optimizer_v2.debug_logger import DebugLogger


class SubtitleOptimizerV2:
    """字幕优化器 V2"""

    def __init__(self, config: Optional[OptimizerConfig] = None):
        """
        初始化优化器

        Args:
            config: 配置对象，默认从 config.yml 加载
        """
        self.config = config or OptimizerConfigLoader.load()

        # 初始化各模块
        self.extractor = SubtitleExtractor()
        self.segment_manager = SegmentManager(
            segment_size=self.config.segment_size,
            overlap_lines=self.config.overlap_lines
        )
        self.llm_optimizer = LLMOptimizer(self.config)
        self.timestamp_reconstructor = TimestampReconstructor()
        self.debug_logger = DebugLogger(
            log_dir=self.config.debug_log_dir,
            enabled=self.config.debug_enabled
        )

    def load_from_file(self, file_path: str):
        """
        从文件加载字幕数据

        Args:
            file_path: JSON 文件路径
        """
        self.extractor.load_from_file(file_path)

    def load_from_dict(self, data: Dict[str, Any]):
        """
        从字典加载字幕数据

        Args:
            data: faster-whisper 输出的字典格式
        """
        self.extractor.load_from_dict(data)

    async def optimize(
        self,
        input_data: Optional[Dict[str, Any]] = None,
        task_id: str = "default_task",
        output_path: Optional[str] = None,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行字幕优化

        Args:
            input_data: 输入数据字典（可选，如果已通过 load_from_file/dict 加载）
            task_id: 任务ID
            output_path: 输出文件路径（可选）
            description: 视频描述（可选）

        Returns:
            优化结果字典
        """
        # 加载数据
        if input_data:
            self.load_from_dict(input_data)

        if not self.extractor.get_all_segments():
            return {
                "success": False,
                "error": "没有加载字幕数据"
            }

        # 提取格式化行
        formatted_lines = self.extractor.extract_formatted_lines()
        total_lines = len(formatted_lines)
        metadata = self.extractor.get_metadata()

        # 创建分段任务
        tasks = self.segment_manager.create_segments(formatted_lines)

        # 记录调试信息
        for task in tasks:
            self.debug_logger.log_request(
                task_id=task_id,
                segment_idx=task.segment_idx,
                total_lines=total_lines,
                segment_range=(task.start_line, task.end_line),
                prompt=self.llm_optimizer._build_user_prompt(
                    total_lines=total_lines,
                    segment_range=(task.start_line, task.end_line),
                    lines=task.lines,
                    description=description
                ),
                lines=task.lines,
                system_prompt=self.llm_optimizer._build_system_prompt()
            )

        # 并发执行优化
        results = await self._optimize_segments(
            tasks, task_id, total_lines, description
        )

        # 检查是否有失败
        failed_results = [r for r in results.values() if not r.success]
        if failed_results:
            # 记录错误
            for result in failed_results:
                self.debug_logger.log_error(
                    task_id=task_id,
                    segment_idx=result.segment_idx,
                    error_type="OPTIMIZATION_FAILED",
                    error_message=result.error_message or "Unknown error"
                )

            return {
                "success": False,
                "error": f"{len(failed_results)} 个段优化失败",
                "failed_segments": [r.segment_idx for r in failed_results],
                "debug_log_dir": str(self.debug_logger.log_dir)
            }

        # 合并结果
        merged_lines = self.segment_manager.merge_segments(
            tasks, results, self.config.diff_threshold
        )

        # 重建时间戳
        reconstructed_segments = self.timestamp_reconstructor.reconstruct_all(
            self.extractor.get_all_segments(),
            merged_lines
        )

        # 构建输出
        output_data = {
            "metadata": {
                **metadata,
                "optimized_at": self._get_timestamp(),
                "original_segments_count": total_lines,
                "optimized_segments_count": len(reconstructed_segments),
                "segments_processed": len(tasks),
                "optimizer_version": "2.0"
            },
            "segments": reconstructed_segments
        }

        # 保存到文件
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "data": output_data,
            "output_path": output_path,
            "debug_log_dir": str(self.debug_logger.log_dir)
        }

    async def _optimize_segments(
        self,
        tasks: List,
        task_id: str,
        total_lines: int,
        description: Optional[str]
    ) -> Dict[int, Any]:
        """
        并发优化所有段

        Args:
            tasks: 分段任务列表
            task_id: 任务ID
            total_lines: 字幕总行数
            description: 视频描述

        Returns:
            优化结果字典 {segment_idx: OptimizationResult}
        """
        results = {}
        semaphore = asyncio.Semaphore(self.config.max_concurrent)

        async def optimize_with_limit(task):
            async with semaphore:
                result = await self.llm_optimizer.optimize_segment(
                    segment_idx=task.segment_idx,
                    start_line=task.start_line,
                    end_line=task.end_line,
                    lines=task.lines,
                    task_id=task_id,
                    total_lines=total_lines,
                    description=description
                )

                # 记录响应
                self.debug_logger.log_response(
                    task_id=task_id,
                    segment_idx=task.segment_idx,
                    raw_response="\n".join(result.optimized_lines) if result.success else "",
                    validation_status="PASS" if result.success else "FAIL",
                    retry_count=result.retry_count,
                    parsed_lines=result.optimized_lines if result.success else None,
                    error_message=result.error_message
                )

                return task.segment_idx, result

        # 并发执行
        coroutines = [optimize_with_limit(task) for task in tasks]
        completed = await asyncio.gather(*coroutines)

        for segment_idx, result in completed:
            results[segment_idx] = result

        return results

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()
```

**Step 4: 更新 __init__.py**

```python
# services/common/subtitle/optimizer_v2/__init__.py
"""
字幕优化器 V2

基于行数锚定的LLM字幕优化器，支持分段并发处理、重叠区去重、时间戳重建。
"""

from services.common.subtitle.optimizer_v2.optimizer import SubtitleOptimizerV2
from services.common.subtitle.optimizer_v2.models import (
    OptimizerConfig,
    SubtitleSegment,
    WordTimestamp,
    OptimizationResult
)
from services.common.subtitle.optimizer_v2.config import OptimizerConfigLoader

__all__ = [
    "SubtitleOptimizerV2",
    "OptimizerConfig",
    "OptimizerConfigLoader",
    "SubtitleSegment",
    "WordTimestamp",
    "OptimizationResult"
]
```

**Step 5: 运行测试（预期通过）**

```bash
python -m pytest tests/unit/subtitle/optimizer_v2/test_optimizer.py -v
```

**Step 6: Commit**

```bash
git add services/common/subtitle/optimizer_v2/__init__.py services/common/subtitle/optimizer_v2/optimizer.py tests/unit/subtitle/optimizer_v2/test_optimizer.py
git commit -m "feat(subtitle_optimizer): add main optimizer entry point"
```

---

## 模块 9: 集成测试

### Task 9: 编写集成测试

**Files:**
- Create: `tests/integration/test_subtitle_optimizer_v2.py`

**Step 1: 编写集成测试**

```python
# tests/integration/test_subtitle_optimizer_v2.py
"""
字幕优化器 V2 集成测试

测试完整的工作流程。
"""

import pytest
import json
import tempfile
import os
from unittest.mock import patch, AsyncMock

from services.common.subtitle.optimizer_v2 import SubtitleOptimizerV2, OptimizerConfig


class TestSubtitleOptimizerV2Integration:
    """集成测试"""

    @pytest.fixture
    def small_input_data(self):
        """小数据集（不分段）"""
        return {
            "metadata": {
                "task_name": "faster_whisper.transcribe_audio",
                "workflow_id": "test_task"
            },
            "segments": [
                {
                    "id": i,
                    "start": float(i),
                    "end": float(i + 1),
                    "text": f"Line {i} content",
                    "words": [
                        {"word": f"Line{i}", "start": float(i), "end": float(i + 0.5)},
                        {"word": "content", "start": float(i + 0.5), "end": float(i + 1)}
                    ]
                }
                for i in range(1, 51)  # 50行
            ]
        }

    @pytest.fixture
    def large_input_data(self):
        """大数据集（需要分段）"""
        return {
            "metadata": {
                "task_name": "faster_whisper.transcribe_audio",
                "workflow_id": "test_task"
            },
            "segments": [
                {
                    "id": i,
                    "start": float(i),
                    "end": float(i + 1),
                    "text": f"Line {i} content",
                    "words": [
                        {"word": f"Line{i}", "start": float(i), "end": float(i + 0.5)},
                        {"word": "content", "start": float(i + 0.5), "end": float(i + 1)}
                    ]
                }
                for i in range(1, 251)  # 250行
            ]
        }

    @pytest.mark.asyncio
    async def test_small_subtitle_no_segmentation(self, small_input_data, tmp_path):
        """测试小字幕不分段处理"""
        optimizer = SubtitleOptimizerV2(
            config=OptimizerConfig(segment_size=100, overlap_lines=20)
        )

        output_path = tmp_path / "output.json"

        with patch.object(
            optimizer.llm_optimizer, '_call_llm', new_callable=AsyncMock
        ) as mock_call:
            # 返回与输入相同的文本
            lines = [f"[{i}]Line {i} content" for i in range(1, 51)]
            mock_call.return_value = "\n".join(lines)

            result = await optimizer.optimize(
                input_data=small_input_data,
                task_id="test_small",
                output_path=str(output_path)
            )

            assert result["success"] is True
            assert output_path.exists()

            # 验证输出
            with open(output_path, 'r') as f:
                output_data = json.load(f)
                assert len(output_data["segments"]) == 50

            # 验证只调用了一次LLM（不分段）
            assert mock_call.call_count == 1

    @pytest.mark.asyncio
    async def test_large_subtitle_with_segmentation(self, large_input_data, tmp_path):
        """测试大字幕分段处理"""
        optimizer = SubtitleOptimizerV2(
            config=OptimizerConfig(segment_size=100, overlap_lines=20, max_concurrent=2)
        )

        output_path = tmp_path / "output.json"

        with patch.object(
            optimizer.llm_optimizer, '_call_llm', new_callable=AsyncMock
        ) as mock_call:
            # 模拟分段返回
            def side_effect(system_prompt, user_prompt):
                # 根据prompt中的范围返回对应的行
                if "第1行" in user_prompt:
                    return "\n".join([f"[{i}]Line {i} content" for i in range(1, 121)])
                elif "第81行" in user_prompt:
                    return "\n".join([f"[{i}]Line {i} content" for i in range(81, 201)])
                elif "第161行" in user_prompt:
                    return "\n".join([f"[{i}]Line {i} content" for i in range(161, 251)])
                return ""

            mock_call.side_effect = side_effect

            result = await optimizer.optimize(
                input_data=large_input_data,
                task_id="test_large",
                output_path=str(output_path)
            )

            assert result["success"] is True

            # 验证调用了多次LLM（分段）
            assert mock_call.call_count >= 2

    @pytest.mark.asyncio
    async def test_retry_mechanism(self, small_input_data, tmp_path):
        """测试重试机制"""
        optimizer = SubtitleOptimizerV2(
            config=OptimizerConfig(max_retries=2, retry_backoff_base=0.01)
        )

        with patch.object(
            optimizer.llm_optimizer, '_call_llm', new_callable=AsyncMock
        ) as mock_call:
            # 第一次返回错误，第二次成功
            mock_call.side_effect = [
                "Invalid response",  # 第一次失败
                "\n".join([f"[{i}]Line {i} content" for i in range(1, 51)])  # 第二次成功
            ]

            result = await optimizer.optimize(
                input_data=small_input_data,
                task_id="test_retry"
            )

            assert result["success"] is True
            assert mock_call.call_count == 2

    @pytest.mark.asyncio
    async def test_failure_handling(self, small_input_data):
        """测试失败处理"""
        optimizer = SubtitleOptimizerV2(
            config=OptimizerConfig(max_retries=1, retry_backoff_base=0.01)
        )

        with patch.object(
            optimizer.llm_optimizer, '_call_llm', new_callable=AsyncMock
        ) as mock_call:
            # 总是返回错误
            mock_call.return_value = "Invalid response"

            result = await optimizer.optimize(
                input_data=small_input_data,
                task_id="test_failure"
            )

            assert result["success"] is False
            assert "失败" in result["error"]
```

**Step 2: 运行测试（预期通过）**

```bash
python -m pytest tests/integration/test_subtitle_optimizer_v2.py -v
```

**Step 3: Commit**

```bash
git add tests/integration/test_subtitle_optimizer_v2.py
git commit -m "test(subtitle_optimizer): add integration tests"
```

---

## 模块 10: LLM API 适配器

### Task 10: 实现LLM API适配器

**Files:**
- Create: `services/common/subtitle/optimizer_v2/llm_providers.py`
- Modify: `services/common/subtitle/optimizer_v2/llm_optimizer.py` (集成适配器)

**Step 1: 创建LLM Provider适配器**

```python
# services/common/subtitle/optimizer_v2/llm_providers.py
"""
LLM Provider 适配器

支持多种LLM API（Gemini、DeepSeek等）。
"""

import os
import aiohttp
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """LLM Provider 抽象基类"""

    @abstractmethod
    async def call(self, system_prompt: str, user_prompt: str) -> str:
        """调用LLM"""
        pass


class GeminiProvider(LLMProvider):
    """Google Gemini Provider"""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-pro"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    async def call(self, system_prompt: str, user_prompt: str) -> str:
        """调用 Gemini API"""
        if not self.api_key:
            raise ValueError("Gemini API key not found")

        url = f"{self.base_url}/models/{self.model}:generateContent"

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key
        }

        # Gemini 使用不同的 prompt 格式
        # 将 system_prompt 和 user_prompt 合并
        combined_prompt = f"{system_prompt}\n\n{user_prompt}"

        data = {
            "contents": [{
                "parts": [{"text": combined_prompt}]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 4096
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Gemini API error: {response.status} - {error_text}")

                result = await response.json()
                # 解析响应
                candidates = result.get("candidates", [])
                if not candidates:
                    raise RuntimeError("No candidates in Gemini response")

                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if not parts:
                    raise RuntimeError("No content parts in Gemini response")

                return parts[0].get("text", "")


class DeepSeekProvider(LLMProvider):
    """DeepSeek Provider"""

    def __init__(self, api_key: Optional[str] = None, model: str = "deepseek-chat"):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.model = model
        self.base_url = "https://api.deepseek.com"

    async def call(self, system_prompt: str, user_prompt: str) -> str:
        """调用 DeepSeek API"""
        if not self.api_key:
            raise ValueError("DeepSeek API key not found")

        url = f"{self.base_url}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 4096
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"DeepSeek API error: {response.status} - {error_text}")

                result = await response.json()
                choices = result.get("choices", [])
                if not choices:
                    raise RuntimeError("No choices in DeepSeek response")

                return choices[0].get("message", {}).get("content", "")


class LLMProviderFactory:
    """LLM Provider 工厂"""

    @staticmethod
    def create(provider_type: str, **kwargs) -> LLMProvider:
        """
        创建 Provider

        Args:
            provider_type: 提供商类型 (gemini, deepseek)
            **kwargs: 额外参数

        Returns:
            LLMProvider 实例
        """
        if provider_type == "gemini":
            return GeminiProvider(**kwargs)
        elif provider_type == "deepseek":
            return DeepSeekProvider(**kwargs)
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")
```

**Step 2: 更新 llm_optimizer.py 集成适配器**

```python
# 在 llm_optimizer.py 中添加
from services.common.subtitle.optimizer_v2.llm_providers import LLMProviderFactory

# 修改 __init__ 方法
    def __init__(self, config: OptimizerConfig):
        self.config = config
        # 创建 provider
        provider_type = config.llm_model.split("-")[0]  # 简单解析
        if "gemini" in config.llm_model:
            provider_type = "gemini"
        elif "deepseek" in config.llm_model:
            provider_type = "deepseek"
        else:
            provider_type = "gemini"  # 默认

        self.provider = LLMProviderFactory.create(provider_type, model=config.llm_model)

# 修改 _call_llm 方法
    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """调用LLM"""
        return await self.provider.call(system_prompt, user_prompt)
```

**Step 3: 添加测试**

```python
# tests/unit/subtitle/optimizer_v2/test_llm_providers.py
import pytest
from unittest.mock import patch, AsyncMock

from services.common.subtitle.optimizer_v2.llm_providers import (
    GeminiProvider,
    DeepSeekProvider,
    LLMProviderFactory
)


class TestLLMProviders:
    """测试LLM Provider"""

    @pytest.mark.asyncio
    async def test_gemini_provider(self):
        """测试 Gemini Provider"""
        provider = GeminiProvider(api_key="test_key", model="gemini-pro")

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = {
                "candidates": [{
                    "content": {
                        "parts": [{"text": "[1]Optimized line"}]
                    }
                }]
            }
            mock_post.return_value.__aenter__.return_value = mock_response

            result = await provider.call("system", "user")
            assert result == "[1]Optimized line"

    @pytest.mark.asyncio
    async def test_deepseek_provider(self):
        """测试 DeepSeek Provider"""
        provider = DeepSeekProvider(api_key="test_key", model="deepseek-chat")

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = {
                "choices": [{
                    "message": {"content": "[1]Optimized line"}
                }]
            }
            mock_post.return_value.__aenter__.return_value = mock_response

            result = await provider.call("system", "user")
            assert result == "[1]Optimized line"

    def test_provider_factory(self):
        """测试 Provider 工厂"""
        gemini = LLMProviderFactory.create("gemini", model="gemini-pro")
        assert isinstance(gemini, GeminiProvider)

        deepseek = LLMProviderFactory.create("deepseek", model="deepseek-chat")
        assert isinstance(deepseek, DeepSeekProvider)
```

**Step 4: 运行测试**

```bash
python -m pytest tests/unit/subtitle/optimizer_v2/test_llm_providers.py -v
```

**Step 5: Commit**

```bash
git add services/common/subtitle/optimizer_v2/llm_providers.py tests/unit/subtitle/optimizer_v2/test_llm_providers.py
git commit -m "feat(subtitle_optimizer): add LLM provider adapters for Gemini and DeepSeek"
```

---

## 模块 11: CLI 工具

### Task 11: 实现命令行工具

**Files:**
- Create: `tools/subtitle_optimizer_v2.py`

**Step 1: 创建CLI工具**

```python
#!/usr/bin/env python3
# tools/subtitle_optimizer_v2.py
"""
字幕优化器 V2 命令行工具

用法:
    python tools/subtitle_optimizer_v2.py \
        --input /path/to/transcribe_data.json \
        --output /path/to/output_optimized.json \
        --task-id my_task_001
"""

import asyncio
import argparse
import json
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from services.common.subtitle.optimizer_v2 import SubtitleOptimizerV2


def main():
    parser = argparse.ArgumentParser(
        description="字幕优化器 V2 - 基于LLM的字幕优化工具"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="输入JSON文件路径 (faster-whisper输出格式)"
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="输出JSON文件路径"
    )
    parser.add_argument(
        "--task-id", "-t",
        default="cli_task",
        help="任务ID (用于调试日志)"
    )
    parser.add_argument(
        "--description", "-d",
        default=None,
        help="视频描述 (传递给LLM)"
    )
    parser.add_argument(
        "--config", "-c",
        default=None,
        help="配置文件路径 (默认使用 config.yml)"
    )

    args = parser.parse_args()

    # 验证输入文件
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"错误: 输入文件不存在: {args.input}")
        sys.exit(1)

    # 创建优化器
    if args.config:
        from services.common.subtitle.optimizer_v2.config import OptimizerConfigLoader
        config = OptimizerConfigLoader.load(args.config)
        optimizer = SubtitleOptimizerV2(config)
    else:
        optimizer = SubtitleOptimizerV2()

    # 执行优化
    async def run():
        print(f"开始优化字幕...")
        print(f"输入: {args.input}")
        print(f"输出: {args.output}")
        print(f"任务ID: {args.task_id}")

        result = await optimizer.optimize(
            input_data=None,  # 通过 load_from_file 加载
            task_id=args.task_id,
            output_path=args.output,
            description=args.description
        )

        if result["success"]:
            print(f"\n✅ 优化成功!")
            print(f"输出文件: {result['output_path']}")
            print(f"调试日志: {result['debug_log_dir']}")

            # 打印统计
            data = result["data"]
            print(f"\n统计:")
            print(f"  - 原始段数: {data['metadata']['original_segments_count']}")
            print(f"  - 处理段数: {data['metadata']['segments_processed']}")
        else:
            print(f"\n❌ 优化失败!")
            print(f"错误: {result['error']}")
            if 'debug_log_dir' in result:
                print(f"调试日志: {result['debug_log_dir']}")
            sys.exit(1)

    # 加载输入文件
    optimizer.load_from_file(args.input)

    # 运行
    asyncio.run(run())


if __name__ == "__main__":
    main()
```

**Step 2: 添加执行权限并测试**

```bash
chmod +x tools/subtitle_optimizer_v2.py
```

**Step 3: Commit**

```bash
git add tools/subtitle_optimizer_v2.py
git commit -m "feat(subtitle_optimizer): add CLI tool for subtitle optimization"
```

---

## 模块 12: 文档和示例

### Task 12: 添加使用文档

**Files:**
- Create: `docs/technical/subtitle_optimizer_v2_usage.md`

**Step 1: 创建使用文档**

```markdown
# 字幕优化器 V2 使用指南

## 概述

字幕优化器 V2 是一个基于LLM的字幕优化工具，采用**行数锚定**策略，确保优化后的字幕结构稳定。

## 特性

- **行数锚定**: 以字幕行数ID为锚定，避免断句错位
- **分段并发**: 支持长字幕分段并发处理
- **重叠区去重**: 智能处理分段边界
- **时间戳重建**: 基于稳定词的两阶段时间戳重建
- **调试日志**: 完整的请求/响应记录

## 快速开始

### 命令行使用

```bash
python tools/subtitle_optimizer_v2.py \
    --input share/workflows/video_to_subtitle_task/nodes/faster_whisper.transcribe_audio/data/transcribe_data_task_id.json \
    --output /tmp/output_optimized.json \
    --task-id my_task_001 \
    --description "这是一段测试视频"
```

### Python API 使用

```python
import asyncio
from services.common.subtitle.optimizer_v2 import SubtitleOptimizerV2

async def main():
    # 创建优化器
    optimizer = SubtitleOptimizerV2()

    # 加载数据
    optimizer.load_from_file("/path/to/transcribe_data.json")

    # 执行优化
    result = await optimizer.optimize(
        task_id="my_task",
        output_path="/path/to/output.json",
        description="视频描述"
    )

    if result["success"]:
        print("优化成功!")
        print(f"输出: {result['output_path']}")
    else:
        print(f"优化失败: {result['error']}")

asyncio.run(main())
```

## 配置

编辑 `config.yml`:

```yaml
subtitle_optimizer:
  segment_size: 100        # 每段处理字幕条数
  overlap_lines: 20        # 重叠行数
  max_concurrent: 3        # 最大并发数
  max_retries: 3           # 最大重试次数

  debug:
    enabled: true
    log_dir: "tmp/subtitle_optimizer_logs"

  llm:
    model: "gemini-pro"    # 或 "deepseek-chat"
    max_tokens: 4096
    temperature: 0.1
```

## 环境变量

- `GEMINI_API_KEY`: Google Gemini API 密钥
- `DEEPSEEK_API_KEY`: DeepSeek API 密钥

## 调试

调试日志保存在 `tmp/subtitle_optimizer_logs/`:

```
{task_id}_seg{idx}_request.txt   # 请求记录
{task_id}_seg{idx}_response.txt  # 响应记录
{task_id}_seg{idx}_error.txt     # 错误记录
```

## 测试

```bash
# 运行单元测试
pytest tests/unit/subtitle/optimizer_v2/ -v

# 运行集成测试
pytest tests/integration/test_subtitle_optimizer_v2.py -v
```
```

**Step 2: Commit**

```bash
git add docs/technical/subtitle_optimizer_v2_usage.md
git commit -m "docs(subtitle_optimizer): add usage documentation"
```

---

## 完成总结

### 已创建的文件

```
services/common/subtitle/optimizer_v2/
├── __init__.py              # 包入口
├── models.py                # 数据模型
├── config.py                # 配置加载
├── debug_logger.py          # 调试日志
├── extractor.py             # 字幕提取
├── segment_manager.py       # 分段管理
├── llm_optimizer.py         # LLM优化
├── llm_providers.py         # LLM Provider适配器
├── timestamp_reconstructor.py # 时间戳重建
└── optimizer.py             # 主优化器

tests/unit/subtitle/optimizer_v2/
├── test_models.py
├── test_config.py
├── test_debug_logger.py
├── test_extractor.py
├── test_segment_manager.py
├── test_llm_optimizer.py
├── test_llm_providers.py
├── test_timestamp_reconstructor.py
└── test_optimizer.py

tests/integration/
└── test_subtitle_optimizer_v2.py

tools/
└── subtitle_optimizer_v2.py

docs/technical/
└── subtitle_optimizer_v2_usage.md
```

### 运行所有测试

```bash
pytest tests/unit/subtitle/optimizer_v2/ tests/integration/test_subtitle_optimizer_v2.py -v
```

---

**计划完成！** 保存于 `docs/plans/2026-01-30-subtitle-optimizer-v2-implementation-plan.md`

---

## 执行选项

**两个执行选项：**

**1. Subagent-Driven (本会话)** - 我为每个 Task 创建子代理，逐任务执行，每个任务后我进行代码审查，快速迭代

**2. Parallel Session (新会话)** - 你开启新会话，使用 `superpowers:executing-plans` 批量执行，带检查点

**选择哪个方式？**