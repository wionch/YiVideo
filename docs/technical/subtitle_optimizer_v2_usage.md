# 字幕优化器 V2 使用文档

## 1. 概述

字幕优化器 V2 是 YiVideo 项目中的字幕优化组件，基于 LLM（大语言模型）实现智能字幕分段优化。它能够处理大型字幕文件，通过智能分段、并发优化和精确的时间戳重建，显著提升字幕质量。

### 核心能力

- **智能分段处理**：自动将大字幕文件分成多个小段，每段独立优化
- **并发优化**：支持多段并发处理，提高效率
- **边界平滑**：重叠区域处理确保分段边界连贯
- **时间戳重建**：基于词级时间戳精确重建优化后的时间戳
- **调试日志**：完整的调试日志记录，便于问题排查

## 2. 特性

### 主要功能

| 特性 | 说明 |
|------|------|
| 智能分段 | 根据配置自动分段，支持重叠行数设置 |
| 并发控制 | 可配置最大并发数，避免 API 限流 |
| 重试机制 | 失败自动重试，支持指数退避 |
| 差异检测 | 检测 LLM 是否实际修改了内容 |
| 多提供商支持 | 支持 DeepSeek、Gemini、智谱 AI、火山引擎 |
| 调试日志 | 详细的调试日志，记录每一步处理过程 |

### 支持的 LLM 提供商

- **DeepSeek** (`deepseek-chat`)
- **Google Gemini** (`gemini-pro`)
- **智谱 AI** (`glm-4`)
- **火山引擎** (`doubao-pro-32k`)

## 3. 快速开始

### 3.1 环境准备

确保已设置环境变量：

```bash
export DEEPSEEK_API_KEY="your_deepseek_api_key"
export GEMINI_API_KEY="your_gemini_api_key"
```

### 3.2 命令行使用

#### 基本用法

```bash
python tools/subtitle_optimizer_v2.py -i input.json -o output.json
```

#### 完整参数

```bash
python tools/subtitle_optimizer_v2.py \
    --input input.json \
    --output output.json \
    --task-id my_task_001 \
    --description "视频描述信息" \
    --config config.yml \
    --verbose
```

#### 参数说明

| 参数 | 简写 | 必需 | 说明 |
|------|------|------|------|
| `--input` | `-i` | 是 | 输入 JSON 文件路径 |
| `--output` | `-o` | 是 | 输出 JSON 文件路径 |
| `--task-id` | `-t` | 否 | 任务 ID（默认: cli_task） |
| `--description` | `-d` | 否 | 视频描述（可选） |
| `--config` | `-c` | 否 | 配置文件路径（默认使用项目根目录 config.yml） |
| `--verbose` | `-v` | 否 | 启用详细日志输出 |

#### 使用示例

```bash
# 基本使用
python tools/subtitle_optimizer_v2.py -i subtitles.json -o optimized.json

# 带任务ID和描述
python tools/subtitle_optimizer_v2.py \
    -i subtitles.json \
    -o optimized.json \
    -t task_001 \
    -d "这是一个技术讲解视频"

# 使用自定义配置
python tools/subtitle_optimizer_v2.py \
    -i subtitles.json \
    -o optimized.json \
    -c /path/to/custom_config.yml \
    -v
```

### 3.3 输入文件格式

输入文件应为 JSON 格式，包含字幕段信息：

```json
{
    "metadata": {
        "language": "zh",
        "duration": 120.5
    },
    "segments": [
        {
            "id": 1,
            "start": 0.0,
            "end": 3.5,
            "text": "这是第一行字幕",
            "words": [
                {"word": "这是", "start": 0.0, "end": 0.8, "probability": 0.95},
                {"word": "第一行", "start": 0.8, "end": 2.0, "probability": 0.92},
                {"word": "字幕", "start": 2.0, "end": 3.5, "probability": 0.98}
            ]
        }
    ]
}
```

### 3.4 输出文件格式

优化后的输出文件包含优化后的字幕段和元数据：

```json
{
    "metadata": {
        "total_lines": 100,
        "modified_lines": 95,
        "unchanged_lines": 5,
        "processing_time_seconds": 15.2
    },
    "segments": [
        {
            "id": 1,
            "start": 0.0,
            "end": 3.5,
            "text": "优化后的第一行字幕",
            "is_modified": true,
            "original_text": "这是第一行字幕",
            "words": [
                {"word": "优化后", "start": 0.0, "end": 0.9},
                {"word": "的", "start": 0.9, "end": 1.0},
                {"word": "第一行", "start": 1.0, "end": 2.2},
                {"word": "字幕", "start": 2.2, "end": 3.5}
            ]
        }
    ]
}
```

## 4. Python API 使用

### 4.1 基本使用

