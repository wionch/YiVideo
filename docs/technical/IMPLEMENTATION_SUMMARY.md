# YiVideo API Gateway 扩展实现总结

## 项目概述

成功为YiVideo系统的API Gateway组件添加了两个主要功能：

1. **MinIO文件接口** (`/v1/files/*`) - 为各组件提供独立的文件管理API
2. **单任务接口** (`/v1/tasks/*`) - 支持单个工作流节点执行和callback机制

## 完成的功能模块

### 1. 依赖管理
- ✅ 在 `services/api_gateway/requirements.txt` 中添加了 `minio` 依赖

### 2. MinIO文件服务 (`minio_service.py`)
- ✅ `MinIOFileService` 类：完整的MinIO操作接口
- ✅ 支持文件上传、下载、删除、列出功能
- ✅ 从环境变量读取配置：`MINIO_HOST`, `MINIO_PORT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`
- ✅ 默认文件桶：`yivideo`
- ✅ 支持task_id目录结构：`yivideo/{task_id}/`
- ✅ 预签名URL生成和文件存在性检查
- ✅ 完整的错误处理和日志记录
- ✅ 单例模式确保资源管理

### 3. API模型定义 (`single_task_models.py`)
- ✅ `TaskStatus` 枚举：pending, running, completed, failed
- ✅ `SingleTaskRequest` - 单任务请求模型
- ✅ `SingleTaskResponse` - 单任务响应模型
- ✅ `TaskStatusResponse` - 任务状态查询响应
- ✅ `FileInfo` - 文件信息模型
- ✅ `CallbackResult` - Callback结果模型
- ✅ 文件操作相关模型：`FileUploadRequest`, `FileUploadResponse`, `FileOperationResponse`, `FileListResponse`, `FileListItem`, `ErrorResponse`

### 4. Callback管理器 (`callback_manager.py`)
- ✅ `CallbackManager` 类：处理任务完成后的通知机制
- ✅ 支持重试机制：指数退避策略（1s, 2s, 4s）
- ✅ 最大重试次数：3次
- ✅ URL验证：防止恶意callback地址（阻止localhost、127.0.0.1等）
- ✅ 批量callback发送支持
- ✅ 完善的错误处理和日志记录
- ✅ HTTP状态码判断：仅对5xx错误重试
- ✅ 单例模式确保全局一致性

### 5. 单任务执行器 (`single_task_executor.py`)
- ✅ `SingleTaskExecutor` 类：执行单个工作流节点
- ✅ 支持所有工作流节点：
  - FFmpeg服务：`ffmpeg.extract_keyframes`, `ffmpeg.extract_audio`, `ffmpeg.crop_subtitle_images`, `ffmpeg.split_audio_segments`
  - Faster-Whisper服务：`faster_whisper.transcribe_audio`
  - Audio Separator服务：`audio_separator.separate_vocals`
  - Pyannote Audio服务：`pyannote_audio.diarize_speakers`
  - PaddleOCR服务：`paddleocr.detect_subtitle_area`, `paddleocr.perform_ocr`
  - IndexTTS服务：`indextts.generate_speech`
  - WService服务：`wservice.generate_subtitle_files`, `wservice.correct_subtitles`, `wservice.ai_optimize_subtitles`
- ✅ 任务状态管理：pending, running, completed, failed, cancelled
- ✅ **HTTP文件路径自动处理**：检测input_data中的HTTP/HTTPS链接并自动下载到临时目录
- ✅ **智能文件扫描**：从任务结果中自动提取文件路径并上传到MinIO
- ✅ Callback集成：任务完成后自动发送结果
- ✅ 任务重试机制：支持失败任务的重新执行
- ✅ 任务取消功能：支持取消pending/running状态的任务

### 6. 文件操作API (`file_operations.py`)
- ✅ `/v1/files/upload` - 文件上传（支持multipart/form-data）
- ✅ `/v1/files/download/{file_path}` - 文件下载
- ✅ `/v1/files/delete/{file_path}` - 文件删除
- ✅ `/v1/files/list/{prefix}` - 列出文件（支持递归选项）
- ✅ `/v1/files/list` - 只使用查询参数的列表请求（支持多bucket）
- ✅ `/v1/files/exists/{file_path}` - 检查文件存在性
- ✅ `/v1/files/url/{file_path}` - 获取预签名URL（支持自定义有效期）
- ✅ `/v1/files/health` - 健康检查
- ✅ 路径安全性验证：防止路径遍历攻击
- ✅ 完整的错误处理和响应格式

