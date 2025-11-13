# Project Context

## Purpose

YiVideo 是一个基于动态工作流引擎的 AI 视频处理平台，采用微服务架构设计。

**核心价值**:
- **配置而非编码**: 通过工作流配置文件动态构建 AI 处理链条，无需修改代码
- **灵活组合**: 支持语音识别、OCR、字幕处理、音频分离、文本转语音等多种 AI 功能的灵活组合
- **资源优化**: 智能 GPU 资源管理，支持多任务并发和自动恢复

**主要功能**:
- 视频/音频处理和分割
- 语音识别 (ASR) 和说话人分离
- 光学字符识别 (OCR)
- 人声/背景音分离
- 文本转语音 (TTS) 和语音克隆
- 字幕生成、合并、校正和 AI 优化
- 图像修复 (Inpainting)

## Tech Stack

### 核心框架
- **Python 3.8+**: 主要开发语言
- **Docker & Docker Compose**: 容器化部署和服务编排
- **Redis**: 消息队列、状态存储、分布式锁、缓存（多数据库架构）
- **Celery**: 分布式任务队列和工作流引擎
- **FastAPI/Flask**: RESTful API 网关

### AI/ML 框架
- **Faster Whisper**: 语音识别 (ASR)
- **Pyannote Audio**: 说话人分离和音频处理
- **PaddleOCR**: 光学字符识别
- **Audio Separator**: 人声/伴奏分离
- **IndexTTS**: 文本转语音
- **GPT-SoVITS**: 语音克隆
- **FFmpeg**: 音视频编解码和处理

### 基础设施
- **CUDA 11.x+**: GPU 加速计算
- **NVIDIA RTX 系列 GPU**: 推荐硬件
- **Prometheus**: 指标收集
- **Grafana**: 可视化监控面板

### 开发工具
- **pytest**: 单元测试和集成测试
- **black/flake8**: 代码格式化和检查
- **mypy**: 静态类型检查

## Project Conventions

### Code Style

**命名规范**:
- **文件名**: 使用 `snake_case`（如 `task_manager.py`）
- **类名**: 使用 `PascalCase`（如 `WorkflowEngine`）
- **函数/变量**: 使用 `snake_case`（如 `process_video`）
- **常量**: 使用 `UPPER_SNAKE_CASE`（如 `MAX_RETRY_COUNT`）

**代码组织**:
```
services/
├── api_gateway/          # API 网关服务
├── workers/              # AI Worker 服务
│   ├── faster_whisper_service/
│   ├── pyannote_audio_service/
│   └── ...
└── common/               # 共享组件和工具
    ├── locks.py         # GPU 锁管理
    ├── state_manager.py # 状态管理
    └── ...
```

**代码注释**:
- 中文注释优先（与现有代码库保持一致）
- 复杂逻辑必须添加解释性注释
- 公共 API 必须包含 docstring

**格式化**:
- 使用 black 格式化工具
- 行长度限制：100 字符
- 使用 4 空格缩进

### Architecture Patterns

**微服务架构**:
- 每个 AI 功能独立部署为 Celery Worker 服务
- 服务间通过 Redis 消息队列通信
- 使用共享存储 `/share` 进行文件交换

**工作流编排**:
- 动态工作流引擎，通过 JSON 配置定义处理流程
- 标准化任务接口：`def standard_task_interface(self: Task, context: dict) -> dict`
- 工作流上下文在所有任务间传递统一的 JSON 字典

**GPU 资源管理**:
- 基于 Redis 的分布式 GPU 锁系统
- 支持智能轮询、超时管理、自动恢复
- 装饰器模式：`@gpu_lock(timeout=1800, poll_interval=0.5)`

**状态管理**:
- 集中式状态管理器（StateManager）
- Redis 存储工作流状态，支持 TTL 自动过期
- 实时监控和健康检查

**配置管理**:
- 配置文件：`config.yml`（主配置）+ `.env`（环境变量）
- 支持环境变量覆盖配置项
- 敏感信息使用环境变量或加密存储

### Testing Strategy

**测试金字塔**:
```
         /\
        /E2E\      端到端测试（少量）
       /------\
      /  集成  \    集成测试（适量）
     /----------\
    /   单元测试  \  单元测试（大量）
   /--------------\
```

**单元测试** (`tests/unit/`):
- Mock 所有外部依赖（Redis、GPU、文件系统）
- 测试纯业务逻辑和算法
- 使用 `@pytest.mark.unit` 标记

**集成测试** (`tests/integration/`):
- 使用真实基础设施（Redis、文件系统）
- 测试单个服务内部组件交互
- GPU 任务在 CPU 模式下运行或使用专用 GPU Runner
- 使用 `@pytest.mark.integration` 标记

