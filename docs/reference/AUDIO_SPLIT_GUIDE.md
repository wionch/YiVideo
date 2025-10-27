# FFmpeg Service 音频分割功能

## 功能概述

音频分割功能是 ffmpeg_service 新增的核心功能，能够根据字幕文件中的时间戳数据，使用 ffmpeg 循环截取音频中对应时间区间的音频段，为后续语音生成提供数据参考和参考音。

## 主要特性

### 1. 智能文件选择
- **音频源选择**：优先选择人声音频（audio_separator），回退到默认音频（ffmpeg）
- **字幕文件选择**：支持多种格式（SRT、JSON），自动识别优先级
- **参数模式**：支持单步测试时直接传入文件路径

### 2. 多格式支持
- **音频格式**：WAV、FLAC、MP3、AAC、M4A
- **字幕格式**：SRT、带说话人信息的SRT、JSON
- **时间戳精度**：毫秒级精度分割

### 3. 按说话人分组
- **自动分组**：根据字幕中的说话人信息自动分组
- **目录结构**：按说话人创建子目录存储
- **统计信息**：详细的说话人统计报告

### 4. 完善的错误处理
- **文件验证**：输入文件存在性和格式验证
- **超时控制**：ffmpeg命令执行超时保护
- **容错机制**：单个片段失败不影响整体处理

## 配置说明

### config.yml 配置项

```yaml
ffmpeg_service:
  # 音频分割配置
  split_audio:
    output_format: "wav"          # 输出音频格式
    sample_rate: 16000            # 采样率
    channels: 1                   # 声道数
    min_segment_duration: 1.0     # 最小片段时长（秒）
    max_segment_duration: 30.0    # 最大片段时长（秒）
    group_by_speaker: true        # 是否按说话人分组
    include_silence: false        # 是否包含静音段
    output_dir: "/share/workflows/audio_segments"
    split_timeout: 300            # ffmpeg超时时间（秒）

  # 字幕文件配置
  subtitle:
    priority_order: ["speaker_srt_path", "subtitle_path", "speaker_json_path"]
    auto_detect_format: true
    timestamp_tolerance: 0.1

  # 音频源配置
  audio_source:
    priority_order: ["vocal_audio", "audio_path"]
    validate_format: true
    supported_formats: ["wav", "flac", "mp3", "aac", "m4a", "ogg", "opus"]
```

## 使用方法

### 1. 工作流集成

在完整的工作流中使用音频分割功能：

```python
workflow_config = {
    "workflow_chain": [
        "ffmpeg.extract_audio",
        "audio_separator.separate_vocals",
        "faster_whisper.generate_subtitles",
        "pyannote_audio.diarize_speakers",
        "ffmpeg.split_audio_segments"  # 音频分割节点
    ]
}
```

### 2. API调用

```bash
curl --request POST \
  --url http://localhost:8788/v1/workflows \
  --header 'content-type: application/json' \
  --data '{
  "video_path": "/app/videos/example.mp4",
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_audio",
      "faster_whisper.generate_subtitles",
      "ffmpeg.split_audio_segments"
    ]
  }
}'
```

### 3. 单步测试

直接调用音频分割任务：

```bash
curl --request POST \
  --url http://localhost:8788/v1/workflows \
  --header 'content-type: application/json' \
  --data '{
  "audio_path": "/app/audio/input.wav",
  "subtitle_path": "/app/subtitles/input.srt",
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.split_audio_segments"
    ]
  }
}'
```

## 输出结构

### 目录结构

```
/share/workflows/{workflow_id}/audio_segments/
├── segments/                    # 普通音频片段
│   ├── segment_001.wav
│   ├── segment_002.wav
│   └── ...
├── by_speaker/                  # 按说话人分组
│   ├── SPEAKER_00/
│   │   ├── segment_003_SPEAKER_00.wav
│   │   └── ...
│   ├── SPEAKER_01/
│   │   ├── segment_005_SPEAKER_01.wav
│   │   └── ...
│   └── ...
└── split_info.json             # 分割信息元数据
```

### 输出数据格式

任务执行完成后返回的数据结构：

