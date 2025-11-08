<<<<<<< HEAD
# WService 字幕AI优化服务文档

> 🧭 **导航**: [YiVideo项目根](/mnt/d/WSL2/docker/YiVideo/CLAUDE.md) > [Workers目录](/mnt/d/WSL2/docker/YiVideo/services/workers/) > **wservice**

## 服务概述

WService是字幕AI优化服务，专注于使用AI技术对字幕进行智能优化、校正和增强。该服务集成了多种AI模型，提供全面的字幕处理能力。

## 核心功能

- **字幕优化**: AI驱动的字幕质量优化
- **语义校正**: 智能语法和语义校正
- **时序调整**: 自动调整字幕时间轴
- **格式转换**: 支持多种字幕格式
- **并发处理**: 高效的并发批处理

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
  - `ai_optimize_subtitles()`: 字幕AI优化
  - `correct_subtitles()`: 字幕校正
  - `merge_subtitles()`: 字幕合并

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
=======
# WService 字幕AI优化服务文档

> 🧭 **导航**: [YiVideo项目根](/mnt/d/WSL2/docker/YiVideo/CLAUDE.md) > [Workers目录](/mnt/d/WSL2/docker/YiVideo/services/workers/) > **wservice**

## 服务概述

WService是字幕AI优化服务，专注于字幕处理和AI优化。该服务从`faster_whisper_service`迁移了所有非GPU功能，提供全面的字幕处理能力。

## 核心功能

- **字幕生成**: 将转录结果转换为SRT等字幕格式
- **说话人合并**: 片段级和词级说话人时间戳合并
- **字幕校正**: AI驱动的字幕质量优化和语义校正
- **格式转换**: 支持多种字幕格式转换
- **并发处理**: 高效的并发批处理

## 迁移说明

以下功能已从`faster_whisper_service`迁移至本服务：
- ✅ generate_subtitle_files: 字幕文件生成
- ✅ merge_speaker_segments: 片段级说话人合并
- ✅ merge_with_word_timestamps: 词级时间戳合并
- ✅ correct_subtitles: 字幕AI校正

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
  - `generate_subtitle_files()`: 字幕文件生成（从faster_whisper_service迁移）
  - `merge_speaker_segments()`: 片段级说话人合并（从faster_whisper_service迁移）
  - `merge_with_word_timestamps()`: 词级时间戳合并（从faster_whisper_service迁移）
  - `correct_subtitles()`: 字幕AI校正（从faster_whisper_service迁移）
  - `ai_optimize_subtitles()`: 字幕AI优化（原有功能）

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
>>>>>>> 002-migrate-nongpu-nodes
