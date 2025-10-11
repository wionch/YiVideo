# IndexTTS Service API 参考文档

## 概述

IndexTTS Service 提供基于 Celery 任务队列的 RESTful API 接口，支持高质量的文本转语音、音色克隆和情感语音控制功能。

## 基础信息

- **基础URL**: `http://localhost:8788`
- **认证方式**: 基于 API Key（可选）
- **数据格式**: JSON
- **字符编码**: UTF-8

## 核心任务 API

### 1. 生成语音 (generate_speech)

生成高质量语音的主要接口，支持音色克隆和情感控制。

**端点**: `POST /v1/workflows`

**请求体**:
```json
{
  "video_path": "/app/videos/example.mp4",
  "workflow_config": {
    "workflow_chain": [
      "indextts.generate_speech"
    ],
    "indextts_config": {
      "text": "要转换的文本内容",
      "output_path": "/share/workflows/output/speech.wav",
      "reference_audio": "/path/to/reference.wav",
      "emotion_reference": "/path/to/emotion.wav",
      "emotion_alpha": 0.65,
      "emotion_vector": [0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.9],
      "emotion_text": "请用开心的语气说这句话",
      "use_random": false,
      "max_text_tokens_per_segment": 120
    }
  }
}
```

**参数说明**:

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `text` | string | ✅ | - | 要转换的文本内容 |
| `output_path` | string | ✅ | - | 输出音频文件路径 |
| `reference_audio` | string | ❌ | null | 音色参考音频文件路径 |
| `emotion_reference` | string | ❌ | null | 情感参考音频文件路径 |
| `emotion_alpha` | float | ❌ | 0.65 | 情感强度 (0.0-1.0) |
| `emotion_vector` | array | ❌ | null | 8维情感向量 [喜,怒,哀,惧,厌恶,低落,惊喜,平静] |
| `emotion_text` | string | ❌ | null | 情感描述文本 |
| `use_random` | boolean | ❌ | false | 是否使用随机采样 |
| `max_text_tokens_per_segment` | integer | ❌ | 120 | 每段最大token数 |

**响应示例**:
```json
{
  "status": "success",
  "workflow_id": "workflow_123456",
  "task_id": "task_789012",
  "output_path": "/share/workflows/output/speech.wav",
  "duration": 12.5,
  "sample_rate": 22050,
  "text_length": 25,
  "processing_time": 8.3,
  "model_info": {
    "model_type": "IndexTTS2",
    "model_version": "2.0",
    "device": "cuda:0"
  },
  "parameters": {
    "reference_audio": "/path/to/reference.wav",
    "emotion_alpha": 0.65,
    "emotion_vector": [0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.9],
    "use_random": false,
    "max_text_tokens_per_segment": 120
  }
}
```

**错误响应**:
```json
{
  "status": "error",
  "error": "输入文本不能为空",
  "task_id": "task_789012",
  "workflow_id": "workflow_123456"
}
```

### 2. 健康检查 (health_check)

检查 IndexTTS 服务的健康状态。

**端点**: `POST /v1/workflows`

**请求体**:
```json
{
  "video_path": "/app/videos/health_check.mp4",
  "workflow_config": {
    "workflow_chain": [
      "indextts.health_check"
    ]
  }
}
```

**响应示例**:
```json
{
  "status": "healthy",
  "service": "indextts_service",
  "gpu": {
    "available": true,
    "count": 1,
    "name": "NVIDIA GeForce RTX 4090"
  },
  "model": "ready",
  "gpu_lock": "available"
}
```

### 3. 获取模型信息 (get_model_info)

获取 IndexTTS2 模型的详细信息。

**端点**: `POST /v1/workflows`

**请求体**:
```json
{
  "video_path": "/app/videos/model_info.mp4",
  "workflow_config": {
    "workflow_chain": [
      "indextts.get_model_info"
    ]
  }
}
```

**响应示例**:
```json
{
  "status": "success",
  "model_info": {
    "model_type": "IndexTTS2",
    "model_version": "2.0",
    "device": "cuda:0",
    "model_path": "/models/indextts",
    "status": "ready",
    "capabilities": {
      "text_to_speech": true,
      "voice_cloning": true,
      "emotion_control": true,
      "multi_language": true,
      "real_time": false
    }
  }
}
```

### 4. 列出语音预设 (list_voice_presets)

获取可用的语音预设列表。

**端点**: `POST /v1/workflows`

**请求体**:
```json
{
  "video_path": "/app/videos/presets.mp4",
  "workflow_config": {
    "workflow_chain": [
      "indextts.list_voice_presets"
    ]
  }
}
```

**响应示例**:
```json
{
  "status": "success",
  "presets": {
    "default": {
      "name": "Default Voice",
      "description": "默认语音",
      "language": "zh-CN",
      "gender": "female"
    },
    "male_01": {
      "name": "Male Voice 01",
      "description": "男声01",
      "language": "zh-CN",
      "gender": "male"
    },
    "female_01": {
      "name": "Female Voice 01",
      "description": "女声01",
      "language": "zh-CN",
      "gender": "female"
    }
  },
  "total_count": 3
}
```

## 监控 API

### 1. GPU锁健康检查

检查 GPU 锁系统的健康状态。

**端点**: `GET /api/v1/monitoring/gpu-lock/health`

**响应示例**:
```json
{
  "status": "healthy",
  "total_locks": 1,
  "active_locks": 0,
  "locks": [
    {
      "lock_key": "gpu_lock:0",
      "locked": false,
      "last_acquired": null,
      "expires_at": null
    }
  ],
  "health_thresholds": {
    "min_success_rate": 0.8,
    "max_timeout_rate": 0.2
  }
}
```

