# Faster Whisper Service 语音识别服务文档

> 🧭 **导航**: [YiVideo项目根](/mnt/d/WSL2/docker/YiVideo/CLAUDE.md) > [Workers目录](/mnt/d/WSL2/docker/YiVideo/services/workers/) > **faster_whisper_service**

## 服务概述

Faster Whisper Service是基于faster-whisper高版本的语音识别(ASR)服务，提供GPU加速的实时语音转文字功能。该服务支持词级时间戳、说话人分离集成和字幕校正优化。

## 核心功能

- **语音识别**: 将音频转换为文字
- **词级时间戳**: 提供精确的词级别时间戳
- **GPU加速**: 使用faster-whisper实现高速推理
- **字幕生成**: 支持SRT、VTT等字幕格式
- **说话人分离**: 与pyannote_audio_service集成
- **字幕校正**: 使用AI进行字幕优化

## 目录结构

```
services/workers/faster_whisper_service/
├── app/
│   ├── celery_app.py           # Celery应用配置
│   ├── faster_whisper_infer.py # Whisper推理引擎
│   ├── model_manager.py        # 模型管理器
│   ├── speaker_word_matcher.py # 说话人词匹配器
│   ├── subtitle_merger.py      # 字幕合并器
│   ├── tts_merger.py          # TTS合并器
│   └── tasks.py               # Celery任务定义
├── Dockerfile
└── requirements.txt
```

## 核心文件

### tasks.py
- **主要任务**:
  - `speech_recognition()`: 语音识别任务
  - 使用`@gpu_lock`装饰器保护GPU资源
  - 支持词级时间戳和说话人分离
  - 集成字幕校正和合并功能

### faster_whisper_infer.py
- **功能**: Whisper推理引擎
- **特性**:
  - 模型加载和管理
  - GPU内存优化
  - 批处理支持

### model_manager.py
- **功能**: 模型生命周期管理
- **特性**:
  - 模型下载和缓存
  - 模型版本管理
  - 内存管理

### subtitle_merger.py
- **功能**: 字幕合并和优化
- **类**:
  - `SubtitleMerger`: 通用字幕合并
  - `WordLevelMerger`: 词级合并器
  - `create_subtitle_merger()`: 创建合并器工厂
  - `validate_speaker_segments()`: 验证说话人片段

## 依赖

```
celery==5.3.4
redis==5.0.1
faster-whisper>=1.1.1
torch>=2.0.0
numpy>=1.24.0
pyyaml>=6.0
pydantic
librosa
psutil
aiohttp
```

## GPU要求

- **必需**: 支持CUDA的GPU
- **推荐**: NVIDIA RTX系列GPU，显存≥8GB
- **CUDA版本**: 11.x或更高

## 任务接口

### 标准任务接口
```python
@celery_app.task(bind=True)
@gpu_lock(timeout=1800, poll_interval=0.5)
def speech_recognition(self, context):
    """
    语音识别任务

    Args:
        context: 工作流上下文，包含:
            - audio_path: 音频文件路径
            - language: 语言代码
            - model_size: 模型大小
            - compute_type: 计算类型

    Returns:
        更新后的context
    """
    pass
```

## 配置参数

- **模型大小**: tiny, base, small, medium, large
- **计算类型**: float16, int8, int8_float16
- **批处理大小**: 可配置
- **设备**: cuda:0, cpu

## 共享存储

- **输入**: `/share/workflows/{workflow_id}/audio/`
- **输出**: `/share/workflows/{workflow_id}/subtitles/`
- **中间文件**: `/share/workflows/{workflow_id}/temp/`

## 监控

- **日志**: 使用`services.common.logger`
- **状态**: 通过`state_manager`更新
- **GPU监控**: 集成GPU锁系统

## 集成服务

- **说话人分离**: `pyannote_audio_service`
- **字幕优化**: `services.common.subtitle.*`
- **状态管理**: `services.common.state_manager`
- **GPU锁**: `services.common.locks`

## 性能优化

1. **模型量化**: 支持int8量化减少显存占用
2. **批处理**: 支持批量推理提高吞吐量
3. **GPU内存管理**: 自动清理和监控
4. **模型缓存**: 避免重复加载模型

## 故障排除

### 常见问题

1. **CUDA内存不足**
   - 减小模型大小
   - 启用量化
   - 减少批处理大小

2. **模型加载失败**
   - 检查网络连接
   - 验证HuggingFace token
   - 检查磁盘空间

3. **推理速度慢**
   - 检查GPU利用率
   - 调整批处理大小
   - 优化模型参数

## 相关文档

- [faster-whisper官方文档](https://github.com/guillaumekln/faster-whisper)
- [GPU锁文档](/mnt/d/WSL2/docker/YiVideo/services/common/CLAUDE.md#gpu锁系统)
- [状态管理文档](/mnt/d/WSL2/docker/YiVideo/services/common/CLAUDE.md#状态管理)
