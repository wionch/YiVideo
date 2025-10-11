# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

YiVideo 是一个基于微服务架构的 AI 视频处理工作流引擎，主要功能是自动化视频字幕提取、翻译、配音和本地化处理。系统采用动态工作流引擎设计，通过配置驱动而非硬编码的方式来编排各种AI功能。经过最新优化，系统实现了 WhisperX 功能模块化重构、Redis 数据存储优化（内存占用减少98%+）和 GPU 锁系统全面升级（响应速度提升83%）。

## 核心架构

### 微服务架构
- **API网关** (`services/api_gateway/`): 系统入口，基于 FastAPI + Gunicorn，负责接收请求和动态构建工作流
- **AI工作节点**: 8个专门的AI服务，通过 Celery 任务队列协调
- **基础设施**: Redis (消息代理/状态存储) + 共享存储 `/share`
- **GPU锁系统**: 基于Redis的智能GPU资源管理，支持并发优化和自动恢复

### 关键组件
1. **ffmpeg_service**: 视频解码和处理
2. **paddleocr_service**: OCR字幕识别（核心服务）
3. **whisperx_service**: 语音识别(ASR) - 已拆分为3个独立任务节点
4. **llm_service**: 大语言模型调用(Gemini, DeepSeek)
5. **inpainting_service**: 硬字幕去除
6. **indextts_service**: IndexTTS语音合成
7. **gptsovits_service**: GPT-SoVITS语音合成
8. **audio_separator_service**: 音频分离服务（基于UVR-MDX和Demucs模型）

## 开发命令

### 环境检查
```bash
python check_env.py  # 检查CUDA、PyTorch、PaddlePaddle等环境
```

### 容器化部署
```bash
# 构建并启动所有服务
docker-compose up -d

# 重新构建特定服务
docker-compose build paddleocr_service

# 查看服务日志
docker-compose logs -f api_gateway
```

### 独立脚本运行
```bash
# 字幕提取（独立运行）
python extract_subtitles.py -i videos/example.mp4 -o output/ --lang en

# 使用自定义配置
python extract_subtitles.py -i videos/example.mp4 --config custom_config.yml
```

### 测试命令
```bash
# 运行环境检查
python check_env.py

# 运行特定服务测试
cd services/workers/paddleocr_service && python test.py
```

## 技术栈和依赖

### AI框架
- **PyTorch生态系统**: torch, torchvision, torchaudio
- **PaddlePaddle**: paddlepaddle-gpu==2.5.2 (版本锁定)
- **关键AI库**:
  - PaddleOCR (>=2.7.0, PP-OCRv5优化版本)
  - WhisperX (Faster-Whisper后端，4倍性能提升)
  - audio-separator (基于UVR-MDX和Demucs模型)
  - pyannote.audio (说话人分离)

### 视频处理
- **FFmpeg**: 自编译支持CUDA加速
- **视频IO**: yt-dlp, av (FFmpeg Python绑定)
- **图像处理**: opencv-python-headless

### 音频处理
- **音频分离**: UVR-MDX, Demucs v4
- **音频格式**: FLAC, WAV, MP3
- **音频处理**: librosa, soundfile

### 系统架构
- **消息队列**: Redis + Celery
- **Web框架**: FastAPI + Gunicorn
- **配置管理**: YAML (config.yml)
- **GPU管理**: 基于Redis的分布式锁系统
- **状态存储**: Redis多数据库分离 (Broker/Backend/Locks/State)

## 配置系统

### 主配置文件 `config.yml`
配置文件分为12个模块：
1. **core**: 系统核心配置 (工作流TTL、临时文件清理)
2. **redis**: Redis连接和数据库分配 (Broker/Backend/Locks/State分离)
3. **decoder**: GPU解码批处理大小
4. **area_detector**: 字幕区域检测参数
5. **keyframe_detector**: 关键帧检测算法参数 (包含dHash焦点区域优化)
6. **ocr**: OCR识别和PaddleOCR详细配置 (PP-OCRv5优化)
7. **postprocessor**: 后处理过滤参数
8. **pipeline**: 流水线控制策略
9. **llm_service**: 大语言模型配置 (Gemini, DeepSeek)
10. **whisperx_service**: WhisperX ASR和说话人分离配置
11. **gpu_lock**: GPU锁管理配置 (指数退避和动态策略)
12. **audio_separator_service**: 音频分离服务配置 (UVR-MDX/Demucs)

