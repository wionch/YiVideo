# WhisperX 工作流配置指南

## 概述

本文档介绍WhisperX功能拆分后的工作流配置方法，包括新的模块化工作流配置和向后兼容性说明。

## 🎯 功能拆分概述

### 拆分前（原有架构）
```
whisperx.generate_subtitles (单一任务)
├── 语音转录
├── 说话人分离（可选）
└── 字幕文件生成
```

### 拆分后（新架构）
```
whisperx.transcribe_audio     → 语音转录
whisperx.diarize_speakers     → 说话人分离（可选）
whisperx.generate_subtitle_files → 字幕文件生成
```

## 📋 工作流配置示例

### 1. 基础字幕工作流（推荐用于大多数场景）

```yaml
basic_subtitle_workflow:
  description: "基础字幕工作流 - 仅语音转录"
  workflow_chain:
    - "ffmpeg.extract_audio"
    - "whisperx.transcribe_audio"
    - "whisperx.generate_subtitle_files"

  params:
    video_path: "input.mp4"
    whisperx_config:
      enable_diarization: false
      enable_word_timestamps: true
```

**使用场景：**
- 单人说话视频
- 快速转录需求
- 成本敏感场景

**输出文件：**
- `basic.srt` - 基础SRT字幕
- `word_timestamps.json` - 词级时间戳（可选）

### 2. 完整字幕工作流（推荐用于多人对话）

```yaml
full_subtitle_workflow:
  description: "完整字幕工作流 - 转录 + 说话人分离"
  workflow_chain:
    - "ffmpeg.extract_audio"
    - "audio_separator.separate_vocals"
    - "whisperx.transcribe_audio"
    - "whisperx.diarize_speakers"
    - "whisperx.generate_subtitle_files"

  params:
    video_path: "meeting.mp4"
    whisperx_config:
      enable_diarization: true
      show_speaker_labels: true
```

**使用场景：**
- 会议记录
- 访谈节目
- 多人对话视频

**输出文件：**
- `basic.srt` - 基础SRT字幕
- `with_speakers.srt` - 带说话人的SRT字幕
- `with_speakers.json` - 说话人信息JSON
- `word_timestamps.json` - 词级时间戳

### 3. 人声优化工作流（推荐用于噪音环境）

```yaml
vocal_optimized_workflow:
  description: "人声优化工作流 - 先分离人声再转录"
  workflow_chain:
    - "ffmpeg.extract_audio"
    - "audio_separator.separate_vocals"
    - "whisperx.transcribe_audio"
    - "whisperx.generate_subtitle_files"

  params:
    video_path: "noisy_video.mp4"
    audio_separator_config:
      model: "UVR-MDX-NET-Inst_HQ_4"
```

**使用场景：**
- 背景噪音较大的视频
- 音乐与语音混合的音频
- 低质量音频源

## 🔧 任务节点详解

### whisperx.transcribe_audio

**功能：** 语音转录，将音频转换为文本

**输入：**
- 音频文件路径（来自ffmpeg或audio_separator）

**输出：**
```json
{
  "segments": [...],
  "audio_path": "/path/to/audio.wav",
  "audio_duration": 392.05,
  "language": "zh",
  "transcribe_duration": 76.20,
  "transcribe_data_file": "/share/workflows/xxx/transcribe_data.json"
}
```

**关键配置：**
- `enable_word_timestamps`: 是否生成词级时间戳
- `model_name`: Whisper模型选择
- `device`: CUDA/CPU设备选择

### whisperx.diarize_speakers

**功能：** 说话人分离，识别不同的说话人

**输入：**
- 转录结果（来自whisperx.transcribe_audio）

**输出：**
```json
{
  "original_segments": [...],
  "speaker_enhanced_segments": [...],
  "detected_speakers": ["SPEAKER_00", "SPEAKER_01"],
  "speaker_statistics": {...},
  "diarization_data_file": "/share/workflows/xxx/diarization_data.json"
}
```

**关键配置：**
- `enable_diarization`: 是否启用说话人分离
- GPU锁自动管理（本地CUDA模式）

### whisperx.generate_subtitle_files

**功能：** 生成各种格式的字幕文件

**输入：**
- 转录结果（必需）
- 说话人分离结果（可选）

**输出：**
```json
{
  "subtitle_path": "/share/workflows/xxx/subtitles/basic.srt",
  "speaker_srt_path": "/share/workflows/xxx/subtitles/with_speakers.srt",
  "speaker_json_path": "/share/workflows/xxx/subtitles/with_speakers.json",
  "word_timestamps_json_path": "/share/workflows/xxx/subtitles/word_timestamps.json",
  "metadata": {...}
}
```

**智能特性：**
- 自动检测可用输入数据
- 根据输入决定生成哪些文件
- 支持多种字幕格式

## 🔄 数据流图

```
视频文件 (input.mp4)
    ↓
ffmpeg.extract_audio
    ↓
音频文件 (audio.wav)
    ↓
audio_separator.separate_vocals (可选)
    ↓
人声音频 (vocal.wav)
    ↓
whisperx.transcribe_audio
    ↓
转录结果 (segments + 词级时间戳)
    ↓
whisperx.diarize_speakers (可选)
    ↓
说话人增强结果 (speaker_enhanced_segments)
    ↓
whisperx.generate_subtitle_files
    ↓
字幕文件 (.srt, .json)
```

