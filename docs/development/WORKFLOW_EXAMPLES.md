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

## 高级工作流：参数化输入

通过参数化输入，您可以精确控制任务之间的数据流，覆盖默认的行为。这对于创建自定义或非标准的工作流非常有用。

占位符语法为：`${{ stages.<stage_name>.output.<field_name> }}`

### 示例：强制使用原始音频进行转录

在标准工作流中，如果 `audio_separator.separate_vocals` 存在，`faster_whisper.transcribe_audio` 会自动使用其输出的人声音频。以下示例演示了如何**强制** `faster_whisper` 使用 `ffmpeg.extract_audio` 输出的原始音频，即使工作流中包含了人声分离步骤。

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
    },
    "faster_whisper.transcribe_audio": {
      "audio_path": "${{ stages.ffmpeg.extract_audio.output.audio_path }}"
    }
  }'
```

在这个请求中，我们为 `faster_whisper.transcribe_audio` 任务明确指定了 `audio_path` 参数，其值指向 `ffmpeg.extract_audio` 阶段的输出。这将覆盖 `faster_whisper` 内部的默认音频查找逻辑。


## 增量执行与调试工作流

增量执行功能允许您在现有工作流的基础上继续执行、重试失败的任务或追加新任务，是调试复杂工作流和进行参数实验的强大工具。

**关键参数**:
- `workflow_id`: 要操作的现有工作流的ID。
- `execution_mode`:
  - `incremental`: 在已成功完成的工作流末尾追加新任务。
  - `retry`: 从第一个失败或未执行的任务开始，重新执行后续所有任务。
- `param_merge_strategy`:
  - `merge`: 合并新旧参数，新参数覆盖旧参数（默认）。
  - `override`: 完全使用新请求中定义的节点参数，忽略所有旧参数。
  - `strict`: 如果新旧参数存在冲突，则报错。

### 场景1：增量追加任务

假设我们已经完成了一个只包含音频提取的工作流，现在希望在这个基础上追加人声分离和语音转录任务。

**步骤1：创建初始工作流**

首先，创建一个只提取音频的简单工作流。执行后，记下返回的 `workflow_id`。

```bash
# 假设返回的 workflow_id 为 "abc-123"
curl -X POST "${API_BASE_URL}/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "'${VIDEO_PATH}'",
    "workflow_config": {
      "workflow_chain": [
        "ffmpeg.extract_audio"
      ]
    }
  }'
```

**步骤2：追加新任务**

使用上一步获得的 `workflow_id`，设置 `execution_mode` 为 `incremental`，并提供一个更长的新任务链。

```bash
# 替换为上一步获得的真实 WORKFLOW_ID
export WORKFLOW_ID="abc-123"

curl -X POST "${API_BASE_URL}/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "'${WORKFLOW_ID}'",
    "execution_mode": "incremental",
    "workflow_config": {
      "workflow_chain": [
        "ffmpeg.extract_audio",
        "audio_separator.separate_vocals",
        "faster_whisper.transcribe_audio"
      ]
    }
  }'
```

**系统行为**:
- 系统会检测到 `ffmpeg.extract_audio` 任务已经成功完成，因此会跳过它。
- 只会执行新增的 `audio_separator.separate_vocals` 和 `faster_whisper.transcribe_audio` 任务，从而节省了时间和计算资源。

### 场景2：从失败点重试

假设一个工作流在 `pyannote_audio.diarize_speakers` 步骤因为配置错误而失败。我们可以修复参数并从失败点继续。

**步骤1：模拟一个失败的工作流**

我们故意提供一个错误的参数（例如，无效的 `hf_token`）来使任务失败。

```bash
# 这个请求可能会失败，记下返回的 workflow_id，例如 "def-456"
curl -X POST "${API_BASE_URL}/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "'${VIDEO_PATH}'",
    "workflow_config": {
      "workflow_chain": [
        "ffmpeg.extract_audio",
        "pyannote_audio.diarize_speakers"
      ]
    },
    "pyannote_audio.diarize_speakers": {
      "hf_token": "a-bad-token" 
    }
  }'
