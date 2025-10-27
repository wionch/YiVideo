# YiVideo 工作流示例文档

## 概述

本文档提供了完整的 YiVideo 视频处理工作流示例，包括如何通过 API 执行各种视频处理任务。

## 基本配置

```bash
# API基础URL
API_BASE_URL="http://localhost:8788"

# 视频文件路径
VIDEO_PATH="/share/videos/666.mp4"
```

## 标准工作流

### 1. 完整视频字幕生成工作流（推荐）

这个工作流执行完整的视频处理流程：
1. 视频 → 视频 + 音频
2. 音频 → 人声音频 + 背景声音频
3. 人声音频 → 转录数据 → 字幕文件

```bash
curl -X POST "${API_BASE_URL}/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "'${VIDEO_PATH}'",
    "workflow_config": {
      "workflow_chain": [
        "ffmpeg.extract_audio",
        "audio_separator.separate_vocals",
        "faster_whisper.transcribe_audio",
        "faster_whisper.generate_subtitle_files"
      ]
    }
  }'
```

### 2. 基础字幕生成工作流

如果不需要人声分离，可以直接使用原始音频进行字幕生成：

```bash
curl -X POST "${API_BASE_URL}/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "'${VIDEO_PATH}'",
    "workflow_config": {
      "workflow_chain": [
        "ffmpeg.extract_audio",
        "faster_whisper.transcribe_audio",
        "faster_whisper.generate_subtitle_files"
      ]
    }
  }'
```

### 3. 只进行音频人声分离

如果只需要分离人声和背景音：

```bash
curl -X POST "${API_BASE_URL}/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "'${VIDEO_PATH}'",
    "workflow_config": {
      "workflow_chain": [
        "ffmpeg.extract_audio",
        "audio_separator.separate_vocals"
      ]
    }
  }'
```

## 完整字幕工作流（带说话人分离）

这个工作流在基础字幕生成之上，增加了说话人分离的步骤，最终生成的字幕会标记出不同的说话人。

1.  **视频** → 音频
2.  音频 → **人声** + 背景音
3.  人声 → **转录数据** (包含词级时间戳)
4.  人声 → **说话人时间戳**
5.  (转录数据 + 说话人时间戳) → **带说话人标签的字幕文件**

```bash
curl -X POST "${API_BASE_URL}/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "'${VIDEO_PATH}'",
    "workflow_config": {
      "workflow_chain": [
        "ffmpeg.extract_audio",
        "audio_separator.separate_vocals",
        "faster_whisper.transcribe_audio",
        "pyannote_audio.diarize_speakers",
        "faster_whisper.generate_subtitle_files"
      ]
    }
  }'
```
## 语音合成工作流

### 1. 基础语音合成

这个工作流使用指定的参考音频，将文本转换为具有相同音色的语音。

```bash
curl -X POST "${API_BASE_URL}/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_config": {
      "workflow_chain": [
        "indextts.generate_speech"
      ]
    },
    "indextts_service": {
      "text": "你好，这是一个使用IndexTTS2生成的语音。",
      "output_path": "/share/outputs/tts_example.wav",
      "spk_audio_prompt": "/share/videos/reference_audio.wav"
    }
  }'
| `indextts.generate_speech` | 基于参考音频生成语音 | 无 |
```

## 工作链说明

### 可用任务

| 任务名称 | 描述 | 依赖 |
|---|---|---|
| `ffmpeg.extract_audio` | 从视频中提取音频 | 无 |
| `audio_separator.separate_vocals` | 分离人声和背景音 | `ffmpeg.extract_audio` |
| `faster_whisper.transcribe_audio` | 对音频进行语音转录，生成包含词级时间戳的中间数据 | `ffmpeg.extract_audio` 或 `audio_separator.separate_vocals` |
| `pyannote_audio.diarize_speakers` | 对音频进行说话人分离 | `ffmpeg.extract_audio` 或 `audio_separator.separate_vocals` |
| `faster_whisper.generate_subtitle_files` | 基于转录数据和可选的说话人数据生成多种格式的字幕文件 | `faster_whisper.transcribe_audio` |

