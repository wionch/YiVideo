# Spec Delta: GPU锁超时配置优化

## Capability
`gpu-lock-configuration`

## 变更类型
- [x] MODIFIED Requirements
- [ ] ADDED Requirements
- [ ] REMOVED Requirements

---

## MODIFIED Requirements

### Requirement: GPU_LOCK_CFG_001 - 锁超时时间优化

GPU锁超时配置 MUST 降低以加快死锁恢复速度,`lock_timeout` SHALL 从 3600秒降低到 600秒,`max_wait_time` SHALL 从 1800秒降低到 300秒,所有超时配置变更 MUST 经过性能测试验证。

**修改原因**: 当前超时配置过长,导致死锁恢复时间长达 1-2 小时。

#### 修改前配置
```yaml
gpu_lock:
  poll_interval: 2
  max_wait_time: 1800        # 30 分钟
  lock_timeout: 3600         # 60 分钟
  max_poll_interval: 10

gpu_lock_monitor:
  timeout_levels:
    warning: 1800            # 30 分钟
    soft_timeout: 3600       # 60 分钟
    hard_timeout: 7200       # 120 分钟
```

#### 修改后配置
```yaml
gpu_lock:
  poll_interval: 2
  max_wait_time: 300         # 5 分钟 (从 30 分钟降低)
  lock_timeout: 600          # 10 分钟 (从 60 分钟降低)
  max_poll_interval: 10

  # 新增: 心跳配置
  heartbeat:
    enabled: true
    interval: 60             # 心跳间隔 (秒)
    timeout: 300             # 心跳超时 (秒)

gpu_lock_monitor:
  timeout_levels:
    warning: 300             # 5 分钟 (从 30 分钟降低)
    soft_timeout: 600        # 10 分钟 (从 60 分钟降低)
    hard_timeout: 900        # 15 分钟 (从 120 分钟降低)

  heartbeat:
    interval: 60
    timeout: 300

  cleanup:
    max_retry: 3
    retry_delay: 60

  enabled: true
  auto_recovery: true
```

#### Scenario: 任务崩溃后快速恢复

**Given**:
- PaddleOCR 任务在处理第 1 帧时崩溃
- 锁未释放

**When**:
- 使用旧配置: 锁保留 60 分钟,监控 120 分钟后强制释放
- 使用新配置: 锁保留 10 分钟,监控 15 分钟后强制释放

**Then**:
- **旧配置**: 后续任务等待 1-2 小时
- **新配置**: 后续任务等待 10-15 分钟
- **改进**: 死锁恢复时间减少 75-87%

**Acceptance Criteria**:
```python
# tests/integration/test_gpu_lock_timeout.py
@pytest.mark.integration
def test_fast_recovery_on_task_crash():
    """验证任务崩溃后快速恢复"""
    lock_key = "gpu_lock:0"

    # 模拟任务崩溃 (获取锁但不释放)
    redis_client.set(lock_key, "locked_by_crashed_task", ex=600)

    # 记录开始时间
    start_time = time.time()

    # 等待锁自动过期
    while redis_client.exists(lock_key):
        time.sleep(1)

    recovery_time = time.time() - start_time

    # 验证: 恢复时间 < 15 分钟
    assert recovery_time < 900  # 15 分钟
    assert recovery_time >= 600  # 至少 10 分钟 (lock_timeout)
```

---

### Requirement: GPU_LOCK_CFG_002 - 长任务保护机制

系统 MUST 支持长时间运行任务的保护机制,长任务 SHALL 通过装饰器参数覆盖默认超时配置,所有长任务 MUST 实现心跳更新,防止被监控系统误杀。

**修改原因**: 降低超时配置可能导致正常的长时间运行任务被误判为死锁。

#### 新增行为
系统必须支持长任务自定义超时配置。

#### Scenario: 长时间 OCR 任务不被误杀

**Given**:
- 大视频 OCR 任务预计运行 1 小时
- 默认 `max_wait_time` 为 300 秒