### 动态工作流配置
工作流通过 `workflow_config` 动态构建，支持灵活的任务编排：

#### 基础字幕提取工作流
```python
workflow_config = {
    "workflow_chain": [
        "ffmpeg.extract_keyframes",
        "paddleocr.recognize_subtitles",
        "llm.translate_text",
        "indextts.generate_speech"
    ]
}
```

#### WhisperX 完整工作流（推荐）
```python
workflow_config = {
    "workflow_chain": [
        "ffmpeg.extract_audio",
        "audio_separator.separate_vocals",
        "whisperx.transcribe_audio",
        "whisperx.diarize_speakers",
        "whisperx.generate_subtitle_files",
        "llm.translate_text",
        "indextts.generate_speech"
    ]
}
```

#### WhisperX 基础工作流（仅转录）
```python
workflow_config = {
    "workflow_chain": [
        "ffmpeg.extract_audio",
        "whisperx.transcribe_audio",
        "whisperx.generate_subtitle_files"
    ]
}
```

#### 兼容性工作流（向后兼容）
```python
workflow_config = {
    "workflow_chain": [
        "ffmpeg.extract_audio",
        "whisperx.generate_subtitles"  # 原有任务继续工作
    ]
}
```

## 核心功能模块

### PaddleOCR服务 (核心)
- **字幕区域检测**: 智能识别视频中的字幕位置
- **关键帧检测**: 基于感知哈希的帧变化检测，包含dHash焦点区域优化
- **OCR识别**: 多语言文字识别，PP-OCRv5模型针对字幕场景优化
- **后处理**: 时间轴合并和过滤

### WhisperX服务 (语音识别)
- **功能拆分**: 3个独立任务节点，支持灵活工作流编排
  - `whisperx.transcribe_audio`: 语音转录
  - `whisperx.diarize_speakers`: 说话人分离
  - `whisperx.generate_subtitle_files`: 字幕文件生成
- **Faster-Whisper后端**: 4倍性能提升
- **词级时间戳**: 精确的语音到文本对齐
- **说话人分离**: 基于pyannote.audio的精确说话人识别

### Audio Separator服务 (音频分离)
- **UVR-MDX模型**: 高质量人声/背景音分离
- **Demucs v4支持**: 最新多轨道音频分离
- **GPU加速**: 支持CUDA硬件加速
- **多种质量模式**: 快速、平衡、高质量选项
- **人声优化**: 专门针对人声分离效果优化

### 视频解码 (FFmpeg)
- **GPU加速解码**: 支持CUDA硬件加速
- **批处理**: 优化显存使用和解码效率
- **多格式支持**: 通过FFmpeg支持各种视频格式
- **音频提取**: 支持从视频中提取音频轨道

### GPU锁系统
- **智能锁管理**: V3智能锁管理器，支持指数退避
- **主动监控**: 实时监控GPU锁状态，自动检测死锁
- **心跳机制**: 完整的任务生命周期管理
- **自动恢复**: 分级超时处理机制

### API接口
- **POST /v1/workflows**: 创建工作流
- **GET /v1/workflows/status/{workflow_id}**: 查询状态
- **GET /api/v1/monitoring/gpu-lock/health**: GPU锁健康状态
- **GET /api/v1/monitoring/heartbeat/all**: 任务心跳状态
- **POST /api/v1/monitoring/release-lock**: 手动释放锁

## 开发注意事项

### GPU资源管理
- 多个服务竞争GPU资源，需要合理分配
- 使用 `NVIDIA_VISIBLE_DEVICES` 环境变量控制
- 显存占用监控很重要

### 共享存储
- 所有服务通过 `/share` 目录交换文件
- 临时文件管理通过 `/tmp` 目录
- 考虑磁盘空间，配置 `cleanup_temp_files`

### 配置优化
- PaddleOCR配置针对字幕场景高度优化
- 关键帧检测算法经过调优，避免重复字幕
- 支持多语言OCR模型选择

### GPU锁优化系统 (2025-10-11更新)
YiVideo系统实现了基于Redis的完整GPU锁管理机制，包含智能锁管理、主动监控、自动恢复和高可观测性。系统经过全面优化，响应速度提升83%，Redis内存占用减少98%+，可靠性显著增强。

