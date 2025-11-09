# API Gateway 模块文档

> 🧭 **导航**: [YiVideo项目根](/mnt/d/WSL2/docker/YiVideo/CLAUDE.md) > **api_gateway**

## 模块概述

API Gateway是YiVideo系统的核心入口和大脑，负责HTTP请求处理、工作流动态构建、状态管理，以及完整的监控体系。模块使用FastAPI构建，提供RESTful API接口来管理AI视频处理工作流。

## 核心功能

### 1. 工作流管理
- **创建工作流**: 支持全新的工作流创建（full模式）
- **增量执行**: 支持向现有工作流追加新任务（incremental模式）
- **重试机制**: 支持从失败任务重新开始执行（retry模式）
- **参数合并**: 支持merge、override、strict三种参数合并策略

### 2. 工作流状态管理
- 在Redis中存储工作流状态
- 支持TTL自动过期机制
- 提供工作流查询端点

### 3. 分布式锁机制
- 使用Redis实现分布式锁
- 防止并发修改工作流
- 支持自动释放和超时机制

### 4. 监控与观测性
- **GPU锁监控**: 实时监控GPU资源使用
- **心跳管理**: 跟踪任务存活状态
- **超时管理**: 分级超时处理（警告/软超时/硬超时）
- **Prometheus集成**: 指标收集和导出
- **健康检查**: 提供系统健康状态端点

## 目录结构

```
services/api_gateway/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI主应用入口
│   ├── workflow_factory.py      # 工作流链构建工厂
│   ├── incremental_utils.py     # 增量执行工具
│   ├── monitoring/              # 监控模块
│   │   ├── __init__.py
│   │   ├── api_endpoints.py     # 监控API端点
│   │   ├── gpu_lock_monitor.py  # GPU锁监控
│   │   ├── heartbeat_manager.py # 心跳管理器
│   │   ├── prometheus_config.py # Prometheus配置
│   │   └── timeout_manager.py   # 超时管理器
│   ├── tmp/                     # 临时文件目录
│   └── videos/                  # 视频文件目录
├── Dockerfile                   # Docker镜像配置
└── requirements.txt             # Python依赖
```

## 核心文件

### main.py
- **作用**: FastAPI应用主入口
- **关键功能**:
  - 定义工作流请求/响应模型（`WorkflowRequest`, `WorkflowResponse`）
  - 提供核心API端点：
    - `POST /v1/workflows`: 创建/执行工作流
    - `GET /v1/workflows/status/{workflow_id}`: 查询工作流状态
  - 支持三种执行模式：full、incremental、retry
  - 启动时初始化监控服务

**核心API端点**:
```python
@app.post("/v1/workflows")
def create_workflow(request: WorkflowRequest)

@app.get("/v1/workflows/status/{workflow_id}")
def get_workflow_status(workflow_id: str)
```

### workflow_factory.py
- **作用**: 构建工作流链的工厂类
- **功能**: 根据配置动态构建Celery任务链

### incremental_utils.py
- **作用**: 增量执行工具
- **核心功能**:
  - `compute_workflow_diff()`: 计算工作流差异
  - `merge_node_params()`: 合并节点参数
  - `acquire_workflow_lock()` / `release_workflow_lock()`: 分布式锁管理

### monitoring/ 目录
提供完整的监控和观测性功能：

**gpu_lock_monitor.py**:
- 主动监控锁状态
- 定期健康检查
- 检测死锁和异常

**heartbeat_manager.py**:
- 管理任务心跳
- 检测任务存活状态
- 提供心跳API

**timeout_manager.py**:
- 分级超时处理
- 警告/软超时/硬超时机制
- 自动清理超时任务

**prometheus_config.py**:
- Prometheus指标配置
- 导出监控指标
- 支持Grafana集成

**api_endpoints.py**:
- 监控相关API端点
- 提供监控数据查询
- 健康检查端点

## 依赖

### 核心依赖 (requirements.txt)
```
fastapi          # Web框架
uvicorn         # ASGI服务器
gunicorn        # WSGI服务器（生产环境）
celery          # 分布式任务队列
redis           # Redis客户端
pyyaml          # YAML解析
requests        # HTTP请求
```

### 共享依赖 (from services.common)
```
services.common.logger      # 日志系统
services.common.context     # 上下文模型
services.common.state_manager # 状态管理
```

## 配置

### 环境变量
- `REDIS_HOST`: Redis服务器地址
- `REDIS_PORT`: Redis端口
- `REDIS_DB_*`: 多个数据库（broker:0, backend:1, locks:2, state:3）

### 监控配置
- 支持Prometheus指标导出
- 可配置监控间隔和超时阈值
- 支持GPU锁监控

## API接口

### 主要端点

#### 1. 创建工作流
```http
POST /v1/workflows
Content-Type: application/json

{
  "video_path": "/share/videos/input/example.mp4",
  "workflow_config": {
    "workflow_chain": [
      {"task": "extract_audio", "params": {...}},
      {"task": "speech_recognition", "params": {...}}
    ]
  },
  "execution_mode": "full",
  "param_merge_strategy": "merge"
}
```

