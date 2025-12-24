# Spec Delta: GPU锁异常处理

## Capability
`gpu-lock-error-handling`

## 变更类型
- [x] MODIFIED Requirements
- [x] ADDED Requirements
- [ ] REMOVED Requirements

---

## MODIFIED Requirements

### Requirement: GPU_LOCK_ERR_001 - Finally 块异常隔离

GPU锁释放的 finally 块 MUST 确保锁一定被释放,即使发生异常,所有 finally 块中的操作 SHALL 使用独立的 try-except 包裹,禁止异常向上传播导致锁泄漏。

**修改原因**: 现有 finally 块中的 `release_lock` 调用可能抛出异常,导致锁永远不会释放。

#### 修改前行为
```python
finally:
    try:
        force_cleanup_gpu_memory(aggressive=True)
    except Exception as cleanup_e:
        logger.warning(f"GPU显存清理失败: {cleanup_e}")

    lock_manager.release_lock(task_name, lock_key, "normal")  # ❌ 可能抛异常!
```

#### 修改后行为
```python
finally:
    # 第一层: GPU 显存清理
    try:
        force_cleanup_gpu_memory(aggressive=True)
    except Exception as cleanup_e:
        logger.warning(f"GPU显存清理失败: {cleanup_e}")

    # 第二层: 正常锁释放
    lock_released = False
    try:
        lock_released = lock_manager.release_lock(task_name, lock_key, "normal")
    except Exception as release_error:
        logger.critical(f"正常释放锁失败: {release_error}", exc_info=True)

    # 第三层: 应急强制释放
    if not lock_released:
        try:
            logger.warning(f"使用应急方式释放锁 {lock_key}")
            redis_client.delete(lock_key)
            send_alert("gpu_lock_emergency_release", {
                "lock_key": lock_key,
                "task_name": task_name
            })
        except Exception as emergency_error:
            logger.critical(f"应急释放锁也失败: {emergency_error}", exc_info=True)
            record_critical_failure(lock_key, task_name, emergency_error)
```

#### Scenario: Redis 连接断开时仍能释放锁

**Given**:
- 任务正在执行,持有锁 `gpu_lock:0`
- Redis 连接突然断开

**When**:
- 任务完成,进入 finally 块
- `release_lock` 调用失败 (Redis 连接错误)

**Then**:
- 捕获异常,记录严重错误日志
- 触发应急释放机制
- 应急释放尝试直接删除锁 (可能失败)
- 记录到持久化存储,触发人工干预告警
- 异常不向上传播,任务正常结束

**Acceptance Criteria**:
```python
# tests/unit/test_gpu_lock_error_handling.py
def test_finally_block_exception_isolation():
    """验证 finally 块异常隔离"""
    with patch('services.common.locks.redis_client') as mock_redis:
        # 模拟 Redis 连接断开
        mock_redis.eval.side_effect = redis.ConnectionError("Connection lost")
        mock_redis.delete.side_effect = redis.ConnectionError("Connection lost")

        # 执行任务
        @gpu_lock(gpu_id=0)
        def task():
            pass

        # 验证: 任务正常完成,不抛异常
        task()  # 不应抛出异常

        # 验证: 记录了严重错误日志
        # (需要 mock logger 验证)
```

---

## ADDED Requirements

### Requirement: GPU_LOCK_ERR_002 - 应急释放机制

系统 MUST 提供应急锁释放机制,当正常释放失败时自动触发,应急释放 SHALL 直接删除锁而不验证所有权,所有应急释放操作 MUST 发送告警通知运维团队。

**添加原因**: 需要在极端情况下 (如 Redis 故障) 确保锁能被释放。

#### 新增行为
系统必须在正常释放失败时自动触发应急释放。

#### Scenario: 应急释放机制自动触发

**Given**:
- 任务持有锁 `gpu_lock:0`
- Redis Lua 脚本执行失败

**When**:
- `release_lock` 返回 `False` 或抛出异常

**Then**:
- 检测到释放失败
- 自动触发应急释放
- 直接调用 `redis_client.delete(lock_key)`
- 发送告警: "gpu_lock_emergency_release"
- 记录详细日志: 锁键、任务名、失败原因

**Acceptance Criteria**:
```python
# services/common/locks.py
def _emergency_release_lock(self, lock_key: str, task_name: str, reason: str):
    """应急释放锁 (不验证所有权)"""
    try:
        logger.warning(f"应急释放锁 {lock_key} (任务: {task_name}, 原因: {reason})")

        # 直接删除锁
        redis_client.delete(lock_key)

        # 增加统计
        self.exception_stats["emergency_releases"] += 1

        # 发送告警
        send_alert("gpu_lock_emergency_release", {
            "lock_key": lock_key,
            "task_name": task_name,
            "reason": reason,
            "timestamp": time.time()
        })

        return True
    except Exception as e:
        logger.critical(f"应急释放锁失败: {e}", exc_info=True)
        record_critical_failure(lock_key, task_name, e)
        return False
```

