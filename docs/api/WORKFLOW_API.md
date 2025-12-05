# 工作流 API 文档

工作流API是YiVideo平台的核心功能，支持动态编排AI视频处理流程。通过工作流，您可以定义多阶段的视频处理任务链，系统会自动调度和执行。

## 📋 目录

- [概述](#概述)
- [端点列表](#端点列表)
- [创建工作流](#创建工作流)
- [查询工作流状态](#查询工作流状态)
- [工作流配置](#工作流配置)
- [执行模式](#执行模式)
- [示例和最佳实践](#示例和最佳实践)

---

## 概述

### 工作流概念
工作流是AI视频处理任务的组合，包含多个顺序执行的节点。每个节点代表一个特定的AI处理任务（如语音识别、字幕生成等）。

### 核心特性
- **动态编排**: 通过JSON配置动态构建处理流程
- **多执行模式**: 支持完整执行、增量追加、失败重试
- **状态持久化**: 实时保存工作流状态和中间结果
- **错误恢复**: 支持从失败节点重新执行

---

## 端点列表

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/v1/workflows` | 创建或增量执行工作流 |
| GET | `/v1/workflows/status/{workflow_id}` | 查询工作流当前状态 |
| GET | `/` | 根路径健康检查 |
| GET | `/test` | GET测试端点 |
| POST | `/test` | POST测试端点 |

---

## 创建工作流

### POST /v1/workflows

创建新的工作流或对现有工作流执行增量操作。

#### 端点信息
- **方法**: `POST`
- **路径**: `/v1/workflows`
- **认证**: 当前无需认证
- **速率限制**: 继承API网关限制
- **异步**: 返回202状态码，工作流异步执行

#### 请求参数

| 名称 | 类型 | 必需 | 描述 |
|------|------|------|------|
| video_path | string | 创建时必需 | 视频文件路径（在MinIO中） |
| workflow_config | object | 是 | 工作流配置对象 |
| workflow_id | string | 增量时必需 | 现有工作流ID |
| execution_mode | string | 否 | 执行模式：full/incremental/retry（默认：full） |
| param_merge_strategy | string | 否 | 参数合并策略：merge/override/strict（默认：merge） |
| **节点参数** | any | 否 | 自定义节点参数 |

#### workflow_config 结构
```json
{
    "workflow_chain": [
        "节点1名称",
        "节点2名称",
        ...
    ]
}
```

#### 请求示例

**创建新工作流**：
```bash
curl -X POST "http://localhost:8000/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "videos/input.mp4",
    "workflow_config": {
      "workflow_chain": [
        "faster_whisper.transcribe_audio",
        "pyannote_audio.diarize_speakers",
        "wservice.generate_subtitle_files"
      ]
    },
    "language": "zh",
    "enable_optimization": true
  }'
```

**增量执行（追加任务）**：
```bash
curl -X POST "http://localhost:8000/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "execution_mode": "incremental",
    "workflow_config": {
      "workflow_chain": [
        "paddleocr.detect_subtitle_area",
        "indextts.generate_speech"
      ]
    },
    "subtitle_region": {
      "top": 100,
      "bottom": 200
    }
  }'
```

**重试失败工作流**：
```bash
curl -X POST "http://localhost:8000/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "execution_mode": "retry",
    "workflow_config": {
      "workflow_chain": [
        "faster_whisper.transcribe_audio",
        "pyannote_audio.diarize_speakers"
      ]
    }
  }'
```

#### 响应模型

**成功响应** (202 Accepted)：
```json
{
    "workflow_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "execution_mode": "full",
    "tasks_total": 3,
    "tasks_skipped": 0,
    "tasks_to_execute": 3,
    "message": "New workflow created and started successfully."
}
```

**响应字段说明**：
- `workflow_id` (string): 工作流的唯一标识符
- `execution_mode` (string): 实际执行的模式
- `tasks_total` (int): 总任务数
- `tasks_skipped` (int): 跳过的任务数（已完成的任务）
- `tasks_to_execute` (int): 本次执行的任务数
- `message` (string): 结果描述

#### 错误响应

**400 Bad Request - 缺少必需参数**：
```json
{
    "detail": "创建新工作流时 'video_path' 字段为必需"
}
```

**404 Not Found - 工作流不存在**：
```json
{
    "detail": "工作流 'a1b2c3d4-e5f6-7890-abcd-ef1234567890' 不存在"
}
```

**409 Conflict - 工作流正在被修改**：
```json
{
    "detail": "工作流正在被另一个请求修改，请稍后重试"
}
```

**500 Internal Server Error - 内部错误**：
```json
{
    "detail": "An internal error occurred: [错误详情]"
}
```

---

## 查询工作流状态

### GET /v1/workflows/status/{workflow_id}

查询工作流的当前状态、执行进度和结果。

#### 端点信息
- **方法**: `GET`
- **路径**: `/v1/workflows/status/{workflow_id}`
- **认证**: 当前无需认证
- **速率限制**: 100次/分钟

#### 路径参数

| 名称 | 类型 | 必需 | 描述 |
|------|------|------|------|
| workflow_id | string | 是 | 工作流ID |

#### 请求示例

```bash
curl -X GET "http://localhost:8000/v1/workflows/status/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

#### 响应模型

**工作流进行中**：
```json
{
    "workflow_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "create_at": "2025-12-05T02:56:00",
    "input_params": {
        "video_path": "videos/input.mp4",
        "workflow_chain": [
            "faster_whisper.transcribe_audio",
            "pyannote_audio.diarize_speakers"
        ],
        "node_params": {
            "language": "zh",
            "enable_optimization": true
        }
    },
    "shared_storage_path": "/share/workflows/a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "stages": {
        "stage_0": {
            "status": "completed",
            "input": { ... },
            "output": { ... },
            "start_time": "2025-12-05T02:56:01",
            "end_time": "2025-12-05T02:57:30",
            "duration": 89
        },
        "stage_1": {
            "status": "running",
            "input": { ... },
            "start_time": "2025-12-05T02:57:31"
        }
    },
    "error": null
}
```

**工作流已完成**：
```json
{
    "workflow_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "create_at": "2025-12-05T02:56:00",
    "input_params": { ... },
    "shared_storage_path": "/share/workflows/a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "stages": {
        "stage_0": {
            "status": "completed",
            "input": { ... },
            "output": { ... },
            "start_time": "2025-12-05T02:56:01",
            "end_time": "2025-12-05T02:57:30",
            "duration": 89
        },
        "stage_1": {
            "status": "completed",
            "input": { ... },
            "output": { ... },
            "start_time": "2025-12-05T02:57:31",
            "end_time": "2025-12-05T02:59:15",
            "duration": 104
        }
    },
    "error": null
}
```

**工作流失败**：
```json
{
    "workflow_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "create_at": "2025-12-05T02:56:00",
    "input_params": { ... },
    "shared_storage_path": "/share/workflows/a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "stages": {
        "stage_0": {
            "status": "completed",
            "input": { ... },
            "output": { ... },
            "start_time": "2025-12-05T02:56:01",
            "end_time": "2025-12-05T02:57:30",
            "duration": 89
        },
        "stage_1": {
            "status": "failed",
            "error": "GPU内存不足，无法加载模型",
            "input": { ... },
            "start_time": "2025-12-05T02:57:31",
            "end_time": "2025-12-05T02:58:00",
            "duration": 29
        }
    },
    "error": "GPU内存不足，无法加载模型"
}
```

#### 响应字段说明

**主要字段**：
- `workflow_id` (string): 工作流ID
- `create_at` (string): 创建时间（ISO 8601格式）
- `input_params` (object): 输入参数
  - `video_path` (string): 视频路径
  - `workflow_chain` (array): 任务链
  - `node_params` (object): 节点参数
- `shared_storage_path` (string): 共享存储路径
- `stages` (object): 各阶段状态
  - `stage_N` (object): 第N个阶段
    - `status` (string): 状态（pending/running/completed/failed）
    - `input` (object): 输入数据
    - `output` (object): 输出结果（完成时有）
    - `error` (string): 错误信息（失败时有）
    - `start_time` (string): 开始时间
    - `end_time` (string): 结束时间
    - `duration` (int): 持续时间（秒）
- `error` (string): 整体错误信息（如果有）

#### 错误响应

**404 Not Found - 工作流不存在**：
```json
{
    "detail": "工作流不存在"
}
```

---

## 测试端点

### GET /

根路径健康检查端点。

#### 端点信息
- **方法**: `GET`
- **路径**: `/`
- **认证**: 无需认证

#### 响应示例
```json
{
    "message": "YiVideo AI Workflow Engine API is running."
}
```

---

### GET /test

测试端点，返回接收到的请求信息。

#### 端点信息
- **方法**: `GET`
- **路径**: `/test`
- **认证**: 无需认证

#### 响应示例
```json
{
    "status": "success",
    "message": "Test endpoint received your request",
    "request_info": {
        "method": "GET",
        "url": "http://localhost:8000/test",
        "client_ip": "127.0.0.1",
        "content_length": 0
    },
    "headers": {
        "host": "localhost:8000",
        "user-agent": "curl/7.68.0"
    },
    "body": null,
    "timestamp": "2025-12-05T02:56:00"
}
```

---

### POST /test

测试端点，打印请求头和Body。

#### 端点信息
- **方法**: `POST`
- **路径**: `/test`
- **认证**: 无需认证

#### 请求示例
```bash
curl -X POST "http://localhost:8000/test" \
  -H "Content-Type: application/json" \
  -d '{"key": "value", "number": 123}'
```

#### 响应示例
```json
{
    "status": "success",
    "message": "Test endpoint received your request",
    "request_info": {
        "method": "POST",
        "url": "http://localhost:8000/test",
        "client_ip": "127.0.0.1",
        "content_length": 37
    },
    "headers": {
        "host": "localhost:8000",
        "content-type": "application/json",
        "user-agent": "curl/7.68.0"
    },
    "body": "{\"key\": \"value\", \"number\": 123}",
    "timestamp": "2025-12-05T02:56:00"
}
```

---

## 工作流配置

### workflow_chain 结构

`workflow_chain`是一个数组，包含按顺序执行的任务名称：

```json
{
    "workflow_chain": [
        "faster_whisper.transcribe_audio",
        "pyannote_audio.diarize_speakers",
        "wservice.generate_subtitle_files"
    ]
}
```

### 支持的任务节点

#### 音频处理
- `faster_whisper.transcribe_audio` - 语音识别
- `audio_separator.separate_vocals` - 人声分离
- `pyannote_audio.diarize_speakers` - 说话人分离

#### 视频处理
- `ffmpeg.extract_keyframes` - 提取关键帧
- `ffmpeg.extract_audio` - 提取音频
- `ffmpeg.crop_subtitle_images` - 提取字幕区域图像
- `ffmpeg.split_audio_segments` - 分割音频片段

#### 文字处理
- `paddleocr.detect_subtitle_area` - 检测字幕区域
- `paddleocr.perform_ocr` - OCR文字识别

#### 语音合成
- `indextts.generate_speech` - TTS语音生成
- `gptsovits_service.generate_speech` - GPT-SoVITS语音合成

#### 字幕处理
- `wservice.generate_subtitle_files` - 生成字幕文件
- `wservice.correct_subtitles` - 字幕纠错
- `wservice.ai_optimize_subtitles` - AI字幕优化

完整列表可通过 `GET /v1/tasks/supported-tasks` 获取。

---

## 执行模式

### 1. full 模式（默认）

创建全新的工作流。

**特性**：
- 生成新的workflow_id
- 必须提供video_path
- 执行所有任务链中的任务
- 适合首次处理视频

**场景**：
```json
{
    "execution_mode": "full",
    "video_path": "videos/input.mp4",
    "workflow_config": {
        "workflow_chain": ["task1", "task2", "task3"]
    }
}
```

### 2. incremental 模式

向现有工作流追加新任务（仅允许尾部追加）。

**特性**：
- 需要现有workflow_id
- 跳过已完成的任务
- 仅执行新增的任务
- 适合需要分阶段处理的场景

**场景**：
```json
{
    "execution_mode": "incremental",
    "workflow_id": "existing-id",
    "workflow_config": {
        "workflow_chain": ["task1", "task2", "task3", "task4"]
    }
}
```

*假设task1-3已完成，则只执行task4*

### 3. retry 模式

从失败的任务开始重新执行。

**特性**：
- 需要现有workflow_id
- 跳过成功完成的任务
- 从失败任务重新开始执行
- 适合故障恢复

**场景**：
```json
{
    "execution_mode": "retry",
    "workflow_id": "failed-id",
    "workflow_config": {
        "workflow_chain": ["task1", "task2", "task3"]
    }
}
```

*假设task1成功，task2失败，则从task2开始重试*

---

## 参数合并策略

### merge 模式（默认）

智能合并新旧参数，新参数覆盖旧参数。

```json
{
    "param_merge_strategy": "merge",
    "old_params": {"a": 1, "b": 2, "c": 3},
    "new_params": {"b": 20, "d": 4}
}
```

**结果**：`{a: 1, b: 20, c: 3, d: 4}`

### override 模式

完全使用新参数，忽略旧参数。

```json
{
    "param_merge_strategy": "override",
    "old_params": {"a": 1, "b": 2, "c": 3},
    "new_params": {"b": 20, "d": 4}
}
```

**结果**：`{b: 20, d: 4}`

### strict 模式

检测到参数冲突时报错。

```json
{
    "param_merge_strategy": "strict",
    "old_params": {"a": 1, "b": 2},
    "new_params": {"b": 20}
}
```

**结果**：返回400错误，提示参数冲突

---

## 示例和最佳实践

### 示例1：完整视频处理流程

```bash
# 创建工作流
curl -X POST "http://localhost:8000/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "videos/lecture.mp4",
    "workflow_config": {
      "workflow_chain": [
        "faster_whisper.transcribe_audio",
        "pyannote_audio.diarize_speakers",
        "wservice.generate_subtitle_files"
      ]
    },
    "language": "zh",
    "enable_optimization": true
  }'
```

**响应**：
```json
{
    "workflow_id": "123e4567-e89b-12d3-a456-426614174000",
    "execution_mode": "full",
    "tasks_total": 3,
    "tasks_to_execute": 3,
    "message": "New workflow created and started successfully."
}
```

**轮询状态**：
```bash
while true; do
    status=$(curl -s "http://localhost:8000/v1/workflows/status/123e4567-e89b-12d3-a456-426614174000")
    echo "$status" | jq '.stages'
    if echo "$status" | jq -e '.error' > /dev/null; then
        echo "工作流失败"
        break
    fi
    completed=$(echo "$status" | jq '[.stages[] | select(.status == "completed")] | length')
    total=$(echo "$status" | jq '[.stages[] | keys] | length')
    if [ "$completed" -eq "$total" ]; then
        echo "工作流完成"
        break
    fi
    sleep 5
done
```

### 示例2：增量处理

```bash
# 初始工作流
curl -X POST "http://localhost:8000/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "videos/input.mp4",
    "workflow_config": {
      "workflow_chain": [
        "faster_whisper.transcribe_audio",
        "pyannote_audio.diarize_speakers"
      ]
    }
  }'

# 等待完成...

# 追加字幕生成任务
curl -X POST "http://localhost:8000/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "123e4567-e89b-12d3-a456-426614174000",
    "execution_mode": "incremental",
    "workflow_config": {
      "workflow_chain": [
        "faster_whisper.transcribe_audio",
        "pyannote_audio.diarize_speakers",
        "wservice.generate_subtitle_files"
      ]
    }
  }'
```

### 示例3：错误恢复

```bash
# 检查工作流状态
status=$(curl -s "http://localhost:8000/v1/workflows/status/123e4567-e89b-12d3-a456-426614174000")
error=$(echo "$status" | jq -r '.error')

if [ "$error" != "null" ]; then
    echo "工作流失败，开始重试..."
    # 重试工作流
    curl -X POST "http://localhost:8000/v1/workflows" \
      -H "Content-Type: application/json" \
      -d '{
        "workflow_id": "123e4567-e89b-12d3-a456-426614174000",
        "execution_mode": "retry",
        "workflow_config": {
          "workflow_chain": [
            "faster_whisper.transcribe_audio",
            "pyannote_audio.diarize_speakers"
          ]
        }
      }'
fi
```

### 最佳实践

#### 1. 工作流设计
- **拆分任务**: 将复杂的视频处理拆分为多个独立任务
- **错误隔离**: 每个任务应该是相对独立的，避免级联失败
- **资源优化**: 合理规划任务顺序，避免重复加载模型

#### 2. 参数管理
- **使用merge策略**: 保持参数的可扩展性
- **参数验证**: 在创建工作流前验证参数格式
- **默认值**: 合理使用默认值减少请求参数

#### 3. 状态监控
- **轮询频率**: 建议每5-10秒查询一次状态
- **超时设置**: 设置合理的总超时时间（建议30分钟以上）
- **错误处理**: 及时捕获和处理工作流错误

#### 4. 并发控制
- **避免过载**: 不要同时创建过多工作流
- **资源清理**: 及时清理已完成的工作流文件
- **增量处理**: 使用incremental模式优化重复处理

#### 5. 调试技巧
- **使用test端点**: 验证请求格式
- **查看日志**: 监控API Gateway和Worker日志
- **分步执行**: 先用单任务API测试单个节点

---

## 性能说明

- **工作流创建**: < 100ms
- **状态查询**: < 50ms
- **工作流执行时间**: 取决于任务链复杂度和视频长度
- **存储要求**: 每个工作流约占用100MB-1GB存储空间

## 相关文档

- [单任务API](SINGLE_TASK_API.md)
- [文件操作API](FILE_OPERATIONS_API.md)
- [监控API](MONITORING_API.md)
- [工作流节点参考](../technical/reference/WORKFLOW_NODES_REFERENCE.md)

## 更新日志

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2025-12-05 | 初始工作流API文档 |

---

*最后更新: 2025-12-05 | 文档版本: 1.0.0*
