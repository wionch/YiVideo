# 监控 API 文档

监控API提供系统运行状态的实时监控和管理功能，包括GPU锁监控、任务心跳、超时处理和系统健康检查。

## 📋 目录

- [概述](#概述)
- [监控组件](#监控组件)
- [端点列表](#端点列表)
- [GPU锁监控](#gpu锁监控)
- [监控器管理](#监控器管理)
- [心跳管理](#心跳管理)
- [超时管理](#超时管理)
- [锁管理](#锁管理)
- [统计信息](#统计信息)
- [健康检查](#健康检查)
- [示例和最佳实践](#示例和最佳实践)

---

## 概述

### 监控架构

监控API提供四个核心监控组件：

1. **GPU锁监控**: 管理系统GPU资源分配，防止资源竞争
2. **监控器**: 周期性检查系统状态和任务健康
3. **心跳管理**: 监控任务运行状态，检测僵尸任务
4. **超时管理**: 自动处理长时间运行的任务

### 核心特性
- **实时监控**: 毫秒级状态更新
- **自动恢复**: 异常情况自动处理
- **详细日志**: 完整的操作历史记录
- **可配置**: 支持自定义监控参数

---

## 监控组件

### GPU锁监控

**作用**: 管理系统GPU资源，确保任务不会并发访问同一GPU

**特性**:
- 分布式锁机制
- TTL自动过期
- 健康状态监控
- 手动释放支持

**锁键格式**: `gpu_lock:{gpu_id}` (例如: `gpu_lock:0`)

### 监控器

**作用**: 周期性检查系统状态，监控GPU锁和任务健康

**功能**:
- 定时检查GPU锁状态
- 检测过期锁
- 监控任务心跳
- 自动清理僵尸资源

**默认配置**:
- 检查间隔: 30秒
- 锁超时检测: 5分钟
- 心跳超时: 2分钟

### 心跳管理

**作用**: 跟踪任务运行状态，检测异常终止的任务

**心跳机制**:
- 任务启动时注册心跳
- 定期更新心跳时间戳
- 检测超时任务
- 自动清理死任务

### 超时管理

**作用**: 自动处理长时间运行或无响应的任务

**处理策略**:
- 检测超时任务
- 强制释放资源
- 更新任务状态
- 记录处理历史

---

## 端点列表

### GPU锁监控
| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/monitoring/gpu-lock/status` | 获取GPU锁状态 |
| GET | `/api/v1/monitoring/gpu-lock/health` | 获取GPU锁健康摘要 |

### 监控器管理
| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/monitoring/monitor/status` | 获取监控器状态 |
| GET | `/api/v1/monitoring/monitor/health` | 获取监控器健康状态 |
| POST | `/api/v1/monitoring/monitor/start` | 启动监控器 |
| POST | `/api/v1/monitoring/monitor/stop` | 停止监控器 |

### 心跳管理
| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/monitoring/heartbeat/task/{task_id}` | 获取指定任务心跳 |
| GET | `/api/v1/monitoring/heartbeat/all` | 获取所有任务心跳 |
| POST | `/api/v1/monitoring/heartbeat/task/{task_id}/start` | 启动任务心跳 |
| DELETE | `/api/v1/monitoring/heartbeat/task/{task_id}` | 停止任务心跳 |
| POST | `/api/v1/monitoring/heartbeat/cleanup` | 清理死任务和孤立心跳 |

### 超时管理
| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/monitoring/timeout/status` | 获取超时处理状态 |
| GET | `/api/v1/monitoring/timeout/config` | 获取超时配置 |
| POST | `/api/v1/monitoring/timeout/check` | 检查并处理超时 |

### 其他
| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/monitoring/lock/release` | 手动释放GPU锁 |
| GET | `/api/v1/monitoring/statistics` | 获取监控统计信息 |
| GET | `/api/v1/monitoring/health` | 获取监控服务健康状态 |

---

## GPU锁监控

### GET /api/v1/monitoring/gpu-lock/status

获取指定GPU锁的详细状态。

#### 查询参数

| 名称 | 类型 | 必需 | 描述 |
|------|------|------|------|
| lock_key | string | 否 | 锁键（默认：gpu_lock:0） |

#### 请求示例

```bash
curl -X GET "http://localhost:8000/api/v1/monitoring/gpu-lock/status?lock_key=gpu_lock:0"
```

#### 响应示例

**锁已占用**：
```json
{
    "lock_key": "gpu_lock:0",
    "is_locked": true,
    "lock_holder": "faster_whisper.transcribe_audio",
    "ttl_seconds": 2847,
    "timestamp": 1701764160.123,
    "health": {
        "status": "healthy",
        "last_check": 1701764160.0,
        "issues": []
    },
    "statistics": {
        "total_attempts": 15,
        "success_count": 12,
        "timeout_count": 2,
        "failure_count": 1,
        "average_execution_time": 156.3
    },
    "recent_history": [
        {
            "action": "acquire",
            "task_name": "faster_whisper.transcribe_audio",
            "timestamp": 1701764160.0,
            "success": true
        }
    ],
    "lock_type": "GPU_LOCK",
    "lock_age": 153.0
}
```

**锁空闲**：
```json
{
    "lock_key": "gpu_lock:0",
    "is_locked": false,
    "lock_holder": null,
    "ttl_seconds": null,
    "timestamp": 1701764160.123,
    "health": {
        "status": "healthy",
        "last_check": 1701764160.0,
        "issues": []
    },
    "statistics": {
        "total_attempts": 15,
        "success_count": 12,
        "timeout_count": 2,
        "failure_count": 1,
        "average_execution_time": 156.3
    },
    "recent_history": [],
    "lock_type": "GPU_LOCK",
    "lock_age": null
}
```

#### 响应字段说明

- `lock_key` (string): 锁键
- `is_locked` (boolean): 是否已被占用
- `lock_holder` (string/null): 锁持有者任务名
- `ttl_seconds` (int/null): 剩余TTL时间
- `timestamp` (float): 时间戳
- `health` (object): 健康状态
  - `status` (string): 状态（healthy/warning/critical）
  - `last_check` (float): 最后检查时间
  - `issues` (array): 问题列表
- `statistics` (object): 统计信息
  - `total_attempts` (int): 总尝试次数
  - `success_count` (int): 成功次数
  - `timeout_count` (int): 超时次数
  - `failure_count` (int): 失败次数
  - `average_execution_time` (float): 平均执行时间
- `recent_history` (array): 最近操作历史
- `lock_type` (string): 锁类型
- `lock_age` (float/null): 锁已占用时间

---

### GET /api/v1/monitoring/gpu-lock/health

获取GPU锁系统的健康状态摘要。

#### 响应示例

```json
{
    "overall_status": "healthy",
    "issues_count": 0,
    "total_attempts": 45,
    "success_rate": 0.96,
    "timeout_rate": 0.02,
    "average_execution_time": 142.5,
    "recent_success_rate": 0.98,
    "lock_holder": "faster_whisper.transcribe_audio",
    "lock_age": 87.3,
    "timestamp": 1701764160.123
}
```

#### 响应字段说明

- `overall_status` (string): 整体状态
- `issues_count` (int): 问题数量
- `total_attempts` (int): 总尝试次数
- `success_rate` (float): 成功率
- `timeout_rate` (float): 超时率
- `average_execution_time` (float): 平均执行时间
- `recent_success_rate` (float): 最近成功率
- `lock_holder` (string/null): 当前锁持有者
- `lock_age` (float/null): 当前锁已占用时间
- `timestamp` (float): 时间戳

---

## 监控器管理

### GET /api/v1/monitoring/monitor/status

获取监控器的当前状态和配置。

#### 响应示例

```json
{
    "monitor_status": {
        "running": true,
        "start_time": 1701764000.0,
        "last_check": 1701764160.0,
        "checks_performed": 532
    },
    "monitor_stats": {
        "gpu_locks_monitored": 1,
        "tasks_monitored": 12,
        "timeouts_detected": 3,
        "tasks_recovered": 2
    },
    "config": {
        "check_interval": 30,
        "gpu_timeout": 300,
        "heartbeat_timeout": 120,
        "enabled": true
    },
    "is_running": true,
    "uptime": 160.123
}
```

---

### GET /api/v1/monitoring/monitor/health

获取监控器的健康状态。

#### 响应示例

```json
{
    "status": "healthy",
    "issues": [],
    "metrics": {
        "check_frequency": "30s",
        "gpu_lock_coverage": "100%",
        "task_monitoring_coverage": "95%",
        "avg_response_time": "45ms"
    },
    "timestamp": 1701764160.123
}
```

---

### POST /api/v1/monitoring/monitor/start

启动监控器。

#### 响应示例

```json
{
    "message": "监控器已启动",
    "success": true
}
```

---

### POST /api/v1/monitoring/monitor/stop

停止监控器。

#### 响应示例

```json
{
    "message": "监控器已停止",
    "success": true
}
```

---

## 心跳管理

### GET /api/v1/monitoring/heartbeat/task/{task_id}

获取指定任务的心跳状态。

#### 路径参数

| 名称 | 类型 | 必需 | 描述 |
|------|------|------|------|
| task_id | string | 是 | 任务ID |

#### 请求示例

```bash
curl -X GET "http://localhost:8000/api/v1/monitoring/heartbeat/task/extract-001"
```

#### 响应示例

**任务活跃**：
```json
{
    "task_id": "extract-001",
    "heartbeat_exists": true,
    "is_registered": true,
    "status": "running",
    "heartbeat_data": {
        "task_name": "ffmpeg.extract_audio",
        "start_time": 1701764100.0,
        "last_update": 1701764160.0,
        "gpu_lock": "gpu_lock:0",
        "progress": 0.65
    },
    "last_update": 1701764160.0,
    "is_running": true
}
```

**任务已停止**：
```json
{
    "task_id": "extract-001",
    "heartbeat_exists": false,
    "is_registered": false,
    "status": "completed",
    "heartbeat_data": null,
    "last_update": null,
    "is_running": false
}
```

#### 响应字段说明

- `task_id` (string): 任务ID
- `heartbeat_exists` (boolean): 心跳是否存在
- `is_registered` (boolean): 是否已注册
- `status` (string): 任务状态
- `heartbeat_data` (object/null): 心跳数据
  - `task_name` (string): 任务名称
  - `start_time` (float): 开始时间
  - `last_update` (float): 最后更新时间
  - `gpu_lock` (string): 使用的GPU锁
  - `progress` (float): 执行进度（0-1）
- `last_update` (float/null): 最后心跳时间
- `is_running` (boolean): 是否正在运行

---

### GET /api/v1/monitoring/heartbeat/all

获取所有任务的心跳状态。

#### 响应示例

```json
{
    "active_tasks": {
        "extract-001": {
            "task_name": "ffmpeg.extract_audio",
            "last_update": 1701764160.0,
            "status": "running"
        },
        "asr-002": {
            "task_name": "faster_whisper.transcribe_audio",
            "last_update": 1701764155.0,
            "status": "running"
        }
    },
    "dead_tasks": [],
    "orphaned_tasks": [
        {
            "task_id": "zombie-003",
            "last_update": 1701763800.0,
            "timeout": true
        }
    ],
    "statistics": {
        "total_tasks": 12,
        "active_count": 8,
        "dead_count": 3,
        "orphaned_count": 1,
        "average_heartbeat_interval": 15.2
    },
    "timestamp": 1701764160.123
}
```

#### 响应字段说明

- `active_tasks` (object): 活跃任务列表
- `dead_tasks` (array): 已完成任务列表
- `orphaned_tasks` (array): 孤立任务列表（超时未更新）
- `statistics` (object): 统计信息
  - `total_tasks` (int): 总任务数
  - `active_count` (int): 活跃任务数
  - `dead_count` (int): 死亡任务数
  - `orphaned_count` (int): 孤立任务数
  - `average_heartbeat_interval` (float): 平均心跳间隔

---

### POST /api/v1/monitoring/heartbeat/task/{task_id}/start

启动指定任务的心跳。

#### 响应示例

```json
{
    "message": "任务 extract-001 心跳已启动",
    "success": true
}
```

---

### DELETE /api/v1/monitoring/heartbeat/task/{task_id}

停止指定任务的心跳。

#### 响应示例

```json
{
    "message": "任务 extract-001 心跳已停止",
    "success": true
}
```

---

### POST /api/v1/monitoring/heartbeat/cleanup

清理死任务和孤立心跳。

#### 响应示例

```json
{
    "message": "心跳清理完成",
    "success": true,
    "cleaned_dead_tasks": 3
}
```

---

## 超时管理

### GET /api/v1/monitoring/timeout/status

获取超时处理的当前状态。

#### 响应示例

```json
{
    "timeout_stats": {
        "total_timeouts_detected": 15,
        "tasks_recovered": 12,
        "resources_released": 8,
        "current_timeouts": 0
    },
    "action_history": [
        {
            "timestamp": 1701764100.0,
            "action": "timeout_recovery",
            "task_id": "extract-001",
            "result": "success"
        }
    ],
    "configured_actions": [
        "force_release_gpu_lock",
        "update_task_status",
        "log_timeout_event"
    ],
    "timestamp": 1701764160.123
}
```

---

### GET /api/v1/monitoring/timeout/config

获取超时管理的配置参数。

#### 响应示例

```json
{
    "gpu_lock_timeout": 300,
    "task_heartbeat_timeout": 120,
    "monitor_check_interval": 30,
    "auto_recovery_enabled": true,
    "max_retry_attempts": 3,
    "timestamp": 1701764160.123
}
```

---

### POST /api/v1/monitoring/timeout/check

手动触发超时检查。

#### 查询参数

| 名称 | 类型 | 必需 | 描述 |
|------|------|------|------|
| lock_key | string | 否 | 锁键（默认：gpu_lock:0） |

#### 响应示例

```json
{
    "checked_locks": ["gpu_lock:0"],
    "timeouts_detected": 0,
    "actions_taken": [],
    "timestamp": 1701764160.123
}
```

---

## 锁管理

### POST /api/v1/monitoring/lock/release

手动释放GPU锁（紧急情况使用）。

#### 请求体

| 名称 | 类型 | 必需 | 描述 |
|------|------|------|------|
| lock_key | string | 是 | 锁键 |
| task_name | string | 否 | 任务名称（默认：manual） |

#### 请求示例

```bash
curl -X POST "http://localhost:8000/api/v1/monitoring/lock/release" \
  -H "Content-Type: application/json" \
  -d '{
    "lock_key": "gpu_lock:0",
    "task_name": "manual"
  }'
```

#### 响应示例

**释放成功**：
```json
{
    "success": true,
    "message": "锁 gpu_lock:0 已成功释放",
    "lock_key": "gpu_lock:0",
    "task_name": "manual"
}
```

**释放失败**：
```json
{
    "success": false,
    "message": "释放锁 gpu_lock:0 失败",
    "lock_key": "gpu_lock:0",
    "task_name": "manual"
}
```

---

## 统计信息

### GET /api/v1/monitoring/statistics

获取完整的监控统计信息。

#### 响应示例

```json
{
    "timestamp": 1701764160.123,
    "gpu_lock": {
        "overall_status": "healthy",
        "total_attempts": 45,
        "success_rate": 0.96,
        "timeout_rate": 0.02
    },
    "monitor": {
        "running": true,
        "uptime": 160.123,
        "checks_performed": 532,
        "issues_detected": 0
    },
    "heartbeat": {
        "active_tasks": 8,
        "dead_tasks": 3,
        "orphaned_tasks": 1,
        "average_interval": 15.2
    },
    "timeout": {
        "total_timeouts": 15,
        "tasks_recovered": 12,
        "resources_released": 8
    }
}
```

---

## 健康检查

### GET /api/v1/monitoring/health

获取监控服务的整体健康状态。

#### 响应示例

**健康**：
```json
{
    "status": "healthy",
    "issues": [],
    "components": {
        "monitor": {
            "status": "healthy",
            "issues": [],
            "metrics": {
                "check_frequency": "30s"
            },
            "timestamp": 1701764160.123
        },
        "heartbeat": {
            "total_tasks": 12,
            "active_count": 8,
            "failure_rate": 0.02,
            "timestamp": 1701764160.123
        }
    },
    "timestamp": 1701764160.123
}
```

**警告**：
```json
{
    "status": "warning",
    "issues": [
        "心跳故障率过高"
    ],
    "components": {
        "monitor": {
            "status": "healthy",
            "issues": [],
            "metrics": {...},
            "timestamp": 1701764160.123
        },
        "heartbeat": {
            "total_tasks": 12,
            "active_count": 8,
            "failure_rate": 0.15,
            "timestamp": 1701764160.123
        }
    },
    "timestamp": 1701764160.123
}
```

#### 响应字段说明

- `status` (string): 整体状态（healthy/warning/critical）
- `issues` (array): 问题列表
- `components` (object): 各组件状态
  - `monitor` (object): 监控器状态
  - `heartbeat` (object): 心跳统计
- `timestamp` (float): 时间戳

---

## 示例和最佳实践

### 示例1：监控GPU锁状态

```bash
#!/bin/bash

# 检查GPU锁状态
status=$(curl -s "http://localhost:8000/api/v1/monitoring/gpu-lock/status")

is_locked=$(echo "$status" | jq -r '.is_locked')
lock_holder=$(echo "$status" | jq -r '.lock_holder')
ttl=$(echo "$status" | jq -r '.ttl_seconds')

if [ "$is_locked" == "true" ]; then
    echo "GPU锁已占用"
    echo "持有者: $lock_holder"
    echo "剩余时间: ${ttl}秒"
else
    echo "GPU锁空闲"
fi

# 获取健康摘要
health=$(curl -s "http://localhost:8000/api/v1/monitoring/gpu-lock/health")
overall_status=$(echo "$health" | jq -r '.overall_status')
echo "健康状态: $overall_status"
```

### 示例2：任务心跳监控

```python
import requests
import time

def check_task_heartbeat(task_id):
    """检查任务心跳状态"""
    response = requests.get(
        f"http://localhost:8000/api/v1/monitoring/heartbeat/task/{task_id}"
    )

    if response.status_code == 200:
        data = response.json()

        if data['is_running']:
            print(f"任务 {task_id} 正在运行")
            if data['heartbeat_data']:
                last_update = data['last_update']
                progress = data['heartbeat_data'].get('progress', 0)
                print(f"进度: {progress*100:.1f}%")
                print(f"最后心跳: {time.ctime(last_update)}")

                # 检查心跳是否超时
                time_since_update = time.time() - last_update
                if time_since_update > 120:  # 2分钟
                    print("⚠️ 心跳可能已超时")
        else:
            print(f"任务 {task_id} 已停止")
    else:
        print(f"任务 {task_id} 不存在")

# 检查多个任务
task_ids = ["extract-001", "asr-002", "ocr-003"]
for task_id in task_ids:
    check_task_heartbeat(task_id)
    print("-" * 50)
```

### 示例3：监控系统健康

```bash
#!/bin/bash

# 获取整体健康状态
health=$(curl -s "http://localhost:8000/api/v1/monitoring/health")

status=$(echo "$health" | jq -r '.status')
issues=$(echo "$health" | jq -r '.issues | length')

echo "监控系统健康状态: $status"
echo "问题数量: $issues"

if [ "$issues" -gt 0 ]; then
    echo "问题列表:"
    echo "$health" | jq -r '.issues[]'
fi

# 检查各组件
monitor_status=$(echo "$health" | jq -r '.components.monitor.status')
heartbeat_failure_rate=$(echo "$health" | jq -r '.components.heartbeat.failure_rate')

echo "监控器状态: $monitor_status"
echo "心跳故障率: $heartbeat_failure_rate"

if (( $(echo "$heartbeat_failure_rate > 0.1" | bc -l) )); then
    echo "⚠️ 心跳故障率过高，建议检查任务状态"
fi
```

### 示例4：自动恢复超时任务

```python
import requests
import json

def auto_recover_timeouts():
    """自动恢复超时任务"""
    # 检查超时
    timeout_response = requests.post(
        "http://localhost:8000/api/v1/monitoring/timeout/check"
    )

    if timeout_response.status_code == 200:
        timeout_data = timeout_response.json()
        timeouts_detected = timeout_data.get('timeouts_detected', 0)

        if timeouts_detected > 0:
            print(f"检测到 {timeouts_detected} 个超时任务")
            print(f"已执行操作: {json.dumps(timeout_data.get('actions_taken', []), indent=2)}")
        else:
            print("未检测到超时任务")

    # 清理死任务和孤立心跳
    cleanup_response = requests.post(
        "http://localhost:8000/api/v1/monitoring/heartbeat/cleanup"
    )

    if cleanup_response.status_code == 200:
        cleanup_data = cleanup_response.json()
        cleaned_count = cleanup_data.get('cleaned_dead_tasks', 0)
        print(f"清理了 {cleaned_count} 个死任务")

# 定期执行自动恢复
if __name__ == "__main__":
    while True:
        auto_recover_timeouts()
        time.sleep(300)  # 每5分钟执行一次
```

### 最佳实践

#### 1. 监控策略
- **定期检查**: 建议每30秒检查一次GPU锁状态
- **健康监控**: 持续监控 `/health` 端点
- **日志记录**: 记录所有监控数据和异常

#### 2. 故障处理
- **自动恢复**: 启用自动超时处理
- **手动干预**: 必要时手动释放锁
- **问题排查**: 使用详细状态端点排查问题

#### 3. 性能优化
- **合理间隔**: 设置合适的监控间隔（30秒）
- **批量查询**: 使用 `/heartbeat/all` 批量检查任务
- **过滤监控**: 只监控关键资源

#### 4. 告警设置
- **阈值告警**: GPU锁占用率超过80%
- **超时告警**: 任务心跳超过2分钟未更新
- **错误率告警**: 心跳故障率超过10%

#### 5. 调试技巧
- **查看历史**: 检查 `recent_history` 字段
- **统计数据**: 分析 `statistics` 了解趋势
- **组件健康**: 分别检查各组件状态

---

## 性能说明

- **状态查询**: < 50ms
- **心跳更新**: < 10ms
- **监控器检查**: 每30秒自动执行
- **自动恢复**: < 100ms

## 相关文档

- [工作流API](WORKFLOW_API.md)
- [单任务API](SINGLE_TASK_API.md)
- [文件操作API](FILE_OPERATIONS_API.md)
- [GPU锁完整指南](../technical/reference/GPU_LOCK_COMPLETE_GUIDE.md)

## 更新日志

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2025-12-05 | 初始监控API文档 |

---

*最后更新: 2025-12-05 | 文档版本: 1.0.0*