**When**:
- 任务使用装饰器参数覆盖超时:
  ```python
  @gpu_lock(gpu_id=0, max_wait_time=3600, lock_timeout=7200)
  def long_ocr_task():
      # 处理大视频
      pass
  ```
- 任务每 60 秒更新心跳

**Then**:
- 任务可以运行 1 小时而不被超时
- 监控系统检查心跳,判定任务正常运行
- 任务不被强制终止

**Acceptance Criteria**:
```python
# services/common/locks.py
def gpu_lock(gpu_id: int = 0, max_wait_time: int = None, lock_timeout: int = None):
    """
    GPU 锁装饰器

    Args:
        gpu_id: GPU 设备 ID
        max_wait_time: 最大等待时间 (秒),覆盖默认配置
        lock_timeout: 锁超时时间 (秒),覆盖默认配置
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 使用自定义超时或默认配置
            actual_max_wait = max_wait_time or config["gpu_lock"]["max_wait_time"]
            actual_lock_timeout = lock_timeout or config["gpu_lock"]["lock_timeout"]

            # ... 使用 actual_max_wait 和 actual_lock_timeout ...
        return wrapper
    return decorator

# 使用示例
@gpu_lock(gpu_id=0, max_wait_time=3600, lock_timeout=7200)
def process_large_video():
    """处理大视频 (预计 1 小时)"""
    pass
```

---

### Requirement: GPU_LOCK_CFG_003 - 监控超时分级策略

监控系统 MUST 实现分级超时策略,`warning` 级别 SHALL 仅记录日志,`soft_timeout` 级别 SHALL 检查心跳后决定是否释放,`hard_timeout` 级别 SHALL 强制释放锁,所有超时级别 MUST 可配置。

**修改原因**: 需要更细粒度的超时控制,避免"一刀切"的强制释放。

#### 新增行为
监控系统必须实现分级超时策略。

#### Scenario: 分级超时处理

**Given**:
- 任务持有锁 `gpu_lock:0`
- 配置:
  ```yaml
  timeout_levels:
    warning: 300       # 5 分钟
    soft_timeout: 600  # 10 分钟
    hard_timeout: 900  # 15 分钟
  ```

**When**:
- 锁持有时间达到不同级别

**Then**:
- **5 分钟 (warning)**: 记录警告日志,不采取行动
- **10 分钟 (soft_timeout)**: 检查心跳
  - 心跳正常 → 不释放,继续监控
  - 心跳超时 → 强制释放
- **15 分钟 (hard_timeout)**: 无条件强制释放

**Acceptance Criteria**:
```python
# services/api_gateway/app/monitoring/gpu_lock_monitor.py
def _check_lock_timeout(self, lock_key: str, lock_value: str, lock_age: float):
    """检查锁超时并采取相应行动"""
    timeout_levels = self.config.get("timeout_levels", {})

    # 1. Warning 级别
    if lock_age >= timeout_levels.get("warning", 300):
        logger.warning(f"锁 {lock_key} 持有时间过长: {lock_age:.1f}秒")

    # 2. Soft Timeout 级别
    if lock_age >= timeout_levels.get("soft_timeout", 600):
        if self._check_heartbeat(lock_key):
            logger.info(f"锁 {lock_key} 心跳正常,继续监控")
            return
        else:
            logger.warning(f"锁 {lock_key} 心跳超时,准备强制释放")
            self._force_release_lock(lock_key)
            return

    # 3. Hard Timeout 级别
    if lock_age >= timeout_levels.get("hard_timeout", 900):
        logger.error(f"锁 {lock_key} 达到 hard_timeout,强制释放")
        self._force_release_lock(lock_key)
        return
```

---

### Requirement: GPU_LOCK_CFG_004 - 配置验证和回滚

所有配置变更 MUST 在测试环境验证后才能应用到生产环境,配置变更 SHALL 通过金丝雀部署逐步推广,系统 MUST 支持一键回滚到稳定配置。

