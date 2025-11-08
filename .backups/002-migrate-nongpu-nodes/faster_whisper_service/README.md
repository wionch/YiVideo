# Faster Whisper Service

基于 Faster-Whisper 的高性能语音转录服务，从 WhisperX Service 拆分而来。

## 功能

- **语音转录** (`faster_whisper.transcribe_audio`): 使用 Faster-Whisper 进行高性能 ASR
- **字幕生成** (`faster_whisper.generate_subtitle_files`): 生成 SRT/VTT 字幕文件

## 特性

✅ 原生 Faster-Whisper API 支持
✅ 词级时间戳精确生成
✅ GPU 锁机制保护资源
✅ CUDA/CPU 自动切换
✅ 支持多种模型规格 (tiny/base/small/medium/large)
✅ FP16 量化支持

## 依赖

- faster-whisper >= 1.1.1
- torch >= 2.0.0
- CUDA 11.8+ (可选)

## 工作流节点

```json
{
  "workflow_chain": [
    "ffmpeg.extract_audio",
    "faster_whisper.transcribe_audio",
    "faster_whisper.generate_subtitle_files"
  ]
}
```

## 配置

通过 `config.yml` 的 `faster_whisper_service` 部分配置：

```yaml
faster_whisper_service:
  model_name: "Systran/faster-whisper-large-v3"
  device: "cuda"
  compute_type: "float16"
  enable_word_timestamps: true
  enable_gpu_lock: true
  gpu_device_id: 0
```

## Celery 队列

- 队列名称: `faster_whisper_queue`
- 并发数: 1 (GPU 资源独占)

## Docker 部署

```bash
# 构建镜像
docker-compose build faster_whisper_service

# 启动服务
docker-compose up -d faster_whisper_service

# 查看日志
docker-compose logs -f faster_whisper_service
```