### 7. 单任务API (`single_task_api.py`)
- ✅ `/v1/tasks` - 创建单任务
  - ✅ **task_id自动生成**：如不提供task_id参数，系统自动生成UUID格式的task_id
  - ✅ **HTTP文件路径支持**：input_data中的所有文件路径支持HTTP/HTTPS链接（如MinIO链接），系统会自动下载到本地临时目录
  - ✅ **callback URL验证**：确保callback URL的安全性和有效性
- ✅ `/v1/tasks/{task_id}/status` - 查询任务状态
- ✅ `/v1/tasks/{task_id}/result` - 获取任务完整结果
- ✅ `/v1/tasks/{task_id}/retry` - 重试失败的任务（生成新的task_id）
- ✅ `/v1/tasks/{task_id}` - 取消任务（仅限pending/running状态）
- ✅ `/v1/tasks/health` - 健康检查
- ✅ `/v1/tasks/supported-tasks` - 获取支持的任务列表（按服务分类）

### 8. 主程序集成 (`main.py`)
- ✅ 导入新模块：`file_operations`, `single_task_api`
- ✅ 集成文件操作路由：`file_operations_router`
- ✅ 集成单任务路由：`single_task_router`
- ✅ 保持与现有 `/v1/workflows` 接口的兼容性
- ✅ FastAPI应用版本更新为1.1.1
- ✅ 启动时初始化监控服务

## API接口文档

### MinIO文件操作接口

#### 上传文件
```http
POST /v1/files/upload?file_path=task_id/filename.wav&bucket=yivideo
Content-Type: multipart/form-data

file: [文件二进制数据]
```

响应：
```json
{
    "file_path": "task_id/filename.wav",
    "bucket": "yivideo",
    "download_url": "http://minio:9000/yivideo/task_id/filename.wav",
    "size": 1024000,
    "uploaded_at": "2025-11-16T17:49:00Z",
    "content_type": "audio/wav"
}
```

#### 下载文件
```http
GET /v1/files/download/task_id/filename.wav?bucket=yivideo
```

返回：文件二进制数据（Content-Disposition头部包含文件名）

#### 删除文件
```http
DELETE /v1/files/task_id/filename.wav?bucket=yivideo
```

响应：
```json
{
    "success": true,
    "message": "文件删除成功: task_id/filename.wav",
    "file_path": "task_id/filename.wav"
}
```

#### 列出文件

**方式1：指定前缀路径参数**
```http
GET /v1/files/list/task_id?bucket=yivideo&recursive=true
```

**方式2：只使用查询参数（支持多bucket）**
```http
GET /v1/files/list?bucket=yivideo&recursive=true
```

**注意：API代码更新后需要重启服务才能生效**

**实际测试结果示例（yivideo桶）：**
```json
{
    "prefix": "",
    "bucket": "yivideo",
    "files": [
        {
            "file_path": "1.jpg",
            "size": 463741,
            "last_modified": "2025-11-15T18:19:09.303000+00:00",
            "etag": "f573ae8c64b1380eb669b02e23bf35c0",
            "content_type": null
        },
        {
            "file_path": "ttt/111222.txt",
            "size": 42,
            "last_modified": "2025-11-16T20:17:18.809000+00:00",
            "etag": "f4fb5367a18c6407ec7067891ddf0b20",
            "content_type": null
        },
        {
            "file_path": "result.txt",
            "size": 6700799,
            "last_modified": "2025-11-15T18:19:10.951000+00:00",
            "etag": "7f3e5c7656c5de34894373a5c1af82f8",
            "content_type": null
        }
    ],
    "total_count": 32
}
```

**按前缀查询示例：**
```http
GET /v1/files/list/ttt/?bucket=yivideo&recursive=true
```
响应：
```json
{
    "prefix": "ttt/",
    "bucket": "yivideo",
    "files": [
        {
            "file_path": "ttt/111222.txt",
            "size": 42,
            "last_modified": "2025-11-16T20:17:18.809000+00:00",
            "etag": "f4fb5367a18c6407ec7067891ddf0b20",
            "content_type": null
        }
    ],
    "total_count": 1
}
```

#### 获取预签名URL
```http
GET /v1/files/url/task_id/filename.wav?bucket=yivideo&expires_hours=24
```

响应：
```json
{
    "file_path": "task_id/filename.wav",
    "bucket": "yivideo",
    "download_url": "http://minio:9000/yivideo/task_id/filename.wav?X-Amz-Algorithm=AWS4-HMAC-SHA256&...",
    "expires_in_hours": 24
}
```

#### 健康检查
```http
GET /v1/files/health
```

响应：
```json
{
    "status": "healthy",
    "minio_host": "minio.example.com",
    "default_bucket": "yivideo",
    "test_files_count": 5
}
```

### 单任务接口

