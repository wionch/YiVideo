# AI字幕优化API文档

**版本**: v1.0.0
**更新日期**: 2025-11-07
**功能**: AI字幕优化功能

## 概述

AI字幕优化系统提供了完整的RESTful API接口，支持通过HTTP调用进行字幕优化。这些API通过YiVideo工作流引擎间接使用，基于Celery任务队列实现异步处理。

## API端点

### 1. 工作流任务API

**端点**: `POST /v1/workflows`

**描述**: 通过工作流引擎执行AI字幕优化任务

**请求参数**:
```json
{
    "workflow_id": "可选-工作流ID（增量执行时提供）",
    "execution_mode": "可选-执行模式：incremental/retry",
    "video_path": "/share/videos/input/example.mp4",
    "workflow_config": {
        "workflow_chain": [
            "faster_whisper.transcribe_audio",
            "wservice.ai_optimize_subtitles",
            "faster_whisper.generate_subtitle_files"
        ]
    },
    "wservice.ai_optimize_subtitles": {
        "subtitle_optimization": {
            "enabled": true,
            "provider": "deepseek",
            "batch_size": 50,
            "overlap_size": 10,
            "max_retries": 3,
            "timeout": 300
        },
        "segments_file": "${{ stages.faster_whisper.transcribe_audio.output.segments_file }}"
    }
}
```

**参数格式说明**:
- **节点参数**: 直接在工作流请求的根级别指定，如 `"wservice.ai_optimize_subtitles": {...}`
- **动态引用**: 使用 `${{ stages.<stage_name>.output.<field_name> }}` 格式引用其他阶段的输出
- **向後兼容**: 仍然支持 `input_params.params.subtitle_optimization` 格式
- **参数解析**: 所有节点参数在工作流执行前都会通过 `parameter_resolver` 进行解析，支持嵌套参数和动态引用

**注意事项**:
- 参数名称必须与节点任务名称完全匹配（如 `wservice.ai_optimize_subtitles`）
- `subtitle_optimization` 是节点参数内的子对象，用于存放优化配置
- 如果同时使用新格式（旧格式兼容）和动态引用，新的参数格式优先级更高

**响应格式**:
```json
{
    "success": true,
    "workflow_id": "fd8cfc21-2d3f-47d7-86fc-2550adc86a37",
    "stages": {
        "faster_whisper.transcribe_audio": {
            "status": "SUCCESS",
            "output": {
                "segments_file": "/share/workflows/fd8cfc21/segments.json",
                "transcribe_duration": 125.5,
                "language": "zh"
            },
            "duration": 125.5
        },
        "wservice.ai_optimize_subtitles": {
            "status": "SUCCESS",
            "output": {
                "optimized_file_path": "/share/workflows/fd8cfc21/optimized.json",
                "original_file_path": "/share/workflows/fd8cfc21/original.json",
                "provider_used": "deepseek",
                "processing_time": 45.2,
                "commands_applied": 15,
                "batch_mode": true,
                "batches_count": 3,
                "segments_count": 100
            },
            "duration": 45.2
        }
    }
}
```

### 2. 查询工作流状态

**端点**: `GET /v1/workflows/{workflow_id}`

**描述**: 查询工作流执行状态和结果

**响应格式**:
```json
{
    "success": true,
    "workflow_id": "fd8cfc21-2d3f-47d7-86fc-2550adc86a37",
    "stages": {
        "wservice.ai_optimize_subtitles": {
            "status": "SUCCESS|FAILED|IN_PROGRESS|PENDING",
            "output": {
                "optimized_file_path": "...",
                "processing_time": 45.2,
                "commands_applied": 15
            },
            "error": "错误信息（如果失败）",
            "duration": 45.2
        }
    }
}
```

### 3. GPU锁监控API

**端点**: `GET /v1/gpu-locks/status`

**描述**: 查询GPU资源锁状态（用于调试）

**响应格式**:
```json
{
    "success": true,
    "gpu_locks": {
        "active_locks": 2,
        "locked_resources": ["gpu:0", "gpu:1"],
        "lock_details": [
            {
                "lock_id": "wservice-gpu-lock",
                "workflow_id": "fd8cfc21",
                "acquired_at": "2025-11-07T10:00:00Z",
                "expires_at": "2025-11-07T10:30:00Z"
            }
        ]
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

### 直接调用Celery任务

```python
from services.workers.wservice.app.tasks import ai_optimize_subtitles