**核心特性**:
- **智能锁管理**: V3智能锁管理器，支持指数退避和动态策略调整
- **主动监控**: 实时监控GPU锁状态，检测死锁和异常
- **自动恢复**: 分级超时处理机制（警告/软超时/硬超时）
- **任务心跳**: 完整的任务生命周期管理
- **完整API**: RESTful监控接口，提供实时状态查询
- **高性能**: 优化配置，响应速度提升83%
- **内存优化**: Redis存储优化，内存占用减少98%+

**关键配置**:
```yaml
gpu_lock:
  poll_interval: 2           # 轮询间隔（秒）- 平衡响应和负载
  max_wait_time: 1800        # 最大等待时间（30分钟）
  lock_timeout: 3600         # 锁超时时间（60分钟）
  exponential_backoff: true  # 启用指数退避
  max_poll_interval: 10      # 最大轮询间隔

gpu_lock_monitor:
  monitor_interval: 30        # 监控间隔（秒）
  timeout_levels:
    warning: 1800            # 警告级别（30分钟）
    soft_timeout: 3600       # 软超时（60分钟）
    hard_timeout: 7200       # 硬超时（120分钟）
  heartbeat:
    interval: 60             # 心跳间隔（秒）
    timeout: 300             # 心跳超时（5分钟）
  health_thresholds:
    min_success_rate: 0.8     # 最小成功率
    max_timeout_rate: 0.2     # 最大超时率
```

**核心组件**:
- `services/common/locks.py`: SmartGpuLockManager智能锁管理器
- `services/api_gateway/app/monitoring/gpu_lock_monitor.py`: GPU锁监控器
- `services/api_gateway/app/monitoring/heartbeat_manager.py`: 心跳管理器
- `services/api_gateway/app/monitoring/timeout_manager.py`: 超时管理器
- `services/common/task_heartbeat_integration.py`: 任务心跳集成

**使用方法**:
```python
# 在GPU任务中使用装饰器
from services.common.locks import gpu_lock

class PaddleOCRTask:
    @gpu_lock()
    def detect_subtitle_area(self, video_path: str):
        """自动集成GPU锁和心跳机制"""
        # 执行GPU任务逻辑
        return result

# Audio Separator服务示例
class AudioSeparatorTask:
    @gpu_lock()
    def separate_vocals(self, audio_path: str):
        """音频分离任务自动集成GPU锁"""
        # 执行音频分离逻辑
        return result
```

**监控API端点**:
- `GET /api/v1/monitoring/gpu-lock/health` - GPU锁健康状态
- `GET /api/v1/monitoring/heartbeat/all` - 所有任务心跳状态
- `GET /api/v1/monitoring/statistics` - 系统统计信息
- `GET /api/v1/monitoring/monitor/status` - 监控器状态
- `POST /api/v1/monitoring/release-lock` - 手动释放锁

### 错误处理
- 使用统一的日志系统 (`services.common.logger`)
- 分布式锁机制 (`services.common.locks`)
- 状态管理通过Redis存储
- GPU锁监控和自动恢复机制 (`services.api_gateway.app.monitoring`)

## 文档结构

项目包含完整的技术文档，按模块分类在 `docs/` 目录下：

### 主要文档分类
- **产品需求**: `docs/development/PRD.md`
- **系统架构**: `docs/architecture/SYSTEM_ARCHITECTURE.md`
- **技术设计**: `docs/architecture/SDD.md`
- **测试策略**: `docs/development/TESTING_STRATEGY.md`
- **部署指南**: `docs/deployment/DEPLOYMENT_GUIDE.md`
- **运维手册**: `docs/operations/OPERATIONS_MANUAL.md`
- **故障排除**: `docs/operations/TROUBLESHOOTING_GUIDE.md`

### 专项文档
- **WhisperX优化**: `docs/whisperx/WHISPERX_COMPLETE_GUIDE.md`
- **WhisperX功能拆分**: `docs/development/WHISPERX_SPLIT_IMPLEMENTATION.md`
- **WhisperX工作流指南**: `docs/reference/WHISPERX_WORKFLOW_GUIDE.md`
- **Redis优化总结**: `docs/reference/REDIS_OPTIMIZATION_SUMMARY.md`
- **GPU锁系统**: `docs/reference/GPU_LOCK_COMPLETE_GUIDE.md`
- **模块依赖**: `docs/reference/module_dependencies.md`
- **字幕关键帧提取**: `docs/reference/SUBTITLE_KEYFRAME_EXTRACTION.md`

