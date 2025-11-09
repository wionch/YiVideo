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
  - `separate_vocals()`: **核心任务**。从音频中分离出人声和背景音。该任务使用`@gpu_lock`装饰器，并通过`model_manager`以子进程模式执行推理，确保了稳定性和资源隔离。
  - `health_check()`: 一个不使用GPU的健康检查任务，用于监控服务状态。

### model_manager.py
- **功能**: 模型下载、管理和推理执行。
- **特性**:
  - `separate_audio_subprocess()`: 核心方法，通过`subprocess`调用独立的推理脚本，将推理过程与Celery worker主进程解耦。
  - 自动下载和缓存预训练模型。

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
@celery_app.task(bind=True, name='audio_separator.separate_vocals')
@gpu_lock()
def separate_vocals(self, context: dict) -> dict:
    """
    [工作流任务] 分离音频中的人声和背景音

    Args:
        context (dict): 工作流上下文。将自动从上下文中寻找合适的音频源
                      （如 `ffmpeg.extract_audio` 的输出）。也可以通过
                      `input_params.audio_separator_config` 传递质量模式等参数。

    Returns:
        dict: 更新后的工作流上下文，output中包含 `vocal_audio` 和 `instrumental`
              等分离后文件的路径。
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
