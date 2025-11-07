# FFmpeg Service 视频处理服务文档

> 🧭 **导航**: [YiVideo项目根](/mnt/d/WSL2/docker/YiVideo/CLAUDE.md) > [Workers目录](/mnt/d/WSL2/docker/YiVideo/services/workers/) > **ffmpeg_service**

## 服务概述

FFmpeg Service是视频和音频处理的核心服务，基于FFmpeg提供视频解码、音频提取、格式转换等基础能力。该服务是其他AI服务的前置步骤，负责媒体文件的预处理。

## 核心功能

- **视频解码**: 提取视频帧和元数据
- **音频提取**: 从视频中提取音频轨道
- **格式转换**: 音频格式转换和重采样
- **音频分割**: 按时间或静音分割音频
- **字幕解析**: 解析和提取字幕文件

## 目录结构

```
services/workers/ffmpeg_service/
├── app/
│   ├── celery_app.py                 # Celery应用配置
│   ├── executor_decode_video.py      # 视频解码执行器
│   ├── modules/
│   │   ├── audio_splitter.py        # 音频分割器
│   │   ├── subtitle_parser.py       # 字幕解析器
│   │   └── video_decoder.py         # 视频解码器
│   └── tasks.py                      # Celery任务定义
├── Dockerfile
└── requirements.txt
```

## 核心文件

### tasks.py
- **主要任务**:
  - `extract_audio()`: 音频提取
  - `decode_video()`: 视频解码
  - `split_audio()`: 音频分割

### executor_decode_video.py
- **功能**: 视频解码执行器
- **特性**:
  - 帧提取
  - 元数据获取
  - 格式检测

### modules/
**audio_splitter.py**: 音频分割器
- 按时间分割
- 按静音检测分割
- 支持多种格式

**video_decoder.py**: 视频解码器
- 帧提取
- 关键帧检测
- 帧率转换

**subtitle_parser.py**: 字幕解析器
- SRT解析
- VTT解析
- 字幕提取

## 依赖

```
celery
redis
ffmpeg-python
numpy
pydantic
```

## 任务接口

### 标准任务接口
```python
@celery_app.task(bind=True)
def extract_audio(self, context):
    """
    音频提取任务

    Args:
        context: 工作流上下文，包含:
            - video_path: 视频文件路径
            - audio_format: 输出音频格式
            - sample_rate: 采样率

    Returns:
        更新后的context，包含audio_path
    """
    pass
```

## 共享存储

- **输入**: `/share/workflows/{workflow_id}/videos/`
- **输出**: `/share/workflows/{workflow_id}/audio/`
- **中间文件**: `/share/workflows/{workflow_id}/temp/`

## 集成服务

- **语音识别**: `faster_whisper_service`
- **说话人分离**: `pyannote_audio_service`
- **OCR服务**: `paddleocr_service`

## 性能优化

1. **多线程**: 使用多线程提高处理速度
2. **内存映射**: 大文件使用内存映射
3. **缓存**: 缓存解码结果

## 故障排除

### 常见问题

1. **FFmpeg未安装**
   - 检查Dockerfile
   - 验证系统依赖

2. **编码失败**
   - 检查输入文件格式
   - 验证输出路径权限

## 相关文档

- [FFmpeg官方文档](https://ffmpeg.org/documentation.html)