```

**步骤2：使用 `retry` 模式修复并继续**

现在，我们提供正确的参数，并使用 `retry` 模式重新提交请求。

```bash
# 替换为上一步获得的真实 WORKFLOW_ID
export WORKFLOW_ID="def-456"
# 替换为你的 Hugging Face Token
export HF_TOKEN="your-real-huggingface-token"

curl -X POST "${API_BASE_URL}/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "'${WORKFLOW_ID}'",
    "execution_mode": "retry",
    "workflow_config": {
      "workflow_chain": [
        "ffmpeg.extract_audio",
        "pyannote_audio.diarize_speakers"
      ]
    },
    "pyannote_audio.diarize_speakers": {
      "hf_token": "'${HF_TOKEN}'"
    }
  }'
```

**系统行为**:
- 系统会跳过已成功的 `ffmpeg.extract_audio` 任务。
- 它会从失败的 `pyannote_audio.diarize_speakers` 任务开始，使用我们提供的新参数重新执行。

### 场景3：参数调优实验

`retry` 模式结合 `override` 策略是进行参数调优的利器。假设你想实验 `faster_whisper` 的不同 `beam_size` 对转录结果的影响，而无需每次都重新提取和分离音频。

**步骤1：运行一次完整的工作流**

首先，运行一个完整的工作流并记下 `workflow_id`。

```bash
# 假设返回的 workflow_id 为 "ghi-789"
curl -X POST "${API_BASE_URL}/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "'${VIDEO_PATH}'",
    "workflow_config": {
      "workflow_chain": [
        "ffmpeg.extract_audio",
        "audio_separator.separate_vocals",
        "faster_whisper.transcribe_audio"
      ]
    },
    "faster_whisper.transcribe_audio": {
      "beam_size": 5
    }
  }'
```

**步骤2：使用 `retry` 和 `override` 策略调整参数**

现在，我们假装 `faster_whisper.transcribe_audio` 任务“未完成”（即使它成功了），并通过 `retry` 模式重新运行它，同时使用 `override` 策略来确保只有新参数生效。

为了让 `retry` 模式重新运行最后一个任务，我们需要手动将 Redis 中该任务的状态修改为 "PENDING" 或 "FAILED"。但更简单的方法是，**在 `retry` 模式下，系统会从第一个非 `SUCCESS` 或 `COMPLETED` 状态的任务开始执行**。如果我们想重新运行一个已成功的任务，可以先将工作流链缩短，然后用 `retry` 模式和新参数重新运行。

一个更直接的方法是，如果最后一个任务是我们要调优的，我们可以直接用 `retry` 模式提交，并提供新参数。系统会跳过之前所有成功的任务，然后用新参数重新运行最后一个任务。

```bash
# 替换为上一步获得的真实 WORKFLOW_ID
export WORKFLOW_ID="ghi-789"

# 实验新的 beam_size
curl -X POST "${API_BASE_URL}/v1/workflows" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "'${WORKFLOW_ID}'",
    "execution_mode": "retry",
    "param_merge_strategy": "override",
    "workflow_config": {
      "workflow_chain": [
        "ffmpeg.extract_audio",
        "audio_separator.separate_vocals",
        "faster_whisper.transcribe_audio"
      ]
    },
    "faster_whisper.transcribe_audio": {
      "beam_size": 10,
      "language": "zh"
    }
  }'
```

**系统行为**:
- 系统会检测到 `ffmpeg.extract_audio` 和 `audio_separator.separate_vocals` 已成功，并跳过它们。
- 它会从 `faster_whisper.transcribe_audio` 开始重新执行。
- 由于 `param_merge_strategy` 是 `override`，它会完全忽略旧的 `beam_size: 5`，只使用新的 `{ "beam_size": 10, "language": "zh" }` 参数。这确保了实验的纯粹性。
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