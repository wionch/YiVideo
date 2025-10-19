# Pyannote Audio Service

基于 Pyannote.audio 的说话人分离服务，从 WhisperX Service 拆分而来。

## 功能

- **说话人分离** (`pyannote_audio.diarize_speakers`): 识别音频中的不同说话人并为每个词分配说话人标签

## 特性

✅ Pyannote.audio 3.x 原生支持
✅ 本地模式和 pyannoteAI API 模式双支持
✅ 词级说话人精确匹配
✅ GPU 锁机制保护资源
✅ CUDA/CPU 自动切换
✅ 高精度说话人分离算法

## 依赖

- pyannote.audio >= 3.3.2
- torch >= 2.0.0
- CUDA 11.8+ (可选)

## 工作流节点

```json
{
  "workflow_chain": [
    "ffmpeg.extract_audio",
    "faster_whisper.transcribe_audio",
    "pyannote_audio.diarize_speakers",
    "faster_whisper.generate_subtitle_files"
  ]
}
```

## 配置

### 本地模式（GPU）

```yaml
whisperx_service:
  diarization:
    use_paid_api: false
    hf_token: "your_huggingface_token"
```

### API 模式（pyannoteAI）

```yaml
whisperx_service:
  diarization:
    use_paid_api: true
    api_key: "your_pyannote_api_key"
```

## Celery 队列

- 队列名称: `pyannote_audio_queue`
- 并发数: 1 (GPU 资源独占)

## Docker 部署

```bash
# 构建镜像
docker-compose build pyannote_audio_service

# 启动服务
docker-compose up -d pyannote_audio_service

# 查看日志
docker-compose logs -f pyannote_audio_service
```

## 环境变量

- `PYANNOTEAI_API_KEY`: PyannoteAI API 密钥（API 模式）
- `HF_TOKEN`: Hugging Face Token（本地模式）