---

### Requirement: GPU_LOCK_ERR_003 - IndexTTS 服务方法调用修复

IndexTTS 服务 MUST 修复 `on_failure` 回调中调用不存在方法的错误,所有服务 SHALL 正确使用锁管理器的 API,任务失败回调 MUST 能正确释放锁。

**添加原因**: IndexTTS 服务调用了不存在的 `force_release_lock()` 方法,导致任务失败时无法释放锁。

#### 新增行为
IndexTTS 服务必须使用正确的方法签名释放锁。

#### Scenario: IndexTTS 任务失败时正确释放锁

**Given**:
- IndexTTS 任务正在执行,持有锁 `gpu_lock:0`
- 任务执行过程中发生异常

**When**:
- Celery 调用 `on_failure` 回调

**Then**:
- `on_failure` 回调正常执行 (不抛 AttributeError)
- 正确调用 `gpu_lock_manager.release_lock(task_name, lock_key, "task_failure")`
- 锁被成功释放
- 记录任务失败日志

**Acceptance Criteria**:
```python
# services/workers/indextts_service/app/tasks.py
from .celery_app import celery_app, gpu_lock_manager  # ✅ 导入已正确

class IndexTTSTask(Task):
    def __init__(self):
        super().__init__()
        self.gpu_lock_manager = gpu_lock_manager  # ✅ 变量名已正确

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"任务 {task_id} 失败: {exc}")

        # ✅ 修复：使用正确的方法签名
        if self.gpu_lock_manager:
            try:
                gpu_id = kwargs.get('gpu_id', 0)
                lock_key = f"gpu_lock:{gpu_id}"
                task_name = task_id
                self.gpu_lock_manager.release_lock(task_name, lock_key, "task_failure")
                logger.info(f"任务 {task_id} 失败后成功释放锁 {lock_key}")
            except Exception as e:
                logger.error(f"释放锁失败: {e}", exc_info=True)
```

**验证测试**:
```python
# tests/unit/test_indextts_error_handling.py
def test_indextts_on_failure_releases_lock():
    """验证 IndexTTS 任务失败时释放锁"""
    from services.workers.indextts_service.app.tasks import IndexTTSTask

    task = IndexTTSTask()
    lock_key = "gpu_lock:0"

    # 模拟任务持有锁
    redis_client.set(lock_key, "locked_by_test_task", ex=600)

    # 模拟任务失败
    task.on_failure(
        exc=Exception("Test failure"),
        task_id="test_task",
        args=(),
        kwargs={'gpu_id': 0},
        einfo=None
    )

    # 验证: 锁已释放
    assert not redis_client.exists(lock_key)
```

---

### Requirement: GPU_LOCK_ERR_004 - 异常统计和监控

系统 MUST 记录所有锁相关异常的统计信息,包括正常释放失败次数、应急释放次数、Lua 脚本错误次数、所有权验证失败次数,系统 SHOULD 提供异常率监控和告警。

**添加原因**: 需要可观测性来监控锁系统的健康状态。

#### 新增行为
系统必须记录和暴露异常统计信息。

#### Scenario: 查询异常统计信息

**Given**:
- 系统已运行一段时间
- 发生了多次锁释放异常

**When**:
- 运维人员查询异常统计:
  ```bash
  curl http://localhost:8788/api/v1/monitoring/gpu-lock/exception-stats
  ```

**Then**:
- API 返回详细的异常统计:
  ```json
  {
    "normal_release_failures": 5,
    "emergency_releases": 3,
    "release_script_errors": 2,
    "ownership_violations": 1,
    "exception_rate": 0.05,
    "emergency_release_rate": 0.03,
    "total_locks": 100,
    "timestamp": 1703433600
  }
  ```

**Acceptance Criteria**:
```python
# services/common/locks.py
class SmartGpuLockManager:
    def __init__(self):
        # ... 现有代码 ...

        # 新增: 异常统计
        self.exception_stats = {
            "normal_release_failures": 0,
            "emergency_releases": 0,
            "release_script_errors": 0,
            "ownership_violations": 0,
        }

    def get_exception_statistics(self) -> Dict[str, Any]:
        """获取异常统计信息"""
        total_locks = self.lock_stats.get("total_locks", 1)
        return {
            **self.exception_stats,
            "exception_rate": self.exception_stats["normal_release_failures"] / max(total_locks, 1),
            "emergency_release_rate": self.exception_stats["emergency_releases"] / max(total_locks, 1),
            "total_locks": total_locks,
            "timestamp": time.time()
        }

# services/api_gateway/app/routes/monitoring.py
@router.get("/gpu-lock/exception-stats")
async def get_gpu_lock_exception_stats():
    """获取 GPU 锁异常统计"""
    return lock_manager.get_exception_statistics()
```

