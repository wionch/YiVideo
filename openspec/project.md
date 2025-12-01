# Project Context

## Purpose

YiVideo 是一个基于动态工作流引擎的AI视频处理平台，采用微服务架构设计。系统核心思想是"配置而非编码"，通过工作流配置文件动态构建AI处理链条，支持以下核心功能：

- **语音识别 (ASR)**: 基于 Faster-Whisper 的高精度语音转文字
- **说话人分离**: 基于 Pyannote-audio 的多说话人识别和分离
- **光学字符识别 (OCR)**: 基于 PaddleOCR 的字幕区域检测和文字识别
- **音频处理**: 人声/背景音分离、音频增强
- **字幕处理**: AI驱动的字幕生成、校对、优化、合并
- **文本转语音 (TTS)**: 多引擎支持的高质量语音合成
- **视频处理**: 基于 FFmpeg 的视频编辑和格式转换

## Tech Stack

### 后端框架与服务
- **Python 3.8+**: 主要编程语言
- **FastAPI**: API Gateway 的 HTTP 服务框架
- **Celery 5.x**: 分布式任务队列和工作流引擎
- **Redis**: 多用途数据存储
  - DB 0: Celery Broker (任务队列)
  - DB 1: Celery Backend (结果存储)
  - DB 2: 分布式锁系统
  - DB 3: 工作流状态管理

### AI/ML 模型与库
- **Faster-Whisper**: GPU加速语音识别
- **Pyannote-audio**: 说话人分离和声纹识别
- **PaddleOCR**: 中英文OCR识别
- **Audio-Separator**: 音频源分离
- **IndexTTS / GPT-SoVITS**: TTS引擎
- **CUDA 11.x+**: GPU加速支持

### 基础设施
- **Docker & Docker Compose**: 容器化部署
- **FFmpeg**: 音视频处理
- **MinIO**: 对象存储服务
- **Prometheus + Grafana**: 监控和可视化
- **共享存储**: `/share` 目录用于服务间文件交换

### 开发工具
- **Pytest**: 单元测试、集成测试、E2E测试
- **Black / Flake8**: 代码格式化和linting
- **Git**: 版本控制

## Project Conventions

### Code Style

#### Python 代码规范
- **格式化工具**: Black (line-length=100)
- **Linting**: Flake8
- **导入顺序**: 标准库 → 第三方库 → 本地模块
- **命名约定**:
  - 类名: `PascalCase` (例如: `StateManager`, `GPULockMonitor`)
  - 函数/方法: `snake_case` (例如: `process_audio`, `get_workflow_status`)
  - 常量: `UPPER_SNAKE_CASE` (例如: `MAX_RETRY_COUNT`, `DEFAULT_TIMEOUT`)
  - 私有成员: 前缀下划线 `_private_method`
- **文档字符串**: 使用 Google 风格的 docstring
- **类型提示**: 优先使用 Python 3.8+ 类型注解

#### 注释语言
- **代码注释**: 与现有代码库保持一致(自动检测中英文)
- **文档**: 主要使用中文,技术术语保留英文

### Architecture Patterns

#### 微服务架构
- **API Gateway 模式**: 统一入口,负责请求路由和工作流编排
- **Worker 模式**: 每个AI功能独立为 Celery Worker 服务
- **共享存储**: 所有服务通过 `/share` 目录交换文件
- **状态管理**: 集中式状态管理器 (StateManager)

