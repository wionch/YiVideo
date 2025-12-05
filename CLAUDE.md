<!-- OPENSPEC:START -->

# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:

-   Mentions planning or proposals (words like proposal, spec, change, plan)
-   Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
-   Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:

-   How to create and apply change proposals
-   Spec format and conventions
-   Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Global Architectural Constraints

**CRITICAL**: You must strictly adhere to these principles for all code generation, refactoring, and design tasks.

### 1. KISS (Keep It Simple, Stupid)

-   **Rule**: Prioritize the simplest implementation path. Avoid over-engineering.
-   **Trigger**: If the code requires complex comments to explain or uses design patterns (like Strategy/Factory) for simple logic.
-   **Directive**: "If a simple `if/else` works, do not use a complex pattern." Keep the cognitive load low.

### 2. DRY (Don't Repeat Yourself)

-   **Rule**: Every piece of logic must have a single, unambiguous representation.
-   **Trigger**: Repeated logic blocks, copy-pasted code, or duplicate magic values.
-   **Directive**: Extract repeated logic into utility functions or constants. _Note: Avoid premature abstraction that hurts readability._

### 3. YAGNI (You Ain't Gonna Need It)

-   **Rule**: Implement ONLY what is explicitly requested in the current Spec/Task.
-   **Trigger**: Adding "hooks" for future features, unused configuration options, or extra interface methods.
-   **Directive**: "Write only the code needed to pass the current tests." Do not speculate on future requirements.

### 4. SOLID (Object-Oriented Design)

-   **SRP**: Single Responsibility Principle (One reason to change).
-   **OCP**: Open/Closed Principle (Extend without modifying).
-   **LSP**: Liskov Substitution Principle (Subtypes must be substitutable).
-   **ISP**: Interface Segregation Principle (No forced dependencies on unused methods).
-   **DIP**: Dependency Inversion Principle (Depend on abstractions).

### Violation Check (Self-Correction)

Before outputting any code, perform this internal check:

1. Is this the simplest way? (KISS)
2. Did I add unused features? (YAGNI)
3. Is logic duplicated? (DRY)
4. Does it violate SOLID?
   **Fix any violations immediately before responding.**

## 项目架构图

```mermaid
graph TB
    %% 用户层
    User[👤 用户] -->|HTTP请求| API[API Gateway<br/>端口8000]

    %% 核心服务层
    API -->|工作流调度| Redis[(Redis<br/>多数据库架构)]
    API -->|状态管理| SM[State Manager]
    API -->|监控| Mon[Monitoring]

    %% 微服务层
    API -->|Celery任务| Workers[AI Workers]

    %% Workers子服务
    Workers --> FF[FFmpeg Service<br/>视频/音频处理]
    Workers --> FW[Faster Whisper<br/>语音识别]
    Workers --> PA[Pyannote Audio<br/>说话人分离]
    Workers --> PO[PaddleOCR<br/>文字识别]
    Workers --> AS[Audio Separator<br/>人声分离]
    Workers --> TTS[IndexTTS<br/>文本转语音]
    Workers --> GPT[GPT-SoVITS<br/>语音克隆]
    Workers --> IP[Inpainting<br/>图像修复]
    Workers --> WS[WService<br/>字幕AI优化]

    %% 共享组件
    SM -->|共享| Common[Common Module]
    Common -->|日志| Logger[Logger]
    Common -->|锁机制| Locks[GPU Locks]
    Common -->|配置| Config[Config Loader]
    Common -->|字幕| Sub[Subtitle Module]

    %% 存储层
    Redis -->|DB 0| Broker[Broker<br/>任务队列]
    Redis -->|DB 1| Backend[Backend<br/>结果存储]
    Redis -->|DB 2| LockDB[Locks<br/>分布式锁]
    Redis -->|DB 3| StateDB[States<br/>工作流状态]

    Share[/share<br/>共享存储] -->|文件交换| Workers

    %% 监控层
    Mon -->|指标| Prom[Prometheus]
    Mon -->|可视化| Graf[Grafana]

    %% 子图：共享组件详细
    subgraph Common [Common Module - 共享组件]
        Logger
        Locks
        Config
        Sub
    end

    %% 子图：字幕处理子模块
    subgraph Sub [Subtitle Module - 字幕处理]
        AICmd[AI Command Parser]
        AIProv[AI Providers]
        CmdExe[Command Executor]
        SubOpt[Subtitle Optimizer]
        SubMerge[Subtitle Merger]
    end

    %% 样式
    classDef userClass fill:#e1f5fe
    classDef serviceClass fill:#f3e5f5
    classDef workerClass fill:#e8f5e9
    classDef storageClass fill:#fff3e0
    classDef monitorClass fill:#fce4ec

    class User userClass
    class API,Mon serviceClass
    class Workers,FF,FW,PA,PO,AS,TTS,GP,IP,WS workerClass
    class Redis,Share storageClass
    class Prom,Graf monitorClass
```

