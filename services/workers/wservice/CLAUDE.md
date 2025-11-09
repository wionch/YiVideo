# WService 字幕AI优化服务文档

> 🧭 **导航**: [YiVideo项目根](/mnt/d/WSL2/docker/YiVideo/CLAUDE.md) > [Workers目录](/mnt/d/WSL2/docker/YiVideo/services/workers/) > **wservice**

## 服务概述

WService是字幕AI优化服务，专注于字幕处理和AI优化。该服务从`faster_whisper_service`迁移了所有非GPU功能，提供全面的字幕处理能力。

## 核心功能

- **字幕生成**: 将转录结果转换为SRT等字幕格式。
- **说话人合并**: 精确地将说话人时间戳与词级时间戳合并。
- **TTS片段准备**: 为语音合成（TTS）任务准备和优化字幕片段。
- **字幕AI优化**: 使用大语言模型对字幕进行校正和润色。
- **格式转换**: 支持多种字幕格式。

## 迁移与整合说明

`wservice` 是所有**非GPU密集型**的字幕后处理中心。它整合了最初分散在 `faster_whisper_service` 中的多个功能模块。

- **已整合功能**:
  - `speaker_word_matcher`: 说话人匹配逻辑（已内联为辅助函数）。
  - `subtitle_merger`: 字幕合并逻辑（现使用 `services.common.subtitle` 公共模块）。
  - `tts_merger`: TTS字幕准备逻辑（已封装为新任务）。
- **当前职责**:
  - 提供所有与字幕生成、合并、AI优化和为TTS准备数据相关的服务节点。

## 目录结构

```
services/workers/wservice/
├── app/
│   ├── celery_app.py         # Celery应用配置
│   ├── subtask/              # 子任务模块
│   └── tasks.py              # Celery任务定义
├── Dockerfile
└── requirements.txt
```

## 核心文件

### tasks.py
- **主要任务**:
  - `generate_subtitle_files()`: 字幕文件生成。
  - `merge_speaker_segments()`: 片段级说话人合并。
  - `merge_with_word_timestamps()`: 词级时间戳精确合并。
  - `correct_subtitles()`: 字幕AI校正。
  - `ai_optimize_subtitles()`: 字幕AI优化（原有功能）。
  - `prepare_tts_segments()`: **(新)** 为TTS准备和优化字幕片段。

### subtask/
- **功能**: 字幕处理的子任务模块
- **包含**: 各种字幕优化子任务

## 依赖

```
celery
redis
torch
transformers
numpy
pydantic
# AI模型相关依赖
```

## 任务接口

### 标准任务接口
```python
@celery_app.task(bind=True)
def ai_optimize_subtitles(self, context):
    """
    字幕AI优化任务

    Args:
        context: 工作流上下文，包含:
            - subtitle_path: 字幕文件路径
            - optimization_level: 优化级别
            - ai_provider: AI服务提供商

    Returns:
        更新后的context，包含优化后的字幕
    """
    pass
```

## 共享存储

- **输入**: `/share/workflows/{workflow_id}/subtitles/`
- **输出**: `/share/workflows/{workflow_id}/optimized/`
- **中间文件**: `/share/workflows/{workflow_id}/temp/`

## 集成服务

- **字幕模块**: `services.common.subtitle.*`
- **状态管理**: `services.common.state_manager`
- **AI提供商**: `services.common.subtitle.ai_providers`