#### 创建单任务
```http
POST /v1/tasks
Content-Type: application/json

{
    "task_name": "ffmpeg.extract_audio",
    "task_id": "unique-task-id",  // 可选，如不提供将自动生成
    "callback": "https://client.example.com/callback",
    "input_data": {
        "video_path": "/path/to/video.mp4"  // 支持HTTP链接，将自动下载
    }
}
```

**不提供task_id的请求示例：**
```http
POST /v1/tasks
Content-Type: application/json

{
    "task_name": "ffmpeg.extract_audio",
    "callback": "https://client.example.com/callback",
    "input_data": {
        "video_path": "https://minio.example.com/yivideo/task-123/video.mp4"
    }
}
```

**响应（自动生成task_id）：**
```json
{
    "task_id": "task-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "status": "pending",
    "message": "任务已创建并开始执行"
}
```

#### 查询任务状态
```http
GET /v1/tasks/unique-task-id/status
```

响应：
```json
{
    "task_id": "unique-task-id",
    "status": "completed",
    "message": "任务执行完成",
    "result": {
        "task_name": "ffmpeg.extract_audio",
        "output": {
            "audio_path": "/share/single_tasks/task_id/audio.wav"
        },
        "duration": 15.2
    },
    "minio_files": [
        {
            "name": "audio.wav",
            "url": "http://minio:9000/yivideo/task_id/audio.wav",
            "type": "audio",
            "size": 1024000
        }
    ],
    "created_at": "2025-11-16T17:49:00Z",
    "updated_at": "2025-11-16T17:49:15Z",
    "callback_status": "sent"
}
```

#### 获取支持的任务列表
```http
GET /v1/tasks/supported-tasks
```

响应：
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
    "total_count": 15,
    "description": "所有支持的单个工作流节点任务"
}
```

#### Callback数据格式
任务完成后，系统会自动发送callback到指定URL：

```json
{
    "task_id": "unique-task-id",
    "status": "completed",
    "result": {
        "task_name": "ffmpeg.extract_audio",
        "output": {
            "audio_path": "/share/single_tasks/task_id/audio.wav"
        },
        "duration": 15.2,
        "metadata": {}
    },
    "minio_files": [
        {
            "name": "audio.wav",
            "url": "http://minio:9000/yivideo/task_id/audio.wav",
            "type": "audio"
        }
    ],
    "timestamp": "2025-11-16T17:49:15Z"
}
```

## 技术特性

### 1. MinIO集成
- ✅ 从环境变量读取配置：可靠且灵活
- ✅ 支持大文件上传：通过临时文件机制
- ✅ 预签名URL：安全的文件访问（可自定义有效期）
- ✅ 目录结构：支持task_id隔离
- ✅ 自动桶创建：如桶不存在则自动创建

### 2. 任务执行
- ✅ 支持所有工作流节点：完整的兼容性
- ✅ 异步执行：高性能的Celery集成
- ✅ 状态管理：详细的任务状态追踪
- ✅ **智能文件处理**：自动扫描结果文件并上传到MinIO
- ✅ **HTTP文件支持**：自动下载远程文件到本地临时目录
- ✅ 任务重试：支持失败任务的重新执行
- ✅ 任务取消：支持取消运行中的任务

### 3. Callback机制
- ✅ 重试机制：指数退避策略，提高可靠性
- ✅ URL验证：防止恶意callback地址和内网访问
- ✅ 错误处理：完善的异常捕获和日志记录
- ✅ 批量支持：支持批量发送callback
- ✅ **智能重试**：仅对5xx错误进行重试，4xx错误直接失败

### 4. 安全性
- ✅ 路径验证：防止路径遍历攻击
- ✅ 文件大小检查：防止大文件攻击
- ✅ URL格式验证：确保callback URL安全
- ✅ 单例模式：避免资源竞争
- ✅ 输入验证：所有API参数都进行严格验证

### 5. 监控和日志
- ✅ 结构化日志：使用统一的日志系统
- ✅ 健康检查：所有服务都提供health endpoint
- ✅ 错误记录：详细的错误信息和堆栈跟踪
- ✅ 性能监控：任务执行时间和成功率统计

## 兼容性

### 与现有工作流的兼容性
- ✅ 保持 `/v1/workflows` 接口完全不变
- ✅ 使用相同的Celery配置和队列
- ✅ 复用现有的state_manager和WorkflowContext
- ✅ 使用相同的Redis存储和配置管理

### 各组件集成方式
1. **直接调用MinIO接口**：各工作流组件可以直接调用 `/v1/files/upload?file_path=...&bucket=...` 上传结果文件
2. **自动文件上传**：单任务执行器会自动扫描并上传生成的文件
3. **统一文件管理**：所有文件都通过MinIO统一管理，便于共享和访问

## 部署说明

### 环境变量要求
确保在环境中设置以下MinIO配置：
```bash
MINIO_HOST=minio.example.com
MINIO_PORT=9000
MINIO_ACCESS_KEY=your_access_key
MINIO_SECRET_KEY=your_secret_key
```

### 依赖安装
```bash
cd services/api_gateway
pip install -r requirements.txt
```

### 启动服务
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**重要：API代码修改后必须重启服务才能生效**

## 测试结果

### 文件列表API测试验证

**测试场景1：列出yivideo桶中所有文件**
```bash
curl "http://localhost:8788/v1/files/list?bucket=yivideo&recursive=true"
```
**结果：** 成功返回32个文件列表

**测试场景2：按前缀查询指定目录**
```bash
curl "http://localhost:8788/v1/files/list/ttt/?bucket=yivideo&recursive=true"
```
**结果：** 成功返回ttt目录下1个文件

**测试场景3：API路由修复**
- **问题：** 初次修改代码后，`GET /v1/files/list?bucket=yivideo&recursive=true` 返回 "Method Not Allowed"
- **原因：** FastAPI服务未重启，路由修改未生效
- **解决方案：** 重启API服务
- **结果：** 重启后API测试完全正常

## 使用示例

### 1. 工作流组件上传结果文件
```python
# 在工作流节点中
import requests

