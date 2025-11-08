# Audio Separator Service 音频分离服务文档

> 🧭 **导航**: [YiVideo项目根](/mnt/d/WSL2/docker/YiVideo/CLAUDE.md) > [Workers目录](/mnt/d/WSL2/docker/YiVideo/services/workers/) > **audio_separator_service**

## 服务概述

Audio Separator Service提供人声和背景音乐分离功能，能够将混合音频分离成人声轨道和伴奏轨道。该服务对于音乐处理和声音增强非常有用。

## 核心功能

- **人声分离**: 分离人声和伴奏
- **多轨道分离**: 支持多轨道音频分离
- **质量优化**: 提供多种分离质量选项
- **格式支持**: 支持多种音频格式

## 目录结构

```
services/workers/audio_separator_service/
├── app/
│   ├── celery_app.py                # Celery应用配置
│   ├── audio_separator_infer.py     # 分离推理引擎
│   ├── config.py                    # 配置管理
│   ├── model_manager.py             # 模型管理器
│   └── tasks.py                     # Celery任务定义
├── audio_separator_standalone.py    # 独立运行脚本
├── Dockerfile
└── requirements.txt
```

## 核心文件

### tasks.py
- **主要任务**:
  - `separate_audio()`: 音频分离任务
  - 使用`@gpu_lock`装饰器

### audio_separator_infer.py
- **功能**: 音频分离推理引擎
- **模型**: 基于深度学习的音频分离模型

### model_manager.py
- **功能**: 模型下载和管理
- **特性**:
  - 自动下载预训练模型
  - 模型版本管理
  - 内存优化

## 依赖

```
celery
redis
librosa
soundfile
numpy
pydantic
# 音频分离模型依赖
```

## GPU要求

- **推荐**: 支持CUDA的GPU
- **显存**: ≥4GB

## 任务接口

### 标准任务接口
```python
@celery_app.task(bind=True)
@gpu_lock(timeout=1800, poll_interval=0.5)
def separate_audio(self, context):
    """
    音频分离任务

    Args:
        context: 工作流上下文，包含:
            - audio_path: 音频文件路径
            - quality: 分离质量 (high/medium/low)

    Returns:
        更新后的context，包含分离后的轨道
    """
    pass
```

## 输出格式

```json
{
  "separated_tracks": {
    "vocals": "/path/to/vocals.wav",
    "accompaniment": "/path/to/accompaniment.wav"
  }
}
```

## 共享存储

- **输入**: `/share/workflows/{workflow_id}/audio/`
- **输出**: `/share/workflows/{workflow_id}/separated/`
- **中间文件**: `/share/workflows/{workflow_id}/temp/`

## 集成服务

- **状态管理**: `services.common.state_manager`
- **GPU锁**: `services.common.locks`
