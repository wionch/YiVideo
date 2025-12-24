# Spec Delta: GPU锁原子性操作

## Capability
`gpu-lock-atomicity`

## 变更类型
- [x] MODIFIED Requirements
- [x] ADDED Requirements
- [ ] REMOVED Requirements

---

## MODIFIED Requirements

### Requirement: GPU_LOCK_ATOM_001 - 锁释放原子性

GPU锁释放操作 MUST 使用 Redis Lua 脚本保证原子性,所有"检查-修改"模式的操作 SHALL 在单个原子事务中完成,禁止使用 GET + DELETE 的非原子组合。

**修改原因**: 现有 `release_lock` 方法使用 GET + DELETE 非原子操作,存在严重竞态条件。

#### 修改前行为
```python
def release_lock(self, task_name: str, lock_key: str, release_reason: str = "normal"):
    lock_value = redis_client.get(lock_key)  # 步骤1
    if lock_value and task_name in lock_value:
        redis_client.delete(lock_key)  # 步骤2 - 非原子!
```

#### 修改后行为
```python
def release_lock(self, task_name: str, lock_key: str, release_reason: str = "normal") -> bool:
    lua_script = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        redis.call("del", KEYS[1])
        return 1
    else
        return 0
    end
    """
    lock_value = f"locked_by_{task_name}"
    result = redis_client.eval(lua_script, 1, lock_key, lock_value)
    return result == 1
```

#### Scenario: 并发释放锁不会导致误删

**Given**:
- 任务A 持有锁 `gpu_lock:0`,值为 `locked_by_task_a`
- 任务A 崩溃,finally 块延迟执行
- Redis 锁自动过期 (600秒后)
- 任务B 获取锁,值为 `locked_by_task_b`

**When**:
- 任务A 的 finally 块延迟执行,尝试释放锁

**Then**:
- Lua 脚本检查锁值不匹配 (`locked_by_task_b` != `locked_by_task_a`)
- 锁不被删除
- 任务B 的锁保持有效
- `release_lock` 返回 `False` 并记录警告日志

**Acceptance Criteria**:
```python
# tests/unit/test_gpu_lock_atomicity.py
def test_release_lock_ownership_verification():
    """验证锁释放的所有权验证"""
    lock_key = "gpu_lock:0"

    # 任务A 获取锁
    redis_client.set(lock_key, "locked_by_task_a", ex=600)

    # 任务B 尝试释放任务A的锁
    result = lock_manager.release_lock("task_b", lock_key, "malicious")

    # 验证: 释放失败,锁仍存在
    assert result is False
    assert redis_client.get(lock_key) == "locked_by_task_a"
```

---

## ADDED Requirements

### Requirement: GPU_LOCK_ATOM_002 - 监控强制释放原子性

监控系统的强制释放操作 MUST 使用 Lua 脚本原子删除锁并返回旧值,确保不会误删正在运行任务的锁,所有强制释放操作 SHALL 记录被释放锁的原持有者信息。

**添加原因**: 监控系统的 `_force_release_lock` 方法存在与锁释放相同的竞态条件。

#### 新增行为
监控系统必须使用原子操作强制释放超时锁。

#### Scenario: 监控强制释放不会误删正常任务的锁

**Given**:
- 监控检测到锁 `gpu_lock:0` 超时 (持有者: task_a, 持有时间: 3601秒)
- 监控准备强制释放锁

**When**:
- 在监控执行强制释放前,任务A 正常完成并释放锁
- 任务B 立即获取锁,值为 `locked_by_task_b`
- 监控的强制释放操作延迟执行

**Then**:
- Lua 脚本原子删除锁并返回旧值
- 如果锁已被任务B持有,监控检测到值变化
- 监控记录日志: "锁已被其他任务获取,跳过强制释放"
- 任务B 的锁不被误删

**Acceptance Criteria**:
```python
# services/api_gateway/app/monitoring/gpu_lock_monitor.py
def _force_release_lock(self, lock_key: str) -> bool:
    lua_script = """
    local lock_value = redis.call("get", KEYS[1])
    if lock_value then
        redis.call("del", KEYS[1])
        return lock_value
    else
        return nil
    end
    """

    released_value = self.redis_client.eval(lua_script, 1, lock_key)

    if released_value:
        logger.info(f"强制释放锁 {lock_key} (持有者: {released_value})")
        pub_sub_manager.publish_lock_release(lock_key, released_value, "forced_by_monitor")
        return True
    else:
        logger.info(f"锁 {lock_key} 已不存在")
        return True
```

---

### Requirement: GPU_LOCK_ATOM_003 - Lua 脚本错误处理

所有 Lua 脚本执行 MUST 包含异常处理,脚本执行失败 SHALL 记录详细错误日志并触发告警,系统 SHOULD 提供脚本执行统计和错误率监控。

**添加原因**: Lua 脚本可能因 Redis 版本不兼容或语法错误而失败,需要完善的错误处理。

#### 新增行为
系统必须捕获和处理 Lua 脚本执行错误。

#### Scenario: Lua 脚本执行失败时的降级处理

**Given**:
- Redis 版本不支持某个 Lua 函数
- 或 Redis 连接不稳定

**When**:
- 执行 `release_lock` 时 Lua 脚本失败

**Then**:
- 捕获异常并记录详细错误信息
- 增加 `release_script_errors` 统计计数
- 触发告警通知运维团队
- 尝试应急释放方式 (直接 DELETE)