详细文档目录请参考：`docs/README.md`

## 常见问题

### 环境问题
- 使用 `check_env.py` 检查环境兼容性
- PaddlePaddle版本需要与CUDA版本匹配
- 确保GPU驱动版本正确
- 验证ollama服务状态（用于MCP Code Search）

### 性能优化
- 调整 `decoder.batch_size` 平衡速度和显存
- 优化 `keyframe_detector.similarity_threshold` 避免重复处理
- 合理配置并发工作进程数
- 使用WhisperX功能拆分减少内存占用
- 利用GPU锁系统优化并发处理

### 调试技巧
- 查看容器日志: `docker-compose logs -f [service_name]`
- 临时文件保留: 设置 `core.cleanup_temp_files: false`
- 使用Redis状态存储查询执行状态
- 监控GPU锁状态: `curl http://localhost:8788/api/v1/monitoring/gpu-lock/health`
- 查看工作流状态: `curl http://localhost:8788/v1/workflows/status/{workflow_id}`

### WhisperX调试
- 检查语音转录: `whisperx.transcribe_audio` 任务状态
- 验证说话人分离: `whisperx.diarize_speakers` 输出
- 确认字幕文件生成: `whisperx.generate_subtitle_files` 结果
- 监控Redis内存使用: `redis-cli info memory | grep used_memory_human`

### Audio Separator调试
- 验证模型下载: 检查 `/models/uvr_mdx` 和 `/models/demucs` 目录
- 测试音频分离: 使用独立脚本 `audio_separator_standalone.py`
- 检查GPU使用率: `nvidia-smi` 命令
- 验证输出格式: 确认FLAC/WAV文件生成正确

### GPU锁调试
**基础调试命令**:
- **监控GPU锁状态**: `curl http://localhost:8788/api/v1/monitoring/gpu-lock/health`
- **查看任务心跳**: `curl http://localhost:8788/api/v1/monitoring/heartbeat/all`
- **获取系统统计**: `curl http://localhost:8788/api/v1/monitoring/statistics`
- **监控器状态**: `curl http://localhost:8788/api/v1/monitoring/monitor/status`
- **手动释放锁**: `curl -X POST http://localhost:8788/api/v1/monitoring/release-lock -H "Content-Type: application/json" -d '{"lock_key": "gpu_lock:0"}'`
- **检查锁配置**: `python -c "from services.common.config_loader import get_gpu_lock_config; print(get_gpu_lock_config())"`
- **Redis内存监控**: `redis-cli info memory | grep used_memory_human`

**常见问题处理**:
1. **任务无法获取GPU锁**: 检查锁状态，必要时手动释放
2. **监控API无响应**: 重启API网关服务 `docker-compose restart api_gateway`
3. **心跳状态异常**: 检查Redis连接和服务状态
4. **Redis内存占用过高**: 检查WhisperX segments数据存储优化
5. **性能问题**: 监控CPU使用率和Redis连接数

**详细文档参考**: `docs/reference/GPU_LOCK_COMPLETE_GUIDE.md` 包含完整的故障排除指南和最佳实践。

## MCP服务使用指南

### 代码检索工具 (推荐优先使用)
- **Code Search** (`mcp__code-search_*`): 基于向量化的智能代码搜索和检索
  - `list_collections()` - 列出可用的代码集合
  - `add_documents(filePath, collection, embeddingService, chunkSize?, chunkOverlap?)` - 添加代码文档到集合
  - `search(query, collection, embeddingService, limit?)` - 在集合中搜索相关代码
  - `delete_collection(collection)` - 删除代码集合

**关键参数说明**:
- `filePath`: 文件或目录路径，支持单个文件或整个目录
- `collection`: 集合名称，用于组织不同模块的代码
- `embeddingService`: 嵌入服务，当前支持 "ollama"
- `chunkSize`: 文档分块大小（可选，默认值根据系统配置）
- `chunkOverlap`: 分块重叠大小（可选，默认值根据系统配置）
- `query`: 搜索查询，支持自然语言描述
- `limit`: 返回结果数量限制（可选，默认值根据系统配置）

**使用优先级**：Code Search > 普通工具