---

### Requirement: GPU_LOCK_ERR_005 - 关键失败持久化

当应急释放也失败时,系统 MUST 将失败信息记录到持久化存储,所有关键失败 SHALL 触发 P0 级别告警,系统 SHOULD 提供失败恢复工具。

**添加原因**: 极端情况下需要人工干预,必须保留足够的信息用于问题定位和恢复。

#### 新增行为
系统必须持久化关键失败信息。

#### Scenario: 关键失败记录和告警

**Given**:
- 任务持有锁 `gpu_lock:0`
- Redis 完全不可用

**When**:
- 正常释放失败
- 应急释放也失败

**Then**:
- 调用 `record_critical_failure`
- 失败信息写入文件: `/var/log/yivideo/gpu_lock_critical_failures.log`
- 触发 P0 级别告警
- 告警包含: 锁键、任务名、失败时间、错误堆栈

**Acceptance Criteria**:
```python
# services/common/locks.py
def record_critical_failure(lock_key: str, task_name: str, error: Exception):
    """记录关键失败到持久化存储"""
    failure_record = {
        "lock_key": lock_key,
        "task_name": task_name,
        "error": str(error),
        "traceback": traceback.format_exc(),
        "timestamp": time.time(),
        "hostname": socket.gethostname()
    }

    # 写入日志文件
    log_file = "/var/log/yivideo/gpu_lock_critical_failures.log"
    try:
        with open(log_file, "a") as f:
            f.write(json.dumps(failure_record) + "\n")
    except Exception as e:
        logger.critical(f"无法写入关键失败日志: {e}")

    # 触发 P0 告警
    send_alert("gpu_lock_critical_failure", {
        "level": "P0",
        "message": f"GPU 锁关键失败: {lock_key}",
        "details": failure_record
    })
```

---

## 验证方法

### 单元测试

```python
# tests/unit/test_gpu_lock_error_handling.py
import pytest
from unittest.mock import patch, MagicMock
import redis
from services.common.locks import lock_manager

def test_emergency_release_on_normal_failure():
    """验证正常释放失败时触发应急释放"""
    with patch('services.common.locks.redis_client') as mock_redis:
        # 模拟 Lua 脚本失败
        mock_redis.eval.side_effect = redis.ConnectionError("Connection lost")
        # 应急释放成功
        mock_redis.delete.return_value = True

        # 执行释放
        @gpu_lock(gpu_id=0)
        def task():
            pass

        task()

        # 验证: 应急释放被调用
        mock_redis.delete.assert_called_once_with("gpu_lock:0")

        # 验证: 统计计数增加
        assert lock_manager.exception_stats["emergency_releases"] == 1

def test_critical_failure_recording():
    """验证关键失败记录"""
    with patch('services.common.locks.redis_client') as mock_redis:
        # 模拟所有释放方式都失败
        mock_redis.eval.side_effect = redis.ConnectionError("Connection lost")
        mock_redis.delete.side_effect = redis.ConnectionError("Connection lost")

        with patch('services.common.locks.record_critical_failure') as mock_record:
            @gpu_lock(gpu_id=0)
            def task():
                pass

            task()

            # 验证: 关键失败被记录
            mock_record.assert_called_once()
            args = mock_record.call_args[0]
            assert args[0] == "gpu_lock:0"  # lock_key
```

### 集成测试

```python
# tests/integration/test_gpu_lock_error_handling.py
@pytest.mark.integration
def test_indextts_task_failure_integration():
    """集成测试: IndexTTS 任务失败场景"""
    from services.workers.indextts_service.app.tasks import generate_speech

    # 模拟任务失败
    with pytest.raises(Exception):
        generate_speech.apply(kwargs={
            'text': 'test',
            'gpu_id': 0,
            'invalid_param': 'cause_error'  # 触发失败
        })

    # 验证: 锁已释放
    time.sleep(1)
    assert not redis_client.exists("gpu_lock:0")
```

---

## 依赖关系

### 上游依赖
- `gpu-lock-atomicity` 能力必须先完成 (原子操作是异常处理的基础)

### 下游依赖
- 无

---

## 影响范围

### 受影响的文件
- `services/common/locks.py` - 核心锁管理器 (finally 块增强)
- `services/workers/indextts_service/app/tasks.py` - IndexTTS 服务修复

### 新增文件
- `/var/log/yivideo/gpu_lock_critical_failures.log` - 关键失败日志

---

**规范作者**: Claude AI
**创建日期**: 2025-12-24
**关联提案**: `fix-gpu-lock-deadlock-risks`
**实施优先级**: P0 (Critical)