# 构造工作流上下文
context = {
    "workflow_id": "test-123",
    "shared_storage_path": "/share/workflows/test-123",
    "stages": {
        "faster_whisper.transcribe_audio": {
            "status": "SUCCESS",
            "output": {
                "segments_file": "/share/workflows/test-123/segments.json",
                "audio_path": "/share/workflows/test-123/audio.wav",
                "language": "zh"
            }
        }
    },
    "input_params": {
        "params": {
            "subtitle_optimization": {
                "enabled": True,
                "provider": "deepseek",
                "batch_size": 50,
                "overlap_size": 10,
                "max_retries": 3,
                "timeout": 300
            }
        }
    }
}

# 异步调用任务
result = ai_optimize_subtitles.delay(context)

# 等待完成并获取结果
try:
    output = result.get(timeout=600)
    print("任务执行成功!")
    print(f"工作流ID: {output['workflow_id']}")
    print(f"状态: {output['stages']['wservice.ai_optimize_subtitles']['status']}")
    if output['stages']['wservice.ai_optimize_subtitles']['status'] == 'SUCCESS':
        print(f"优化文件: {output['stages']['wservice.ai_optimize_subtitles']['output']['optimized_file_path']}")
except Exception as e:
    print(f"任务执行失败: {e}")
```

### 使用字幕优化模块

```python
from services.common.subtitle.subtitle_optimizer import SubtitleOptimizer

# 创建优化器实例
optimizer = SubtitleOptimizer(
    provider="deepseek",
    batch_size=50,
    overlap_size=10,
    max_retries=3,
    timeout=300
)

# 准备输入数据
input_data = {
    "metadata": {
        "task_name": "faster_whisper.transcribe_audio",
        "workflow_id": "test-123",
        "language": "zh"
    },
    "segments": [
        {
            "id": 1,
            "start": 0.0,
            "end": 2.94,
            "text": "你的儿子王思聪是一个网红"
        }
    ]
}

# 执行优化
result = optimizer.optimize(
    segments_data=input_data,
    output_path="/share/workflows/test-123/optimized.json"
)

# 检查结果
if result['success']:
    print(f"优化成功!")
    print(f"处理时间: {result['processing_time']:.2f}秒")
    print(f"应用指令: {result['commands_applied']}个")
    print(f"使用提供商: {result['provider_used']}")
    if result.get('batch_mode'):
        print(f"批处理模式: {result['batches_count']}个批次")
else:
    print(f"优化失败: {result.get('error')}")
```

### 大体积字幕处理示例

```python
from services.common.subtitle.subtitle_optimizer import SubtitleOptimizer
from services.common.subtitle.concurrent_batch_processor import ConcurrentBatchProcessor

# 创建大体积字幕优化器
optimizer = SubtitleOptimizer(
    provider="deepseek",
    batch_size=100,        # 增大批次大小
    overlap_size=20,       # 增加重叠
    max_retries=3,
    timeout=300,
    batch_threshold=100    # 超过100条启用批处理
)

# 模拟大量字幕数据
large_data = {
    "metadata": {"task_name": "test"},
    "segments": [
        {"id": i, "start": i*3.0, "end": (i+1)*3.0, "text": f"这是第{i}段字幕"}
        for i in range(1, 501)  # 500条字幕
    ]
}

# 执行优化（自动使用批处理）
result = optimizer.optimize(
    segments_data=large_data,
    output_path="/share/workflows/test-123/large_optimized.json"
)

print(f"总片段数: {result['segments_count']}")
print(f"批处理数: {result['batches_count']}")
print(f"总处理时间: {result['processing_time']:.2f}秒")
```

### AI提供商工厂使用

```python
from services.common.subtitle.ai_providers import AIProviderFactory

# 获取AI提供商实例
provider = AIProviderFactory.get_provider(
    provider_name="deepseek",
    api_key="your-api-key",
    model="deepseek-chat",
    timeout=300,
    max_retries=3
)

# 调用AI服务
response = provider.call_ai(
    prompt="优化以下字幕：...",
    system_prompt="你是一个专业的字幕校对员...",
    max_tokens=2000,
    temperature=0.1
)

print(f"AI响应: {response['text']}")
print(f"Token使用: {response['usage']}")
```

### 指令解析和执行

```python
from services.common.subtitle.ai_command_parser import AICommandParser
from services.common.subtitle.command_executor import CommandExecutor