### 2. 任务心跳状态

获取所有任务的心跳状态。

**端点**: `GET /api/v1/monitoring/heartbeat/all`

**响应示例**:
```json
{
  "total_tasks": 5,
  "active_tasks": 3,
  "tasks": [
    {
      "task_id": "task_123",
      "task_name": "indextts.generate_speech",
      "worker_id": "worker@hostname",
      "last_heartbeat": "2025-10-12T10:30:00Z",
      "status": "running"
    }
  ]
}
```

### 3. 系统统计信息

获取系统整体统计信息。

**端点**: `GET /api/v1/monitoring/statistics`

**响应示例**:
```json
{
  "system": {
    "total_tasks": 100,
    "successful_tasks": 95,
    "failed_tasks": 5,
    "success_rate": 0.95,
    "avg_processing_time": 15.2
  },
  "gpu": {
    "utilization": 0.75,
    "memory_used": "6.2GB",
    "memory_total": "8.0GB"
  },
  "workers": {
    "total": 1,
    "active": 1,
    "idle": 0
  }
}
```

## 工作流状态查询

### 1. 查询工作流状态

**端点**: `GET /v1/workflows/status/{workflow_id}`

**响应示例**:
```json
{
  "workflow_id": "workflow_123456",
  "status": "running",
  "current_stage": "indextts.generate_speech",
  "progress": 75,
  "stages": [
    {
      "name": "indextts.generate_speech",
      "status": "running",
      "started_at": "2025-10-12T10:25:00Z",
      "output": {
        "processing_time": 8.3
      }
    }
  ],
  "created_at": "2025-10-12T10:25:00Z",
  "updated_at": "2025-10-12T10:30:00Z"
}
```

## 错误代码

| 错误代码 | HTTP状态码 | 说明 |
|----------|------------|------|
| `INVALID_INPUT` | 400 | 输入参数无效 |
| `MODEL_NOT_READY` | 503 | 模型未就绪 |
| `GPU_UNAVAILABLE` | 503 | GPU不可用 |
| `INSUFFICIENT_MEMORY` | 503 | GPU内存不足 |
| `TASK_TIMEOUT` | 408 | 任务执行超时 |
| `PROCESSING_ERROR` | 500 | 处理过程中发生错误 |

## 使用示例

### 1. 基础文本转语音

```bash
curl -X POST http://localhost:8788/v1/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "/app/videos/example.mp4",
    "workflow_config": {
      "workflow_chain": ["indextts.generate_speech"],
      "indextts_config": {
        "text": "你好，这是IndexTTS2生成的语音。",
        "output_path": "/share/workflows/output/hello.wav"
      }
    }
  }'
```

### 2. 音色克隆

```bash
curl -X POST http://localhost:8788/v1/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "/app/videos/example.mp4",
    "workflow_config": {
      "workflow_chain": ["indextts.generate_speech"],
      "indextts_config": {
        "text": "这是使用音色克隆生成的语音。",
        "output_path": "/share/workflows/output/cloned.wav",
        "reference_audio": "/share/reference/target_voice.wav"
      }
    }
  }'
```

### 3. 情感语音控制

```bash
curl -X POST http://localhost:8788/v1/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "/app/videos/example.mp4",
    "workflow_config": {
      "workflow_chain": ["indextts.generate_speech"],
      "indextts_config": {
        "text": "今天天气真好，心情很愉快！",
        "output_path": "/share/workflows/output/happy.wav",
        "emotion_vector": [0.8, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 0.0]
      }
    }
  }'
```

### 4. 查询工作流状态

```bash
curl -X GET http://localhost:8788/v1/workflows/status/workflow_123456
```

## 性能优化建议

### 1. 参数优化

- **文本长度**: 建议单次处理文本不超过500字符
- **分段设置**: 根据文本复杂度调整 `max_text_tokens_per_segment`
- **情感控制**: 合理使用 `emotion_alpha` 参数 (0.3-0.8)

### 2. 并发控制

- **任务并发**: 建议同时运行的任务数不超过GPU数量
- **批处理**: 对于大量文本，建议分批处理

### 3. 缓存策略

- **模型缓存**: 保持模型常驻内存以提高响应速度
- **结果缓存**: 缓存常用文本的语音生成结果

## SDK 和客户端库

### Python 客户端

```python
import requests
import json

class IndexTTSClient:
    def __init__(self, base_url="http://localhost:8788"):
        self.base_url = base_url

    def generate_speech(self, text, output_path, **kwargs):
        """生成语音"""
        data = {
            "video_path": "/app/videos/api_request.mp4",
            "workflow_config": {
                "workflow_chain": ["indextts.generate_speech"],
                "indextts_config": {
                    "text": text,
                    "output_path": output_path,
                    **kwargs
                }
            }
        }

        response = requests.post(
            f"{self.base_url}/v1/workflows",
            json=data
        )
        return response.json()

    def get_workflow_status(self, workflow_id):
        """查询工作流状态"""
        response = requests.get(
            f"{self.base_url}/v1/workflows/status/{workflow_id}"
        )
        return response.json()

# 使用示例
client = IndexTTSClient()
result = client.generate_speech(
    text="Hello, this is a test.",
    output_path="/share/workflows/output/test.wav"
)
print(result)
```

## 版本历史

### v1.0.0 (2025-10-12)
- 初始版本发布
- 支持基础文本转语音
- 支持音色克隆和情感控制
- 提供完整的监控API

## 许可证

API 接口遵循 MIT 许可证。IndexTTS2 模型遵循其原始许可证。