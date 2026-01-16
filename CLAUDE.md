# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

YiVideo 是一个动态、可配置的 AI 视频处理工作流引擎。核心理念是"配置而非编码"——通过 workflow_config 动态编排 Celery 任务链，组合 ASR/OCR/LLM/TTS 等原子能力，无需修改服务端代码。

**技术栈:**

-   Python 3.11+ + FastAPI (API 网关)
-   Celery + Redis (任务编排与状态存储)
-   MinIO (产物存储)
-   Docker Compose (服务编排)
-   CUDA + GPU 支持

## 架构与核心概念

### 服务分层

```
API Gateway (FastAPI)
    ↓ 动态构建任务链
Celery Broker (Redis)
    ↓ 任务分发
Worker Services (Celery):
    - ffmpeg_service: 视频/音频处理
    - faster_whisper_service: 语音识别 (ASR)
    - paddleocr_service: 光学字符识别 (OCR)
    - pyannote_audio_service: 说话人分离
    - wservice: 字幕生成与优化
    - indextts_service / gptsovits_service: 文本转语音 (TTS)
    - audio_separator_service: 音频分离
    - inpainting_service: 视频修复
```

### 核心抽象

**WorkflowContext** (`services/common/context.py`): 标准化的工作流上下文，在整个工作流生命周期中传递和修改，包含:

-   `workflow_id`: 工作流唯一标识
-   `input_params`: 输入参数
-   `shared_storage_path`: 共享存储路径
-   `stages`: 各阶段执行结果 (Dict)
-   `error`: 错误信息

**BaseNodeExecutor** (`services/common/base_node_executor.py`): 所有节点执行器的抽象基类，子类必须实现:

-   `validate_input()`: 验证输入参数
-   `execute_core_logic()`: 执行核心业务逻辑
-   `get_cache_key_fields()`: 返回缓存键字段列表

### 关键设计模式

1. **标准任务接口**: 所有 Celery 任务统一签名 `task(self: Task, context: dict) -> dict`
2. **GPU 锁管理**: 通过 `@gpu_lock()` 装饰器实现 GPU 资源竞争控制
3. **状态复用**: 基于 task_id + task_name 的缓存机制，避免重复计算
4. **MinIO 上传去重**: 通过内容哈希避免重复上传相同文件

## 常用命令

### 构建与运行

```bash
# 构建所有服务镜像
docker-compose build

# 启动堆栈 (网关映射到 8788 端口)
docker-compose up -d

# 查看特定服务日志
docker-compose logs -f api_gateway
docker-compose logs -f faster_whisper_service

# 停止容器 (保留卷)
docker-compose down
```

### 测试

```bash
# 运行所有测试
pytest tests

# 运行单个测试文件
pytest tests/unit/common/test_node_response_validator.py

# 运行单个测试方法
pytest tests/unit/common/test_node_response_validator.py::TestNodeResponseValidator::test_valid_response

# 仅运行 GPU 标记的测试
pytest -m gpu

# 详细输出模式
pytest -v -s

# 仅运行上次失败的测试
pytest --lf
```

### 代码质量

```bash
# 格式化代码 (行长 100)
black --line-length 100 <file>

# 检查代码风格
flake8 <file>

# 安装依赖
pip install -r requirements.txt
```

## 配置管理

### 配置层级

1. **config.yml**: 运行时配置 (Redis DB 分配、工作流 TTL、自动上传等)
2. **.env**: 环境变量 (Redis/MinIO 连接信息、API 密钥)
3. **docker-compose.yml**: 服务编排 (使用 YAML 锚点实现模块化)

### Redis DB 分配

-   DB 0: Celery Broker
-   DB 1: Celery Backend
-   DB 2: 分布式锁
-   DB 3: 工作流状态存储

### 关键环境变量

```bash
# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# MinIO
MINIO_HOST=minio
MINIO_PORT=9000
MINIO_ACCESS_KEY=<access_key>
MINIO_SECRET_KEY=<secret_key>

# AI 服务 API 密钥
GEMINI_API_KEY=<key>
DEEPSEEK_API_KEY=<key>
ZHIPU_API_KEY=<key>
HF_TOKEN=<token>
```

## 开发工作流

### 添加新的 Worker 节点

1. 在 `services/workers/<service_name>/` 创建服务目录
2. 从 `BaseNodeExecutor` 继承创建 Executor 类
3. 在 `app/tasks.py` 定义 Celery 任务 (使用 `@celery_app.task` 装饰器)
4. 添加 Dockerfile (基于 `Dockerfile.base`)
5. 在 `docker-compose.yml` 添加服务定义
6. 更新 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`

### 单任务 API 调用流程

```python
# POST /v1/tasks
{
  "task_name": "ffmpeg.extract_audio",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook",
  "input_data": {
    "video_path": "http://localhost:9000/yivideo/demo.mp4"
  }
}
```

系统会:

1. 检查 Redis 缓存 (task_id + task_name)
2. 如果命中且成功，直接回调并返回缓存结果
3. 否则调度 Celery 任务执行
4. 任务完成后自动回调 (如果提供了 callback URL)

## 重要约定

### 代码风格

-   **格式化**: Black (行长 100)
-   **类型提示**: 必须使用 Python 3.8+ 类型注解
-   **文档字符串**: Google 风格
-   **命名**:
    -   类: `PascalCase`
    -   函数/变量: `snake_case`
    -   常量: `UPPER_SNAKE_CASE`
    -   私有成员: `_prefix`

### 错误处理

-   使用具体异常类型 (避免裸 `except:`)
-   验证输入时抛出 `ValueError`
-   记录异常上下文: `logger.error(f"...", exc_info=True)`

### GPU 资源管理

-   所有 GPU 任务必须使用 `@gpu_lock()` 装饰器
-   默认超时 600 秒，可通过参数调整: `@gpu_lock(timeout=1800)`
-   锁存储在 Redis DB2，支持监控和自动恢复

### 文件路径约定

-   **输入**: MinIO URL 或本地路径 (`/app/videos/`, `/share/`)
-   **临时文件**: `/app/tmp/<task_id>/`
-   **输出**: 自动上传到 MinIO 并生成 `*_minio_url` 字段

## 自定义 Skills

项目提供以下 Claude Code skills (位于 `.claude/skills/`):

-   **mcp-tools-orchestrator**: 自动编排 YiVideo 场景下的 MCP servers
-   **research-mode**: 证据驱动的需求分析与落地执行专家模式
-   **yivideo-conventional-commits**: 生成规范的 Git commit message 和 PR 描述
-   **yivideo-docker-testing**: 在 Docker 容器内执行测试和调试

## 参考文档

-   **API 参考**: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
-   **工作流示例**: `docs/technical/reference/WORKFLOW_EXAMPLES_GUIDE.md`
-   **GPU 锁指南**: `docs/technical/reference/GPU_LOCK_COMPLETE_GUIDE.md`

## 🏛️ 全局架构约束 (Principles)

所有重构和设计任务必须通过以下过滤网：

1. **KISS (保持简单)**：如果简单的 `if/else` 能工作，严禁引入复杂的工厂模式或策略模式。
2. **DRY (拒绝重复)**：看到重复代码，必须提取为 Utility 或 Mixin。
3. **YAGNI (拒绝过度设计)**：只写当前需要的代码，不要为未来写"钩子"。
4. **SOLID**：特别是 **单一职责 (SRP)** —— 每个 Worker 只做一件事。

**违规检查**：在输出代码前，自问："我是否把事情搞复杂了？" 如果是，**请重写**。