```json
{
  "audio_segments_dir": "/share/workflows/abc123/audio_segments",
  "audio_source": "人声音频 (audio_separator)",
  "subtitle_source": "带说话人信息SRT",
  "total_segments": 150,
  "successful_segments": 148,
  "failed_segments": 2,
  "total_duration": 392.05,
  "processing_time": 45.67,
  "audio_format": "wav",
  "sample_rate": 16000,
  "channels": 1,
  "split_info_file": "/share/workflows/abc123/audio_segments/split_info.json",
  "segments_count": 148,
  "speaker_groups": {
    "SPEAKER_00": {
      "count": 89,
      "duration": 245.3,
      "files": [...]
    },
    "SPEAKER_01": {
      "count": 59,
      "duration": 146.75,
      "files": [...]
    }
  }
}
```

### 分割信息文件 (split_info.json)

```json
{
  "metadata": {
    "total_segments": 148,
    "successful_segments": 148,
    "failed_segments": 0,
    "success_rate": 1.0,
    "total_duration": 392.05,
    "processing_time": 45.67,
    "processing_speed": 8.58,
    "audio_format": "wav",
    "sample_rate": 16000,
    "channels": 1,
    "created_at": 1678901234.567
  },
  "segments": [
    {
      "id": 1,
      "start_time": 1.0,
      "end_time": 3.5,
      "duration": 2.5,
      "text": "Hello, this is the first subtitle.",
      "speaker": "SPEAKER_00",
      "file_path": "/share/workflows/abc123/audio_segments/by_speaker/SPEAKER_00/segment_001_SPEAKER_00.wav",
      "file_size": 40012
    }
  ],
  "speaker_groups": {
    "SPEAKER_00": {
      "count": 89,
      "duration": 245.3,
      "files": [...]
    }
  }
}
```

## 性能优化

### 1. 处理速度
- **并发处理**：支持多进程音频分割
- **内存管理**：优化大文件的内存使用
- **GPU加速**：利用ffmpeg硬件加速

### 2. 存储优化
- **格式选择**：WAV无损质量，FLAC压缩，MP3小文件
- **采样率优化**：16kHz适合语音处理，保持质量
- **文件命名**：智能命名避免冲突

### 3. 错误恢复
- **超时保护**：防止ffmpeg进程卡死
- **重试机制**：失败片段自动重试
- **部分成功**：单个失败不影响整体

## 故障排除

### 常见问题

1. **ffmpeg命令未找到**
   ```
   解决方案：确保ffmpeg已安装并在PATH中
   ```

2. **音频文件格式不支持**
   ```
   解决方案：检查supported_formats配置，支持更多格式
   ```

3. **字幕文件解析失败**
   ```
   解决方案：检查字幕文件编码和格式，使用UTF-8编码
   ```

4. **输出目录权限不足**
   ```
   解决方案：确保/share目录有写权限
   ```

### 调试方法

1. **查看日志**
   ```bash
   docker-compose logs -f ffmpeg_service
   ```

2. **检查配置**
   ```python
   from services.common.config_loader import CONFIG
   ffmpeg_config = CONFIG.get('ffmpeg_service', {})
   print(ffmpeg_config)
   ```

3. **测试字幕解析**
   ```python
   from modules.subtitle_parser import parse_subtitle_segments
   segments = parse_subtitle_segments("test.srt")
   print(f"解析到 {len(segments)} 个片段")
   ```

## 扩展开发

### 1. 添加新的字幕格式支持

在 `modules/subtitle_parser.py` 中添加新的解析方法：

```python
@staticmethod
def parse_new_format(file_path: str) -> List[SubtitleSegment]:
    """解析新格式的字幕文件"""
    # 实现解析逻辑
    pass
```

### 2. 添加新的音频格式支持

在 `modules/audio_splitter.py` 中更新编解码器映射：

```python
def _get_audio_codec(self) -> str:
    codec_map = {
        "wav": "pcm_s16le",
        "new_format": "new_codec",  # 添加新格式
    }
    return codec_map.get(self.output_format, "pcm_s16le")
```

### 3. 自定义处理逻辑

继承AudioSplitter类并重写处理方法：

```python
class CustomAudioSplitter(AudioSplitter):
    def _extract_segment(self, input_audio, segment, output_file):
        # 自定义分割逻辑
        pass
```

## 版本信息

- **当前版本**: 1.0.0
- **最后更新**: 2025-10-11
- **兼容性**: YiVideo v2.0+
- **依赖**: FFmpeg 4.0+, Python 3.8+