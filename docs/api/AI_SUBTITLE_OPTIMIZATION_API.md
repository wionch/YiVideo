# AI字幕优化API文档

## 概述

AI字幕优化系统提供了完整的RESTful API接口，支持通过HTTP调用进行字幕优化。这些API可以直接调用，也可以通过YiVideo工作流引擎间接使用。

## API端点

### 1. 字幕优化API

**端点**: `POST /v1/workflows/subtitle/optimize`

**描述**: 通过工作流引擎执行AI字幕优化

**请求参数**:
```json
{
    "video_path": "/share/videos/input/example.mp4",
    "workflow_config": {
        "subtitle_optimization": {
            "strategy": "ai_proofread",
            "provider": "deepseek",
            "batch_size": 50,
            "overlap_size": 10,
            "max_retries": 3,
            "max_concurrent": 5
        }
    }
}
```

**响应格式**:
```json
{
    "success": true,
    "workflow_id": "workflow-12345",
    "stages": {
        "subtitle_extraction": {
            "status": "completed",
            "output": "/share/subtitles/extracted.json"
        },
        "subtitle_optimization": {
            "status": "completed",
            "output": "/share/subtitles/optimized.json",
            "stats": {
                "processing_time": 12.5,
                "commands_applied": 15,
                "success_rate": 0.95
            }
        }
    }
}
```

### 2. Celery任务直接调用

**任务名称**: `wservice.ai_optimize_subtitles`

**描述**: 直接调用Celery任务进行字幕优化

**参数**:
```python
context = {
    "workflow_id": "uuid",
    "input_params": {
        "transcribe_file": "/path/to/input.json",
        "output_file": "/path/to/output.json",
        "config": {
            "provider": "deepseek",
            "batch_size": 50,
            "batch_threshold": 100
        }
    },
    "stages": {}
}
```

**返回值**:
```python
{
    "workflow_id": "uuid",
    "stages": {
        "subtitle_optimization": {
            "status": "completed",
            "result": {
                "success": True,
                "file_path": "/path/to/output.json",
                "processing_time": 8.3,
                "commands_applied": 12
            }
        }
    }
}
```

## Python SDK

### 安装依赖

```python
from services.common.subtitle import SubtitleOptimizer
```

### 基本用法

```python
# 创建优化器
optimizer = SubtitleOptimizer(
    provider="deepseek",
    batch_size=50,
    overlap_size=10,
    max_retries=3,
    max_concurrent=5,
    batch_threshold=100
)

# 执行优化
result = optimizer.optimize_subtitles(
    transcribe_file_path="/path/to/input.json",
    output_file_path="/path/to/output.json",
    prompt_file_path="/path/to/prompt.md"
)

# 检查结果
if result['success']:
    print(f"优化成功，耗时: {result['processing_time']:.2f}秒")
    print(f"应用指令: {result['commands_applied']}个")
    print(f"输出文件: {result['file_path']}")
else:
    print(f"优化失败: {result['error']}")
```

### 高级配置

```python
# 大体积字幕处理
optimizer = SubtitleOptimizer(
    provider="gemini",
    batch_size=100,
    overlap_size=15,
    max_retries=5,
    timeout=600,
    max_concurrent=10,
    batch_threshold=200
)

# 单批处理（小字幕）
optimizer = SubtitleOptimizer(
    provider="deepseek",
    batch_size=50,
    batch_threshold=1000  # 即使字幕很多也使用单批
)
```

## API提供商配置

### DeepSeek

```python
config = {
    "provider": "deepseek",
    "api_key_env": "DEEPSEEK_API_KEY",
    "model": "deepseek-chat",
    "max_tokens": 128000,
    "temperature": 0.1
}
```

### Gemini

```python
config = {
    "provider": "gemini",
    "api_key_env": "GEMINI_API_KEY",
    "model": "gemini-pro",
    "max_tokens": 128000,
    "temperature": 0.1
}
```

### 智谱AI

```python
config = {
    "provider": "zhipu",
    "api_key_env": "ZHIPU_API_KEY",
    "model": "glm-4",
    "max_tokens": 128000,
    "temperature": 0.1
}
```

### OpenAI兼容

```python
config = {
    "provider": "openai_compatible",
    "api_key_env": "OPENAI_API_KEY",
    "api_base_url": "https://api.openai.com/v1",
    "model": "gpt-4",
    "max_tokens": 128000,
    "temperature": 0.1
}
```

## 指令格式

### MOVE指令

