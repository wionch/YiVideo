# 单任务 API 文档

单任务API允许您直接执行单个AI处理任务，无需创建完整的工作流。这对于独立的、简单的处理任务非常有用。

## 📋 目录

- [概述](#概述)
- [端点列表](#端点列表)
- [任务状态模型](#任务状态模型)
- [创建任务](#创建任务)
- [查询任务状态](#查询任务状态)
- [获取任务结果](#获取任务结果)
- [重试任务](#重试任务)
- [取消任务](#取消任务)
- [健康检查](#健康检查)
- [支持的任务](#支持的任务)
- [Callback机制](#callback机制)
- [示例和最佳实践](#示例和最佳实践)

---

## 概述

### 单任务 vs 工作流

**单任务**：
- 直接执行单个AI处理节点
- 适合简单、独立的任务
- 无需复杂的配置
- 执行速度快

**工作流**：
- 多个任务的组合
- 适合复杂的处理流程
- 支持任务依赖和顺序执行
- 适合批量处理

### 核心特性
- **直接执行**: 绕过工作流，直接调用AI服务
- **状态追踪**: 实时查询任务状态和结果
- **错误恢复**: 支持任务重试
- **Callback支持**: 任务完成后自动回调通知
- **灵活输入**: 支持多种输入数据格式

---

## 端点列表

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/v1/tasks` | 创建并执行单个任务 |
| GET | `/v1/tasks/{task_id}/status` | 查询任务状态 |
| GET | `/v1/tasks/{task_id}/result` | 获取任务完整结果 |
| POST | `/v1/tasks/{task_id}/retry` | 重试失败的任务 |
| DELETE | `/v1/tasks/{task_id}` | 取消任务（运行中） |
| GET | `/v1/tasks/health` | 单任务服务健康检查 |
| GET | `/v1/tasks/supported-tasks` | 获取支持的任务列表 |

---

## 任务状态模型

### 状态定义

| 状态 | 描述 | 可执行操作 |
|------|------|------------|
| pending | 任务已创建，等待执行 | 取消 |
| running | 任务正在执行 | 取消 |
| completed | 任务成功完成 | 重试 |
| failed | 任务执行失败 | 重试 |
| cancelled | 任务已被取消 | 重试 |

### 状态流转图

```
pending → running → completed
              ↓
            failed → retry → pending
              ↓
            cancelled
```

---

## 创建任务

### POST /v1/tasks

创建并执行一个新的任务。

#### 端点信息
- **方法**: `POST`
- **路径**: `/v1/tasks`
- **认证**: 当前无需认证
- **速率限制**: 100次/分钟

#### 请求参数

| 名称 | 类型 | 必需 | 描述 |
|------|------|------|------|
| task_name | string | 是 | 任务名称（如 'ffmpeg.extract_audio'） |
| task_id | string | 否 | 任务ID（不提供则自动生成） |
| callback | string | 否 | 任务完成后的回调URL |
| input_data | object | 是 | 任务输入数据 |

#### 请求示例

**提取音频**：
```bash
curl -X POST "http://localhost:8000/v1/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "task_name": "ffmpeg.extract_audio",
    "task_id": "extract-001",
    "input_data": {
      "video_path": "videos/input.mp4",
      "audio_format": "wav",
      "sample_rate": 16000
    }
  }'
```

**语音识别**：
```bash
curl -X POST "http://localhost:8000/v1/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "task_name": "faster_whisper.transcribe_audio",
    "task_id": "asr-001",
    "input_data": {
      "audio_path": "audio/lecture.wav",
      "language": "zh",
      "model_size": "base"
    }
  }'
```

**带回调的任务**：
```bash
curl -X POST "http://localhost:8000/v1/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "task_name": "paddleocr.perform_ocr",
    "callback": "https://your-domain.com/api/callback",
    "input_data": {
      "image_path": "images/subtitle_region.png",
      "languages": ["chinese", "english"]
    }
  }'
```

#### 响应模型

**成功响应**：
```json
{
    "task_id": "extract-001",
    "status": "pending",
    "message": "任务已创建并开始执行"
}
```

#### 错误响应

**400 Bad Request - 缺少参数**：
```json
{
    "detail": "task_name不能为空"
}
```

**400 Bad Request - 无效回调URL**：
```json
{
    "detail": "无效的callback URL格式"
}
```

**500 Internal Server Error - 服务器错误**：
```json
{
    "detail": "创建单任务失败: [错误详情]"
}
```

---

## 查询任务状态

### GET /v1/tasks/{task_id}/status

查询任务的当前状态。

#### 端点信息
- **方法**: `GET`
- **路径**: `/v1/tasks/{task_id}/status`
- **认证**: 当前无需认证
- **速率限制**: 200次/分钟

#### 路径参数

| 名称 | 类型 | 必需 | 描述 |
|------|------|------|------|
| task_id | string | 是 | 任务ID |

#### 请求示例

```bash
curl -X GET "http://localhost:8000/v1/tasks/extract-001/status"
```

#### 响应模型

**任务进行中**：
```json
{
    "task_id": "extract-001",
    "status": "running",
    "message": "任务正在执行中",
    "created_at": "2025-12-05T02:56:00",
    "updated_at": "2025-12-05T02:57:30",
    "callback_status": null
}
```

**任务已完成**：
```json
{
    "task_id": "extract-001",
    "status": "completed",
    "message": "任务执行成功",
    "result": {
        "audio_path": "videos/input_audio.wav",
        "duration": 3600,
        "format": "wav",
        "sample_rate": 16000
    },
    "minio_files": [
        {
            "file_path": "videos/input_audio.wav",
            "download_url": "http://localhost:9000/...",
            "size": 57600000,
            "content_type": "audio/wav"
        }
    ],
    "created_at": "2025-12-05T02:56:00",
    "updated_at": "2025-12-05T02:59:15",
    "callback_status": "pending"
}
```

**任务失败**：
```json
{
    "task_id": "extract-001",
    "status": "failed",
    "message": "GPU内存不足，无法加载模型",
    "result": {
        "error": "GPU内存不足，无法加载模型",
        "error_code": "GPU_OUT_OF_MEMORY"
    },
    "created_at": "2025-12-05T02:56:00",
    "updated_at": "2025-12-05T02:58:00"
}
```

#### 响应字段说明

- `task_id` (string): 任务ID
- `status` (string): 任务状态
- `message` (string): 状态消息
- `result` (object): 任务结果数据（完成/失败时有）
- `minio_files` (array): MinIO文件信息列表（完成时有）
- `created_at` (string): 创建时间
- `updated_at` (string): 最后更新时间
- `callback_status` (string): 回调发送状态（pending/sent/failed）

#### 错误响应

**404 Not Found - 任务不存在**：
```json
{
    "detail": "任务不存在: extract-001"
}
```

---

## 获取任务结果

### GET /v1/tasks/{task_id}/result

获取任务的完整结果（包含更多详细信息）。

#### 端点信息
- **方法**: `GET`
- **路径**: `/v1/tasks/{task_id}/result`
- **认证**: 当前无需认证

#### 请求示例

```bash
curl -X GET "http://localhost:8000/v1/tasks/extract-001/result"
```

#### 响应示例

```json
{
    "task_id": "extract-001",
    "status": "completed",
    "message": "任务执行成功",
    "result": {
        "audio_path": "videos/input_audio.wav",
        "duration": 3600,
        "format": "wav",
        "sample_rate": 16000,
        "channels": 1,
        "bit_rate": 128000
    },
    "minio_files": [
        {
            "file_path": "videos/input_audio.wav",
            "download_url": "http://localhost:9000/yivideo/videos/input_audio.wav",
            "size": 57600000,
            "content_type": "audio/wav"
        }
    ],
    "input_params": {
        "task_name": "ffmpeg.extract_audio",
        "task_id": "extract-001",
        "input_data": {
            "video_path": "videos/input.mp4",
            "audio_format": "wav",
            "sample_rate": 16000
        }
    },
    "execution_info": {
        "start_time": "2025-12-05T02:56:00",
        "end_time": "2025-12-05T02:59:15",
        "duration": 195,
        "worker_id": "worker_1",
        "queue": "ffmpeg_queue"
    },
    "created_at": "2025-12-05T02:56:00",
    "updated_at": "2025-12-05T02:59:15"
}
```

**区别说明**：
- `/status`: 轻量级状态信息，快速查询
- `/result`: 完整结果数据，包含输入参数和执行信息

---

## 重试任务

### POST /v1/tasks/{task_id}/retry

重试失败或已完成的任务（创建新任务实例）。

#### 端点信息
- **方法**: `POST`
- **路径**: `/v1/tasks/{task_id}/retry`
- **认证**: 当前无需认证

#### 路径参数

| 名称 | 类型 | 必需 | 描述 |
|------|------|------|------|
| task_id | string | 是 | 要重试的任务ID |

#### 请求示例

```bash
curl -X POST "http://localhost:8000/v1/tasks/extract-001/retry"
```

#### 响应示例

```json
{
    "task_id": "extract-001-retry-a1b2c3d4",
    "status": "pending",
    "message": "任务重试已开始，原任务ID: extract-001"
}
```

**说明**：
- 会生成新的任务ID，避免与原任务冲突
- 使用原任务的输入参数
- 可以修改输入参数后重试

#### 错误响应

**400 Bad Request - 任务状态不允许重试**：
```json
{
    "detail": "任务状态不允许重试: running"
}
```

**404 Not Found - 任务不存在**：
```json
{
    "detail": "任务不存在: extract-001"
}
```

---

## 取消任务

### DELETE /v1/tasks/{task_id}

取消正在运行或等待执行的任务。

#### 端点信息
- **方法**: `DELETE`
- **路径**: `/v1/tasks/{task_id}`
- **认证**: 当前无需认证

#### 路径参数

| 名称 | 类型 | 必需 | 描述 |
|------|------|------|------|
| task_id | string | 是 | 要取消的任务ID |

#### 请求示例

```bash
curl -X DELETE "http://localhost:8000/v1/tasks/extract-001"
```

#### 响应示例

**成功取消**：
```json
{
    "task_id": "extract-001",
    "status": "cancelled",
    "message": "任务已成功取消"
}
```

#### 错误响应

**400 Bad Request - 任务状态不允许取消**：
```json
{
    "detail": "任务状态不允许取消: completed"
}
```

**404 Not Found - 任务不存在**：
```json
{
    "detail": "任务不存在: extract-001"
}
```

---

## 健康检查

### GET /v1/tasks/health

检查单任务服务的健康状态。

#### 端点信息
- **方法**: `GET`
- **路径**: `/v1/tasks/health`
- **认证**: 当前无需认证

#### 响应示例

**健康**：
```json
{
    "status": "healthy",
    "service": "single_task_api",
    "celery_broker": "redis://redis:6379/0",
    "minio_service": "available"
}
```

**不健康**：
```json
{
    "status": "unhealthy",
    "error": "无法连接到Celery Broker"
}
```

---

## 支持的任务

### GET /v1/tasks/supported-tasks

获取所有支持的单任务类型列表。

#### 端点信息
- **方法**: `GET`
- **路径**: `/v1/tasks/supported-tasks`
- **认证**: 当前无需认证

#### 响应示例

```json
{
    "supported_tasks": {
        "ffmpeg": [
            "ffmpeg.extract_keyframes",
            "ffmpeg.extract_audio",
            "ffmpeg.crop_subtitle_images",
            "ffmpeg.split_audio_segments"
        ],
        "faster_whisper": [
            "faster_whisper.transcribe_audio"
        ],
        "audio_separator": [
            "audio_separator.separate_vocals"
        ],
        "pyannote_audio": [
            "pyannote_audio.diarize_speakers"
        ],
        "paddleocr": [
            "paddleocr.detect_subtitle_area",
            "paddleocr.perform_ocr"
        ],
        "indextts": [
            "indextts.generate_speech"
        ],
        "wservice": [
            "wservice.generate_subtitle_files",
            "wservice.correct_subtitles",
            "wservice.ai_optimize_subtitles"
        ]
    },
    "total_count": 16,
    "description": "所有支持的单个工作流节点任务"
}
```

### 支持的任务详细列表

#### FFmpeg 服务
- `ffmpeg.extract_keyframes` - 提取视频关键帧
- `ffmpeg.extract_audio` - 从视频提取音频
- `ffmpeg.crop_subtitle_images` - 提取字幕区域图像
- `ffmpeg.split_audio_segments` - 分割音频片段

#### Faster-Whisper 服务
- `faster_whisper.transcribe_audio` - 语音识别转文字

#### 音频分离服务
- `audio_separator.separate_vocals` - 人声和背景音乐分离

#### Pyannote-Audio 服务
- `pyannote_audio.diarize_speakers` - 说话人分离和识别

#### PaddleOCR 服务
- `paddleocr.detect_subtitle_area` - 检测字幕区域
- `paddleocr.perform_ocr` - OCR文字识别

#### IndexTTS 服务
- `indextts.generate_speech` - 文本转语音合成

#### WService 服务
- `wservice.generate_subtitle_files` - 生成字幕文件
- `wservice.correct_subtitles` - 字幕文本纠错
- `wservice.ai_optimize_subtitles` - AI字幕优化

---

## Callback机制

### 工作原理

当任务完成时，系统会向指定的callback URL发送POST请求，通知任务结果。

### Callback 请求格式

**请求头**：
```http
Content-Type: application/json
X-Task-Status: completed  # 或 failed
```

**请求体**：
```json
{
    "task_id": "extract-001",
    "status": "completed",
    "result": {
        "audio_path": "videos/input_audio.wav",
        "duration": 3600
    },
    "minio_files": [
        {
            "file_path": "videos/input_audio.wav",
            "download_url": "http://localhost:9000/...",
            "size": 57600000
        }
    ],
    "timestamp": "2025-12-05T02:59:15Z"
}
```

### Callback 验证

Callback URL必须满足以下条件：
- 必须是有效的HTTP/HTTPS URL
- 不能包含特殊字符
- 建议使用POST方法接收回调

### 使用示例

```bash
curl -X POST "http://localhost:8000/v1/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "task_name": "faster_whisper.transcribe_audio",
    "task_id": "asr-001",
    "callback": "https://your-domain.com/api/task-callback",
    "input_data": {
      "audio_path": "audio/lecture.wav",
      "language": "zh"
    }
  }'
```

### Callback 服务器示例（Python Flask）

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/api/task-callback', methods=['POST'])
def handle_callback():
    data = request.json
    task_id = data.get('task_id')
    status = data.get('status')
    result = data.get('result')

    print(f"任务 {task_id} {status}")
    print(f"结果: {result}")

    # 处理任务结果
    if status == 'completed':
        # 下载文件或进一步处理
        pass
    elif status == 'failed':
        # 处理失败情况
        pass

    return jsonify({"received": True})

if __name__ == '__main__':
    app.run(port=5000)
```

---

## 示例和最佳实践

### 示例1：完整的单任务执行流程

```bash
# 1. 创建任务
response=$(curl -s -X POST "http://localhost:8000/v1/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "task_name": "ffmpeg.extract_audio",
    "task_id": "extract-001",
    "input_data": {
      "video_path": "videos/input.mp4",
      "audio_format": "wav"
    }
  }')

task_id=$(echo "$response" | jq -r '.task_id')
echo "任务ID: $task_id"

# 2. 轮询任务状态
while true; do
    status=$(curl -s "http://localhost:8000/v1/tasks/$task_id/status")
    current_status=$(echo "$status" | jq -r '.status')
    echo "当前状态: $current_status"

    if [ "$current_status" == "completed" ]; then
        echo "任务完成！"
        # 获取结果
        result=$(curl -s "http://localhost:8000/v1/tasks/$task_id/result")
        echo "$result" | jq '.result'
        break
    elif [ "$current_status" == "failed" ]; then
        echo "任务失败！"
        error=$(echo "$status" | jq -r '.result.error')
        echo "错误: $error"
        break
    fi

    sleep 3
done
```

### 示例2：批量任务执行

```bash
#!/bin/bash

tasks=(
    '{"task_name": "ffmpeg.extract_keyframes", "task_id": "task1", "input_data": {"video_path": "v1.mp4", "interval": 10}}'
    '{"task_name": "ffmpeg.extract_keyframes", "task_id": "task2", "input_data": {"video_path": "v2.mp4", "interval": 10}}'
    '{"task_name": "ffmpeg.extract_keyframes", "task_id": "task3", "input_data": {"video_path": "v3.mp4", "interval": 10}}'
)

# 并发执行任务
for task in "${tasks[@]}"; do
    curl -X POST "http://localhost:8000/v1/tasks" \
      -H "Content-Type: application/json" \
      -d "$task" &
done

# 等待所有任务完成
wait
echo "所有任务已提交"
```

### 示例3：带回调的异步任务

```python
import requests
import time

# 创建任务
task_data = {
    "task_name": "faster_whisper.transcribe_audio",
    "callback": "https://your-domain.com/callback",
    "input_data": {
        "audio_path": "audio/lecture.wav",
        "language": "zh"
    }
}

response = requests.post(
    "http://localhost:8000/v1/tasks",
    json=task_data
)

task_id = response.json()['task_id']
print(f"任务已创建: {task_id}")

# 任务将在后台执行，完成后自动回调
# 无需轮询状态
```

### 示例4：任务失败重试

```bash
# 检查任务状态
status=$(curl -s "http://localhost:8000/v1/tasks/extract-001/status")
current_status=$(echo "$status" | jq -r '.status')

if [ "$current_status" == "failed" ]; then
    echo "任务失败，开始重试..."
    # 重试任务
    retry_response=$(curl -s -X POST "http://localhost:8000/v1/tasks/extract-001/retry")
    new_task_id=$(echo "$retry_response" | jq -r '.task_id')
    echo "新任务ID: $new_task_id"
fi
```

### 最佳实践

#### 1. 任务设计
- **单一职责**: 每个任务只做一件事
- **独立执行**: 避免任务间的复杂依赖
- **参数验证**: 在提交前验证输入参数

#### 2. 状态管理
- **合理轮询**: 避免过于频繁的状态查询（建议3-5秒间隔）
- **超时设置**: 设置合理的任务超时时间
- **状态持久化**: 保存重要任务的task_id

#### 3. 错误处理
- **捕获异常**: 妥善处理网络和API错误
- **重试机制**: 对临时失败实施指数退避重试
- **错误日志**: 记录和监控任务失败原因

#### 4. 性能优化
- **批量提交**: 合理控制并发任务数量
- **回调优先**: 优先使用callback机制而非轮询
- **资源管理**: 及时下载和处理结果文件

#### 5. 调试技巧
- **使用健康检查**: 定期检查服务健康状态
- **查看任务列表**: 使用 `GET /v1/tasks/supported-tasks` 了解可用任务
- **分层测试**: 先用简单任务测试，再执行复杂任务

---

## 性能说明

- **任务创建**: < 50ms
- **状态查询**: < 30ms
- **任务执行时间**: 取决于具体任务类型
- **并发限制**: 建议不超过10个并发任务

## 相关文档

- [工作流API](WORKFLOW_API.md)
- [文件操作API](FILE_OPERATIONS_API.md)
- [监控API](MONITORING_API.md)
- [工作流节点参考](../technical/reference/WORKFLOW_NODES_REFERENCE.md)

## 更新日志

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2025-12-05 | 初始单任务API文档 |

---

*最后更新: 2025-12-05 | 文档版本: 1.0.0*