def upload_result_files(workflow_id: str, files: List[str]):
    for file_path in files:
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        minio_path = f"{workflow_id}/{os.path.basename(file_path)}"
        response = requests.post(
            f"http://api-gateway:8000/v1/files/upload?file_path={minio_path}&bucket=yivideo",
            files={'file': file_data}
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"File uploaded: {result['download_url']}")
```

### 2. 客户端调用单任务接口
```python
import requests

# 创建单任务（不提供task_id，自动生成）
request_data = {
    "task_name": "faster_whisper.transcribe_audio",
    "callback": "https://client.example.com/callback/transcription",
    "input_data": {
        "audio_path": "/path/to/audio.wav"  # 或HTTP链接
    }
}

response = requests.post(
    "http://api-gateway:8000/v1/tasks",
    json=request_data
)

task_id = response.json()["task_id"]

# 查询任务状态
status_response = requests.get(
    f"http://api-gateway:8000/v1/tasks/{task_id}/status"
)

print(f"Task status: {status_response.json()}")

# 获取任务结果
result_response = requests.get(
    f"http://api-gateway:8000/v1/tasks/{task_id}/result"
)

print(f"Task result: {result_response.json()}")
```

### 3. HTTP文件路径处理示例
```python
# 使用HTTP文件路径，系统会自动下载
request_data = {
    "task_name": "ffmpeg.extract_audio",
    "callback": "https://client.example.com/callback",
    "input_data": {
        "video_path": "https://minio.example.com/yivideo/task-123/video.mp4"
    }
}

# 系统会自动：
# 1. 下载 https://minio.example.com/yivideo/task-123/video.mp4 到 /tmp/single_tasks/{task_id}/
# 2. 将本地路径传递给工作流节点
# 3. 任务完成后扫描结果文件并上传到MinIO
```

## 预期收益

1. **文件管理标准化**：各组件通过统一接口管理MinIO文件
2. **灵活性提升**：支持单个功能调用，降低使用门槛
3. **异步处理**：callback机制支持事件驱动集成
4. **开发效率**：标准化的接口提高开发效率
5. **运维友好**：完善的监控和日志支持运维管理
6. **可扩展性**：模块化设计便于后续功能扩展
7. **远程文件支持**：HTTP文件路径自动处理，简化集成复杂度
8. **智能文件管理**：自动扫描和上传生成文件，减少手动操作

## 核心架构特点

### 1. 模块化设计
- ✅ 每个功能模块独立实现，便于维护和测试
- ✅ 单例模式确保资源管理的一致性
- ✅ 清晰的依赖关系和接口定义

### 2. 错误处理机制
- ✅ 完善的异常捕获和错误恢复
- ✅ 详细的日志记录便于调试
- ✅ HTTP状态码的正确使用

### 3. 性能优化
- ✅ 异步任务执行，避免阻塞
- ✅ 临时文件管理，及时清理
- ✅ 连接池和资源复用

### 4. 可观测性
- ✅ 健康检查端点
- ✅ 结构化日志输出
- ✅ 任务状态追踪

---

*实现完成时间：2025-11-16*  
*测试验证时间：2025-11-16 20:30*  
*开发工程师：AI Assistant*  
*版本：v1.1.1*