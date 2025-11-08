# YiVideo 工作流节点功能文档

## 概述

本文档详细描述了 YiVideo 系统中所有可用的工作流节点的功能、参数、输入输出格式和使用方法。每个节点都是一个独立的 Celery 任务，可以通过工作流配置组合成复杂的视频处理流程。

## 文档结构

- [FFmpeg 服务节点](#ffmpeg-服务节点) - 视频和音频处理
- [Faster-Whisper 服务节点](#faster-whisper-服务节点) - 语音识别和字幕生成
- [Audio Separator 服务节点](#audio-separator-服务节点) - 音频分离
- [Pyannote Audio 服务节点](#pyannote-audio-服务节点) - 说话人分离
- [PaddleOCR 服务节点](#paddleocr-服务节点) - 文字识别
- [IndexTTS 服务节点](#indextts-服务节点) - 语音合成
- [WService 字幕优化服务节点](#wservice-字幕优化服务节点) - AI字幕优化

## 通用参数说明

所有工作流节点都遵循统一的接口规范：

### 标准任务签名
```python
def task_name(self: Task, context: dict) -> dict:
```

### 上下文结构
```json
{
  "workflow_id": "工作流唯一标识符",
  "input_params": {
    "输入参数名称": "参数值"
  },
  "stages": {
    "其他阶段名称": {
      "status": "SUCCESS|FAILED|IN_PROGRESS",
      "output": "输出数据"
    }
  },
  "shared_storage_path": "/share/workflows/{workflow_id}/"
}
```

### 标准输出格式
```json
{
  "workflow_id": "工作流ID",
  "stages": {
    "当前节点名称": {
      "status": "SUCCESS|FAILED",
      "output": "节点输出数据",
      "duration": 处理时长(秒),
      "error": "错误信息(如果失败)"
    }
  }
}
```

---

## FFmpeg 服务节点

FFmpeg 服务提供视频和音频的基础处理功能，包括关键帧提取、音频提取、字幕区域裁剪和音频分割。

### 1. ffmpeg.extract_keyframes

从视频中抽取若干关键帧图片，为后续的字幕区域检测提供素材。

**功能描述**：随机从视频中抽取指定数量的关键帧图片，保存为 JPEG 格式。

**输入参数**：
- `video_path` (string, 全局必需): 视频文件路径，在API请求的顶层提供。
- `keyframe_sample_count` (int, 节点可选): 抽取帧数，默认 100。

**配置来源说明**：
- `video_path`: **全局参数** (在API请求的顶层 `video_path` 字段提供)
- `keyframe_sample_count`: **节点参数** (在请求体中的 `ffmpeg.extract_keyframes` 对象内提供)

**输出格式**：
```json
{
  "keyframe_dir": "/share/workflows/{workflow_id}/keyframes"
}
```

**使用示例**：
```json
{
  "workflow_config": {
    "workflow_chain": ["ffmpeg.extract_keyframes"]
  },
  "ffmpeg.extract_keyframes": {
    "keyframe_sample_count": 50
  }
}
```

**依赖关系**：无

**注意事项**：
- 抽取的帧为随机分布，不是均匀分布
- 输出图片格式为 JPEG
- 关键帧目录会在字幕区域检测完成后自动清理

---

### 2. ffmpeg.extract_audio

从视频中提取音频文件，转换为适合语音识别的格式。

**功能描述**：使用 FFmpeg 从视频中提取音频，转换为 16kHz 单声道 WAV 格式。

**输入参数**：
- `video_path` (string, 全局必需): 视频文件路径，在API请求的顶层提供。

**配置来源说明**：
- `video_path`: **全局参数** (在API请求的顶层 `video_path` 字段提供)

**输出格式**：
```json
{
  "audio_path": "/share/workflows/{workflow_id}/audio/{video_name}.wav"
}
```

**使用示例**：
```json
{
  "workflow_config": {
    "workflow_chain": ["ffmpeg.extract_audio"]
  }
}
```

**依赖关系**：无

**技术规格**：
- 编码：16-bit PCM
- 采样率：16kHz (ASR 推荐采样率)
- 声道：单声道
- 超时：1800秒

**注意事项**：
- 自动覆盖已存在的音频文件
- 支持所有 FFmpeg 支持的视频格式
- 文件大小验证，确保输出文件不为空

---

### 3. ffmpeg.crop_subtitle_images

根据检测到的字幕区域，从视频中并发裁剪字幕条图片。

**功能描述**：通过外部脚本并发解码视频，根据字幕区域坐标裁剪出所有字幕帧图片。

**输入参数**：
- `video_path` (string, 全局必需): 视频文件路径，在API请求的顶层提供。
- `decode_processes` (int, 节点可选): 解码进程数，默认 10。

**配置来源说明**：
- `video_path`: **全局参数** (在API请求的顶层 `video_path` 字段提供)
- `decode_processes`: **节点参数** (在请求体中的 `ffmpeg.crop_subtitle_images` 对象内提供)

**前置依赖**：
- `paddleocr.detect_subtitle_area` - 必须先完成字幕区域检测

**输出格式**：
```json
{
  "cropped_images_path": "/share/workflows/{workflow_id}/cropped_images/frames"
}
```

**使用示例**：
```json
{
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_keyframes",
      "paddleocr.detect_subtitle_area",
      "ffmpeg.crop_subtitle_images"
    ]
  },
  "ffmpeg.crop_subtitle_images": {
    "decode_processes": 8
  }
}
```

**依赖关系**：
- 需要 `paddleocr.detect_subtitle_area` 的输出 `subtitle_area`

**技术特性**：
- 并发解码处理，提高处理速度
- GPU 加速（使用 GPU 锁保护）
- 超时保护：1800秒

---

### 4. ffmpeg.split_audio_segments

根据字幕文件的时间戳数据分割音频片段，支持按说话人分组。

**功能描述**：根据字幕时间戳将音频分割为小片段，为语音生成提供参考音频。支持多种输出格式和按说话人分组存储。

**输入参数**：
- `audio_path` (string, 节点可选): 指定音频文件路径，支持 `${{...}}` 格式的参数引用。如果未提供，将启用智能检测。
- `subtitle_path` (string, 节点可选): 指定字幕文件路径，支持 `${{...}}` 格式的参数引用。如果未提供，将启用智能检测。
- `output_format` (string, 节点可选): 输出格式，默认 "wav"。
- `sample_rate` (int, 节点可选): 采样率，默认 16000。
- `channels` (int, 节点可选): 声道数，默认 1。
- `min_segment_duration` (float, 节点可选): 最小片段时长，默认 1.0秒。
- `max_segment_duration` (float, 节点可选): 最大片段时长，默认 30.0秒。
- `group_by_speaker` (bool, 节点可选): 按说话人分组，默认 false。
- `include_silence` (bool, 节点可选): 包含静音片段，默认 false。
- `enable_concurrent` (bool, 节点可选): 启用并发分割，默认 true。
- `max_workers` (int, 节点可选): 最大工作线程数，默认 8。
- `concurrent_timeout` (int, 节点可选): 并发超时时间，默认 600秒。

**配置来源说明**：
- 所有列出的参数均为 **节点参数**，在请求体中的 `ffmpeg.split_audio_segments` 对象内提供。

**参数引用支持**：
所有字符串类型的参数都支持 `${{ stages.<stage_name>.output.<field_name> }}` 格式的动态引用，例如：
```json
{
  "ffmpeg.split_audio_segments": {
    "audio_path": "${{ stages.audio_separator.separate_vocals.output.vocal_audio }}",
    "subtitle_path": "${{ stages.faster_whisper.generate_subtitle_files.output.speaker_srt_path }}",
    "output_format": "wav",
    "group_by_speaker": true
  }
}
```

**智能音频源选择**（按优先级）：
1. 人声音频 (`audio_separator.separate_vocals` 输出的 `vocal_audio`)
2. 默认音频 (`ffmpeg.extract_audio` 输出的 `audio_path`)
3. 参数传入的 `audio_path`

**智能字幕文件选择**（按优先级）：
1. 带说话人信息 SRT (`speaker_srt_path`)
2. 基础 SRT (`subtitle_path`)
3. 带说话人信息 JSON (`speaker_json_path`)
4. 参数传入的 `subtitle_path`

**前置依赖**：
- `ffmpeg.extract_audio` 或 `audio_separator.separate_vocals`
- `faster_whisper.generate_subtitle_files`

**输出格式**：
```json
{
  "audio_segments_dir": "/share/workflows/{workflow_id}/audio_segments",
  "audio_source": "实际使用的音频文件路径",
  "subtitle_source": "实际使用的字幕文件路径",
  "total_segments": 150,
  "successful_segments": 148,
  "failed_segments": 2,
  "total_duration": 1200.5,
  "processing_time": 45.2,
  "audio_format": "wav",
  "sample_rate": 16000,
  "channels": 1,
  "split_info_file": "/share/workflows/{workflow_id}/audio_segments/split_info.json",
  "segments_count": 148,
  "speaker_summary": {
    "SPEAKER_00": {
      "count": 80,
      "duration": 650.3
    },
    "SPEAKER_01": {
      "count": 68,
      "duration": 550.2
    }
  }
}
```

**使用示例**：
```json
{
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_audio",
      "faster_whisper.transcribe_audio",
      "faster_whisper.generate_subtitle_files",
      "ffmpeg.split_audio_segments"
    ]
  },
  "ffmpeg.split_audio_segments": {
    "output_format": "wav",
    "group_by_speaker": false,
    "min_segment_duration": 2.0,
    "max_workers": 6
  }
}
```

**依赖关系**：
- 音频源：`ffmpeg.extract_audio` 或 `audio_separator.separate_vocals`
- 字幕源：`faster_whisper.generate_subtitle_files`

**特性**：
- 智能源选择，自动从工作流上下文获取最佳输入
- 支持并发分割，提高处理速度
- 完善的错误处理和统计信息
- 按说话人分组存储
- 详细的分割信息保存到 JSON 文件

---

## Faster-Whisper 服务节点

Faster-Whisper 服务提供基于 faster-whisper 模型的语音识别和字幕生成功能，支持多语言和词级时间戳。

### 1. faster_whisper.transcribe_audio

对音频进行语音转录，生成包含词级时间戳的详细转录数据。

**功能描述**：使用 faster-whisper 模型对音频进行语音识别，生成包含词级时间戳的精确转录结果。

**输入参数**：
- `audio_path` (string, 节点可选): 指定音频文件路径，以覆盖智能音频源选择逻辑。支持 `${{...}}` 格式的参数引用。

**配置来源说明**：
- `audio_path`: **节点参数** (在请求体中的 `faster_whisper.transcribe_audio` 对象内提供)。
- **其他模型参数**: 如模型大小 (`model_size`)、语言 (`language`)、计算精度、VAD过滤等，均为 **全局配置**，请在 `config.yml` 文件中修改。它们**不是**节点参数。

**全局配置示例 (config.yml)**:
```yaml
faster_whisper_service:
  default_model: "large-v3"
  default_device: "cuda"
  default_compute_type: "float16"
  default_language: "zh"
  default_word_timestamps: true
  default_vad_filter: true
```

**智能音频源选择**（按优先级）：
1. 人声音频 (`audio_separator.separate_vocals` 输出的 `vocal_audio`)
2. 默认音频 (`ffmpeg.extract_audio` 输出的 `audio_path`)
3. 参数传入的 `audio_path`

**前置依赖**：
- `ffmpeg.extract_audio` 或 `audio_separator.separate_vocals`

**输出格式**：
```json
{
  "segments_file": "/share/workflows/{workflow_id}/transcription/segments.json",
  "transcribe_duration": 125.5,
  "language": "zh",
  "model_used": "base",
  "total_words": 850,
  "processing_time": 45.2
}
```

**Segments 文件格式**：
```json
{
  "segments": [
    {
      "id": 0,
      "seek": 0,
      "start": 0.0,
      "end": 3.5,
      "text": "这是第一段转录文本",
      "tokens": [1234, 5678, 9012],
      "temperature": 0.0,
      "avg_logprob": -0.25,
      "compression_ratio": 1.2,
      "no_speech_prob": 0.1,
      "words": [
        {
          "word": "这是",
          "start": 0.0,
          "end": 0.8,
          "probability": 0.95
        },
        {
          "word": "第一段",
          "start": 0.9,
          "end": 2.1,
          "probability": 0.92
        },
        {
          "word": "转录文本",
          "start": 2.2,
          "end": 3.5,
          "probability": 0.88
        }
      ]
    }
  ]
}
```

**使用示例**：
```json
{
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_audio",
      "faster_whisper.transcribe_audio"
    ]
  },
  "faster_whisper.transcribe_audio": {
    "model_size": "base",
    "language": "zh",
    "beam_size": 5,
    "word_timestamps": true,
    "vad_filter": true
  }
}
```

**依赖关系**：
- `ffmpeg.extract_audio` 或 `audio_separator.separate_vocals`

**技术特性**：
- GPU 加速（使用 GPU 锁保护）
- 支持多种模型大小，平衡速度和精度
- 自动语言检测
- 词级时间戳精确同步
- 语音活动检测过滤

**模型选择建议**：
- `tiny`: 最快速度，精度较低，适合实时应用
- `base`: 平衡速度和精度，推荐日常使用
- `small`: 较好精度，速度适中
- `medium`: 高精度，处理时间较长
- `large-v3`: 最高精度，需要充足硬件资源

---

## Audio Separator 服务节点

Audio Separator 服务提供基于 UVR-MDX 模型的专业音频分离功能，支持人声与伴奏的高质量分离。

### 1. audio_separator.separate_vocals

分离音频中的人声和背景音，支持多种模型和质量模式。

**功能描述**：使用 UVR-MDX 深度学习模型将音频分离为人声和各种乐器轨道，支持高质量分离和GPU加速。

**输入参数**：
- `audio_path` (string, 节点可选): 指定音频文件路径，以覆盖智能音频源选择逻辑。
- `model_name` (string, 节点可选): 指定要使用的分离模型名称，如 "UVR-MDX-NET-Inst_HQ_3"。如果未提供，则根据 `quality_mode` 从全局配置中选择默认模型。
- `quality_mode` (string, 节点可选): 质量模式，会影响默认模型的选择。可选值: `"fast"`, `"default"`, `"high_quality"`。

**配置来源说明**：
- `audio_path`, `model_name`, `quality_mode`: **节点参数** (在请求体中的 `audio_separator.separate_vocals` 对象内提供)。
- **其他分离参数**: 如 `output_format`, `sample_rate`, `normalize` 等，均为 **全局配置**，请在 `config.yml` 文件中修改。它们**不是**节点参数。

**全局配置示例 (config.yml)**:
```yaml
audio_separator_service:
  # ... (other settings)
  separator_options:
    output_format: "flac"
    sample_rate: 44100
    bit_rate: 320
    normalize: true
```

**智能音频源选择**（按优先级）：
1. `ffmpeg.extract_audio` 输出的 `audio_path`
2. `input_params` 中的 `audio_path`
3. `input_params` 中的 `video_path`（自动提取音频）

**前置依赖**：
- `ffmpeg.extract_audio` (推荐)

**输出格式**：
```json
{
  "output_dir": "/share/workflows/{workflow_id}/audio_separated",
  "vocal_audio": "/share/workflows/{workflow_id}/audio_separated/video_(Vocals)_htdemucs.flac",
  "instrumental_audio": "/share/workflows/{workflow_id}/audio_separated/video_(Other)_htdemucs.flac",
  "bass_audio": "/share/workflows/{workflow_id}/audio_separated/video_(Bass)_htdemucs.flac",
  "drums_audio": "/share/workflows/{workflow_id}/audio_separated/video_(Drums)_htdemucs.flac",
  "audio_list": [
    "/share/workflows/{workflow_id}/audio_separated/video_(Vocals)_htdemucs.flac",
    "/share/workflows/{workflow_id}/audio_separated/video_(Other)_htdemucs.flac",
    "/share/workflows/{workflow_id}/audio_separated/video_(Bass)_htdemucs.flac",
    "/share/workflows/{workflow_id}/audio_separated/video_(Drums)_htdemucs.flac"
  ],
  "model_used": "htdemucs",
  "quality_mode": "default",
  "processing_time": 180.5,
  "audio_format": "flac",
  "sample_rate": 44100,
  "channels": 2
}
```

**使用示例**：
```json
{
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_audio",
      "audio_separator.separate_vocals"
    ]
  },
  "audio_separator.separate_vocals": {
    "audio_separator_config": {
      "quality_mode": "high_quality",
      "model_type": "demucs",
      "use_vocal_optimization": true,
      "vocal_optimization_level": 2,
      "output_format": "flac"
    }
  }
}
```

**依赖关系**：
- `ffmpeg.extract_audio` (推荐)

**质量模式说明**：
- `fast`: 快速模式，使用轻量级模型
- `default`: 默认模式，平衡质量和速度
- `high_quality`: 高质量模式，使用最佳模型

**支持的模型类型**：
- `demucs`: Demucs 系列模型，推荐日常使用
- `mdx`: MDX 系列模型，专业音质
- `vr`: Vocal Remover 模型，专门人声分离

**输出轨道说明**：
- `Vocals`: 人声轨道（推荐用于语音识别）
- `Other`: 伴奏/其他轨道
- `Bass`: 低音轨道
- `Drums`: 鼓声轨道

**技术特性**：
- GPU 加速处理（使用 GPU 锁保护）
- 支持多种音频格式输入
- 自动音量标准化
- 人声优化算法
- 高质量 FLAC 输出

**注意事项**：
- 处理时间较长，特别是高质量模式
- GPU 内存使用量较高
- 建议使用人声轨道进行后续的语音识别

---

## Pyannote Audio 服务节点

Pyannote Audio 服务提供基于 pyannote-audio 模型的专业说话人分离功能，支持多人对话场景的说话人识别和时间分割。

### 1. pyannote_audio.diarize_speakers

对音频进行说话人分离，识别不同说话人及其时间区间。

**功能描述**：使用 pyannote-audio 深度学习模型识别音频中的不同说话人，生成精确的说话人时间戳。

**输入参数**：
- `audio_path` (string, 节点可选): 指定音频文件路径，以覆盖智能音频源选择逻辑。

**配置来源说明**：
- `audio_path`: **节点参数** (在请求体中的 `pyannote_audio.diarize_speakers` 对象内提供)。
- **Hugging Face Token (`hf_token`)**: **必需的全局配置**，请在 `config.yml` 中设置。
- **其他 diarization 参数**: 如 `num_speakers`, `min_duration_on`, `min_duration_off` 等，均为 **全局配置**，请在 `config.yml` 文件中修改。它们**不是**节点参数。

**全局配置示例 (config.yml)**:
```yaml
pyannote_audio_service:
  # ... (other settings)
  diarization_options:
    hf_token: "your_hugging_face_token_here"
    num_speakers: 0 # 0 for auto-detection
    min_duration_on: 0.5
    min_duration_off: 0.3
```

**智能音频源选择**（按优先级）：
1. 人声音频 (`audio_separator.separate_vocals` 输出的 `vocal_audio`)
2. 默认音频 (`ffmpeg.extract_audio` 输出的 `audio_path`)
3. 参数传入的 `audio_path`

**前置依赖**：
- `ffmpeg.extract_audio` 或 `audio_separator.separate_vocals`

**输出格式**：
```json
{
  "diarization_path": "/share/workflows/{workflow_id}/diarization/diarization_result.json",
  "speaker_srt_path": "/share/workflows/{workflow_id}/diarization/speaker_diarization.srt",
  "speaker_json_path": "/share/workflows/{workflow_id}/diarization/speaker_segments.json",
  "word_timestamps_json_path": "/share/workflows/{workflow_id}/diarization/word_timestamps.json",
  "num_speakers_detected": 2,
  "total_speech_duration": 280.5,
  "model_used": "pyannote/speaker-diarization-3.1",
  "processing_time": 95.2,
  "speakers": ["SPEAKER_00", "SPEAKER_01"]
}
```

**说话人分离结果格式**：
```json
{
  "speakers": {
    "SPEAKER_00": [
      {
        "start": 0.0,
        "end": 5.2,
        "confidence": 0.95,
        "duration": 5.2
      },
      {
        "start": 12.8,
        "end": 18.5,
        "confidence": 0.92,
        "duration": 5.7
      }
    ],
    "SPEAKER_01": [
      {
        "start": 5.5,
        "end": 12.3,
        "confidence": 0.88,
        "duration": 6.8
      }
    ]
  },
  "statistics": {
    "total_speech_time": 17.7,
    "speaker_percentages": {
      "SPEAKER_00": 58.6,
      "SPEAKER_01": 41.4
    }
  }
}
```

**使用示例**：
```json
{
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_audio",
      "audio_separator.separate_vocals",
      "pyannote_audio.diarize_speakers"
    ]
  },
  "pyannote_audio.diarize_speakers": {
    "hf_token": "hf_your_huggingface_token_here",
    "num_speakers": 2,
    "min_duration_on": 0.5,
    "min_duration_off": 0.3
  }
}
```

**依赖关系**：
- `ffmpeg.extract_audio` 或 `audio_separator.separate_vocals`

**配置要求**：
1. **Hugging Face Token**: 必需有效的 Hugging Face 访问令牌
2. **模型许可**: 确保有权限使用选定的说话人分离模型
3. **GPU 推荐**: 虽然支持 CPU，但 GPU 处理速度更快

**技术特性**：
- GPU 加速处理（使用 GPU 锁保护）
- 自动说话人数量检测
- 高精度时间边界检测
- 置信度评估
- 支持多种语言和音频场景

**注意事项**：
- 首次运行会自动下载模型（约 1GB）
- 需要有效的 Hugging Face 访问令牌
- 推荐使用人声分离后的音频以提高准确性
- 处理时间与音频长度和说话人数量相关

**最佳实践**：
- 对于清晰的人声推荐使用 `audio_separator.separate_vocals` 的输出
- 音频质量越好，分离效果越准确
- 说话人差异越大，识别效果越好

---

## PaddleOCR 服务节点

PaddleOCR 服务提供基于 PaddleOCR 模型的文字识别功能，专门用于视频字幕的检测、识别和处理。

### 1. paddleocr.detect_subtitle_area

通过关键帧分析检测视频中的字幕区域位置。

**功能描述**：分析视频关键帧，使用计算机视觉技术检测字幕通常出现的区域位置。

**输入参数**：
- 无直接参数，从工作流上下文自动获取关键帧

**前置依赖**：
- `ffmpeg.extract_keyframes`

**输出格式**：
```json
{
  "subtitle_area": {
    "x": 0,
    "y": 0.85,
    "width": 1.0,
    "height": 0.15
  },
  "detection_confidence": 0.95,
  "keyframes_analyzed": 100,
  "detection_method": "unified_bottom_detection"
}
```

**使用示例**：
```json
{
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_keyframes",
      "paddleocr.detect_subtitle_area"
    ]
  }
}
```

**依赖关系**：
- `ffmpeg.extract_keyframes`

**检测原理**：
- 分析多帧字幕位置分布
- 识别字幕出现的规律区域
- 计算最佳字幕区域坐标
- 支持多种字幕位置检测

---

### 2. paddleocr.create_stitched_images

将裁剪的字幕条图像拼接成大图，提高 OCR 识别效率。

**功能描述**：将多个独立的字幕条图像拼接成一张大图，便于批量 OCR 处理。

**输入参数**：
- 无直接节点参数。

**配置来源说明**：
- **拼接参数**: 如 `concat_batch_size`, `stitching_workers` 等，均为 **全局配置**，请在 `config.yml` 文件中修改。

---

### 3. paddleocr.perform_ocr

对拼接后的字幕图像进行文字识别。

**功能描述**：使用 PaddleOCR 模型对字幕图像进行高精度文字识别。

**输入参数**：
- 无直接节点参数。

**配置来源说明**：
- **OCR参数**: 如 `lang`, `use_angle_cls`, `use_gpu` 等，均为 **全局配置**，请在 `config.yml` 文件中修改。

---

### 4. paddleocr.postprocess_and_finalize

后处理 OCR 结果并生成最终的字幕文件。

**功能描述**：对 OCR 识别结果进行智能后处理，包括时间对齐、文本校正、格式化等。

**输入参数**：
- 无直接节点参数。

**配置来源说明**：
- **后处理参数**: 如 `time_alignment_method`, `text_correction`, `min_confidence_threshold` 等，均为 **全局配置**，请在 `config.yml` 文件中修改。

## IndexTTS 服务节点

IndexTTS 服务提供基于 IndexTTS2 模型的高质量语音合成功能，支持情感化语音生成和音色克隆。

### 1. indextts.generate_speech

使用参考音频生成具有相同音色的语音。

**功能描述**：基于 IndexTTS2 模型，使用参考音频的音色特征合成新的语音内容，支持情感表达。

**输入参数**：
- `text` (string, 必需): 要合成的文本内容。
- `output_path` (string, 必需): 输出音频文件路径。
- `spk_audio_prompt` (string, 必需): 说话人参考音频路径。
- `emo_audio_prompt` (string, 可选): 情感参考音频路径。

**配置来源说明**：
- `text`, `output_path`, `spk_audio_prompt`, `emo_audio_prompt`: **节点参数** (在请求体中的 `indextts.generate_speech` 对象内提供)。
- **其他合成参数**: 如 `emotion_alpha`, `speed` 等，均为 **全局配置**，请在 `config.yml` 文件中修改。它们**不是**节点参数。

**输出格式**：
```json
{
  "output_path": "/share/workflows/{workflow_id}/tts/generated_speech.wav",
  "processing_time": 15.2,
  "text_length": 85,
  "audio_duration": 12.5,
  "reference_audio_used": "/share/reference/speaker.wav",
  "emotion_audio_used": "/share/reference/emotion.wav",
  "model_info": {
    "model_name": "IndexTTS2",
    "sample_rate": 22050,
    "channels": 1
  },
  "generation_params": {
    "emotion_alpha": 1.0,
    "speed": 1.0,
    "segments_generated": 3
  }
}
```

**使用示例**：
```json
{
  "workflow_config": {
    "workflow_chain": ["indextts.generate_speech"]
  },
  "indextts.generate_speech": {
    "text": "你好，这是一个使用IndexTTS2生成的语音示例。",
    "output_path": "/share/workflows/{workflow_id}/tts/example.wav",
    "spk_audio_prompt": "/share/reference/speaker_voice.wav",
    "emo_audio_prompt": "/share/reference/happy_emotion.wav",
    "emotion_alpha": 1.2,
    "speed": 1.0
  }
}
```

**依赖关系**：无

**技术特性**：
- 高质量音色克隆
- 情感化语音合成
- GPU 加速处理（使用 GPU 锁保护）
- 支持长文本分段处理
- 自然韵律和语调

**参数说明**：
- `spk_audio_prompt`: 决定合成语音的音色特征
- `emo_audio_prompt`: 控制语音的情感表达
- `emotion_alpha`: 调节情感强度（0.5-2.0）
- `speed`: 控制语音速度（0.5-2.0）

**注意事项**：
- 必须提供说话人参考音频
- 参考音频质量直接影响合成效果
- 建议参考音频时长 3-10 秒
- 情感音频是可选的，用于控制情感表达

---

## WService 字幕优化服务节点

WService 服务提供基于 AI 大模型的字幕智能优化功能，支持错别字修正、语法优化、标点符号补充和口头禅过滤。

### 1. wservice.ai_optimize_subtitles

对转录后的字幕进行 AI 智能优化和校正。

**功能描述**：使用 AI 大模型对 faster_whisper 转录的字幕进行智能优化，包括错别字修正、标点补充、口头禅删除、语法优化等。支持大体积字幕的并发处理，采用滑窗重叠分段策略保证上下文完整性。

**输入参数**：
- `segments_file` (string, 节点可选): 输入字幕文件路径。**支持 `${{...}}` 动态引用**，优先级高于自动检测。

**配置来源说明**：
- `segments_file`: **节点参数** (在请求体中的 `wservice.ai_optimize_subtitles` 对象内提供)。
- `subtitle_optimization` (object): **全局参数** (在API请求的顶层 `workflow_config` 内提供)，包含 `enabled`, `provider`, `batch_size` 等所有优化相关的微调选项。

**前置依赖**：
- `faster_whisper.transcribe_audio` (必需)

**智能输入源选择**（按优先级）：
1. **`segments_file` 参数**: 如果在节点参数中明确提供了 `segments_file`（支持动态引用），将直接使用该文件
2. **`faster_whisper.transcribe_audio` 输出**: 自动获取 `faster_whisper.transcribe_audio` 阶段的 `segments_file`

**输出格式**：
```json
{
  "optimized_file_path": "/share/workflows/{workflow_id}/optimized.json",
  "original_file_path": "/share/workflows/{workflow_id}/original.json",
  "provider_used": "deepseek",
  "processing_time": 12.5,
  "commands_applied": 15,
  "batch_mode": true,
  "batches_count": 3,
  "segments_count": 100
}
```

**依赖关系**：
- 必需：`faster_whisper.transcribe_audio`
- 后置：`wservice.generate_subtitle_files` (可选)

**注意事项**：
- `subtitle_optimization` 的详细参数（如 `provider`, `batch_size`）应在API请求顶层的 `workflow_config` 中配置。
- 需要配置相应AI提供商的API密钥。
- 大体积字幕自动启用分段处理。
- 滑窗重叠机制确保上下文完整性。

---

### 2. wservice.correct_subtitles

使用 LLM 对字幕进行智能校正和优化。

**功能描述**：基于大语言模型对转录字幕进行语法纠错、标点优化、语义理解等智能处理。

**输入参数**：
- `subtitle_path` (string, 节点可选): 待校正的字幕文件路径。**支持 `${{...}}` 动态引用**，优先级高于自动检测。

**配置来源说明**：
- `subtitle_path`: **节点参数** (在请求体中的 `wservice.correct_subtitles` 对象内提供)。
- **其他校正参数**: 如 `correction_model`, `correction_type`, `target_language` 等，均为 **全局配置**，请在 `config.yml` 文件中修改。它们**不是**节点参数。

**智能输入源选择**（按优先级）：
1.  **`subtitle_path` 参数**: 如果在节点参数中明确提供了 `subtitle_path`（支持动态引用），将直接使用该文件。
2.  **`generate_subtitle_files` 的输出 (带说话人)**: 自动寻找 `wservice.generate_subtitle_files` 阶段输出的 `speaker_srt_path`。
3.  **`generate_subtitle_files` 的输出 (基础SRT)**: 最后尝试使用 `wservice.generate_subtitle_files` 阶段输出的 `subtitle_path`。

**输出格式**：
```json
{
  "corrected_subtitle_path": "/share/workflows/{workflow_id}/subtitles/video_corrected.srt",
  "correction_report": "/share/workflows/{workflow_id}/subtitles/correction_report.json",
  "processing_time": 25.3
}
```

**依赖关系**：
- `wservice.generate_subtitle_files` (如果未通过 `subtitle_path` 参数指定输入)

**注意事项**：
- 校正相关的微调参数（如 `correction_model`）应在 `config.yml` 中配置。
- 需要配置相应的 LLM API 密钥。

---

### 3. wservice.generate_subtitle_files

基于转录数据和可选的说话人数据生成多种格式的字幕文件。

**功能描述**：将转录数据转换为标准字幕格式，支持 SRT、VTT、ASS 等格式，并可选择集成说话人信息。

**输入参数**：
- `segments_file` (string, 节点可选): 指定转录数据文件路径，以覆盖智能输入源选择逻辑。
- `diarization_file` (string, 节点可选): 指定说话人分离数据文件路径，以覆盖智能输入源选择逻辑。

**配置来源说明**：
- `segments_file`, `diarization_file`: **节点参数** (在请求体中的 `wservice.generate_subtitle_files` 对象内提供)。
- **其他字幕格式化参数**: 如 `output_formats`, `max_chars_per_line`, `max_lines_per_subtitle` 等，均为 **全局配置**，请在 `config.yml` 文件中修改。它们**不是**节点参数。

**全局配置示例 (config.yml)**:
```yaml
wservice:
  # ... (other wservice settings)
  subtitle_options:
    max_chars_per_line: 42
    max_lines_per_subtitle: 2
    min_subtitle_duration: 1.0
    include_speaker_labels: true
```

**前置依赖**：
- `faster_whisper.transcribe_audio` (必需)
- `pyannote_audio.diarize_speakers` (可选，用于说话人信息)
- `wservice.ai_optimize_subtitles` (可选，可先优化再生成文件)

**输出格式**：
```json
{
  "subtitle_path": "/share/workflows/{workflow_id}/subtitles/video.srt",
  "vtt_path": "/share/workflows/{workflow_id}/subtitles/video.vtt",
  "ass_path": "/share/workflows/{workflow_id}/subtitles/video.ass",
  "txt_path": "/share/workflows/{workflow_id}/subtitles/video.txt",
  "speaker_srt_path": "/share/workflows/{workflow_id}/subtitles/video_with_speakers.srt",
  "speaker_json_path": "/share/workflows/{workflow_id}/subtitles/video_with_speakers.json",
  "word_timestamps_json_path": "/share/workflows/{workflow_id}/subtitles/video_word_timestamps.json",
  "segments_count": 125,
  "words_count": 850,
  "total_duration": 300.5,
  "languages_detected": ["zh"]
}
```

**使用示例**：
```json
{
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_audio",
      "faster_whisper.transcribe_audio",
      "wservice.generate_subtitle_files"
    ]
  },
  "wservice.generate_subtitle_files": {
    "output_formats": ["srt", "vtt", "ass"],
    "max_chars_per_line": 40,
    "include_speaker_labels": true,
    "speaker_label_format": "[SPEAKER_00]"
  }
}
```

**带说话人信息的示例**：
```json
{
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_audio",
      "audio_separator.separate_vocals",
      "faster_whisper.transcribe_audio",
      "pyannote_audio.diarize_speakers",
      "wservice.generate_subtitle_files"
    ]
  },
  "wservice.generate_subtitle_files": {
    "output_formats": ["srt", "json"],
    "include_speaker_labels": true,
    "speaker_label_format": "Speaker 1:"
  }
}
```

**依赖关系**：
- 必需：`faster_whisper.transcribe_audio`
- 可选：`pyannote_audio.diarize_speakers`

**输出文件说明**：

1. **基础 SRT 文件** (`subtitle_path`): 标准字幕格式
2. **带说话人 SRT** (`speaker_srt_path`): 包含说话人信息的字幕
3. **带说话人 JSON** (`speaker_json_path`): 完整的结构化数据
4. **词级时间戳 JSON** (`word_timestamps_json_path`): 精确的词级时间戳
5. **其他格式**: VTT、ASS、TXT 等

**字幕格式特性**：
- 自动断行和时长优化
- 智能合并短字幕
- 拆分长字幕
- 时间轴平滑处理
- 说话人切换边界优化

---

### 4. wservice.merge_speaker_segments

将转录字幕与说话人时间段进行合并（片段级）。

**功能描述**：根据字幕片段的整体时间戳，将其归属到对应的说话人。这是一个宏观层面的合并，适合于一句字幕只属于一个说话人的场景。

**输入参数**：无直接节点参数。任务从工作流上下文中自动获取所需数据。

**前置依赖**：
- `faster_whisper.transcribe_audio`
- `pyannote_audio.diarize_speakers`

**输出格式**：
```json
{
  "merged_segments": [
    {
      "start": 0.0,
      "end": 3.5,
      "text": "这是第一段归属给某个说话人的文本",
      "speaker": "SPEAKER_00"
    }
  ]
}
```

**使用示例**：
```json
{
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_audio",
      "faster_whisper.transcribe_audio",
      "pyannote_audio.diarize_speakers",
      "wservice.merge_speaker_segments"
    ]
  }
}
```

**依赖关系**：
- `faster_whisper.transcribe_audio`
- `pyannote_audio.diarize_speakers`

**注意事项**：
- 合并精度为片段级，可能不适用于一句话内多人交谈的场景。
- 为获得更高精度，建议使用 `wservice.merge_with_word_timestamps` 节点。

---

### 5. wservice.merge_with_word_timestamps

使用词级时间戳进行高精度字幕与说话人合并。

**功能描述**：利用 `faster_whisper` 输出的词级时间戳，将每个独立的**词**与说话人时间段进行匹配。即使在同一字幕片段内有多个说话人，此方法也能实现精确的归属。

**输入参数**：无直接节点参数。任务从工作流上下文中自动获取所需数据。

**前置依赖**：
- `faster_whisper.transcribe_audio` (必须启用了词级时间戳)
- `pyannote_audio.diarize_speakers`

**输出格式**：
```json
{
  "merged_segments": [
    {
      "start": 0.0,
      "end": 3.5,
      "text": "你好，我是小王。 不，我是小李。",
      "speaker": "MIXED",
      "words": [
        {"word": "你好，", "start": 0.0, "end": 0.5, "speaker": "SPEAKER_00"},
        {"word": "我是小王。", "start": 0.6, "end": 1.5, "speaker": "SPEAKER_00"},
        {"word": "不，", "start": 1.8, "end": 2.2, "speaker": "SPEAKER_01"},
        {"word": "我是小李。", "start": 2.3, "end": 3.5, "speaker": "SPEAKER_01"}
      ]
    }
  ]
}
```

**使用示例**：
```json
{
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_audio",
      "faster_whisper.transcribe_audio",
      "pyannote_audio.diarize_speakers",
      "wservice.merge_with_word_timestamps"
    ]
  },
  "faster_whisper.transcribe_audio": {
     "word_timestamps": true
  }
}
```

**依赖关系**：
- `faster_whisper.transcribe_audio`
- `pyannote_audio.diarize_speakers`

**技术特性**：
- 这是**推荐**的说话人合并方式，精度最高。
- 能够处理一句话内说话人切换的复杂场景。
- 依赖 `faster_whisper.transcribe_audio` 任务输出词级时间戳。

---

## 工作流组合示例

### 完整字幕生成工作流

```json
{
  "video_path": "/share/videos/example.mp4",
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_audio",
      "audio_separator.separate_vocals",
      "faster_whisper.transcribe_audio",
      "pyannote_audio.diarize_speakers",
      "faster_whisper.generate_subtitle_files"
    ]
  },
  "audio_separator.separate_vocals": {
    "audio_separator_config": {
      "quality_mode": "high_quality",
      "use_vocal_optimization": true
    }
  },
  "faster_whisper.transcribe_audio": {
    "model_size": "base",
    "language": "zh",
    "word_timestamps": true
  },
  "pyannote_audio.diarize_speakers": {
    "hf_token": "your_hf_token",
    "num_speakers": 2
  }
}
```

### OCR 字幕提取工作流

```json
{
  "video_path": "/share/videos/example.mp4",
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_keyframes",
      "paddleocr.detect_subtitle_area",
      "ffmpeg.crop_subtitle_images",
      "paddleocr.create_stitched_images",
      "paddleocr.perform_ocr",
      "paddleocr.postprocess_and_finalize"
    ]
  },
  "ffmpeg.extract_keyframes": {
    "keyframe_sample_count": 50
  }
}
```

### 语音合成工作流

```json
{
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_audio",
      "faster_whisper.transcribe_audio",
      "ffmpeg.split_audio_segments",
      "indextts.generate_speech"
    ]
  },
  "indextts.generate_speech": {
    "text": "这是要合成的文本内容",
    "output_path": "/share/workflows/{workflow_id}/tts/output.wav",
    "spk_audio_prompt": "${{ stages.ffmpeg.split_audio_segments.output.audio_segments_dir }}/segment_001.wav"
  }
}
```

## 错误处理和调试

### 常见错误类型

1. **文件不存在错误**
   - 检查输入文件路径是否正确
   - 确认文件在共享存储目录中

2. **GPU 资源不足**
   - 检查 GPU 可用性：`nvidia-smi`
   - 调整并发任务数量
   - 使用 CPU 模式（如果支持）

3. **模型下载失败**
   - 检查网络连接
   - 确认有足够的存储空间
   - 验证访问令牌和权限

4. **参数配置错误**
   - 参考各节点的参数说明
   - 检查参数类型和取值范围
   - 查看服务日志获取详细错误信息

### 调试建议

1. **查看服务日志**：`docker-compose logs [service_name]`
2. **检查工作流状态**：通过 API 查询工作流执行状态
3. **验证输入文件**：确保文件格式和内容正确
4. **测试单个节点**：单独运行有问题的节点进行调试
5. **监控资源使用**：检查 CPU、GPU、内存使用情况

## 性能优化建议

### 通用优化

1. **合理的任务顺序**：按照依赖关系安排任务执行顺序
2. **参数调优**：根据需求选择合适的模型和质量参数
3. **并发控制**：合理设置并发任务数量，避免资源竞争
4. **缓存利用**：利用已有的中间结果，避免重复计算

### 特定节点优化

1. **音频处理**：使用人声分离后的音频提高识别准确率
2. **模型选择**：根据精度要求选择合适的模型大小
3. **GPU 利用**：确保 GPU 锁有效配置，提高资源利用率
4. **文件格式**：选择高质量的输入格式，避免不必要的格式转换

## 版本兼容性

- **文档版本**：v1.0
- **支持的系统版本**：YiVideo v2.0+
- **最后更新时间**：2024年

---

*本文档会随系统更新而持续维护，如有疑问或建议，请提交 Issue 或 PR。*