## 项目概述

YiVideo 是一个基于动态工作流引擎的 AI 视频处理平台，采用微服务架构设计。系统核心思想是"配置而非编码"，通过工作流配置文件动态构建 AI 处理链条，支持语音识别、OCR、字幕处理、音频分离、文本转语音等多种 AI 功能的灵活组合。

## 核心架构

### 微服务组件

-   **api_gateway**: 系统总入口和大脑，负责 HTTP 请求处理、工作流动态构建、状态管理
-   **AI Workers**: 独立的 Celery worker 服务
    -   `ffmpeg_service`: 视频处理、音频提取和分割
    -   `faster_whisper_service`: 语音识别(ASR)，基于 faster-whisper，仅 GPU 推理功能
    -   `pyannote_audio_service`: 说话人分离，基于 pyannote-audio 独立部署
    -   `paddleocr_service`: 光学字符识别(OCR)
    -   `audio_separator_service`: 人声/背景音分离
    -   `indextts_service`: 文本转语音(TTS)
    -   `wservice`: 字幕 AI 优化服务，负责字幕生成、合并、校正等非 GPU 任务

### 基础设施

-   **Redis**: 作为 Celery 消息队列、状态存储、分布式锁和缓存
-   **共享存储**: `/share`目录用于所有服务间的文件共享
-   **GPU 锁系统**: 基于 Redis 的分布式 GPU 资源管理，支持智能轮询和自动恢复

## 模块索引

本项目已建立完整的 AI 上下文索引，各模块文档位置如下：

### 📋 主要模块文档

-   **根目录**: [`/mnt/d/WSL2/docker/YiVideo/CLAUDE.md`](./CLAUDE.md) - 项目整体架构、开发和运维指南
-   **API 网关**: [`/mnt/d/WSL2/docker/YiVideo/services/api_gateway/CLAUDE.md`](./services/api_gateway/CLAUDE.md) - API 接口、工作流管理、监控
-   **共享组件**: [`/mnt/d/WSL2/docker/YiVideo/services/common/CLAUDE.md`](./services/common/CLAUDE.md) - 状态管理、GPU 锁、日志、配置、字幕处理

### 🤖 Worker 服务文档

-   **FFmpeg 服务**: [`/mnt/d/WSL2/docker/YiVideo/services/workers/ffmpeg_service/CLAUDE.md`](./services/workers/ffmpeg_service/CLAUDE.md) - 视频/音频处理
-   **Faster Whisper**: [`/mnt/d/WSL2/docker/YiVideo/services/workers/faster_whisper_service/CLAUDE.md`](./services/workers/faster_whisper_service/CLAUDE.md) - 语音识别(ASR)
-   **Pyannote Audio**: [`/mnt/d/WSL2/docker/YiVideo/services/workers/pyannote_audio_service/CLAUDE.md`](./services/workers/pyannote_audio_service/CLAUDE.md) - 说话人分离
-   **PaddleOCR**: [`/mnt/d/WSL2/docker/YiVideo/services/workers/paddleocr_service/CLAUDE.md`](./services/workers/paddleocr_service/CLAUDE.md) - 光学字符识别
-   **Audio Separator**: [`/mnt/d/WSL2/docker/YiVideo/services/workers/audio_separator_service/CLAUDE.md`](./services/workers/audio_separator_service/CLAUDE.md) - 人声/伴奏分离
-   **IndexTTS**: [`/mnt/d/WSL2/docker/YiVideo/services/workers/indextts_service/CLAUDE.md`](./services/workers/indextts_service/CLAUDE.md) - 文本转语音
-   **GPT-SoVITS**: [`/mnt/d/WSL2/docker/YiVideo/services/workers/gptsovits_service/CLAUDE.md`](./services/workers/gptsovits_service/CLAUDE.md) - 语音克隆
-   **Inpainting**: [`/mnt/d/WSL2/docker/YiVideo/services/workers/inpainting_service/CLAUDE.md`](./services/workers/inpainting_service/CLAUDE.md) - 图像修复
-   **WService**: [`/mnt/d/WSL2/docker/YiVideo/services/workers/wservice/CLAUDE.md`](./services/workers/wservice/CLAUDE.md) - 字幕 AI 优化