# 解析AI响应中的指令
parser = AICommandParser()
commands = parser.parse_commands(ai_response_text)

print(f"解析到 {len(commands)} 个指令")
for cmd in commands:
    print(f"- {cmd['command']}: {cmd}")

# 执行指令
executor = CommandExecutor(segments_data)
result = executor.execute_commands(commands)

print(f"成功执行: {result['successful_count']}个")
print(f"失败: {result['failed_count']}个")
print(f"处理后数据: {result['optimized_segments']}")
```

### 性能监控

```python
from services.common.subtitle.metrics import OptimizationMetrics

# 创建指标收集器
metrics = OptimizationMetrics()

# 在优化过程中记录指标
with metrics.track_optimization("test-optimization"):
    # 执行优化
    result = optimizer.optimize(...)

# 获取性能报告
report = metrics.get_report()
print(f"总请求数: {report['total_requests']}")
print(f"平均处理时间: {report['avg_duration']:.2f}秒")
print(f"错误率: {report['error_rate']:.2%}")
print(f"成功率: {report['success_rate']:.2%}")
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

#### 1. 工作流上下文错误

```json
{
    "success": false,
    "error": "工作流上下文无效",
    "error_type": "VALUE_ERROR",
    "details": {
        "required_fields": ["workflow_id", "stages"],
        "missing_fields": ["stages"]
    }
}
```

#### 1.5. 参数解析错误

```json
{
    "success": false,
    "error": "参数解析失败: 在阶段 'faster_whisper.transcribe_audio' 的输出中未找到字段 'segments_file'",
    "error_type": "PARAM_RESOLVE_ERROR",
    "details": {
        "parameter": "segments_file",
        "reference": "${{ stages.faster_whisper.transcribe_audio.output.segments_file }}",
        "available_fields": ["audio_path", "language", "transcribe_duration"]
    }
}
```

**解决方案**:
- 检查引用的阶段是否已成功完成
- 确认字段名称是否正确
- 验证阶段输出的实际字段名

#### 2. 转录文件不存在

```json
{
    "success": false,
    "error": "转录文件不存在: /share/workflows/test/segments.json",
    "error_type": "FILE_NOT_FOUND",
    "stage": "wservice.ai_optimize_subtitles",
    "workflow_id": "test-123"
}
```

#### 3. AI API调用失败

```json
{
    "success": false,
    "error": "AI API调用失败: 401 Unauthorized",
    "error_type": "AI_API_ERROR",
    "details": {
        "provider": "deepseek",
        "retry_count": 3,
        "max_retries": 3,
        "last_error": "Invalid API key",
        "request_timeout": 300
    },
    "stage": "wservice.ai_optimize_subtitles"
}
```

#### 4. AI响应格式无效

```json
{
    "success": false,
    "error": "AI响应格式无效",
    "error_type": "AI_RESPONSE_INVALID",
    "details": {
        "provider": "gemini",
        "response_snippet": "无法解析JSON响应",
        "expected_format": "JSON数组格式的指令列表"
    },
    "stage": "wservice.ai_optimize_subtitles"
}
```

#### 5. 批处理失败

```json
{
    "success": false,
    "error": "批处理部分失败",
    "error_type": "BATCH_ERROR",
    "details": {
        "total_batches": 5,
        "success_batches": 3,
        "failed_batches": 2,
        "batch_details": [
            {
                "batch_id": 1,
                "status": "FAILED",
                "error": "网络超时"
            },
            {
                "batch_id": 3,
                "status": "FAILED",
                "error": "指令验证失败"
            }
        ]
    }
}
```

#### 6. 文件写入失败

```json
{
    "success": false,
    "error": "无法写入优化文件: /share/workflows/test/optimized.json",
    "error_type": "FILE_WRITE_ERROR",
    "details": {
        "output_path": "/share/workflows/test/optimized.json",
        "error": "Permission denied",
        "available_space": "1.2GB"
    }
}
```

#### 7. 配置文件错误

```json
{
    "success": false,
    "error": "字幕优化配置错误",
    "error_type": "CONFIG_ERROR",
    "details": {
        "parameter": "provider",
        "invalid_value": "invalid_provider",
        "expected_values": ["deepseek", "gemini", "zhipu", "volcengine", "openai_compatible"]
    }
}
```

#### 8. System Prompt文件不存在

