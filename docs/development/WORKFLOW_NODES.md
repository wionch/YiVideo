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
- `video_path` (string, 必需): 视频文件路径
- `keyframe_sample_count` (int, 可选): 抽取帧数，默认 100

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
- `video_path` (string, 必需): 视频文件路径

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
- `video_path` (string, 必需): 视频文件路径
- `decode_processes` (int, 可选): 解码进程数，默认 10

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
- `audio_path` (string, 可选): 指定音频文件路径（优先级高于自动检测）
- `subtitle_path` (string, 可选): 指定字幕文件路径（优先级高于自动检测）
- `output_format` (string, 可选): 输出格式，默认 "wav"
- `sample_rate` (int, 可选): 采样率，默认 16000
- `channels` (int, 可选): 声道数，默认 1
- `min_segment_duration` (float, 可选): 最小片段时长，默认 1.0秒
- `max_segment_duration` (float, 可选): 最大片段时长，默认 30.0秒
- `group_by_speaker` (bool, 可选): 按说话人分组，默认 true
- `include_silence` (bool, 可选): 包含静音片段，默认 false
- `enable_concurrent` (bool, 可选): 启用并发分割，默认 true
- `max_workers` (int, 可选): 最大工作线程数，默认 8
- `concurrent_timeout` (int, 可选): 并发超时时间，默认 600秒

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
    "group_by_speaker": true,
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
- `audio_path` (string, 可选): 指定音频文件路径（自动检测优先）
- `model_size` (string, 可选): 模型大小，默认 "base"
  - 可选值：`tiny`, `base`, `small`, `medium`, `large-v3`, `large-v2`
- `language` (string, 可选): 指定语言代码，如 "zh", "en"（不指定则自动检测）
- `task` (string, 可选): 任务类型，默认 "transcribe"
  - 可选值：`transcribe`, `translate`
- `beam_size` (int, 可选): 束搜索大小，默认 5
- `vad_filter` (bool, 可选): 启用语音活动检测过滤，默认 true
- `word_timestamps` (bool, 可选): 启用词级时间戳，默认 true
- `condition_on_previous_text` (bool, 可选): 基于前文条件化，默认 true
- `temperature` (float, 可选): 采样温度，默认 0.0
- `compression_ratio_threshold` (float, 可选): 压缩比阈值，默认 2.4
- `logprob_threshold` (float, 可选): 对数概率阈值，默认 -1.0
- `no_speech_threshold` (float, 可选): 无语音阈值，默认 0.6

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

### 2. faster_whisper.generate_subtitle_files

基于转录数据和可选的说话人数据生成多种格式的字幕文件。

**功能描述**：将转录数据转换为标准字幕格式，支持 SRT、VTT、ASS 等格式，并可选择集成说话人信息。

**输入参数**：
- `segments_file` (string, 可选): 指定转录数据文件路径（自动检测优先）
- `diarization_file` (string, 可选): 指定说话人分离数据文件路径（可选）
- `output_formats` (list, 可选): 输出格式列表，默认 ["srt"]
  - 可选值：`"srt"`, `"vtt"`, `"ass"`, `"txt"`, `"json"`
- `max_chars_per_line` (int, 可选): 每行最大字符数，默认 42
- `max_lines_per_subtitle` (int, 可选): 每个字幕最大行数，默认 2
- `min_subtitle_duration` (float, 可选): 最小字幕时长，默认 1.0秒
- `max_subtitle_duration` (float, 可选): 最大字幕时长，默认 7.0秒
- `include_speaker_labels` (bool, 可选): 包含说话人标签，默认 true（如果提供说话人数据）
- `speaker_label_format` (string, 可选): 说话人标签格式，默认 "[SPEAKER_00]"
  - 可选值：`"[SPEAKER_00]"`, `"Speaker 1:"`, `"发言人A:"`

