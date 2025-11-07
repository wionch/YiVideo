# IndexTTS Service 文本转语音服务文档

> 🧭 **导航**: [YiVideo项目根](/mnt/d/WSL2/docker/YiVideo/CLAUDE.md) > [Workers目录](/mnt/d/WSL2/docker/YiVideo/services/workers/) > **indextts_service**

## 服务概述

IndexTTS Service基于IndexTTS模型实现高质量的文本转语音(TTS)功能，支持多说话人、多语言语音合成。该服务可将文字内容转换为自然流畅的语音。

## 核心功能

- **文本转语音**: 将文字转换为语音
- **多说话人**: 支持不同声音角色
- **多语言**: 支持多语言语音合成
- **情感控制**: 支持情感和语调控制
- **批量处理**: 支持批量文本转语音

## 目录结构

```
services/workers/indextts_service/
├── app.py                    # 主应用
├── tasks.py                  # Celery任务
├── tts_engine.py             # TTS引擎
├── Dockerfile
└── requirements.txt
```

## 核心文件

### tasks.py
- **主要任务**:
  - `text_to_speech()`: 文本转语音任务
  - 使用`@gpu_lock`装饰器

### tts_engine.py
- **功能**: TTS推理引擎
- **特性**:
  - 模型加载和管理
  - 音频生成
  - 后处理优化

## 依赖

```
celery
redis
torch
torchaudio
numpy
pydantic
# IndexTTS相关依赖
```

## GPU要求

- **必需**: 支持CUDA的GPU
- **显存**: ≥6GB

## 任务接口

### 标准任务接口
```python
@celery_app.task(bind=True)
@gpu_lock(timeout=1800, poll_interval=0.5)
def text_to_speech(self, context):
    """
    文本转语音任务

    Args:
        context: 工作流上下文，包含:
            - text: 要转换的文字
            - speaker_id: 说话人ID
            - language: 语言代码
            - speed: 语速

    Returns:
        更新后的context，包含生成的音频路径
    """
    pass
```

## 配置参数

- **说话人ID**: 可用说话人列表
- **语速**: 0.5-2.0
- **音调**: 可调节
- **音量**: 可调节

## 共享存储

- **输入**: `/share/workflows/{workflow_id}/text/`
- **输出**: `/share/workflows/{workflow_id}/audio/`
- **中间文件**: `/share/workflows/{workflow_id}/temp/`

## 集成服务

- **字幕处理**: `services.common.subtitle.*`
- **状态管理**: `services.common.state_manager`
- **GPU锁**: `services.common.locks`