**Acceptance Criteria**:
```python
# services/common/locks.py
def release_lock(self, task_name: str, lock_key: str, release_reason: str = "normal") -> bool:
    try:
        result = redis_client.eval(RELEASE_LOCK_SCRIPT, 1, lock_key, lock_value)
        if result == 1:
            return True
        else:
            self.exception_stats["ownership_violations"] += 1
            return False
    except redis.exceptions.ResponseError as e:
        # Lua 脚本执行错误
        logger.error(f"Lua 脚本执行失败: {e}", exc_info=True)
        self.exception_stats["release_script_errors"] += 1
        send_alert("lua_script_error", {"lock_key": lock_key, "error": str(e)})
        return False
    except Exception as e:
        logger.error(f"释放锁异常: {e}", exc_info=True)
        return False
```

---

### Requirement: GPU_LOCK_ATOM_004 - 锁获取原子性 (可选优化)

GPU锁获取操作 SHOULD 使用 Lua 脚本保证原子性,避免 EXISTS + SET 的竞态条件,所有锁获取操作 SHALL 包含过期时间设置,防止永久锁。

**添加原因**: 虽然当前 `SET NX EX` 已是原子操作,但显式使用 Lua 脚本可提高一致性和可维护性。

#### 新增行为
锁获取操作应使用 Lua 脚本实现 (可选优化)。

#### Scenario: 原子获取锁

**Given**:
- 锁 `gpu_lock:0` 不存在

**When**:
- 任务A 和任务B 同时尝试获取锁

**Then**:
- Lua 脚本原子检查锁是否存在
- 只有一个任务成功获取锁
- 另一个任务获取失败,进入等待轮询

**Acceptance Criteria**:
```python
# services/common/locks.py (可选优化)
ACQUIRE_LOCK_SCRIPT = """
if redis.call("exists", KEYS[1]) == 0 then
    redis.call("set", KEYS[1], ARGV[1], "EX", ARGV[2])
    return 1
else
    return 0
end
"""

def _try_acquire_lock(self, lock_key: str, lock_value: str, timeout: int) -> bool:
    result = redis_client.eval(ACQUIRE_LOCK_SCRIPT, 1, lock_key, lock_value, timeout)
    return result == 1
```

---

## 验证方法

### 单元测试

```python
# tests/unit/test_gpu_lock_atomicity.py
import pytest
import threading
import time
from services.common.locks import lock_manager, redis_client

def test_concurrent_release_no_race_condition():
    """验证并发释放锁不会导致竞态条件"""
    lock_key = "gpu_lock:0"

    # 任务A 获取锁
    redis_client.set(lock_key, "locked_by_task_a", ex=600)

    # 模拟并发释放
    results = []

    def release_by_task_a():
        result = lock_manager.release_lock("task_a", lock_key, "normal")
        results.append(("task_a", result))

    def release_by_task_b():
        result = lock_manager.release_lock("task_b", lock_key, "malicious")
        results.append(("task_b", result))

    threads = [
        threading.Thread(target=release_by_task_a),
        threading.Thread(target=release_by_task_b),
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 验证: 只有任务A 成功释放
    assert ("task_a", True) in results
    assert ("task_b", False) in results
    assert not redis_client.exists(lock_key)

def test_lua_script_error_handling():
    """验证 Lua 脚本错误处理"""
    with patch('services.common.locks.redis_client') as mock_redis:
        # 模拟 Lua 脚本执行错误
        mock_redis.eval.side_effect = redis.exceptions.ResponseError("ERR unknown command")

        result = lock_manager.release_lock("test_task", "gpu_lock:0", "normal")

        # 验证: 返回 False 并记录错误
        assert result is False
        assert lock_manager.exception_stats["release_script_errors"] == 1
```

### 集成测试

```python
# tests/integration/test_gpu_lock_atomicity.py
@pytest.mark.integration
def test_monitor_force_release_atomicity():
    """验证监控强制释放的原子性"""
    from services.api_gateway.app.monitoring.gpu_lock_monitor import GPULockMonitor

    lock_key = "gpu_lock:0"
    monitor = GPULockMonitor()

    # 任务A 获取锁
    redis_client.set(lock_key, "locked_by_task_a", ex=600)

    # 模拟监控检测到超时
    time.sleep(1)

    # 在监控强制释放前,任务A 正常释放并被任务B 获取
    redis_client.set(lock_key, "locked_by_task_b", ex=600)

    # 监控尝试强制释放
    result = monitor._force_release_lock(lock_key)

    # 验证: 强制释放成功,但返回的是任务B的锁值
    assert result is True
    # 检查日志中记录了正确的持有者
```

---

## 依赖关系

### 上游依赖
- 无 (可立即实施)

### 下游依赖
- `gpu-lock-error-handling` 能力依赖本规范完成 (异常处理需要原子操作作为基础)

---

## 影响范围

### 受影响的文件
- `services/common/locks.py` - 核心锁管理器
- `services/api_gateway/app/monitoring/gpu_lock_monitor.py` - 监控系统

### 受影响的服务
- 所有使用 `@gpu_lock()` 装饰器的服务 (7个)

---

**规范作者**: Claude AI
**创建日期**: 2025-12-24
**关联提案**: `fix-gpu-lock-deadlock-risks`
**实施优先级**: P0 (Critical)
