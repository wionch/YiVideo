# Pyannote Audio Service 说话人分离服务文档

> 🧭 **导航**: [YiVideo项目根](/mnt/d/WSL2/docker/YiVideo/CLAUDE.md) > [Workers目录](/mnt/d/WSL2/docker/YiVideo/services/workers/) > **pyannote_audio_service**

## 服务概述

Pyannote Audio Service基于pyannote-audio实现说话人分离(Diarization)功能，能够将多说话人的音频分离出各自的说话片段和时间戳。该服务独立部署，支持GPU加速。

## 核心功能

- **说话人分离**: 识别音频中的不同说话人
- **时间戳生成**: 提供精确的说话片段时间戳
- **GPU加速**: 基于pyannote-audio的GPU推理
- **说话人数量检测**: 自动或手动指定说话人数量
- **与ASR集成**: 为语音识别提供说话人标签

## 目录结构

```
services/workers/pyannote_audio_service/
├── app/
│   ├── celery_app.py         # Celery应用配置
│   ├── pyannote_infer.py     # 推理引擎
│   └── tasks.py              # Celery任务定义
├── Dockerfile
└── requirements.txt
```

## 核心文件

### tasks.py
- **主要任务**:
  - `diarize_speakers()`: 说话人分离任务
  - 使用`@gpu_lock`装饰器
  - 输出JSON格式的说话人片段

### pyannote_infer.py
- **功能**: pyannote推理引擎封装
- **特性**:
  - 模型自动下载
  - 批处理支持
  - 内存优化

## 依赖

```
celery
redis
pyannote.audio
torch
torchaudio
numpy
pydantic
```

## GPU要求

- **必需**: 支持CUDA的GPU
- **推荐**: NVIDIA GPU，显存≥4GB

## 任务接口

### 标准任务接口
```python
@celery_app.task(bind=True, name='pyannote_audio.diarize_speakers')
@gpu_lock(timeout=1800, poll_interval=0.5)
def diarize_speakers(self, context: dict) -> dict:
    """
    说话人分离任务 (子进程隔离模式)

    通过调用独立的推理脚本来执行说话人分离，以确保稳定性。

    Args:
        context (dict): 工作流上下文，将自动从中寻找合适的音频源。

    Returns:
        dict: 更新后的工作流上下文，包含指向分离结果文件(.json)的路径。
    """
    pass
```

## 输出格式

```json
{
  "speaker_segments": [
    {
      "start": 0.5,
      "end": 2.3,
      "speaker": "SPEAKER_00"
    },
    {
      "start": 2.5,
      "end": 5.1,
      "speaker": "SPEAKER_01"
    }
  ]
}
```

## 共享存储

- **输入**: `/share/workflows/{workflow_id}/audio/`
- **输出**: `/share/workflows/{workflow_id}/speaker_diarization.json`
- **中间文件**: `/share/workflows/{workflow_id}/temp/`

## 集成服务

- **语音识别**: `faster_whisper_service`
- **状态管理**: `services.common.state_manager`
- **GPU锁**: `services.common.locks`

## 性能优化

1. **模型选择**: 根据音频质量选择合适模型
2. **批处理**: 支持批量处理多段音频
3. **GPU内存管理**: 自动监控和清理

## 相关文档

- [pyannote-audio官方文档](https://github.com/pyannote/pyannote-audio)
- [GPU锁文档](/mnt/d/WSL2/docker/YiVideo/services/common/CLAUDE.md#gpu锁系统)