```python
import asyncio
from services.common.subtitle.optimizer_v2 import (
    SubtitleOptimizerV2,
    SubtitleOptimizerConfig,
)

async def optimize_subtitles():
    # 1. 创建配置
    config = SubtitleOptimizerConfig(
        segment_size=100,      # 每段100行
        overlap_lines=20,      # 重叠20行
        max_concurrent=3,      # 最大并发3
        max_retries=3,         # 最大重试3次
    )

    # 2. 创建优化器
    optimizer = SubtitleOptimizerV2(config)

    # 3. 加载数据
    optimizer.load_from_file("input.json")
    # 或者从字典加载
    # optimizer.load_from_dict(subtitle_data_dict)

    # 4. 执行优化
    result = await optimizer.optimize(output_path="output.json")

    # 5. 处理结果
    print(f"总行数: {result['metadata']['total_lines']}")
    print(f"修改行数: {result['metadata']['modified_lines']}")

    return result

# 运行
result = asyncio.run(optimize_subtitles())
```

### 4.2 使用自定义 LLM 配置

```python
from services.common.subtitle.optimizer_v2 import (
    SubtitleOptimizerV2,
    SubtitleOptimizerConfig,
    LLMConfig,
)

# 创建自定义 LLM 配置
llm_config = LLMConfig(
    model="gemini-pro",
    max_tokens=4096,
    temperature=0.1,
)

# 创建优化器配置
config = SubtitleOptimizerConfig(
    segment_size=100,
    llm=llm_config,
)

optimizer = SubtitleOptimizerV2(config)
```

### 4.3 从配置加载器加载配置

```python
from services.common.subtitle.optimizer_v2 import OptimizerConfigLoader

# 从配置文件加载
config = OptimizerConfigLoader.load("config.yml")

# 或使用默认配置
config = OptimizerConfigLoader.get_default_config()

# 创建优化器
optimizer = SubtitleOptimizerV2(config)
```

### 4.4 获取优化详情

```python
# 获取优化后的行
optimized_lines = optimizer.get_optimized_lines()

# 获取原始分段
original_segments = optimizer.get_original_segments()

# 获取优化结果详情
optimization_results = optimizer.get_optimization_results()

# 获取总行数
total_lines = optimizer.get_total_lines()
```

## 5. 配置说明

### 5.1 config.yml 配置项

字幕优化器 V2 的配置位于 `config.yml` 的 `subtitle_optimizer` 部分：

```yaml
subtitle_optimizer:
    # === 分段配置 ===
    # 每段字幕行数（推荐100行，平衡处理速度和上下文理解）
    segment_size: 100
    # 相邻分段之间的重叠行数（推荐20行，确保边界平滑过渡）
    overlap_lines: 20

    # === 并发配置 ===
    # 最大并发处理数（推荐3，避免API限流）
    max_concurrent: 3

    # === 重试配置 ===
    # 最大重试次数
    max_retries: 3
    # 重试退避基数（秒）
    retry_backoff_base: 1

    # === 差异检测配置 ===
    # 差异阈值（0-1），用于检测LLM是否修改了内容
    # 低于此阈值认为内容未变化
    diff_threshold: 0.3
    # 最大重叠扩展行数（处理边界问题时使用）
    max_overlap_expand: 50

    # === 调试配置 ===
    debug:
        # 是否启用调试日志
        enabled: true
        # 调试日志目录
        log_dir: "tmp/subtitle_optimizer_logs"

    # === LLM配置 ===
    llm:
        # 默认模型
        model: "gemini-pro"
        # 最大令牌数
        max_tokens: 4096
        # 温度参数（越低越保守）
        temperature: 0.1
```

### 5.2 配置项详细说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `segment_size` | int | 100 | 每段处理的字幕行数，根据字幕总长度和 API 限制调整 |
| `overlap_lines` | int | 20 | 相邻段之间的重叠行数，确保边界连贯性 |
| `max_concurrent` | int | 3 | 最大并发处理数，根据 API 限流策略调整 |
| `max_retries` | int | 3 | 失败后的最大重试次数 |
| `retry_backoff_base` | int | 1 | 重试退避基数（秒），实际延迟 = base * (2 ** attempt) |
| `diff_threshold` | float | 0.3 | 差异检测阈值，低于此值认为内容未修改 |
| `max_overlap_expand` | int | 50 | 处理边界问题时的最大扩展行数 |
| `debug.enabled` | bool | true | 是否启用调试日志 |
| `debug.log_dir` | str | "tmp/subtitle_optimizer_logs" | 调试日志保存目录 |
| `llm.model` | str | "gemini-pro" | 默认使用的 LLM 模型 |
| `llm.max_tokens` | int | 4096 | LLM 最大输出令牌数 |
| `llm.temperature` | float | 0.1 | LLM 温度参数，越低输出越确定 |

## 6. 环境变量

### 6.1 必需的 API 密钥

| 环境变量 | 说明 | 适用提供商 |
|----------|------|-----------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | DeepSeek |
| `GEMINI_API_KEY` | Google Gemini API 密钥 | Gemini |
| `ZHIPU_API_KEY` | 智谱 AI API 密钥 | 智谱 AI |
| `VOLCENGINE_API_KEY` | 火山引擎 API 密钥 | 火山引擎 |

### 6.2 设置环境变量

#### Linux/macOS