### 其他MCP工具
- **Context7** (`mcp__context7_*`): 获取最新的库文档和API参考
- **Web搜索** (`mcp__web-search-prime_*`): 查找技术解决方案和最佳实践
- **AI视觉分析** (`mcp__zai-mcp-server_*`): 分析图片和视频内容
- **Redis工具** (`mcp__redis_*`): Redis键值对操作和管理

### 网络检索工具
- **Context7** (`mcp__context7_*`): 获取最新的库文档和API参考
- **Web搜索** (`mcp__web-search-prime_*`): 查找技术解决方案和最佳实践
- **AI视觉分析** (`mcp__zai-mcp-server_*`): 分析图片和视频内容

### 工作流程指导

#### 1. 代码理解阶段
```python
# 优先使用Code Search工具
mcp__code-search__search("PaddleOCRTask class", "collection_name", "ollama")  # 搜索特定类
mcp__code-search__search("GPU lock decorator", "collection_name", "ollama")   # 搜索GPU锁相关代码
mcp__code-search__search("Audio Separator service", "collection_name", "ollama")  # 搜索音频分离服务
mcp__code-search__search("WhisperX transcribe task", "collection_name", "ollama")  # 搜索WhisperX任务
mcp__code-search__list_collections()                                        # 查看可用集合
```

#### 2. 信息查询阶段
```python
# 查找库文档
mcp__context7__resolve-library-id("fastapi")                          # 解析库ID
mcp__context7__get-library-docs("/vercel/next.js", "routing")         # 获取特定主题文档

# 搜索解决方案
mcp__web-search-prime__webSearchPrime("Docker GPU memory optimization") # 网络搜索
mcp__web-search-prime__webSearchPrime("audio-separator UVR-MDX configuration") # 音频分离配置搜索
```

#### 3. 问题解决阶段
```python
# 使用视觉分析工具（如需要）
mcp__zai-mcp-server__analyze_image("/path/to/screenshot.png", "Describe the UI layout")

# 使用Redis工具调试
mcp__redis__get("gpu_lock:0")  # 查看GPU锁状态
mcp__redis__list("workflow:*")  # 列出工作流相关键
```

#### 4. 项目特定搜索策略
```python
# 按服务模块搜索
mcp__code-search__search("paddleocr service configuration", "paddleocr", "ollama")
mcp__code-search__search("whisperx workflow tasks", "whisperx", "ollama")
mcp__code-search__search("audio separator models", "audio_separator", "ollama")
mcp__code-search__search("gpu lock monitoring", "common_modules", "ollama")

# 按功能搜索
mcp__code-search__search("workflow factory implementation", "api_gateway", "ollama")
mcp__code-search__search("redis state management", "common_modules", "ollama")
mcp__code-search__search("celery task configuration", "all_services", "ollama")
```

## 开发约束和最佳实践

### 1. 文件操作约束
```bash
# ✅ 推荐：使用Code Search工具
mcp__code-search__search("config file", "collection_name", "ollama")    # 搜索配置相关代码
mcp__code-search__search("GPU lock", "collection_name", "ollama")       # 搜索GPU锁相关代码

# ✅ 次选：使用普通工具（当Code Search无法满足需求时）
Read("path/to/file")
Grep("pattern", "path/")
```

### 2. 代码搜索约束
```bash
# ✅ 推荐：使用Code Search工具
mcp__code-search__search("PaddleOCRTask class", "collection_name", "ollama")    # 搜索特定类
mcp__code-search__search("workflow factory", "collection_name", "ollama")       # 搜索工作流工厂
mcp__code-search__search("Audio Separator task", "collection_name", "ollama")   # 搜索音频分离任务
mcp__code-search__list_collections()                                          # 查看可用集合

# ✅ 次选：使用Grep工具进行精确匹配
Grep("class PaddleOCRTask", "services/")
Grep("whisperx.transcribe_audio", "services/")
```

### 3. 网络检索约束
```bash
# ✅ 推荐：使用专门的检索工具
mcp__context7__resolve-library-id("pytorch")                      # 查找PyTorch文档
mcp__web-search-prime__webSearchPrime("Docker compose GPU setup") # 搜索技术方案
mcp__web-search-prime__webSearchPrime("audio-separation Demucs v4") # 搜索音频分离技术

# ❌ 避免：让Claude猜测或使用过时的知识
```