### ✨ 特性

-   📊 **已生成 Mermaid 结构图** - 完整展示系统架构和模块关系
-   🧭 **已为 12 个模块添加导航面包屑** - 每个模块文档都包含清晰的导航路径
-   📚 **详细文档** - 包含 API 接口、配置参数、使用示例、最佳实践
-   🔗 **交叉引用** - 模块间相互引用，便于快速定位相关功能

## 常用开发命令

### Docker 服务管理

```bash
# 构建所有服务
docker-compose build

# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看特定服务日志
docker-compose logs -f api_gateway
docker-compose logs -f faster_whisper_service
docker-compose logs -f pyannote_audio_service

# 重启特定服务
docker-compose restart faster_whisper_service
docker-compose restart pyannote_audio_service

# 停止所有服务
docker-compose down
```

### 开发和调试

```bash
# 检查Redis状态
docker-compose exec redis redis-cli ping

# 查看工作流状态
docker-compose exec api_gateway python -c "
import redis
r = redis.Redis(host='redis', db=3)
keys = r.keys('workflow_state:*')
print(f'Active workflows: {len(keys)}')"

# 检查GPU锁状态
docker-compose exec api_gateway python -c "
import redis
r = redis.Redis(host='redis', db=2)
locks = r.keys('gpu_lock:*')
print(f'Active GPU locks: {len(locks)}')"
```

### 测试命令

```bash
# 运行单元测试（在服务容器内）
docker-compose exec api_gateway pytest tests/unit/

# 运行集成测试
docker-compose exec api_gateway pytest tests/integration/

# 运行端到端测试
docker-compose exec api_gateway pytest tests/e2e/
```

## 工作流配置系统

### 标准工作流接口

-   **端点**: `POST /v1/workflows`
-   **工作流上下文**: 所有任务间传递统一的 JSON 字典，包含 workflow_id、input_params、stages、error 等字段
-   **标准化任务接口**: 所有 Celery 任务使用`def standard_task_interface(self: Task, context: dict) -> dict:`签名

### 工作流配置示例

```json
{
    "video_path": "/share/videos/input/example.mp4",
    "workflow_config": {
        "subtitle_generation": {
            "strategy": "asr",
            "provider": "faster_whisper"
        },
        "subtitle_refinement": {
            "strategy": "llm_proofread",
            "provider": "gemini"
        }
    }
}
```

## GPU 资源管理

### GPU 锁装饰器使用

```python
from services.common.locks import gpu_lock

@gpu_lock(timeout=1800, poll_interval=0.5)
def gpu_intensive_task(self, context):
    # GPU密集型任务代码
    pass
```

### GPU 锁监控

系统集成了完整的 GPU 锁监控和自动恢复机制：

-   **GPULockMonitor**: 主动监控锁状态，定期健康检查
-   **TaskHeartbeatManager**: 管理任务心跳，检测任务存活状态
-   **TimeoutManager**: 分级超时处理（警告/软超时/硬超时）
-   **监控 API**: 完整的 RESTful API 接口用于查询监控信息

## 配置文件结构

### 主要配置文件

