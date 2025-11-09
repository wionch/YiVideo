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
  - `generate_speech()`: **核心任务**。基于提供的文本和参考音频（音色）生成语音。它使用`@gpu_lock`并以子进程模式运行，确保稳定性。
  - `list_voice_presets()`: 列出所有可用的语音预设。这是一个非GPU任务，用于查询配置。
  - `get_model_info()`: 获取当前TTS模型的技术信息和能力。这是一个非GPU任务。

### tts_engine.py
- **功能**: TTS推理引擎 (子进程模式)
- **类**: `MultiProcessTTSEngine`
- **特性**:
  - 在独立的子进程中加载和运行模型，与主Celery进程隔离。
  - 懒加载机制，只在首次需要时初始化。
  - 通过命令行参数传递配置，确保进程间解耦。

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
@celery_app.task(bind=True, base=IndexTTSTask, name='indextts.generate_speech')
@gpu_lock()
def generate_speech(self, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    IndexTTS语音生成任务 (子进程隔离)

    Args:
        context (Dict[str, Any]): 任务上下文，核心参数包括:
            - text: 要转换的文本
            - output_path: 输出音频文件路径
            - spk_audio_prompt: 必需，说话人参考音频路径
            - emo_audio_prompt: (可选) 情感参考音频路径

    Returns:
        Dict[str, Any]: 包含生成音频路径及状态的任务执行结果
    """
    pass

@celery_app.task(bind=True, name='indextts.list_voice_presets')
def list_voice_presets(self) -> Dict[str, Any]:
    """
    列出可用的语音预设
    """
    pass

@celery_app.task(bind=True, name='indextts.get_model_info')
def get_model_info(self) -> Dict[str, Any]:
    """
    获取模型信息
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