### 4. GPU任务开发约束
```python
# ✅ 所有GPU任务必须使用锁装饰器
from services.common.locks import gpu_lock

@gpu_lock()
def process_with_gpu(self, input_data):
    # GPU处理逻辑
    return result

# ✅ WhisperX任务示例
@gpu_lock()
@celery_app.task(bind=True, name='whisperx.transcribe_audio')
def transcribe_audio(self, context: dict) -> dict:
    # 语音转录逻辑
    return result

# ✅ Audio Separator任务示例
@gpu_lock()
@celery_app.task(bind=True, name='audio_separator.separate_vocals')
def separate_vocals(self, context: dict) -> dict:
    # 音频分离逻辑
    return result
```

### 5. 工作流开发约束
```python
# ✅ 推荐使用WhisperX拆分后的任务
workflow_config = {
    "workflow_chain": [
        "ffmpeg.extract_audio",
        "whisperx.transcribe_audio",      # 独立转录任务
        "whisperx.diarize_speakers",      # 独立说话人分离任务
        "whisperx.generate_subtitle_files" # 独立字幕生成任务
    ]
}

# ✅ 包含音频分离的完整工作流
workflow_config = {
    "workflow_chain": [
        "ffmpeg.extract_audio",
        "audio_separator.separate_vocals", # 音频分离
        "whisperx.transcribe_audio",
        "whisperx.diarize_speakers",
        "whisperx.generate_subtitle_files"
    ]
}

# ✅ 向后兼容原有任务
workflow_config = {
    "workflow_chain": [
        "ffmpeg.extract_audio",
        "whisperx.generate_subtitles"      # 原有任务继续工作
    ]
}
```

### 6. Redis数据优化约束
```python
# ✅ 使用segments数据按需加载
def get_segments_data(stage_output: dict, field_name: str = None) -> list:
    """统一的数据获取接口，支持新旧格式"""

# ✅ 大数据存储在文件系统，Redis只存储索引
workflow_context.stages[stage_name] = StageExecution(
    status="SUCCESS",
    output={
        'segments_file': '/share/workflows/{id}/segments.json',  # 文件路径
        'segments_count': 150,  # 元数据
        'duration': 120.5
    }
)
```

## 代码搜索最佳实践

### 推荐集合设置
```bash
# 为不同服务模块建立专门的集合
mcp__code-search__add_documents("services/api_gateway/", "api_gateway", "ollama")
mcp__code-search__add_documents("services/common/", "common_modules", "ollama")
mcp__code-search__add_documents("services/workers/paddleocr_service/", "paddleocr", "ollama")
mcp__code-search__add_documents("services/workers/whisperx_service/", "whisperx", "ollama")
mcp__code-search__add_documents("services/workers/audio_separator_service/", "audio_separator", "ollama")
mcp__code-search__add_documents("config.yml", "configuration", "ollama")
```

### 集合管理
```bash
# 查看当前可用的代码集合
mcp__code-search__list_collections()

# 添加新的代码文档到集合（支持文件或目录）
mcp__code-search__add_documents("services/api_gateway/app/main.py", "api_gateway", "ollama")
mcp__code-search__add_documents("services/common/", "common_modules", "ollama", chunkSize=1000, chunkOverlap=200)

# 在集合中搜索相关代码
mcp__code-search__search("FastAPI routing", "api_gateway", "ollama", limit=10)
mcp__code-search__search("GPU lock implementation", "common_modules", "ollama", limit=5)
mcp__code-search__search("WhisperX transcribe task", "whisperx", "ollama", limit=5)
mcp__code-search__search("Audio Separator models", "audio_separator", "ollama", limit=5)

# 删除集合（谨慎使用）
mcp__code-search__delete_collection("collection_name")
```

### 搜索策略
1. **精确搜索**: 使用具体的类名、方法名或模块名
   - `mcp__code-search__search("PaddleOCRTask class", "paddleocr", "ollama")`
   - `mcp__code-search__search("transcribe_audio task", "whisperx", "ollama")`

2. **功能搜索**: 使用描述功能的短语，如"GPU lock decorator"
   - `mcp__code-search__search("GPU lock decorator", "common_modules", "ollama")`
   - `mcp__code-search__search("workflow factory", "api_gateway", "ollama")`