-   `config.yml`: 主配置文件，包含所有服务配置项
-   `docker-compose.yml`: Docker 服务编排配置
-   `.env`: 环境变量配置（不提交到版本控制）

### 关键配置项

-   **Redis 配置**: 多数据库分离使用（broker:0, backend:1, locks:2, state:3）
-   **语音识别配置**: faster_whisper 模型选择、GPU 加速、参数优化
-   **说话人分离配置**: pyannote-audio 模型选择、GPU 加速、说话人数量设置
-   **OCR 配置**: PaddleOCR 参数优化、多语言支持
-   **GPU 锁配置**: 轮询间隔、超时设置、指数退避

## 开发规范

### 代码组织

-   `services/`: 所有微服务代码
    -   `api_gateway/`: API 网关服务
    -   `workers/`: AI worker 服务
    -   `common/`: 共享组件和工具
-   `tests/`: 测试代码，按单元/集成/E2E 分层
-   `docs/`: 项目文档

### 测试策略

遵循测试金字塔原则：

-   **单元测试**: Mock 所有外部依赖，测试纯业务逻辑
-   **集成测试**: 使用真实基础设施，测试单个服务内部交互
-   **端到端测试**: 完整业务流程测试，模拟真实用户场景

### GPU 任务测试

-   单元测试层严格使用 Mock，不触碰 GPU
-   集成测试层可在 CPU 模式下运行或使用专用 GPU Runner
-   使用`@pytest.mark.gpu`标记 GPU 相关测试

## 文件系统和存储

### 目录结构

-   `/share/`: 服务间共享存储
-   `/videos/`: 视频文件存储
-   `/locks/`: GPU 锁文件存储
-   `/tmp/`: 临时文件存储
-   `/models/`: AI 模型文件存储

### 工作流数据管理

-   每个工作流创建独立的临时目录
-   支持配置自动清理临时文件
-   Redis 中存储工作流状态，设置 TTL 自动过期

## 监控和运维

### 监控组件

-   **Prometheus**: 指标收集
-   **Grafana**: 可视化监控面板
-   **GPU 锁监控**: 实时监控 GPU 资源使用和锁状态

### 日志管理

-   所有服务使用统一日志格式
-   支持结构化日志输出
-   配置日志轮转和清理策略

### 健康检查

每个服务都提供健康检查端点，支持容器级别的健康检查配置。

## 部署和运维

### 生产环境部署

参考 `docs/deployment/DEPLOYMENT_GUIDE.md` 进行完整的生产环境部署。

### 常见运维操作

-   **服务重启**: `docker-compose restart <service_name>`
-   **清理资源**: `docker system prune -f`
-   **备份 Redis**: `docker-compose exec redis redis-cli --rdb backup.rdb`

## 故障排除

### 常见问题

1. **GPU 锁死锁**: 检查 GPU 锁监控状态，使用自动恢复机制
2. **内存不足**: 调整 batch_size 和 worker_processes 配置
3. **模型下载失败**: 检查网络连接和 HuggingFace token 配置

### 调试技巧

-   使用`docker-compose logs`查看服务日志
-   检查 Redis 中的工作流状态和 GPU 锁状态
-   使用 nvidia-smi 监控 GPU 使用情况

## API 接口

### 主要端点

-   `POST /v1/workflows`: 创建和执行工作流
-   `GET /v1/workflows/{workflow_id}`: 查询工作流状态
-   `GET /v1/gpu-locks/status`: 查询 GPU 锁状态
-   `GET /health`: 健康检查

### 响应格式

所有 API 响应使用统一的 JSON 格式，包含 success、data、error 等字段。

## 注意事项

### 安全考虑

-   所有敏感配置使用环境变量或加密存储
-   API 接口支持 JWT 认证和速率限制
-   容器运行使用非 root 用户

### 性能优化

-   使用 GPU 锁避免资源冲突
-   配置适当的并发数和批处理大小
-   启用模型缓存和量化

### 兼容性

-   支持 CUDA 11.x+
-   推荐使用 NVIDIA RTX 系列 GPU
-   Python 版本：3.8+