```json
{
    "success": false,
    "error": "System prompt文件不存在",
    "error_type": "PROMPT_NOT_FOUND",
    "details": {
        "prompt_path": "/app/prompts/subtitle_optimization.md",
        "search_paths": [
            "/app/prompts/",
            "/share/prompts/"
        ]
    }
}
```

### 错误代码说明

| 错误类型 | 状态码 | HTTP状态码 | 说明 | 解决方案 |
|----------|--------|------------|------|----------|
| `VALUE_ERROR` | INVALID_INPUT | 400 | 输入参数无效 | 检查工作流上下文格式 |
| `PARAM_RESOLVE_ERROR` | INVALID_INPUT | 400 | 动态参数解析失败 | 检查${{}}引用格式和字段名 |
| `FILE_NOT_FOUND` | FILE_ERROR | 404 | 转录文件不存在 | 确保faster_whisper任务已成功完成 |
| `FILE_READ_ERROR` | FILE_ERROR | 400 | 无法读取转录文件 | 检查文件权限和格式 |
| `FILE_WRITE_ERROR` | FILE_ERROR | 500 | 无法写入优化文件 | 检查存储空间和权限 |
| `AI_API_ERROR` | EXTERNAL_ERROR | 502 | AI API调用失败 | 检查API密钥和网络连接 |
| `AI_RESPONSE_INVALID` | PARSE_ERROR | 400 | AI响应格式无效 | 检查System Prompt配置 |
| `PROMPT_NOT_FOUND` | CONFIG_ERROR | 500 | Prompt文件不存在 | 确保prompt文件存在 |
| `BATCH_ERROR` | PROCESSING_ERROR | 422 | 批处理失败 | 查看批处理详情日志 |
| `TIMEOUT_ERROR` | TIMEOUT | 408 | 请求超时 | 增加timeout参数值 |
| `CONFIG_ERROR` | CONFIG_ERROR | 500 | 配置错误 | 检查参数值和类型 |

### 错误恢复策略

#### 1. 自动重试机制
- AI API错误：指数退避重试（1s, 2s, 4s...）
- 最大重试次数：3次（可配置）
- 网络超时：自动重试

#### 2. 优雅降级
- 批处理失败：使用原始字幕
- AI响应无效：跳过该批次
- 部分指令失败：继续执行其他指令

#### 3. 错误日志
- 记录详细错误信息（仅限调试模式）
- 脱敏处理敏感信息（API密钥等）
- 工作流状态持久化

### 调试建议

```python
# 启用详细日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 检查工作流状态
from services.common.state_manager import StateManager
state_mgr = StateManager()
status = state_mgr.get_workflow_status("test-123")
print(status)

# 查看Redis中的工作流数据
import redis
r = redis.Redis(host='redis', db=3)
workflow_data = r.get('workflow_state:test-123')
print(workflow_data)

# 检查GPU锁状态
locks = r.keys('gpu_lock:*')
print(f"活跃GPU锁: {len(locks)}")
```

## 性能指标

### Prometheus监控指标

```python
# 任务执行指标
ai_subtitle_optimization_requests_total  # 总请求数
ai_subtitle_optimization_duration_seconds  # 处理时间
ai_subtitle_optimization_errors_total  # 错误数
ai_subtitle_optimization_segments_count  # 处理片段数
ai_subtitle_optimization_commands_applied  # 应用指令数

# 批处理指标
ai_subtitle_optimization_api_calls_total  # API调用数
ai_subtitle_optimization_api_duration_seconds  # API调用时间
ai_subtitle_optimization_batch_count  # 批处理数量
```

### 性能基准

| 字幕条数 | 批处理模式 | 平均时间 | 95%分位时间 | 内存使用 |
|----------|------------|----------|-------------|----------|
| < 50 | 单批 | 5-10秒 | 15秒 | 200MB |
| 50-200 | 批处理 | 20-60秒 | 90秒 | 500MB |
| 200-500 | 批处理 | 60-120秒 | 180秒 | 1GB |
| > 500 | 批处理 | 2-5分钟 | 8分钟 | 2GB |

### 优化建议

1. **小文件** (<50条): 禁用批处理，避免额外开销
2. **中文件** (50-200条): 批处理大小50，重叠10
3. **大文件** (>200条): 批处理大小100，重叠20
4. **网络慢**: 增加timeout到600秒
5. **API限制**: 降低并发数到2-3

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