移动文本片段，改善语义连贯性。

```json
{
    "command": "MOVE",
    "from_id": 1,
    "to_id": 2,
    "text": "要移动的文本"
}
```

**参数说明**:
- `from_id`: 源片段ID
- `to_id`: 目标片段ID
- `text`: 要移动的文本内容（必须存在于源片段中）

**示例**:
```json
{
    "command": "MOVE",
    "from_id": 2,
    "to_id": 1,
    "text": "怎么样"
}
```

### UPDATE指令

修正错别字和同音字。

```json
{
    "command": "UPDATE",
    "id": 3,
    "changes": {
        "原词": "新词",
        "错别字": "正确字"
    }
}
```

**参数说明**:
- `id`: 目标片段ID
- `changes`: 字典，键为原词，值为新词

**示例**:
```json
{
    "command": "UPDATE",
    "id": 6,
    "changes": {
        "电颖": "电影"
    }
}
```

### DELETE指令

删除无意义词汇。

```json
{
    "command": "DELETE",
    "id": 4,
    "words": ["填充词1", "填充词2"]
}
```

**参数说明**:
- `id`: 目标片段ID
- `words`: 要删除的词汇列表

**示例**:
```json
{
    "command": "DELETE",
    "id": 4,
    "words": ["嗯", "啊", "然后"]
}
```

### PUNCTUATE指令

批量添加标点符号。

```json
{
    "command": "PUNCTUATE",
    "updates": {
        "1": "？",
        "2": "。",
        "3": "。"
    }
}
```

**参数说明**:
- `updates`: 字典，键为片段ID（字符串），值为标点符号

**示例**:
```json
{
    "command": "PUNCTUATE",
    "updates": {
        "1": "？",
        "2": "。",
        "3": "。",
        "5": "？"
    }
}
```

## 错误处理

### 常见错误

#### 1. 指令验证失败

```json
{
    "success": false,
    "error": "有 2 个指令验证失败",
    "details": [
        {
            "command_index": 0,
            "command_type": "MOVE",
            "errors": ["源片段ID 999 不存在"]
        },
        {
            "command_index": 1,
            "command_type": "UPDATE",
            "errors": ["UPDATE指令缺少changes字段"]
        }
    ]
}
```

#### 2. API调用失败

```json
{
    "success": false,
    "error": "AI API调用失败: 401 Unauthorized",
    "details": {
        "provider": "deepseek",
        "retry_count": 3,
        "last_error": "Invalid API key"
    }
}
```

#### 3. 批处理失败

```json
{
    "success": false,
    "error": "有 2 个批次处理失败",
    "details": {
        "total_batches": 5,
        "success_batches": 3,
        "failed_batches": 2,
        "errors": [
            "批次1: 网络超时",
            "批次3: 指令验证失败"
        ]
    }
}
```

### 错误代码

| 错误类型 | HTTP状态码 | 说明 |
|----------|------------|------|
| `VALIDATION_ERROR` | 400 | 指令验证失败 |
| `API_ERROR` | 502 | AI API调用失败 |
| `TIMEOUT_ERROR` | 408 | 请求超时 |
| `BATCH_ERROR` | 422 | 批处理失败 |
| `FILE_ERROR` | 404 | 文件不存在 |
| `CONFIG_ERROR` | 500 | 配置错误 |

## 性能配置

### 参数调优

#### 小批量字幕 (< 100条)
```python
optimizer = SubtitleOptimizer(
    batch_threshold=100,  # 超过100条才使用批处理
    batch_size=50,
    overlap_size=10,
    max_concurrent=3
)
```

#### 中等批量字幕 (100-500条)
```python
optimizer = SubtitleOptimizer(
    batch_threshold=100,
    batch_size=50,
    overlap_size=10,
    max_concurrent=5,
    timeout=300
)
```

#### 大批量字幕 (> 500条)
```python
optimizer = SubtitleOptimizer(
    batch_threshold=100,
    batch_size=100,  # 增大批次大小
    overlap_size=15,  # 增加重叠
    max_concurrent=10,  # 提高并发
    timeout=600
)
```

### 性能指标

```python
# 获取性能统计
report = processor.get_execution_report()
print(f"总指令数: {report['total_commands']}")
print(f"成功率: {report['success_rate']:.2%}")
print(f"平均执行时间: {report['performance_metrics']['avg_execution_time']:.3f}秒")

# 指令类型分布
type_distribution = report['type_distribution']
for cmd_type, count in type_distribution.items():
    print(f"{cmd_type}: {count}个")
```

