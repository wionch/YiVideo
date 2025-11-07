# Common 共享组件模块文档

> 🧭 **导航**: [YiVideo项目根](/mnt/d/WSL2/docker/YiVideo/CLAUDE.md) > **common**

## 模块概述

Common模块是YiVideo系统的共享组件核心，提供了所有微服务通用的基础设施、工具和共享功能。该模块遵循"单一职责"和"依赖倒置"原则，为整个系统提供一致的基础能力。

## 核心功能模块

### 1. 🔄 状态管理 (state_manager.py)
**功能**: 管理工作流状态的持久化
- **作用**: 在Redis中创建、更新、查询、删除工作流状态
- **TTL机制**: 默认7天自动过期
- **数据库**: 使用Redis DB 3
- **主要函数**:
  - `create_workflow_state()`: 创建初始工作流状态
  - `update_workflow_state()`: 更新工作流状态（保留TTL）
  - `get_workflow_state()`: 查询工作流状态
  - `_get_key()`: 生成标准化Redis键

**关键配置**:
```python
REDIS_STATE_DB = 3
WORKFLOW_TTL_DAYS = 7
WORKFLOW_TTL_SECONDS = 604800
```

### 2. 📊 工作流上下文 (context.py)
**功能**: 定义标准化的数据结构
- **核心模型**:
  - `WorkflowContext`: 标准化工作流上下文
    - `workflow_id`: UUID唯一标识符
    - `create_at`: ISO 8601时间戳
    - `input_params`: 输入参数字典
    - `shared_storage_path`: 共享存储路径
    - `stages`: 阶段执行状态集合
    - `error`: 顶层错误信息
  - `StageExecution`: 阶段执行状态
    - `status`: 状态（PENDING/IN_PROGRESS/SUCCESS/FAILED）
    - `output`: 成功输出数据
    - `error`: 失败错误信息
    - `duration`: 执行耗时

**特点**:
- 使用Pydantic模型验证
- 支持extra字段（灵活扩展）
- 跨服务间统一数据传输格式

### 3. 🔐 GPU锁系统 (locks.py)
**功能**: 智能GPU资源管理
- **版本**: V3 - 智能锁机制
- **核心特性**:
  - **多机制支持**:
    - POLLING: 轮询机制
    - EVENT_DRIVEN: 事件驱动
    - HYBRID: 混合机制
  - **指数退避**: 智能调整轮询间隔
  - **Pub/Sub支持**: 事件通知机制
  - **自动恢复**: 死锁检测和自动恢复

**核心类**:
- `LockMechanism`: 锁机制枚举
- `PubSubManager`: Redis Pub/Sub管理器
  - `publish_lock_release()`: 发布锁释放事件
  - `subscribe_to_lock()`: 订阅锁事件
  - `unsubscribe_from_lock()`: 取消订阅

**装饰器**:
```python
@gpu_lock(timeout=1800, poll_interval=0.5)
def gpu_intensive_task(self, context):
    # GPU密集型任务代码
    pass
```

**关键配置**:
- 数据库: Redis DB 2
- 默认超时: 1800秒（30分钟）
- 默认轮询间隔: 0.5秒

### 4. 🎛️ 配置管理 (config_loader.py)
**功能**: 实时配置加载器
- **特点**: 支持配置热重载
- **配置源**: 项目根目录 `config.yml`
- **主要函数**:
  - `get_config()`: 获取全局配置
  - `get_cleanup_temp_files_config()`: 获取临时文件清理配置
  - `get_gpu_lock_config()`: 获取GPU锁配置
  - `get_redis_config()`: 获取Redis配置

**实现原理**:
- 每次调用都重新读取文件（无缓存）
- 支持实时配置变更
- 统一错误处理和日志记录

### 5. 📝 统一日志系统 (logger.py)
**功能**: 单例模式的统一日志管理
- **特性**:
  - **双输出**: 控制台 + 文件
  - **日志轮转**: 10MB分割，保留5个备份
  - **格式化**: 统一的日志格式
  - **单例模式**: 避免重复初始化

**关键类**:
- `UnifiedLogger`: 统一日志管理器
  - `_setup_logging()`: 设置日志系统
  - `get_logger(name)`: 获取指定名称logger
  - `set_level(level)`: 设置日志级别

**日志格式**:
```
%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

### 6. ⚙️ Celery配置 (celery_config.py)
**功能**: Celery任务队列配置
- **作用**: 提供统一的Celery配置参数
- **与Redis集成**: 支持多个数据库分离

### 7. 🔧 任务装饰器 (task_decorator.py)
**功能**: 标准化任务装饰器
- **作用**: 封装通用任务逻辑
- **功能**: 参数验证、异常处理、状态管理

### 8. 🧠 参数解析器 (parameter_resolver.py)
**功能**: 动态参数解析
- **作用**: 解析和验证工作流参数
- **特性**: 支持嵌套参数、类型转换

### 9. 💾 GPU内存管理 (gpu_memory_manager.py)
**功能**: GPU内存使用监控
- **作用**: 监控和管理GPU内存使用
- **特性**: 内存溢出检测、自动清理

## 目录结构

```
services/common/
├── __init__.py                 # 模块初始化
├── celery_config.py            # Celery配置
├── config_loader.py            # 配置文件加载器
├── context.py                  # 数据模型定义
├── gpu_memory_manager.py       # GPU内存管理
├── locks.py                    # GPU锁系统
├── logger.py                   # 统一日志管理
├── parameter_resolver.py       # 参数解析器
├── state_manager.py            # 状态管理
├── task_decorator.py           # 任务装饰器
└── subtitle/                   # 字幕处理子模块
    ├── README.md
    ├── __init__.py
    ├── ai_command_parser.py        # AI命令解析器
    ├── ai_providers.py            # AI服务提供商
    ├── ai_request_builder.py      # AI请求构建器
    ├── command_executor.py        # 命令执行器
    ├── command_statistics.py      # 命令统计
    ├── concurrent_batch_processor.py # 并发批处理器
    ├── metrics.py                 # 指标统计
    ├── optimized_file_generator.py # 优化文件生成器
    ├── prompt_loader.py           # 提示词加载器
    ├── sliding_window_splitter.py  # 滑窗分割器
    ├── subtitle_correction.py     # 字幕校正
    ├── subtitle_correction_config.py # 字幕校正配置
    ├── subtitle_extractor.py      # 字幕提取器
    ├── subtitle_merger.py         # 字幕合并器
    ├── subtitle_optimizer.py      # 字幕优化器
    ├── subtitle_parser.py         # 字幕解析器
    ├── subtitle_segment_processor.py # 字幕段处理器
    └── token_utils.py             # Token工具
