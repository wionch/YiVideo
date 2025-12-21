<!-- OPENSPEC:START -->

# OpenSpec 说明

这些说明适用于参与本项目的 AI 助手。

当请求中包含以下内容时，请务必打开 `@/openspec/AGENTS.md`：

-   提及计划或提案（如 proposal, spec, change, plan 等词汇）
-   引入新功能、破坏性变更、架构调整或重大的性能/安全工作
-   内容模棱两可，你在编码前需要权威的规范

使用 `@/openspec/AGENTS.md` 来了解：

-   如何创建和应用变更提案
-   规范的格式和惯例
-   项目结构和准则

请保留此托管块，以便 'openspec update' 可以刷新说明。

<!-- OPENSPEC:END -->

# GEMINI.md

本文件为 Gemini Code (gemini.ai/code) 处理本仓库代码时提供指导。

## 项目概览

**YiVideo** 是一个基于动态工作流引擎和微服务架构的 AI 视频处理平台。核心理念是“配置优于编码”——AI 处理流水线通过工作流配置文件动态构建。

### 核心特性

-   **自动语音识别 (ASR)**: 基于 Faster-Whisper 的高精度语音转文本
-   **说话人分离 (Speaker Diarization)**: 使用 Pyannote-audio 进行多说话人识别和分离
-   **光学字符识别 (OCR)**: 通过 PaddleOCR 进行字幕区域检测和文本识别
-   **音频处理**: 人声/背景声分离和音频增强
-   **字幕处理**: AI 驱动的字幕生成、校对、优化和合并
-   **文本转语音 (TTS)**: 多引擎高质量语音合成
-   **视频处理**: 基于 FFmpeg 的视频编辑和格式转换

## 项目结构

```
yivideo/
├── services/                    # 微服务目录
│   ├── api_gateway/             # API 网关 - 统一入口点
│   ├── common/                  # 通用模块（状态管理、工具类）
│   └── workers/                 # Celery Worker 服务
│       ├── faster_whisper_service/   # ASR 语音识别
│       ├── pyannote_audio_service/   # 说话人分离
│       ├── paddleocr_service/        # OCR 文本识别
│       ├── audio_separator_service/  # 音频分离
│       ├── ffmpeg_service/           # 视频处理
│       ├── indextts_service/         # TTS 语音合成
│       ├── gptsovits_service/        # GPT-SoVITS TTS
│       ├── inpainting_service/       # 视频修复 (Inpainting)
│       └── wservice/                 # 通用工作流服务
├── config/                      # 配置文件
├── config.yml                   # 主配置文件
├── docker-compose.yml           # 容器编排
├── docs/                        # 项目文档
├── openspec/                    # OpenSpec 规范
├── tests/                       # 测试目录
├── share/                       # 服务间共享存储
└── scripts/                     # 实用脚本
```

## 技术栈

### 后端框架与服务

-   **Python 3.8+**: 主要编程语言
-   **FastAPI**: API 网关的 HTTP 服务框架
-   **Celery 5.x**: 分布式任务队列和工作流引擎
-   **Redis**: 多用途数据存储 (DB0: Broker, DB1: Backend, DB2: Locks, DB3: State)

### AI/ML 模型与库

-   **Faster-Whisper**: GPU 加速的语音识别
-   **Pyannote-audio**: 说话人分离和声纹识别
-   **PaddleOCR**: 中英文 OCR 识别
-   **Audio-Separator**: 音频源分离
-   **IndexTTS / GPT-SoVITS**: TTS 引擎

### 基础设施

-   **Docker & Docker Compose**: 容器化部署
-   **FFmpeg**: 音视频处理
-   **MinIO**: 对象存储服务
-   **CUDA 11.x+**: GPU 加速支持

## 开发命令

```
# 容器管理
docker-compose up -d              # 启动所有服务
docker-compose ps                 # 检查服务状态
docker-compose logs -f <service>  # 查看日志

# 测试
pytest tests/unit/                # 单元测试
pytest tests/integration/         # 集成测试
pytest -m gpu                     # GPU 测试
```

## 全局架构约束

**关键**: 在所有代码生成、重构和设计任务中，你必须严格遵守这些原则。

### 1. KISS (Keep It Simple, Stupid) - 保持简单

-   **规则**: 优先选择最简单的实现路径。避免过度设计。
-   **触发条件**: 如果代码需要复杂的注释来解释，或者为简单的逻辑使用了设计模式（如策略/工厂模式）。
-   **指令**: “如果简单的 `if/else` 能解决问题，就不要使用复杂的模式。” 保持低认知负荷。

### 2. DRY (Don't Repeat Yourself) - 不要重复自己

-   **规则**: 每一段逻辑都必须有单一、明确的表示。
-   **触发条件**: 重复的逻辑块、复制粘贴的代码或重复的魔术值。
-   **指令**: 将重复的逻辑提取到工具函数或常量中。_注意：避免过早抽象从而损害可读性。_

### 3. YAGNI (You Ain't Gonna Need It) - 你不会需要它

-   **规则**: 仅实现当前规范/任务中明确要求的内容。
-   **触发条件**: 为未来功能添加“钩子”、未使用的配置选项或额外的接口方法。
-   **指令**: “只编写通过当前测试所需的代码。” 不要推测未来的需求。

### 4. SOLID (面向对象设计)

-   **SRP**: 单一职责原则 (一个改变的理由)。
-   **OCP**: 开闭原则 (对扩展开放，对修改关闭)。
-   **LSP**: 里氏替换原则 (子类型必须可替换)。
-   **ISP**: 接口隔离原则 (不强制依赖未使用的方法)。
-   **DIP**: 依赖倒置原则 (依赖于抽象)。

### 违规检查 (自我纠正)

在输出任何代码之前，请执行此内部检查：

1. 这是最简单的方法吗？(KISS)
2. 我是否添加了未使用的功能？(YAGNI)
3. 逻辑是否重复？(DRY)
4. 是否违反了 SOLID 原则？

**在响应之前立即修复任何违规行为。**

## 代码风格指南

-   **格式化**: Black (line-length=100), Flake8
-   **命名**: 类 `PascalCase`, 函数 `snake_case`, 常量 `UPPER_SNAKE_CASE`
-   **文档**: Google 风格的 docstrings, Python 3.8+ 类型注解
-   **注释语言**: 保持与现有代码库一致

## 架构模式

-   **API 网关模式**: 请求路由和工作流编排的统一入口点
-   **Worker 模式**: 每个 AI 能力作为独立的 Celery Worker 隔离
-   **共享存储**: `/share` 目录用于服务间文件交换
-   **状态管理**: 集中式 StateManager

## Git 工作流

使用 Conventional Commits: `<type>(<scope>): <subject>`

**类型**: `feat` | `fix` | `refactor` | `docs` | `test` | `chore` | `perf`

**重要**: 未经用户明确请求，不要自动执行 git commit/push 操作。