**端到端测试** (`tests/e2e/`):
- 完整业务流程测试，模拟真实用户场景
- 测试跨服务工作流
- 使用 `@pytest.mark.e2e` 标记

**GPU 测试**:
- 使用 `@pytest.mark.gpu` 标记 GPU 相关测试
- 单元测试层严格使用 Mock，不触碰 GPU
- CI/CD 中 GPU 测试为可选执行

### Git Workflow

**分支策略**:
- `master`: 主分支，稳定生产版本
- `task/<feature-name>_<date>_<id>`: 功能分支（如 `task/redundant-code-analysis_20251111_001`）
- `hotfix/<issue-name>`: 紧急修复分支

**提交规范**:
使用约定式提交（Conventional Commits）格式：
```
<type>(<scope>): <subject>

<body>

<footer>
```

**类型**:
- `feat`: 新功能
- `fix`: 错误修复
- `refactor`: 重构（不改变功能）
- `perf`: 性能优化
- `docs`: 文档更新
- `test`: 测试相关
- `chore`: 构建/工具链更新

**示例**:
```
feat(whisper): 增加批量处理支持

- 添加批量音频处理接口
- 优化 GPU 内存使用
- 更新相关文档

Closes #123
```

**Pull Request**:
- 必须通过所有单元测试和集成测试
- 必须经过代码审查
- 更新相关文档（如修改了 API 或配置）

## Domain Context

**AI 视频处理领域**:
- 视频处理流程：提取音频 → ASR 识别 → 说话人分离 → 字幕生成 → OCR 识别 → 字幕合并 → AI 优化
- 音频处理：人声分离、音频增强、语音合成
- 字幕处理：时间轴对齐、格式转换、多语言支持

**工作流概念**:
- **工作流 (Workflow)**: 由多个阶段组成的完整处理流程
- **阶段 (Stage)**: 工作流中的一个处理步骤
- **任务 (Task)**: Celery 任务，执行具体的 AI 处理
- **上下文 (Context)**: 工作流执行过程中传递的状态和数据

**GPU 资源管理**:
- **GPU 锁 (GPU Lock)**: 防止多任务同时使用同一 GPU 导致 OOM
- **轮询 (Polling)**: 任务等待 GPU 资源释放的策略
- **心跳 (Heartbeat)**: 任务存活状态检测机制
- **超时管理 (Timeout)**: 分级超时处理（警告/软超时/硬超时）

**字幕处理**:
- **ASR 字幕**: 语音识别生成的原始字幕
- **OCR 字幕**: 视频画面中识别的文字
- **字幕合并**: 融合多个来源的字幕
- **字幕校正**: 使用 LLM 优化字幕质量（断句、错别字、语义）

## Important Constraints

### 技术约束
- **GPU 内存限制**: 单个 GPU 同一时间只能运行一个密集型任务
- **并发限制**: Celery Worker 并发数受 GPU 数量限制
- **模型加载**: 首次加载模型耗时较长，需要缓存策略
- **文件大小**: 支持的最大视频文件大小受存储空间限制

### 性能约束
- **实时性要求**: 字幕生成需要在合理时间内完成（通常 < 视频时长）
- **内存使用**: 避免一次性加载大文件到内存
- **批处理大小**: 需要根据 GPU 内存动态调整 batch_size

### 安全约束
- **容器安全**: 所有容器使用非 root 用户运行
- **API 认证**: 生产环境必须启用 JWT 认证
- **速率限制**: API 接口配置速率限制防止滥用
- **敏感数据**: 所有敏感配置使用环境变量或加密存储

### 兼容性约束
- **Python 版本**: 3.8+
- **CUDA 版本**: 11.x+（推荐 11.8）
- **GPU 要求**: NVIDIA RTX 系列（推荐 RTX 3090/4090）
- **操作系统**: Linux（推荐 Ubuntu 20.04/22.04）

## External Dependencies

### AI 模型服务
- **HuggingFace**: 模型下载和托管
  - faster-whisper 系列模型
  - pyannote-audio 模型
  - 需要配置 HuggingFace token

### 第三方 API（可选）
- **OpenAI API**: 字幕 AI 优化（GPT 系列）
- **Google Gemini API**: 字幕校正和翻译
- **百度 AI**: 备用语音识别和 NLP 服务

### 基础服务
- **Redis**: 消息队列、缓存、锁、状态存储
- **共享存储**: NFS 或本地共享目录 `/share`
- **Docker Registry**: 镜像存储和分发

### 监控和日志
- **Prometheus**: 指标采集和存储
- **Grafana**: 监控仪表板
- **ELK Stack**（可选）: 日志聚合和分析

### 开发依赖
- **GitHub**: 代码托管和版本控制
- **Docker Hub**: 公共镜像拉取
- **PyPI**: Python 包管理