## ⚙️ 配置参数详解

### WhisperX 核心配置

```yaml
whisperx_config:
  # 基础ASR配置
  model_name: "Systran/faster-whisper-large-v3"  # 模型选择
  language: null                                    # 语言代码，null=自动检测
  device: "cuda"                                    # 推理设备
  compute_type: "float16"                           # 计算精度

  # 功能开关
  enable_word_timestamps: true    # 词级时间戳
  enable_diarization: false       # 说话人分离
  show_speaker_labels: true       # 显示说话人标签

  # 性能参数
  batch_size: 4                   # 批处理大小
```

### 模型选择指南

| 模型名称 | 速度 | 准确性 | 显存需求 | 适用场景 |
|---------|------|--------|----------|----------|
| Systran/faster-whisper-large-v3 | 中等 | 高 | ~2GB | 通用场景（推荐） |
| Systran/faster-whisper-medium | 快 | 中等 | ~1GB | 快速转录 |
| Systran/faster-whisper-base | 很快 | 低 | ~0.5GB | 实时转录 |

### 设备选择指南

```yaml
# GPU加速（推荐）
device: "cuda"
compute_type: "float16"  # 节省显存

# CPU模式（兼容性）
device: "cpu"
compute_type: "float32"  # CPU精度
```

## 🚀 性能优化建议

### 1. 工作流选择优化

**根据场景选择合适的工作流：**
- 单人说话 → `basic_subtitle_workflow`
- 多人对话 → `full_subtitle_workflow`
- 噪音环境 → `vocal_optimized_workflow`
- 快速转录 → `transcribe_only_workflow`

### 2. 参数调优

**提高速度：**
```yaml
whisperx_config:
  enable_word_timestamps: false    # 禁用词级时间戳
  enable_diarization: false         # 禁用说话人分离
  model_name: "medium"              # 使用中等模型
```

**提高准确性：**
```yaml
whisperx_config:
  enable_word_timestamps: true     # 启用词级时间戳
  enable_diarization: true          # 启用说话人分离
  model_name: "large-v3"            # 使用大型模型
```

### 3. 资源管理

**GPU显存优化：**
```yaml
whisperx_config:
  compute_type: "float16"          # 使用半精度
  batch_size: 2                     # 减少批处理大小
```

**并发处理：**
- 每个任务节点独立排队，支持并发执行
- GPU锁机制确保资源安全访问

## 🔄 向后兼容性

### 现有系统无需修改

原有的`whisperx.generate_subtitles`任务完全保留：

```yaml
# 原有工作流配置仍然有效
legacy_workflow:
  workflow_chain:
    - "ffmpeg.extract_audio"
    - "whisperx.generate_subtitles"  # 原有任务

  params:
    # 原有配置方式保持不变
    whisperx_config: {...}
```

### 迁移指南

**从单一任务迁移到模块化工作流：**

1. **评估当前需求**
   - 是否需要说话人分离？
   - 是否需要词级时间戳？
   - 性能要求如何？

2. **选择合适的工作流**
   - 参考[工作流选择建议](#工作流选择建议)

3. **更新配置**
   - 替换`whisperx.generate_subtitles`为新的工作流链
   - 调整配置参数

4. **测试验证**
   - 使用相同的输入文件测试
   - 对比输出结果质量

## 🐛 故障排除

### 常见问题

**1. 任务失败：无法获取音频文件路径**
- 确认前置任务（ffmpeg.extract_audio）已成功完成
- 检查音频文件是否存在于指定路径

**2. 说话人分离失败**
- 检查`enable_diarization`配置
- 确认GPU资源充足（本地模式）
- 验证网络连接（付费模式）

**3. 字幕文件生成失败**
- 确认转录任务已成功完成
- 检查输出目录权限
- 验证磁盘空间充足

### 调试技巧

**启用详细日志：**
```yaml
logging:
  level: "DEBUG"
  services:
    whisperx_service: "DEBUG"
```

**检查任务状态：**
```bash
# 查看工作流状态
curl http://localhost:8788/api/v1/workflows/status/{workflow_id}

# 查看GPU锁状态
curl http://localhost:8788/api/v1/monitoring/gpu-lock/health
```

## 📈 监控和统计

### 任务执行统计

每个任务节点都会生成详细的统计信息：

```json
{
  "statistics": {
    "total_segments": 219,
    "total_words": 3542,
    "transcribe_duration": 76.20,
    "average_segment_duration": 1.79,
    "processing_speed": 5.14  // 音频时长/处理时长
  }
}
```

### GPU锁监控

```bash
# 查看GPU锁统计
curl http://localhost:8788/api/v1/monitoring/statistics

# 查看任务心跳状态
curl http://localhost:8788/api/v1/monitoring/heartbeat/all
```

## 📚 参考资源

- [WhisperX完整指南](../whisperx/WHISPERX_COMPLETE_GUIDE.md)
- [GPU锁系统指南](GPU_LOCK_COMPLETE_GUIDE.md)
- [API文档](../api/API_REFERENCE.md)
- [工作流配置示例](../../config/examples/workflow_examples.yml)

## 🔗 相关链接

- [WhisperX官方文档](https://github.com/m-bain/whisperX)
- [faster-whisper文档](https://github.com/guillaumekln/faster-whisper)
- [UVR人声分离](https://github.com/Anjok07/ultimatevocalremovergui)