# Faster Whisper Service 语音识别服务文档

> 🧭 **导航**: [YiVideo项目根](/mnt/d/WSL2/docker/YiVideo/CLAUDE.md) > [Workers目录](/mnt/d/WSL2/docker/YiVideo/services/workers/) > **faster_whisper_service**

## 服务概述

Faster Whisper Service是基于faster-whisper高版本的语音识别(ASR)服务，提供GPU加速的实时语音转文字功能。该服务专注于GPU推理，仅负责语音转录，生成带词级时间戳的转录数据。

## 核心功能

- **语音识别**: 将音频转换为文字（GPU加速）
- **词级时间戳**: 提供精确的词级别时间戳
- **GPU加速**: 使用faster-whisper实现高速推理
- **模型管理**: 自动下载、缓存和管理模型
- **内存优化**: GPU显存管理和优化

## 架构设计：子进程隔离推理模型

为了确保系统的高稳定性和健壮性，本服务采用了一种**子进程隔离（Subprocess Isolation）**的架构来执行GPU推理任务。

### 设计原因
该设计的核心目标是解决在生产环境中常见的 **Celery prefork模型与CUDA初始化之间的冲突**。在Celery的多进程工作池中直接加载CUDA模型可能会导致不可预测的错误，例如进程死锁、显存泄漏或CUDA初始化失败。通过将推理任务隔离到独立的子进程中，可以完全规避这些问题。

### 工作流程
1.  **任务接收**: Celery worker（在`tasks.py`中）接收到`transcribe_audio`任务请求。
2.  **子进程调用**: 主进程不直接加载模型，而是通过Python的`subprocess.run()`模块，调用一个专用的推理脚本`faster_whisper_infer.py`。
3.  **参数传递**: 所有推理所需的参数（如音频文件路径、模型大小、语言、计算类型等）都通过命令行参数安全地传递给子进程。
4.  **独立推理**: `faster_whisper_infer.py`脚本在一个全新的、干净的进程中加载模型、执行推理，并将结果（包括词级时间戳）写入一个临时的JSON文件。
5.  **结果回收**: 主进程等待子进程执行完成。成功后，主进程读取临时JSON文件以获取转录结果，然后清理临时文件。
6.  **错误处理**: 如果子进程执行失败或超时，主进程会捕获异常，记录详细的`stderr`输出，并将任务标记为失败，从而不会影响到Celery worker本身。

### 主要优势
- **极高的稳定性**: 彻底隔离了CUDA环境。即使GPU推理过程中发生致命错误，也只会导致子进程退出，而不会使整个Celery服务崩溃。
- **纯净的资源管理**: 每个推理任务都在一个独立的进程中运行，任务结束后进程完全退出，确保了GPU显存等资源的彻底释放，避免了内存泄漏的风险。
- **依赖解耦**: 将核心的推理逻辑与任务调度逻辑（Celery）完全解耦，使得两部分可以独立维护和升级。

## 迁移说明

非GPU字幕处理功能已迁移至`wservice`服务，包括：
- 字幕文件生成
- 说话人片段合并
- 词级时间戳合并
- 字幕AI校正

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
  - `transcribe_audio()`: 语音识别任务（GPU推理）
  - 使用GPU锁装饰器保护GPU资源
  - 支持词级时间戳生成
  - 输出标准化转录数据供后续字幕处理使用

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
@celery_app.task(bind=True, name='faster_whisper.transcribe_audio')
def transcribe_audio(self, context: dict) -> dict:
    """
    语音识别任务 (独立转录节点)

    通过子进程隔离模型执行语音转录，支持CUDA和CPU模式。
    是否使用GPU锁由服务内部根据配置和设备状态动态决定。

    Args:
        context (dict): 工作流上下文。音频文件路径等参数会从
                      前置任务(如 audio_separator 或 ffmpeg)的输出中自动获取。

    Returns:
        dict: 更新后的工作流上下文。
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
- **输出**: `/share/workflows/{workflow_id}/transcribe_data.json`（转录数据）
- **中间文件**: `/share/workflows/{workflow_id}/temp/`

## 监控

- **日志**: 使用`services.common.logger`
- **状态**: 通过`state_manager`更新
- **GPU监控**: 集成GPU锁系统

## 集成服务

- **下游字幕处理**: `wservice`（接收转录数据并生成字幕）
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