#### 核心设计原则
- **SOLID原则**: 单一职责、开闭原则、依赖倒置
- **KISS (Keep It Simple)**: 追求简洁,拒绝过度设计
- **DRY (Don't Repeat Yourself)**: 避免重复,提取共享组件
- **YAGNI (You Aren't Gonna Need It)**: 仅实现当前所需功能

#### 关键架构模式
- **责任链模式**: 工作流任务链式执行
- **装饰器模式**: GPU锁、日志、监控等横切关注点
- **工厂模式**: 动态任务创建和服务发现
- **观察者模式**: 任务状态变更通知

### Testing Strategy

#### 测试金字塔
```
       E2E Tests (少量)
           ▲
      Integration Tests (适量)
           ▲
      Unit Tests (大量)
```

#### 测试层级
1. **单元测试** (`tests/unit/`)
   - Mock 所有外部依赖 (Redis, 文件系统, GPU)
   - 测试纯业务逻辑
   - 覆盖率目标: >80%
   - 运行速度: 快速 (<5秒)

2. **集成测试** (`tests/integration/`)
   - 使用真实 Redis 和文件系统
   - 测试服务内部模块交互
   - GPU 任务使用 CPU 模式或专用 GPU Runner
   - 使用 `@pytest.mark.gpu` 标记 GPU 测试

3. **端到端测试** (`tests/e2e/`)
   - 完整业务流程测试
   - 模拟真实用户场景
   - 可选择性在 CI/CD 中运行

#### 测试命名约定
- 测试文件: `test_<module_name>.py`
- 测试类: `Test<ClassName>`
- 测试方法: `test_<scenario>_<expected_result>`

### Git Workflow

#### 分支策略
- **master**: 主分支,生产环境代码
- **feature/***: 功能开发分支
- **fix/***: 问题修复分支
- **refactor/***: 代码重构分支

#### Commit 约定
使用 Conventional Commits 规范:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**类型 (type)**:
- `feat`: 新功能
- `fix`: 问题修复
- `refactor`: 代码重构
- `docs`: 文档更新
- `test`: 测试相关
- `chore`: 构建/工具变更
- `perf`: 性能优化

**示例**:
```
feat(paddleocr): add manifest_minio_url field to create_stitched_images

添加manifest_minio_url字段,支持MinIO URL输出

Closes #123
```

#### 代码审查要求
- 所有代码必须经过 PR 审查
- 至少一位团队成员批准
- 通过所有 CI 检查
- **重要**: 未经用户明确要求,不要自动执行 git commit/push

## Domain Context

### AI 视频处理领域知识

#### 语音识别 (ASR) 流程
1. 音频提取 → 2. 降噪预处理 → 3. VAD 检测 → 4. 语音识别 → 5. 时间戳对齐

#### 说话人分离流程
1. 音频分析 → 2. 说话人检测 → 3. 声纹聚类 → 4. 时间轴分割 → 5. 标签标注

#### OCR 字幕处理流程
1. 视频帧提取 → 2. 字幕区域检测 → 3. 文字识别 → 4. 时序去重 → 5. 字幕合并

#### 字幕优化工作流
1. 原始字幕生成 (ASR/OCR)
2. AI 校对 (语法、标点、分段)
3. 时间轴优化 (合并、拆分)
4. 说话人标注
5. 最终输出 (SRT/VTT/ASS)

### 工作流引擎核心概念

#### 工作流上下文 (Context)
统一的 JSON 字典,在所有任务间传递:
```python
{
    "workflow_id": "uuid",
    "input_params": {...},
    "stages": {...},
    "error": None,
    "metadata": {...}
}
```

#### 标准任务接口
所有 Celery 任务使用统一签名:
```python
def standard_task_interface(self: Task, context: dict) -> dict:
    """标准任务接口"""
    pass
```

#### GPU 资源管理
- 基于 Redis 的分布式锁机制
- 智能轮询和指数退避
- 心跳检测和自动恢复
- 分级超时处理

## Important Constraints

### 技术约束
1. **GPU 资源有限**: 需要严格的锁机制避免冲突
2. **内存限制**: 大文件处理需要流式处理,避免一次性加载
3. **存储空间**: 临时文件需要及时清理
4. **网络带宽**: 大文件传输需要断点续传支持

### 业务约束
1. **实时性要求**: 某些任务需要在指定时间内完成
2. **准确性要求**: AI 识别结果需要达到一定准确率阈值
3. **成本控制**: GPU 使用成本,需要优化资源利用率

### 安全约束
1. **敏感配置**: API密钥、Token 必须使用环境变量
2. **文件权限**: 共享存储需要严格的权限控制
3. **容器安全**: 所有容器使用非 root 用户运行

### 兼容性约束
1. **CUDA 版本**: 需要 CUDA 11.x+
2. **GPU 型号**: 推荐 NVIDIA RTX 系列
3. **Python 版本**: 3.8+
4. **平台支持**: Linux (WSL2 支持)

## External Dependencies

### AI 模型依赖
- **Faster-Whisper Models**: HuggingFace Hub (systran/faster-whisper-*)
- **Pyannote Models**: HuggingFace Hub (需要 HF Token)
- **PaddleOCR Models**: 官方模型库
- **TTS Models**: 自托管或第三方服务

### 云服务依赖
- **MinIO**: 对象存储服务 (可替换为 S3)
- **Redis**: 内存数据库 (必需)
- **HuggingFace**: 模型下载 (需要稳定网络)

### 第三方 API
- **LLM 服务**: Gemini / OpenAI / DeepSeek (字幕优化)
- **TTS 服务**: 可选的第三方 TTS API
- **监控服务**: Prometheus + Grafana

### 关键系统依赖
- **FFmpeg**: 音视频处理核心
- **CUDA Toolkit**: GPU 加速支持
- **Docker Engine**: 容器运行时
- **共享文件系统**: 服务间文件交换