**响应**:
```json
{
  "workflow_id": "uuid-string",
  "execution_mode": "full",
  "tasks_total": 2,
  "tasks_skipped": 0,
  "tasks_to_execute": 2,
  "message": "New workflow created and started successfully."
}
```

#### 2. 查询工作流状态
```http
GET /v1/workflows/status/{workflow_id}
```

**响应**: 返回完整的工作流上下文状态

#### 3. 监控与健康检查端点

所有监控端点都位于 `/api/v1/monitoring` 前缀下。

##### GPU锁管理
- `GET /gpu-lock/status`: 获取指定GPU锁的详细状态。
- `GET /gpu-lock/health`: 获取GPU锁系统的整体健康状况摘要。
- `POST /lock/release`: 手动释放一个指定的GPU锁。

##### 监控器管理
- `GET /monitor/status`: 获取GPU锁监控器的当前状态、统计和配置。
- `GET /monitor/health`: 获取监控器的健康状态，包括任何检测到的问题。
- `POST /monitor/start`: 启动后台GPU锁监控器。
- `POST /monitor/stop`: 停止后台GPU锁监控器。

##### 任务心跳管理
- `GET /heartbeat/task/{task_id}`: 获取指定任务的心跳状态。
- `GET /heartbeat/all`: 获取所有活动、死亡和孤立任务的心跳状态概览。
- `POST /heartbeat/task/{task_id}/start`: 为指定任务手动启动心跳。
- `DELETE /heartbeat/task/{task_id}`: 停止指定任务的心跳。
- `POST /heartbeat/cleanup`: 执行清理操作，移除死亡和孤立的心跳记录。

##### 超时管理
- `GET /timeout/status`: 获取超时管理器的状态，包括统计和历史记录。
- `GET /timeout/config`: 获取当前的超时配置。
- `POST /timeout/check`: 手动触发对指定锁的超时检查。

##### 综合统计与健康检查
- `GET /statistics`: 获取所有监控组件（GPU锁、监控器、心跳、超时）的综合统计信息。
- `GET /health`: 获取整个监控服务的聚合健康状态。 **注意**: 此端点的完整路径是 `/api/v1/monitoring/health`。

## 关键流程

### 1. 创建新工作流（full模式）
1. 验证请求参数（video_path必需）
2. 生成唯一workflow_id
3. 创建共享存储目录
4. 构建工作流上下文
5. 保存状态到Redis
6. 构建任务链并异步执行

### 2. 增量执行（incremental模式）
1. 获取分布式锁（防止并发修改）
2. 验证工作流存在
3. 计算工作流差异
4. 合并参数
5. 构建新任务链
6. 更新状态并执行
7. 释放锁

### 3. 重试执行（retry模式）
1. 获取分布式锁
2. 验证工作流存在
3. 识别失败任务
4. 重新执行失败任务
5. 释放锁

## 监控指标

### GPU锁监控
- 锁获取/释放次数
- 锁等待时间
- 死锁检测

### 心跳监控
- 任务心跳频率
- 任务存活状态
- 心跳超时统计

### 超时监控
- 超时任务数量
- 超时时间分布
- 自动清理统计

## 开发和调试

### 本地运行
```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 调试命令
```bash
# 查看工作流状态
curl http://localhost:8000/v1/workflows/status/{workflow_id}

# 检查监控指标
curl http://localhost:8000/v1/monitoring/gpu-locks/status

# 健康检查
curl http://localhost:8000/health
```

### 日志
- 使用`services.common.logger`统一日志
- 结构化日志输出
- 支持不同日志级别

## Docker部署

### Dockerfile
- 基于官方Python镜像
- 安装系统依赖
- 配置非root用户
- 暴露8000端口

### 容器化运行
```bash
# 构建镜像
docker build -t yivideo-api-gateway .

# 运行容器
docker run -d -p 8000:8000 \
  -e REDIS_HOST=redis \
  yivideo-api-gateway
```

## 最佳实践

### 1. 错误处理
- 使用HTTPException进行HTTP错误响应
- 记录详细错误日志
- 区分业务错误和系统错误

### 2. 并发控制
- 使用Redis分布式锁
- 防止工作流并发修改
- 自动释放锁（使用try-finally）

### 3. 状态管理
- 合理设置Redis TTL
- 及时更新工作流状态
- 支持幂等操作

### 4. 监控
- 集成Prometheus指标
- 定期健康检查
- 及时处理超时

## 注意事项

1. **工作流ID**: 使用UUID确保唯一性
2. **共享存储**: 自动创建工作流目录，权限设置为777
3. **Redis连接**: 检查Redis连接状态，失败时快速降级
4. **锁管理**: 始终使用try-finally确保锁释放
5. **参数验证**: 使用Pydantic模型进行严格的参数验证

## 相关模块

- **services/common/state_manager**: 状态管理
- **services/common/context**: 上下文模型
- **services/common/logger**: 日志系统
- **services/workers/***: 各种AI worker服务
- **Redis**: 消息队列、状态存储、分布式锁