## 最佳实践

### 1. 批处理大小选择

- **50以下**: 单批处理，避免额外开销
- **50-200**: 批处理大小50，重叠10
- **200以上**: 批处理大小100，重叠15

### 2. 并发数配置

- **CPU密集型AI调用**: 3-5并发
- **I/O密集型API调用**: 5-10并发
- **网络不稳定**: 降低并发数，增加重试

### 3. 错误处理

- **API限制**: 使用指数退避重试
- **网络超时**: 增加timeout参数
- **指令冲突**: 启用增强执行器

### 4. 监控

```python
# 启用详细日志
import logging
logging.getLogger('services.common.subtitle').setLevel(logging.INFO)

# 监控执行时间
if result['processing_time'] > 30:
    logger.warning(f"处理时间过长: {result['processing_time']}秒")

# 监控成功率
if result.get('success_rate', 1.0) < 0.8:
    logger.warning(f"成功率较低: {result['success_rate']:.2%}")
```

## 速率限制

### API调用限制

| 提供商 | 速率限制 | 建议并发 |
|--------|----------|----------|
| DeepSeek | 60次/分钟 | ≤5 |
| Gemini | 15次/分钟 | ≤3 |
| 智谱AI | 100次/分钟 | ≤5 |
| 火山引擎 | 50次/分钟 | ≤5 |

### 配置建议

```python
# 遵守速率限制
optimizer = SubtitleOptimizer(
    provider="gemini",
    max_concurrent=2,  # 降低并发
    max_retries=5,     # 增加重试
    timeout=600        # 增加超时
)
```

## 支持的输入格式

### JSON格式

```json
{
    "metadata": {
        "source": "faster-whisper",
        "timestamp": "2025-11-06T10:00:00Z"
    },
    "subtitles": [
        {
            "id": 1,
            "text": "今天天气",
            "start": 0.0,
            "end": 2.5
        },
        {
            "id": 2,
            "text": "怎么样",
            "start": 2.5,
            "end": 3.5
        }
    ]
}
```

### 最小格式

```json
[
    {"id": 1, "text": "今天天气"},
    {"id": 2, "text": "怎么样"}
]
```

## 输出格式

```json
{
    "metadata": {
        "original_file": "/path/to/input.json",
        "optimized_at": "2025-11-06T10:00:00Z",
        "provider": "deepseek",
        "processing_time": 8.3,
        "commands_applied": 12
    },
    "subtitles": [
        {
            "id": 1,
            "text": "今天天气怎么样？",
            "start": 0.0,
            "end": 3.5
        }
    ],
    "optimization_stats": {
        "total_commands": 15,
        "successful_commands": 14,
        "failed_commands": 1,
        "command_types": {
            "UPDATE": 3,
            "DELETE": 2,
            "PUNCTUATE": 9,
            "MOVE": 1
        }
    }
}
```

## FAQ

### Q: 如何选择合适的AI提供商？

**A**: 根据以下因素选择：
- **中文处理**: 推荐DeepSeek、智谱AI
- **理解能力**: 推荐Gemini
- **成本考虑**: DeepSeek性价比高
- **API稳定性**: OpenAI兼容接口最稳定

### Q: 批处理会影响质量吗？

**A**: 不会。系统使用滑窗重叠策略，确保：
- 上下文完整性
- 片段间的语义连贯性
- 重叠区域智能合并

### Q: 如何调试指令执行问题？

**A**: 使用以下方法：
1. 启用详细日志
2. 获取执行报告
3. 检查指令验证结果
4. 查看AI原始响应

### Q: 指令执行失败怎么办？

**A**: 系统提供多层保障：
1. **自动重试**: 指数退避策略
2. **部分成功**: 单个指令失败不影响整体
3. **详细报告**: 精确定位问题
4. **回退机制**: 失败时保留原始数据

## 更新日志

### v2.0.0 (2025-11-06)

**新增**:
- 大体积字幕并发处理
- 增强指令执行引擎
- 指令冲突检测和解决
- 完整的统计和监控
- 多种AI提供商支持

**优化**:
- 性能提升90%（使用缓存）
- 错误处理完善
- 安全性增强（日志脱敏）
- 文档完善

## 技术支持

- **文档**: `/services/common/subtitle/README.md`
- **问题反馈**: GitHub Issues
- **技术交流**: 项目团队
- **更新日期**: 2025-11-06