```bash
export DEEPSEEK_API_KEY="your_deepseek_api_key"
export GEMINI_API_KEY="your_gemini_api_key"
```

#### Windows (PowerShell)

```powershell
$env:DEEPSEEK_API_KEY="your_deepseek_api_key"
$env:GEMINI_API_KEY="your_gemini_api_key"
```

#### Docker Compose

在 `.env` 文件中设置：

```bash
DEEPSEEK_API_KEY=your_deepseek_api_key
GEMINI_API_KEY=your_gemini_api_key
```

### 6.3 环境变量文件示例

参考 `.env.example` 文件：

```bash
# AI 服务 API 密钥
DEEPSEEK_API_KEY=deepseek_api_key
GEMINI_API_KEY=gemini_api_key
ZHIPU_API_KEY=zhipu_api_key
VOLCENGINE_API_KEY=volcengine_api_key
```

## 7. 调试指南

### 7.1 调试日志位置

调试日志默认保存在 `tmp/subtitle_optimizer_logs/` 目录下，每个任务有独立的日志文件：

```
tmp/subtitle_optimizer_logs/
├── {task_id}_debug_YYYYMMDD_HHMMSS.json
├── {task_id}_segments_YYYYMMDD_HHMMSS.json
└── ...
```

### 7.2 启用详细日志

#### 命令行方式

```bash
python tools/subtitle_optimizer_v2.py -i input.json -o output.json -v
```

#### Python API 方式

```python
import logging

# 设置日志级别
logging.getLogger().setLevel(logging.DEBUG)
```

### 7.3 调试日志内容

调试日志包含以下信息：

- **输入数据**：原始字幕数据
- **分段信息**：分段结果和重叠区域
- **LLM 请求/响应**：发送给 LLM 的内容和返回结果
- **优化结果**：每段的优化结果
- **合并过程**：分段合并的详细过程
- **时间戳重建**：时间戳重建的映射关系

### 7.4 常见问题排查

#### 问题：API 调用失败

**排查步骤：**
1. 检查环境变量是否正确设置
2. 查看调试日志中的错误信息
3. 确认 API 密钥是否有效
4. 检查网络连接

#### 问题：优化结果不理想

**排查步骤：**
1. 检查输入数据格式是否正确
2. 查看调试日志中的 LLM 响应
3. 调整 `temperature` 参数
4. 尝试不同的 LLM 提供商

#### 问题：处理时间过长

**排查步骤：**
1. 增加 `max_concurrent` 配置
2. 检查 API 响应时间
3. 考虑使用更快的 LLM 提供商
4. 调整 `segment_size` 以平衡并发和 API 调用次数

## 8. 测试说明

### 8.1 运行单元测试

```bash
# 运行所有字幕优化器 V2 的单元测试
pytest tests/unit/subtitle/optimizer_v2/ -v

# 运行特定测试文件
pytest tests/unit/subtitle/optimizer_v2/test_config.py -v
pytest tests/unit/subtitle/optimizer_v2/test_optimizer.py -v
pytest tests/unit/subtitle/optimizer_v2/test_segment_manager.py -v
```

### 8.2 运行集成测试

```bash
# 运行集成测试
pytest tests/integration/test_subtitle_optimizer_v2.py -v
```

### 8.3 测试覆盖范围

#### 单元测试

- `test_config.py` - 配置加载和验证
- `test_models.py` - 数据模型
- `test_extractor.py` - 字幕提取器
- `test_segment_manager.py` - 分段管理器
- `test_llm_optimizer.py` - LLM 优化器
- `test_llm_providers.py` - LLM 提供商
- `test_timestamp_reconstructor.py` - 时间戳重建器
- `test_debug_logger.py` - 调试日志记录器
- `test_optimizer.py` - 主优化器

#### 集成测试

- 小字幕不分段处理
- 大字幕不分段处理
- 重试机制
- 失败处理
- 部分失败处理
- 并发优化控制
- 输出文件生成
- 端到端测试

### 8.4 在 Docker 中运行测试

```bash
# 进入容器
docker exec -it <container_name> bash

# 运行测试
cd /app
pytest tests/unit/subtitle/optimizer_v2/ -v
pytest tests/integration/test_subtitle_optimizer_v2.py -v
```

### 8.5 测试数据格式

测试使用标准字幕数据格式：

```python
{
    "metadata": {
        "language": "zh",
        "duration": 150.0
    },
    "segments": [
        {
            "id": 1,
            "start": 0.0,
            "end": 3.0,
            "text": "测试字幕文本",
            "words": [...]
        }
    ]
}
```

---

## 附录

### 相关文件

- 主优化器：`services/common/subtitle/optimizer_v2/optimizer.py`
- CLI 工具：`tools/subtitle_optimizer_v2.py`
- 配置文件：`config.yml`
- 单元测试：`tests/unit/subtitle/optimizer_v2/`
- 集成测试：`tests/integration/test_subtitle_optimizer_v2.py`

### 版本信息

- 当前版本：2.0.0
- 最后更新：2026-01-30