**修改原因**: 配置变更有风险,需要完善的验证和回滚机制。

#### 新增行为
系统必须支持配置验证和回滚。

#### Scenario: 配置变更验证流程

**Given**:
- 准备应用新的超时配置

**When**:
- 运维人员执行验证流程:
  1. 在测试环境应用新配置
  2. 执行性能基准测试
  3. 验证通过后,金丝雀部署 (10% 节点)
  4. 观察 24 小时无异常
  5. 灰度发布 (50% 节点)
  6. 全量发布

**Then**:
- 每个阶段都有明确的验证标准
- 任何阶段失败都可以快速回滚
- 全量发布后持续监控 7 天

**Acceptance Criteria**:
```bash
#!/bin/bash
# scripts/validate_gpu_lock_config.sh

# 1. 备份当前配置
cp config.yml config.yml.backup

# 2. 应用新配置
cat > config.yml <<EOF
gpu_lock:
  max_wait_time: 300
  lock_timeout: 600
  # ...
EOF

# 3. 重启服务
docker-compose restart api_gateway

# 4. 执行基准测试
python tests/performance/test_gpu_lock_performance.py

# 5. 验证结果
if [ $? -eq 0 ]; then
    echo "✅ 配置验证通过"
else
    echo "❌ 配置验证失败,回滚"
    cp config.yml.backup config.yml
    docker-compose restart api_gateway
    exit 1
fi
```

---

## 验证方法

### 性能基准测试

```python
# tests/performance/test_gpu_lock_timeout.py
import pytest
import time
from services.common.locks import lock_manager

@pytest.mark.performance
def test_lock_timeout_recovery_time():
    """验证锁超时恢复时间"""
    lock_key = "gpu_lock:0"

    # 模拟任务崩溃
    redis_client.set(lock_key, "locked_by_crashed_task", ex=600)

    start_time = time.time()

    # 等待锁自动过期
    while redis_client.exists(lock_key):
        time.sleep(1)

    recovery_time = time.time() - start_time

    # 验证: 恢复时间在 10-15 分钟之间
    assert 600 <= recovery_time <= 900

@pytest.mark.performance
def test_long_task_not_killed():
    """验证长任务不被误杀"""
    @gpu_lock(gpu_id=0, max_wait_time=3600, lock_timeout=7200)
    def long_task():
        time.sleep(1200)  # 运行 20 分钟

    # 执行长任务
    start_time = time.time()
    long_task()
    duration = time.time() - start_time

    # 验证: 任务成功完成
    assert duration >= 1200
```

### 压力测试

```python
# tests/stress/test_gpu_lock_config.py
@pytest.mark.stress
def test_concurrent_tasks_with_new_config():
    """验证新配置下的并发性能"""
    results = []

    def task(task_id):
        try:
            @gpu_lock(gpu_id=0)
            def work():
                time.sleep(2)
                results.append(task_id)
            work()
        except Exception as e:
            logger.error(f"任务 {task_id} 失败: {e}")

    # 启动 50 个并发任务
    threads = [threading.Thread(target=task, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 验证: 成功率 > 90%
    success_rate = len(results) / 50
    assert success_rate > 0.9
```

---

## 依赖关系

### 上游依赖
- `gpu-lock-monitoring` 能力 (心跳检测机制)

### 下游依赖
- 无

---

## 影响范围

### 受影响的文件
- `config.yml` - 配置文件更新

### 受影响的服务
- 所有使用 GPU 锁的服务 (7个)

---

## 风险评估

### 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 长任务超时 | 中 | 高 | 装饰器参数覆盖 + 心跳检测 |
| 配置回滚失败 | 低 | 高 | 自动化回滚脚本 + 备份 |
| 性能下降 | 低 | 中 | 性能基准测试验证 |

---

**规范作者**: Claude AI
**创建日期**: 2025-12-24
**关联提案**: `fix-gpu-lock-deadlock-risks`
**实施优先级**: P1 (High)