3. **模块搜索**: 按服务或模块名称进行限定搜索
   - `mcp__code-search__search("configuration", "configuration", "ollama")`
   - `mcp__code-search__search("celery app", "all_services", "ollama")`

4. **多轮搜索**: 从广泛到具体，逐步缩小搜索范围
   - 先搜索 "whisperx service" 了解整体架构
   - 再搜索 "transcribe_audio implementation" 了解具体实现

### 项目特定搜索模式
```bash
# 按服务类型搜索
mcp__code-search__search("OCR configuration", "paddleocr", "ollama")
mcp__code-search__search("ASR model settings", "whisperx", "ollama")
mcp__code-search__search("audio separation UVR-MDX", "audio_separator", "ollama")

# 按功能模块搜索
mcp__code-search__search("state management", "common_modules", "ollama")
mcp__code-search__search("monitoring endpoints", "api_gateway", "ollama")
mcp__code-search__search("GPU resource management", "common_modules", "ollama")

# 按任务类型搜索
mcp__code-search__search("celery task definition", "all_services", "ollama")
mcp__code-search__search("workflow chain configuration", "configuration", "ollama")
mcp__code-search__search("Redis database schema", "common_modules", "ollama")
```

## 故障排除和调试

### MCP服务调试
```bash
# 检查可用的代码搜索集合
mcp__code-search__list_collections()

# 测试搜索功能
mcp__code-search__search("GPU lock", "collection_name", "ollama", limit=5)

# 测试添加文档
mcp__code-search__add_documents("path/to/test_file.py", "test_collection", "ollama")

# 验证ollama服务状态
curl http://localhost:11434/api/tags
```

### 工具使用建议
1. **Code Search优先**: 对于代码相关操作，优先使用Code Search工具
2. **网络检索辅助**: 遇到不确定的技术问题时，主动使用网络检索
3. **工具组合**: 结合使用多种MCP工具以获得最佳效果
4. **Redis调试**: 使用Redis工具检查系统状态

### 常见问题处理
1. **Code Search无结果**:
   - 检查集合是否存在：`mcp__code-search__list_collections()`
   - 确认搜索查询是否过于具体，尝试更广泛的关键词
   - 检查目标文档是否已添加到集合中

2. **搜索结果不准确**:
   - 使用更具体的查询描述
   - 调整搜索策略，尝试不同的关键词组合
   - 考虑重新添加文档到集合，使用不同的分块参数

3. **添加文档失败**:
   - 检查文件路径是否正确存在
   - 确认有足够的磁盘空间和权限
   - 检查ollama服务是否正常运行

4. **网络检索失败**: 确认网络连接和API配置
5. **工具选择混乱**: 参考上述工作流程指导，按阶段选择合适工具

### 系统级调试
```bash
# 检查服务状态
docker-compose ps

# 查看服务日志
docker-compose logs -f api_gateway
docker-compose logs -f whisperx_service
docker-compose logs -f audio_separator_service

# 检查GPU状态
nvidia-smi

# 检查Redis状态
redis-cli ping
redis-cli info memory

# 检查工作流状态
curl http://localhost:8788/v1/workflows/status/{workflow_id}

# 检查GPU锁状态
curl http://localhost:8788/api/v1/monitoring/gpu-lock/health
```

### 服务特定调试
#### WhisperX服务调试
```bash
# 检查WhisperX任务状态
curl http://localhost:8788/api/v1/celery/active_tasks

# 验证模型文件
ls -la /models/whisperx/

# 检查音频文件处理
docker-compose exec whisperx_service ls -la /share/workflows/
```

#### Audio Separator服务调试
```bash
# 验证UVR-MDX模型
ls -la /models/uvr_mdx/

# 验证Demucs模型
ls -la /models/demucs/

# 测试音频分离
python services/workers/audio_separator_service/audio_separator_standalone.py
```

#### PaddleOCR服务调试
```bash
# 检查OCR模型
ls -la /models/paddleocr/

# 测试OCR识别
cd services/workers/paddleocr_service && python test.py
```

### 性能监控
```bash
# 监控系统资源
htop

# 监控GPU使用率
watch -n 1 nvidia-smi

# 监控Redis内存
watch -n 5 "redis-cli info memory | grep used_memory_human"

# 监控磁盘空间
df -h

# 监控网络连接
netstat -tulpn | grep :8788
```