**前置依赖**：
- `faster_whisper.transcribe_audio` (必需)
- `pyannote_audio.diarize_speakers` (可选，用于说话人信息)

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
      "faster_whisper.generate_subtitle_files"
    ]
  },
  "faster_whisper.generate_subtitle_files": {
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
      "faster_whisper.generate_subtitle_files"
    ]
  },
  "faster_whisper.generate_subtitle_files": {
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

### 3. faster_whisper.correct_subtitles

使用 LLM 对字幕进行智能校正和优化。

**功能描述**：基于大语言模型对转录字幕进行语法纠错、标点优化、语义理解等智能处理。

**输入参数**：
- `subtitle_file` (string, 必需): 待校正的字幕文件路径
- `correction_model` (string, 可选): 校正模型，默认 "gemini"
  - 可选值：`"gemini"`, `"gpt4"`, `"claude"`
- `correction_type` (string, 可选): 校正类型，默认 "comprehensive"
  - 可选值：`"basic"`, `"comprehensive"`, `"proofread"`, `"localization"`
- `target_language` (string, 可选): 目标语言，默认 "zh"
- `preserve_timestamps` (bool, 可选): 保持时间戳不变，默认 true
- `batch_size` (int, 可选): 批处理大小，默认 10
- `api_key` (string, 可选): LLM API 密钥

**前置依赖**：
- `faster_whisper.generate_subtitle_files`

**输出格式**：
```json
{
  "corrected_subtitle_path": "/share/workflows/{workflow_id}/subtitles/video_corrected.srt",
  "correction_report": "/share/workflows/{workflow_id}/subtitles/correction_report.json",
  "original_segments": 125,
  "corrected_segments": 125,
  "corrections_count": 15,
  "correction_types": ["punctuation", "grammar", "spacing"],
  "processing_time": 25.3
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
      "faster_whisper.correct_subtitles"
    ]
  },
  "faster_whisper.correct_subtitles": {
    "correction_model": "gemini",
    "correction_type": "comprehensive",
    "target_language": "zh",
    "preserve_timestamps": true
  }
}
```

**依赖关系**：
- `faster_whisper.generate_subtitle_files`

**校正类型说明**：
- `basic`: 基础标点和空格校正
- `comprehensive`: 全面语法、语义、标点校正
- `proofread`: 专业校对级别
- `localization`: 本地化处理，包括文化适配

**注意事项**：
- 需要配置相应的 LLM API 密钥
- 处理时间取决于文本长度和模型响应速度
- 批处理可以优化 API 调用成本

---

## Audio Separator 服务节点

Audio Separator 服务提供基于 UVR-MDX 模型的专业音频分离功能，支持人声与伴奏的高质量分离。

### 1. audio_separator.separate_vocals

分离音频中的人声和背景音，支持多种模型和质量模式。

**功能描述**：使用 UVR-MDX 深度学习模型将音频分离为人声和各种乐器轨道，支持高质量分离和GPU加速。

**输入参数**：
- `audio_path` (string, 可选): 指定音频文件路径（自动检测优先）
- `audio_separator_config` (object, 可选): 分离配置对象
  - `quality_mode` (string): 质量模式，默认 "default"
    - 可选值：`"fast"`, `"default"`, `"high_quality"`
  - `model_type` (string): 模型类型，默认 "demucs"
    - 可选值：`"demucs"`, `"mdx"`, `"vr"`
  - `model_name` (string): 具体模型名称（可选，自动选择）
  - `use_vocal_optimization` (bool): 启用人声优化，默认 false
  - `vocal_optimization_level` (int): 人声优化级别，默认 0
  - `output_format` (string): 输出格式，默认 "flac"
  - `sample_rate` (int): 输出采样率，默认 44100
  - `bit_rate` (int): 比特率，默认 320
  - `normalize` (bool): 音量标准化，默认 true
  - `amp_factor` (float): 放大系数，默认 1.0

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
- `audio_path` (string, 可选): 指定音频文件路径（自动检测优先）
- `hf_token` (string, 必需): Hugging Face 访问令牌
- `num_speakers` (int, 可选): 说话人数量（不指定则自动检测）
- `min_duration_on` (float, 可选): 最小说话时长，默认 0.5秒
- `min_duration_off` (float, 可选): 最小静音时长，默认 0.3秒
- `overlap_ratio` (float, 可选): 重叠比例，默认 0.5
- `model_name` (string, 可选): 模型名称，默认 "pyannote/speaker-diarization-3.1"

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

### 2. pyannote_audio.get_speaker_segments

获取已完成的说话人分离结果，提供详细的分析数据。

**功能描述**：从已完成的说话人分离结果中提取详细信息，包括说话人统计、时间分布等。

**输入参数**：
- `diarization_file` (string, 必需): 说话人分离结果文件路径
- `analysis_level` (string, 可选): 分析级别，默认 "basic"
  - 可选值：`"basic"`, `"detailed"`, `"statistics"`
- `time_window` (float, 可选): 时间窗口大小（秒），默认 10.0
- `include_confidence` (bool, 可选): 包含置信度信息，默认 true

**前置依赖**：
- `pyannote_audio.diarize_speakers`

**输出格式**：
```json
{
  "speaker_segments": "/share/workflows/{workflow_id}/diarization/detailed_segments.json",
  "statistics": {
    "total_speakers": 2,
    "total_speech_duration": 280.5,
    "silence_duration": 45.2,
    "speaker_durations": {
      "SPEAKER_00": 165.3,
      "SPEAKER_01": 115.2
    },
    "speaker_percentages": {
      "SPEAKER_00": 58.9,
      "SPEAKER_01": 41.1
    },
    "average_segment_duration": 8.5,
    "segment_count": 33
  },
  "analysis_summary": {
    "dominant_speaker": "SPEAKER_00",
    "speaker_turns": 15,
    "overlap_instances": 2,
    "confidence_average": 0.92
  }
}
```

**使用示例**：
```json
{
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_audio",
      "pyannote_audio.diarize_speakers",
      "pyannote_audio.get_speaker_segments"
    ]
  },
  "pyannote_audio.get_speaker_segments": {
    "analysis_level": "detailed",
    "include_confidence": true,
    "time_window": 15.0
  }
}
```

**依赖关系**：
- `pyannote_audio.diarize_speakers`

**分析级别说明**：
- `basic`: 基础说话人段信息
- `detailed`: 详细的时间分析和统计
- `statistics`: 完整的统计分析报告

---

### 3. pyannote_audio.validate_diarization

验证说话人分离结果的质量和准确性。

**功能描述**：对说话人分离结果进行质量评估，包括置信度分析、异常检测等。

**输入参数**：
- `diarization_file` (string, 必需): 说话人分离结果文件路径
- `validation_criteria` (object, 可选): 验证标准
  - `min_confidence_threshold` (float): 最小置信度阈值，默认 0.8
  - `max_silence_gap` (float): 最大静音间隔，默认 5.0秒
  - `min_segment_duration` (float): 最小片段时长，默认 1.0秒
  - `check_speaker_consistency` (bool): 检查说话人一致性，默认 true

**前置依赖**：
- `pyannote_audio.diarize_speakers`

**输出格式**：
```json
{
  "validation_result": "/share/workflows/{workflow_id}/diarization/validation_report.json",
  "quality_score": 0.91,
  "validation_passed": true,
  "issues_found": [],
  "recommendations": [
    "说话人分离质量良好",
    "建议使用当前结果进行后续处理"
  ],
  "detailed_metrics": {
    "average_confidence": 0.92,
    "low_confidence_segments": 2,
    "suspicious_gaps": 0,
    "speaker_consistency_score": 0.95
  }
}
```

**使用示例**：
```json
{
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_audio",
      "pyannote_audio.diarize_speakers",
      "pyannote_audio.validate_diarization"
    ]
  },
  "pyannote_audio.validate_diarization": {
    "validation_criteria": {
      "min_confidence_threshold": 0.85,
      "max_silence_gap": 3.0,
      "check_speaker_consistency": true
    }
  }
}
```

**依赖关系**：
- `pyannote_audio.diarize_speakers`

**验证指标**：
- 置信度分布分析
- 异常短片段检测
- 不合理静音间隔检测
- 说话人一致性验证

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
- 无直接参数，从工作流上下文自动获取裁剪图像

**前置依赖**：
- `ffmpeg.crop_subtitle_images`

**输出格式**：
```json
{
  "stitched_image_path": "/share/workflows/{workflow_id}/ocr/stitched_subtitles.png",
  "image_count": 125,
  "stitching_method": "grid_layout",
  "output_dimensions": {
    "width": 1920,
    "height": 3000
  }
}
```

**使用示例**：
```json
{
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_keyframes",
      "paddleocr.detect_subtitle_area",
      "ffmpeg.crop_subtitle_images",
      "paddleocr.create_stitched_images"
    ]
  }
}
```

**依赖关系**：
- `ffmpeg.crop_subtitle_images`

**拼接特性**：
- 自动网格布局优化
- 保持图像清晰度
- 高效存储格式
- 支持大量图像拼接

---

### 3. paddleocr.perform_ocr

对拼接后的字幕图像进行文字识别。

**功能描述**：使用 PaddleOCR 模型对字幕图像进行高精度文字识别。

**输入参数**：
- `ocr_config` (object, 可选): OCR 配置
  - `lang` (string): 语言设置，默认 "ch"
    - 可选值：`"ch"`, `"en"`, `"chinese_cht"`, `"ko"`, `"ja"`
  - `use_angle_cls` (bool): 启用文字方向分类，默认 true
  - `use_gpu` (bool): 使用 GPU 加速，默认 true
  - `det_model_dir` (string): 检测模型路径（可选）
  - `rec_model_dir` (string): 识别模型路径（可选）
  - `cls_model_dir` (string): 分类模型路径（可选）

**前置依赖**：
- `paddleocr.create_stitched_images`

**输出格式**：
```json
{
  "ocr_results_path": "/share/workflows/{workflow_id}/ocr/ocr_results.json",
  "raw_text_path": "/share/workflows/{workflow_id}/ocr/raw_text.txt",
  "subtitles_extracted": 125,
  "confidence_average": 0.92,
  "processing_time": 45.2,
  "languages_detected": ["ch"]
}
```

**使用示例**：
```json
{
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_keyframes",
      "paddleocr.detect_subtitle_area",
      "ffmpeg.crop_subtitle_images",
      "paddleocr.create_stitched_images",
      "paddleocr.perform_ocr"
    ]
  },
  "paddleocr.perform_ocr": {
    "ocr_config": {
      "lang": "ch",
      "use_angle_cls": true,
      "use_gpu": true
    }
  }
}
```

**依赖关系**：
- `paddleocr.create_stitched_images`

**OCR 特性**：
- 支持多语言识别
- 高精度文字检测
- GPU 加速处理
- 置信度评估
- 自动文字方向校正

---

### 4. paddleocr.postprocess_and_finalize

后处理 OCR 结果并生成最终的字幕文件。

**功能描述**：对 OCR 识别结果进行智能后处理，包括时间对齐、文本校正、格式化等。

**输入参数**：
- `postprocess_config` (object, 可选): 后处理配置
  - `time_alignment_method` (string): 时间对齐方法，默认 "linear"
    - 可选值：`"linear"`, `"adaptive"`, `"manual"`
  - `text_correction` (bool): 启用文本校正，默认 true
  - `output_format` (string): 输出格式，默认 "srt"
    - 可选值：`"srt"`, `"vtt"`, `"ass"`, `"txt"`
  - `min_confidence_threshold` (float): 最小置信度阈值，默认 0.8
  - `merge_similar_subtitles` (bool): 合并相似字幕，默认 true

**前置依赖**：
- `paddleocr.perform_ocr`

**输出格式**：
```json
{
  "final_subtitle_path": "/share/workflows/{workflow_id}/ocr/final_subtitles.srt",
  "corrected_text_path": "/share/workflows/{workflow_id}/ocr/corrected_text.txt",
  "processing_summary": {
    "original_subtitles": 125,
    "final_subtitles": 118,
    "merged_subtitles": 7,
    "low_confidence_filtered": 5,
    "corrections_made": 12
  },
  "quality_metrics": {
    "average_confidence": 0.94,
    "text_accuracy": 0.97,
    "timing_accuracy": 0.92
  }
}
```

**使用示例**：
```json
{
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
  "paddleocr.postprocess_and_finalize": {
    "postprocess_config": {
      "time_alignment_method": "adaptive",
      "text_correction": true,
      "output_format": "srt",
      "min_confidence_threshold": 0.85
    }
  }
}
```

**依赖关系**：
- `paddleocr.perform_ocr`

**后处理功能**：
- 智能时间轴对齐
- OCR 错误校正
- 重复字幕合并
- 低置信度内容过滤
- 字幕格式标准化
- 质量评估和统计

---

## IndexTTS 服务节点

IndexTTS 服务提供基于 IndexTTS2 模型的高质量语音合成功能，支持情感化语音生成和音色克隆。

### 1. indextts.generate_speech

使用参考音频生成具有相同音色的语音。

**功能描述**：基于 IndexTTS2 模型，使用参考音频的音色特征合成新的语音内容，支持情感表达。

**输入参数**：
- `text` (string, 必需): 要合成的文本内容
- `output_path` (string, 必需): 输出音频文件路径
- `spk_audio_prompt` (string, 必需): 说话人参考音频路径
- `emo_audio_prompt` (string, 可选): 情感参考音频路径
- `emotion_alpha` (float, 可选): 情感强度系数，默认 1.0
- `emotion_vector` (array, 可选): 情感向量（高级参数）
- `emotion_text` (string, 可选): 情感描述文本
- `use_emo_text` (bool, 可选): 使用情感文本，默认 false
- `use_random` (bool, 可选): 随机情感变化，默认 false
- `speed` (float, 可选): 语速控制，默认 1.0
- `max_text_tokens_per_segment` (int, 可选): 每段最大token数，默认 120
- `verbose` (bool, 可选): 详细输出，默认 false

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

### 2. indextts.list_voice_presets

列出可用的语音预设和音色选项。

**功能描述**：获取系统中可用的语音预设、音色模型和参考音频列表。

**输入参数**：
- `preset_type` (string, 可选): 预设类型过滤
  - 可选值：`"all"`, `"custom"`, `"builtin"`
- `include_details` (bool, 可选): 包含详细信息，默认 false

**输出格式**：
```json
{
  "presets": [
    {
      "name": "female_news",
      "display_name": "新闻女声",
      "language": "zh",
      "gender": "female",
      "description": "清晰专业的新闻播报音色",
      "reference_audio": "/share/presets/female_news.wav",
      "emotion_samples": [
        "/share/presets/female_news_neutral.wav",
        "/share/presets/female_news_happy.wav"
      ]
    }
  ],
  "total_count": 5,
  "supported_languages": ["zh", "en"],
  "preset_categories": ["news", "storytelling", "conversation"]
}
```

**使用示例**：
```json
{
  "workflow_config": {
    "workflow_chain": ["indextts.list_voice_presets"]
  },
  "indextts.list_voice_presets": {
    "preset_type": "all",
    "include_details": true
  }
}
```

**依赖关系**：无

---

### 3. indextts.get_model_info

获取 IndexTTS 模型的详细信息和技术规格。

**功能描述**：返回当前加载的 IndexTTS 模型的技术信息、配置参数和支持的功能。

**输入参数**：
- `include_performance_info` (bool, 可选): 包含性能信息，默认 false

**输出格式**：
```json
{
  "model_name": "IndexTTS2",
  "version": "2.0.1",
  "sample_rate": 22050,
  "channels": 1,
  "supported_languages": ["zh", "en", "ja", "ko"],
  "max_text_length": 1000,
  "model_size": "2.3GB",
  "capabilities": {
    "voice_cloning": true,
    "emotion_control": true,
    "speed_control": true,
    "multi_language": true
  },
  "performance_info": {
    "gpu_memory_required": "4GB",
    "average_generation_time": "0.8x realtime",
    "supported_batch_sizes": [1, 2, 4, 8]
  },
  "recommendations": {
    "optimal_reference_duration": "3-10 seconds",
    "best_audio_formats": ["wav", "flac"],
    "recommended_sample_rate": 22050
  }
}
```

**使用示例**：
```json
{
  "workflow_config": {
    "workflow_chain": ["indextts.get_model_info"]
  },
  "indextts.get_model_info": {
    "include_performance_info": true
  }
}
```

**依赖关系**：无

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
    "spk_audio_prompt": "${{ stages.ffmpeg.split_audio_segments.output.audio_segments_dir }}/speaker_00_segment_001.wav"
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