# YiVideo - AI视频处理平台 项目信息

## 项目概述

YiVideo 是一个基于动态工作流引擎的AI视频处理平台，采用微服务架构设计。系统核心思想是"配置而非编码"，通过工作流配置文件动态构建AI处理链条，支持语音识别、OCR、字幕处理、音频分离、文本转语音等多种AI功能的灵活组合。

### 核心特性
- 🎯 **动态工作流引擎**: 通过配置构建AI处理流程，无需硬编码
- 🔧 **微服务架构**: 8个独立的AI worker服务，松耦合、易扩展
- 🚀 **GPU资源管理**: 基于Redis的分布式GPU锁系统，智能轮询和自动恢复
- 📦 **标准化接口**: 所有任务使用统一的工作流上下文传递
- 🎨 **多AI能力**: ASR、说话人分离、OCR、音频分离、TTS、语音克隆等

## 微服务架构

### API网关
- **api_gateway**: 系统总入口和大脑，负责HTTP请求处理、工作流动态构建、状态管理

### AI Worker服务
- **ffmpeg_service**: 视频处理、音频提取和分割
- **faster_whisper_service**: 语音识别(ASR)，基于faster-whisper高版本支持
- **pyannote_audio_service**: 说话人分离，基于pyannote-audio独立部署
- **paddleocr_service**: 光学字符识别(OCR)
- **audio_separator_service**: 人声/背景音分离
- **indextts_service**: 文本转语音(TTS)
- **gptsovits_service**: 语音克隆和合成
- **inpainting_service**: 视频修复和处理

### 基础设施
- **Redis**: Celery消息队列、状态存储、分布式锁和缓存（多DB分离）
- **共享存储**: `/share`目录用于所有服务间的文件共享
- **GPU锁系统**: 分布式GPU资源管理，支持智能轮询和自动恢复

## 技术栈

### 后端框架
- Python 3.8+
- FastAPI / Flask
- Celery (分布式任务队列)

### AI框架与模型
- PyTorch (深度学习基础框架)
- PaddlePaddle (OCR框架)
- Faster-Whisper (语音识别)
- Pyannote-audio (说话人分离)
- PaddleOCR (光学字符识别)
- Audio-separator (音频分离)
- GPTSoVits (语音克隆)
- IndexTTS (文本转语音)

### 基础设施
- Docker & Docker Compose
- Redis (消息队列 + 状态存储 + 分布式锁)
- CUDA / GPU加速
- FFmpeg (音视频处理)

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

# 清理资源
docker system prune -f
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

# 监控GPU使用情况
nvidia-smi

# 备份Redis数据
docker-compose exec redis redis-cli --rdb backup.rdb
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

## 目录结构
```
YiVideo/
├── services/              # 微服务代码
│   ├── api_gateway/      # API网关服务
│   ├── workers/          # AI Worker服务
│   │   ├── ffmpeg_service/
│   │   ├── faster_whisper_service/
│   │   ├── pyannote_audio_service/
│   │   ├── paddleocr_service/
│   │   ├── audio_separator_service/
│   │   ├── indextts_service/
│   │   ├── gptsovits_service/
│   │   └── inpainting_service/
│   └── common/           # 共享组件和工具
│       ├── locks.py      # GPU锁系统
│       ├── config_loader.py
│       └── gpu_memory_manager.py
├── docs/                 # 项目文档
│   ├── architecture/     # 架构文档
│   ├── deployment/       # 部署文档
│   ├── development/      # 开发文档
│   ├── operations/       # 运维文档
│   └── reference/        # 参考文档
├── config/               # 配置文件目录
│   └── system_prompt/    # 系统提示词配置
├── share/                # 服务间共享存储
├── videos/               # 视频文件存储
├── locks/                # GPU锁文件存储
├── tmp/                  # 临时文件存储
├── .claude/              # Claude Code配置
│   ├── commands/         # 自定义命令
│   ├── memory-bank/      # 记忆库
│   └── project-info.md   # 本文档
├── config.yml            # 主配置文件
├── docker-compose.yml    # Docker服务编排
├── CLAUDE.md             # Claude指导文档
└── requirements.txt      # Python依赖
```

## 工作流配置系统

### 标准工作流接口
- **API端点**: `POST /v1/workflows`
- **工作流上下文**: 所有任务间传递统一的JSON字典，包含workflow_id、input_params、stages、error等字段
- **标准化任务接口**: 所有Celery任务使用 `def standard_task_interface(self: Task, context: dict) -> dict:` 签名

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

### 主要API端点
- `POST /v1/workflows` - 创建和执行工作流
- `GET /v1/workflows/{workflow_id}` - 查询工作流状态
- `GET /v1/gpu-locks/status` - 查询GPU锁状态
- `GET /health` - 健康检查

## GPU资源管理

### GPU锁装饰器使用
```python
from services.common.locks import gpu_lock

@gpu_lock(timeout=1800, poll_interval=0.5)
def gpu_intensive_task(self, context):
    """GPU密集型任务自动获取和释放GPU锁"""
    # GPU密集型任务代码
    pass
```