### 任务输出

#### ffmpeg.extract_audio
- `audio_path`: 提取的音频文件路径

#### audio_separator.separate_vocals
#### indextts.generate_speech
- `output_path`: 生成的语音文件路径。
- `processing_time`: 处理时长（秒）。
- `audio_list`: 所有分离的音频文件列表
- `vocal_audio`: 人声音频文件路径（推荐用于字幕生成）
- `model_used`: 使用的分离模型
- `quality_mode`: 质量模式
- `processing_time`: 处理时间

#### faster_whisper.transcribe_audio
- `segments_file`: 包含完整转录结果（含词级时间戳）的JSON文件路径。
- `transcribe_duration`: 转录处理时长（秒）。
- `language`: 检测到的语言代码。

#### faster_whisper.generate_subtitle_files
- `subtitle_path`: 基础SRT字幕文件路径。
- `speaker_srt_path`: (如果提供了说话人数据) 带说话人信息的SRT字幕文件路径。
- `speaker_json_path`: (如果提供了说话人数据) 带说话人信息的JSON文件路径。
- `word_timestamps_json_path`: 词级时间戳JSON文件路径。

#### pyannote_audio.diarize_speakers
- `diarization_path`: 说话人分离结果文件路径
- `speaker_srt_path`: 带说话人信息的SRT字幕文件路径（如果启用）
- `speaker_json_path`: 带说话人信息的JSON文件路径（如果启用）
- `word_timestamps_json_path`: 词级时间戳JSON文件路径（如果启用）

## 查询工作流状态

### 1. 获取工作流状态

```bash
# 替换 WORKFLOW_ID 为实际的工作流ID
curl -X GET "${API_BASE_URL}/v1/workflows/status/{WORKFLOW_ID}"
```

### 2. 获取所有工作流列表

```bash
curl -X GET "${API_BASE_URL}/v1/workflows/list"
```

## 输出文件结构

工作流完成后，文件结构如下：

```
/share/workflows/{workflow_id}/
├── audio/
│   ├── {video_name}.wav                    # 原始提取音频
│   └── audio_separated/
│       ├── {video_name}_(Vocals)_htdemucs.flac    # 人声音频
│       ├── {video_name}_(Other)_htdemucs.flac     # 背景音
│       ├── {video_name}_(Bass)_htdemucs.flac      # 低音
│       └── {video_name}_(Drums)_htdemucs.flac     # 鼓声
└── subtitles/
    ├── {video_name}.srt                         # 基础字幕
    ├── {video_name}_with_speakers.srt           # 带说话人信息的字幕
    ├── {video_name}_with_speakers.json          # 带说话人信息的JSON
    └── {video_name}_word_timestamps.json        # 词级时间戳JSON
```

## 错误处理

### 常见错误及解决方案

1. **视频文件不存在**
   - 检查 `video_path` 是否正确
   - 确保视频文件在 `/share/videos/` 目录下

2. **工作流任务失败**
   - 查看具体任务的错误信息
   - 检查 Docker 服务状态：`docker-compose ps`
   - 查看服务日志：`docker-compose logs [service_name]`

3. **GPU资源不足**
   - 检查 GPU 可用性：`nvidia-smi`
   - 调整并发任务数量
   - 使用 CPU 模式（如果支持）

## 性能优化建议

1. **使用人声音频**：推荐使用 `audio_separator.separate_vocals` 分离出的人声音频进行字幕生成，可以提高识别准确率。

2. **调整模型参数**：根据需求选择合适的 WhisperX 模型大小，平衡速度和精度。

3. **批量处理**：对于多个视频文件，可以并行提交多个工作流任务。

## 监控和调试

### GPU 锁监控
```bash
# 检查 GPU 锁状态
curl http://localhost:8788/api/v1/monitoring/gpu-lock/health

# 查看任务心跳状态
curl http://localhost:8788/api/v1/monitoring/heartbeat/all
```

### 系统统计
```bash
# 获取系统统计信息
curl http://localhost:8788/api/v1/monitoring/statistics
```