```

## 字幕处理子模块 (subtitle/)

### 功能概述
字幕处理子模块提供完整的AI字幕处理能力，包括字幕生成、校正、优化、合并等功能。

### 核心组件

**1. AI服务提供商 (ai_providers.py)**
- 支持多个AI服务提供商（Gemini、OpenAI等）
- 统一接口抽象
- 动态切换和负载均衡

**2. 命令执行器 (command_executor.py)**
- 执行字幕相关命令
- 支持并发执行
- 错误处理和重试机制

**3. 字幕处理器系列**
- `subtitle_correction.py`: 字幕校正
- `subtitle_optimizer.py`: 字幕优化
- `subtitle_merger.py`: 字幕合并
- `subtitle_parser.py`: 字幕解析
- `subtitle_extractor.py`: 字幕提取

**4. 工具模块**
- `token_utils.py`: Token管理
- `sliding_window_splitter.py`: 滑窗分割
- `prompt_loader.py`: 提示词加载
- `concurrent_batch_processor.py`: 并发批处理
- `metrics.py`: 指标统计

**5. AI命令系统**
- `ai_command_parser.py`: 解析AI命令
- `ai_request_builder.py`: 构建AI请求
- `command_executor.py`: 执行AI命令
- `command_statistics.py`: 统计命令执行

## Redis数据库分离

Common模块使用Redis的多个数据库实现功能分离：

| 数据库 | 用途 | 模块 |
|--------|------|------|
| DB 0 | Celery Broker | Celery任务队列 |
| DB 1 | Celery Backend | 任务结果存储 |
| DB 2 | 分布式锁 | locks.py |
| DB 3 | 工作流状态 | state_manager.py |

## 核心使用示例

### 1. 使用状态管理
```python
from services.common.context import WorkflowContext
from services.common.state_manager import create_workflow_state, get_workflow_state

# 创建工作流上下文
context = WorkflowContext(
    workflow_id="uuid-1234",
    input_params={"video_path": "/path/to/video.mp4"},
    shared_storage_path="/share/workflows/uuid-1234"
)

# 保存状态
create_workflow_state(context)

# 查询状态
state = get_workflow_state("uuid-1234")
```

### 2. 使用GPU锁
```python
from services.common.locks import gpu_lock

@gpu_lock(timeout=1800, poll_interval=0.5)
def process_video(self, context):
    # GPU密集型处理
    pass
```

### 3. 使用日志系统
```python
from services.common.logger import get_logger

logger = get_logger(__name__)
logger.info("这是一条信息日志")
logger.error("这是一条错误日志")
```

### 4. 加载配置
```python
from services.common.config_loader import get_config, get_redis_config

# 获取完整配置
config = get_config()

# 获取Redis配置
redis_config = get_redis_config()
```

## 最佳实践

### 1. 状态管理
- 总是使用`WorkflowContext`模型
- 及时更新工作流状态
- 合理设置TTL时间
- 使用`update_workflow_state()`保留TTL

### 2. GPU锁使用
- 对所有GPU密集型任务使用`@gpu_lock`装饰器
- 设置合理的超时时间
- 避免长时间持有锁
- 使用异常处理确保锁释放

### 3. 配置管理
- 使用`config_loader`而非硬编码配置
- 利用配置热重载功能
- 为配置项提供默认值

### 4. 日志记录
- 使用`get_logger(name)`获取logger
- 遵循日志级别规范
- 记录关键业务事件

### 5. Redis连接
- 使用多数据库分离功能
- 妥善处理连接失败
- 检查Redis连接状态

## 监控和调试

### 日志文件位置
- 路径: `logs/yivideo.log`
- 轮转: 10MB一个文件，保留5个
- 格式: 时间 - 名称 - 级别 - 消息

### 调试命令
```python
# 检查Redis状态
from services.common.state_manager import redis_client
if redis_client:
    redis_client.ping()

# 查看配置
from services.common.config_loader import get_config
config = get_config()
print(config)
```

## 注意事项

1. **配置热重载**: 配置读取函数每次都重新读取文件，无缓存机制
2. **Redis连接**: 所有模块都假设Redis可用，连接失败会记录日志但不会崩溃
3. **单例模式**: Logger使用单例模式，避免重复配置
4. **异常处理**: 所有模块都有完善的异常处理和日志记录
5. **数据库分离**: 确保使用正确的Redis数据库编号

## 相关模块

- **services/api_gateway**: 主要消费者
- **services/workers/***: 所有worker服务
- **Redis**: 核心依赖
- **config.yml**: 配置文件源