### GPU锁监控组件
- **GPULockMonitor**: 主动监控锁状态，定期健康检查
- **TaskHeartbeatManager**: 管理任务心跳，检测任务存活状态
- **TimeoutManager**: 分级超时处理（警告/软超时/硬超时）
- **监控API**: RESTful API接口查询监控信息

## 配置文件

### Redis多DB架构
- **db:0** - Celery Broker (消息队列)
- **db:1** - Celery Backend (结果存储)
- **db:2** - 分布式锁
- **db:3** - 工作流状态存储

### 主要配置项
- **core**: 工作流TTL、临时文件清理策略
- **redis**: 连接配置和DB分配
- **decoder**: GPU解码批处理大小
- **area_detector**: 字幕区域检测参数
- **keyframe_detector**: 关键帧检测参数
- **faster_whisper**: ASR模型和参数
- **pyannote**: 说话人分离模型和参数
- **paddleocr**: OCR引擎参数

## RIPER Workflow

本项目支持 RIPER 开发流程，用于结构化、上下文高效的开发。

### 可用命令
- `/riper:strict` - 启用严格的RIPER协议执行
- `/riper:research` - 研究模式，用于信息收集
- `/riper:innovate` - 创新模式，用于头脑风暴（可选）
- `/riper:plan` - 规划模式，创建技术规范
- `/riper:execute` - 执行模式，实施计划
- `/riper:execute <substep>` - 执行计划中的特定步骤
- `/riper:review` - 审查模式，验证实现
- `/memory:save` - 保存上下文到记忆库
- `/memory:recall` - 从记忆库检索
- `/memory:list` - 列出所有记忆

### 工作流阶段
1. **Research & Innovate** - 理解和探索代码库和需求
2. **Plan** - 创建详细的技术规范并保存到记忆库
3. **Execute** - 精确实现已批准计划中的内容
4. **Review** - 根据计划验证实现

### 使用流程
1. 使用 `/riper:strict` 启用严格模式
2. 使用 `/riper:research` 调查代码库
3. 可选：使用 `/riper:innovate` 进行头脑风暴
4. 使用 `/riper:plan` 创建计划
5. 使用 `/riper:execute` 执行（或 `/riper:execute 1.2` 执行特定步骤）
6. 使用 `/riper:review` 验证

## Memory Bank 策略

### ⚠️ 关键：仓库级记忆库
- 记忆库位置: 使用 `git rev-parse --show-toplevel` 找到根目录，然后是 `[ROOT]/.claude/memory-bank/`
- 永远不要在子目录或包中创建记忆库
- 所有记忆都是分支感知和日期组织的
- 记忆在会话间持久化，可与团队共享

### Memory Bank 结构
```
.claude/memory-bank/
├── [branch-name]/
│   ├── plans/      # 技术规范
│   ├── reviews/    # 代码审查报告
│   └── sessions/   # 会话上下文
```

## 开发规范

### 测试策略
遵循测试金字塔原则：
- **单元测试**: Mock所有外部依赖，测试纯业务逻辑
- **集成测试**: 使用真实基础设施，测试单个服务内部交互
- **端到端测试**: 完整业务流程测试，模拟真实用户场景

### GPU任务测试
- 单元测试层严格使用Mock，不触碰GPU
- 集成测试层可在CPU模式下运行或使用专用GPU Runner
- 使用 `@pytest.mark.gpu` 标记GPU相关测试

### 代码组织原则
- 遵循现有代码模式和风格
- 所有任务使用标准化接口
- GPU密集型任务必须使用 `@gpu_lock` 装饰器
- 为新功能编写测试
- 文档化复杂逻辑

### 安全考虑
- 所有敏感配置使用环境变量或加密存储
- API接口支持JWT认证和速率限制
- 容器运行使用非root用户

### 性能优化
- 使用GPU锁避免资源冲突
- 配置适当的并发数和批处理大小
- 启用模型缓存和量化
- 合理设置Redis TTL避免内存泄漏

## 故障排除

### 常见问题
1. **GPU锁死锁**: 检查GPU锁监控状态，使用自动恢复机制
2. **内存不足**: 调整batch_size和worker_processes配置
3. **模型下载失败**: 检查网络连接和HuggingFace token配置
4. **Redis连接失败**: 检查Redis服务状态和网络配置

### 调试技巧
- 使用 `docker-compose logs -f <service>` 查看实时日志
- 检查Redis中的工作流状态和GPU锁状态
- 使用 `nvidia-smi` 监控GPU使用情况
- 查看 `/share` 目录中的临时文件和处理结果

## 兼容性要求
- CUDA 11.x+
- 推荐使用NVIDIA RTX系列GPU
- Python 3.8+
- Docker & Docker Compose

---

💡 **提示**: 更详细的架构和开发指南请参考项目根目录的 `CLAUDE.md` 文件以及 `docs/` 目录下的文档。
