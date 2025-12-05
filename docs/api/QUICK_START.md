# YiVideo API 快速开始指南

本指南将帮助您在5分钟内快速上手YiVideo API，通过实际示例学习如何使用API进行AI视频处理。

## 📋 目录

- [5分钟快速开始](#5分钟快速开始)
- [前置准备](#前置准备)
- [步骤1：健康检查](#步骤1健康检查)
- [步骤2：上传文件](#步骤2上传文件)
- [步骤3：创建工作流](#步骤3创建工作流)
- [步骤4：监控执行](#步骤4监控执行)
- [步骤5：获取结果](#步骤5获取结果)
- [端到端示例](#端到端示例)
- [常见错误](#常见错误)
- [最佳实践](#最佳实践)
- [常用代码片段](#常用代码片段)

---

## 5分钟快速开始

这是一个最简单的工作流示例：上传视频 → 创建工作流 → 等待完成 → 下载结果。

```bash
# 1. 检查服务状态
curl http://localhost:8000/

# 2. 上传视频文件
curl -X POST "http://localhost:8000/v1/files/upload" \
  -F "file=@/path/to/video.mp4" \
  -F "file_path=videos/demo.mp4"

# 3. 创建工作流
workflow_id=$(curl -s -X POST "http://localhost:8000/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "videos/demo.mp4",
    "workflow_config": {
      "workflow_chain": ["faster_whisper.transcribe_audio"]
    }
  }' | jq -r '.workflow_id')

echo "工作流ID: $workflow_id"

# 4. 轮询状态
while true; do
  status=$(curl -s "http://localhost:8000/v1/workflows/status/$workflow_id")
  error=$(echo "$status" | jq -r '.error')
  if [ "$error" != "null" ]; then
    echo "工作流失败: $error"
    break
  fi
  completed=$(echo "$status" | jq '[.stages[] | select(.status == "completed")] | length')
  total=$(echo "$status" | jq '[.stages[] | keys] | length')
  if [ "$completed" -eq "$total" ]; then
    echo "工作流完成！"
    echo "$status" | jq '.stages'
    break
  fi
  echo "进度: $completed/$total"
  sleep 5
done
```

---

## 前置准备

### 环境要求

1. **YiVideo服务已启动**
   ```bash
   docker-compose up -d
   ```

2. **API服务地址**
   ```
   http://localhost:8000
   ```

3. **测试文件**
   - 准备一个视频文件（如：`video.mp4`）
   - 或使用示例文件

### 工具安装

```bash
# 安装jq（JSON处理工具）
sudo apt-get install jq  # Ubuntu/Debian
brew install jq          # macOS

# 或使用Python requests
pip install requests
```

---

## 步骤1：健康检查

### 检查API服务状态

```bash
curl http://localhost:8000/
```

**期望响应**：
```json
{
    "message": "YiVideo AI Workflow Engine API is running."
}
```

### 检查监控系统

```bash
curl http://localhost:8000/api/v1/monitoring/health
```

**期望响应**：
```json
{
    "status": "healthy",
    "issues": [],
    "components": { ... }
}
```

### 检查GPU状态

```bash
curl "http://localhost:8000/api/v1/monitoring/gpu-lock/status"
```

**期望响应**：
```json
{
    "lock_key": "gpu_lock:0",
    "is_locked": false,
    "health": {
        "status": "healthy"
    }
}
```

---

## 步骤2：上传文件

### 上传视频文件

```bash
curl -X POST "http://localhost:8000/v1/files/upload" \
  -F "file=@/path/to/your/video.mp4" \
  -F "file_path=videos/my_video.mp4" \
  -F "bucket=yivideo"
```

**成功响应**：
```json
{
    "file_path": "videos/my_video.mp4",
    "bucket": "yivideo",
    "download_url": "http://localhost:9000/yivideo/videos/my_video.mp4",
    "size": 10485760,
    "uploaded_at": "2025-12-05T03:00:00Z",
    "content_type": "video/mp4"
}
```

### 验证文件

```bash
curl -I "http://localhost:8000/v1/files/download/videos/my_video.mp4"
```

**期望响应头**：
```http
HTTP/1.1 200 OK
Content-Type: video/mp4
Content-Length: 10485760
```

---

## 步骤3：创建工作流

### 创建简单工作流（语音识别）

```bash
curl -X POST "http://localhost:8000/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "videos/my_video.mp4",
    "workflow_config": {
      "workflow_chain": [
        "faster_whisper.transcribe_audio"
      ]
    },
    "language": "zh"
  }'
```

**成功响应**：
```json
{
    "workflow_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "execution_mode": "full",
    "tasks_total": 1,
    "tasks_to_execute": 1,
    "message": "New workflow created and started successfully."
}
```

### 创建复杂工作流（完整视频处理）

```bash
curl -X POST "http://localhost:8000/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "videos/my_video.mp4",
    "workflow_config": {
      "workflow_chain": [
        "ffmpeg.extract_audio",
        "faster_whisper.transcribe_audio",
        "pyannote_audio.diarize_speakers",
        "wservice.generate_subtitle_files"
      ]
    },
    "language": "zh",
    "enable_optimization": true
  }'
```

---

## 步骤4：监控执行

### 查询工作流状态

```bash
# 替换为实际的工作流ID
workflow_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890"

curl -s "http://localhost:8000/v1/workflows/status/$workflow_id" | jq '.'
```

**进行中响应**：
```json
{
    "workflow_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "stages": {
        "stage_0": {
            "status": "running",
            "input": { ... },
            "start_time": "2025-12-05T03:00:01"
        }
    },
    "error": null
}
```

**完成响应**：
```json
{
    "workflow_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "stages": {
        "stage_0": {
            "status": "completed",
            "input": { ... },
            "output": { ... },
            "start_time": "2025-12-05T03:00:01",
            "end_time": "2025-12-05T03:02:30",
            "duration": 149
        }
    },
    "error": null
}
```

### 自动轮询脚本

```bash
#!/bin/bash
workflow_id="$1"  # 传入工作流ID

if [ -z "$workflow_id" ]; then
    echo "用法: $0 <workflow_id>"
    exit 1
fi

echo "监控工作流: $workflow_id"
echo "按 Ctrl+C 停止"
echo "----------------------------------------"

while true; do
    status=$(curl -s "http://localhost:8000/v1/workflows/status/$workflow_id")
    error=$(echo "$status" | jq -r '.error')

    if [ "$error" != "null" ]; then
        echo "❌ 工作流失败: $error"
        break
    fi

    stages=$(echo "$status" | jq '.stages')
    completed=$(echo "$stages" | jq '[.[] | select(.status == "completed")] | length')
    total=$(echo "$stages" | jq '[.[] | keys] | length')
    running=$(echo "$stages" | jq '[.[] | select(.status == "running")] | length')

    printf "\r进度: %d/%d 完成, %d 运行中" "$completed" "$total" "$running"

    if [ "$completed" -eq "$total" ] && [ "$total" -gt 0 ]; then
        echo ""
        echo "✅ 工作流完成！"
        echo "$status" | jq '.stages'
        break
    fi

    sleep 5
done
```

使用方法：
```bash
chmod +x monitor_workflow.sh
./monitor_workflow.sh a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 步骤5：获取结果

### 查看输出文件

工作流完成后，结果文件存储在共享目录中：

```bash
# 查看工作流目录
ls -la /share/workflows/a1b2c3d4-e5f6-7890-abcd-ef1234567890/

# 或通过API下载
curl "http://localhost:8000/v1/files/download/videos/result.srt" \
  -o output.srt
```

### 获取详细结果

```bash
curl -s "http://localhost:8000/v1/workflows/status/$workflow_id" \
  | jq '.stages.stage_0.output'
```

### 清理资源

```bash
# 删除工作流目录
curl -X DELETE "http://localhost:8000/v1/files/directories?directory_path=/share/workflows/$workflow_id"
```

---

## 端到端示例

### Python完整示例

```python
import requests
import time
import json

class YiVideoClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url

    def upload_file(self, file_path, remote_path, bucket="yivideo"):
        """上传文件"""
        with open(file_path, 'rb') as f:
            files = {'file': f}
            data = {'file_path': remote_path, 'bucket': bucket}
            response = requests.post(f"{self.base_url}/v1/files/upload",
                                   files=files, data=data)
            return response.json()

    def create_workflow(self, video_path, workflow_chain, **params):
        """创建工作流"""
        data = {
            "video_path": video_path,
            "workflow_config": {"workflow_chain": workflow_chain}
        }
        data.update(params)

        response = requests.post(f"{self.base_url}/v1/workflows",
                               json=data)
        return response.json()

    def get_workflow_status(self, workflow_id):
        """获取工作流状态"""
        response = requests.get(f"{self.base_url}/v1/workflows/status/{workflow_id}")
        return response.json()

    def wait_for_completion(self, workflow_id, timeout=1800):
        """等待工作流完成"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            status = self.get_workflow_status(workflow_id)

            if status.get('error'):
                raise Exception(f"工作流失败: {status['error']}")

            stages = status.get('stages', {})
            completed = sum(1 for s in stages.values() if s.get('status') == 'completed')
            total = len(stages)

            if completed == total and total > 0:
                return status

            print(f"进度: {completed}/{total}")
            time.sleep(5)

        raise TimeoutError("工作流超时")

# 使用示例
client = YiVideoClient()

try:
    # 1. 上传文件
    print("1. 上传文件...")
    upload_result = client.upload_file("video.mp4", "videos/demo.mp4")
    print(f"   上传成功: {upload_result['file_path']}")

    # 2. 创建工作流
    print("\n2. 创建工作流...")
    workflow = client.create_workflow(
        video_path="videos/demo.mp4",
        workflow_chain=["faster_whisper.transcribe_audio"],
        language="zh"
    )
    workflow_id = workflow['workflow_id']
    print(f"   工作流ID: {workflow_id}")

    # 3. 等待完成
    print("\n3. 等待执行...")
    result = client.wait_for_completion(workflow_id)
    print("   ✅ 工作流完成！")

    # 4. 显示结果
    print("\n4. 结果:")
    print(json.dumps(result['stages'], indent=2))

except Exception as e:
    print(f"❌ 错误: {e}")
```

### 复杂工作流示例

```bash
#!/bin/bash

# 创建完整视频处理工作流
workflow_response=$(curl -s -X POST "http://localhost:8000/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "videos/lecture.mp4",
    "workflow_config": {
      "workflow_chain": [
        "ffmpeg.extract_audio",
        "faster_whisper.transcribe_audio",
        "pyannote_audio.diarize_speakers",
        "wservice.generate_subtitle_files"
      ]
    },
    "language": "zh",
    "enable_optimization": true,
    "speaker_count": 2
  }')

workflow_id=$(echo "$workflow_response" | jq -r '.workflow_id')
echo "工作流已创建: $workflow_id"

# 使用监控脚本跟踪进度
./monitor_workflow.sh "$workflow_id"

# 获取最终结果
echo "获取结果..."
curl -s "http://localhost:8000/v1/workflows/status/$workflow_id" \
  | jq '.stages'

# 清理
read -p "是否删除工作流目录？(y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
  curl -X DELETE "http://localhost:8000/v1/files/directories?directory_path=/share/workflows/$workflow_id"
  echo "工作流目录已删除"
fi
```

---

## 常见错误

### 错误1：GPU锁被占用

**症状**：
```json
{
    "detail": "GPU资源不足"
}
```

**解决方案**：
```bash
# 检查GPU锁状态
curl "http://localhost:8000/api/v1/monitoring/gpu-lock/status"

# 等待锁释放或手动释放
curl -X POST "http://localhost:8000/api/v1/monitoring/lock/release" \
  -H "Content-Type: application/json" \
  -d '{"lock_key": "gpu_lock:0", "task_name": "manual"}'
```

### 错误2：文件不存在

**症状**：
```json
{
    "detail": "文件不存在: videos/nonexistent.mp4"
}
```

**解决方案**：
```bash
# 先上传文件
curl -X POST "http://localhost:8000/v1/files/upload" \
  -F "file=@local.mp4" \
  -F "file_path=videos/local.mp4"
```

### 错误3：工作流配置无效

**症状**：
```json
{
    "detail": "workflow_config 中的 workflow_chain 不能为空"
}
```

**解决方案**：
```bash
# 确保workflow_chain是数组
curl -X POST "http://localhost:8000/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "videos/demo.mp4",
    "workflow_config": {
      "workflow_chain": ["faster_whisper.transcribe_audio"]
    }
  }'
```

### 错误4：任务超时

**症状**：
```json
{
    "error": "任务执行超时"
}
```

**解决方案**：
```bash
# 检查超时配置
curl "http://localhost:8000/api/v1/monitoring/timeout/config"

# 重试工作流
curl -X POST "http://localhost:8000/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "failed-workflow-id",
    "execution_mode": "retry",
    "workflow_config": {
      "workflow_chain": ["task1", "task2"]
    }
  }'
```

---

## 最佳实践

### 1. 工作流设计

**好的做法**：
- 合理拆分任务，每个任务专注于单一功能
- 避免任务间的复杂依赖
- 考虑资源使用，合理安排任务顺序

**示例**：
```json
{
    "workflow_chain": [
        "ffmpeg.extract_audio",          # 先提取音频
        "faster_whisper.transcribe_audio", # 再识别语音
        "wservice.generate_subtitle_files" # 最后生成字幕
    ]
}
```

### 2. 错误处理

**实现重试机制**：
```python
import time
import random

def execute_with_retry(func, max_retries=3, delay=5):
    """带重试的函数执行"""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait_time = delay * (2 ** attempt) + random.uniform(0, 1)
            print(f"尝试 {attempt + 1} 失败: {e}，{wait_time:.1f}s后重试...")
            time.sleep(wait_time)
```

### 3. 资源管理

**及时清理**：
```bash
# 工作流完成后清理临时文件
curl -X DELETE "http://localhost:8000/v1/files/directories?directory_path=/share/workflows/$workflow_id"
```

**批量清理脚本**：
```bash
#!/bin/bash
# 清理7天前的工作流

for dir in /share/workflows/*; do
    if [ -d "$dir" ]; then
        dir_name=$(basename "$dir")
        age=$(find "$dir" -maxdepth 0 -type d -mtime +7 -print 2>/dev/null)
        if [ -n "$age" ]; then
            echo "清理旧工作流: $dir_name"
            curl -X DELETE "http://localhost:8000/v1/files/directories?directory_path=$dir"
        fi
    fi
done
```

### 4. 监控建议

**定期检查健康状态**：
```bash
#!/bin/bash
# 健康检查脚本

health=$(curl -s http://localhost:8000/api/v1/monitoring/health)
status=$(echo "$health" | jq -r '.status')
issues=$(echo "$health" | jq -r '.issues | length')

if [ "$status" != "healthy" ] || [ "$issues" -gt 0 ]; then
    echo "⚠️ 系统健康状态: $status"
    echo "$health" | jq '.issues'
    # 发送告警通知
fi
```

### 5. 性能优化

**避免过度轮询**：
```python
import time

def smart_poll_workflow(client, workflow_id, initial_interval=5, max_interval=30):
    """智能轮询，间隔逐渐增大"""
    interval = initial_interval

    while True:
        status = client.get_workflow_status(workflow_id)

        if status.get('error'):
            raise Exception(f"工作流失败: {status['error']}")

        stages = status.get('stages', {})
        completed = sum(1 for s in stages.values() if s.get('status') == 'completed')
        total = len(stages)

        if completed == total and total > 0:
            return status

        print(f"进度: {completed}/{total}，{interval}s后再次检查...")
        time.sleep(interval)

        # 逐渐增大间隔，但不超过最大值
        interval = min(interval + 5, max_interval)
```

---

## 常用代码片段

### 单任务执行

```python
# 直接执行单个任务
result = requests.post("http://localhost:8000/v1/tasks", json={
    "task_name": "ffmpeg.extract_audio",
    "task_id": "extract-001",
    "input_data": {
        "video_path": "videos/input.mp4",
        "audio_format": "wav"
    }
}).json()

task_id = result['task_id']

# 轮询状态
while True:
    status = requests.get(f"http://localhost:8000/v1/tasks/{task_id}/status").json()
    if status['status'] in ['completed', 'failed', 'cancelled']:
        break
    time.sleep(3)

print(status)
```

### 批量文件上传

```python
import os
import requests

def batch_upload(directory, remote_prefix):
    """批量上传目录中的文件"""
    for filename in os.listdir(directory):
        local_path = os.path.join(directory, filename)
        if os.path.isfile(local_path):
            remote_path = f"{remote_prefix}/{filename}"
            print(f"上传: {filename}")

            with open(local_path, 'rb') as f:
                response = requests.post(
                    "http://localhost:8000/v1/files/upload",
                    files={'file': f},
                    data={'file_path': remote_path}
                )
                print(f"  结果: {response.json()['file_path']}")

# 使用
batch_upload("/path/to/videos", "videos/batch1")
```

### 工作流增量执行

```python
# 第一阶段：语音识别
workflow1 = client.create_workflow(
    video_path="videos/lecture.mp4",
    workflow_chain=["faster_whisper.transcribe_audio"],
    language="zh"
)
client.wait_for_completion(workflow1['workflow_id'])

# 第二阶段：字幕生成（增量追加）
workflow2 = client.create_workflow(
    workflow_id=workflow1['workflow_id'],
    execution_mode="incremental",
    workflow_config={
        "workflow_chain": [
            "faster_whisper.transcribe_audio",
            "wservice.generate_subtitle_files"
        ]
    }
)
client.wait_for_completion(workflow2['workflow_id'])
```

### 监控任务心跳

```python
import requests
import time

def monitor_tasks(task_ids):
    """批量监控任务心跳"""
    while True:
        for task_id in task_ids:
            response = requests.get(
                f"http://localhost:8000/api/v1/monitoring/heartbeat/task/{task_id}"
            )

            if response.status_code == 200:
                data = response.json()
                status = data.get('status')
                last_update = data.get('last_update')

                if status == 'running' and last_update:
                    time_since_update = time.time() - last_update
                    if time_since_update > 120:  # 2分钟
                        print(f"⚠️ 任务 {task_id} 心跳超时")

        time.sleep(30)  # 每30秒检查一次

# 使用
task_ids = ["task1", "task2", "task3"]
monitor_tasks(task_ids)
```

---

## 下一步

恭喜！您已经掌握了YiVideo API的基本使用。接下来建议：

1. **阅读详细文档**：
   - [工作流API](./WORKFLOW_API.md) - 深入了解工作流功能
   - [单任务API](./SINGLE_TASK_API.md) - 学习单任务执行
   - [监控API](./MONITORING_API.md) - 掌握系统监控

2. **探索高级功能**：
   - 自定义工作流配置
   - 增量执行和重试机制
   - 回调机制的使用

3. **优化实践**：
   - 实现自动重试
   - 设置监控告警
   - 优化资源使用

4. **查看示例**：
   - [工作流示例指南](../technical/reference/WORKFLOW_EXAMPLES_GUIDE.md)
   - [工作流节点参考](../technical/reference/WORKFLOW_NODES_REFERENCE.md)

---

## 获取帮助

- **文档**: 查看 `docs/` 目录下的详细文档
- **API参考**: 使用Swagger UI (如果有启用)
- **日志**: 检查API Gateway和Worker日志
- **GitHub**: 提交Issue或查看示例

---

*快速开始指南版本: 1.0.0 | 最后更新: 2025-12-05*
