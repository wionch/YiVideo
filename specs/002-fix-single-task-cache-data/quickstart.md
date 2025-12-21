# 快速开始: 单步任务缓存复用数据过滤

## 1. 功能说明
本功能修复了单步任务在命中缓存时返回过多历史数据的问题。现在，当您请求一个特定的 `task_id` 和 `task_name` 且命中缓存时，响应中的 `result.stages` 将仅包含您当前请求的任务数据。

## 2. 验证步骤

### 2.1 准备数据
发送第一个请求，执行任务 A：
```bash
curl -X POST http://localhost:8788/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_name": "ffmpeg.extract_audio",
    "task_id": "job-filter-test-001",
    "input_data": { "video_path": "..." }
  }'
```
等待任务完成。

发送第二个请求，执行任务 B (在同一个 task_id 下)：
```bash
curl -X POST http://localhost:8788/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_name": "faster_whisper.transcribe_audio",
    "task_id": "job-filter-test-001",
    "input_data": { "audio_path": "..." }
  }'
```
等待任务完成。

### 2.2 触发缓存复用并验证过滤
再次请求任务 A：
```bash
curl -X POST http://localhost:8788/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_name": "ffmpeg.extract_audio",
    "task_id": "job-filter-test-001",
    "input_data": { "video_path": "..." }
  }'
```

**预期结果**:
响应中的 `result.stages` 应该**只包含** `ffmpeg.extract_audio`，而不包含 `faster_whisper.transcribe_audio`。

## 3. 注意事项
- 此变更仅影响 API 响应视图，Redis 中的完整工作流状态仍然完整保留。
- 查询 `/v1/tasks/{task_id}/status` 接口仍然会返回该 ID 下的所有阶段信息（设计如此，用于获取全局状态）。
