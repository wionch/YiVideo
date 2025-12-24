# Proposal: 修复GPU锁死锁风险和资源泄漏问题

## 变更ID
`fix-gpu-lock-deadlock-risks`

## 变更类型
- [ ] 文档修复 (Documentation Fix)
- [ ] 配置优化 (Configuration Optimization)
- [ ] 新功能 (Feature)
- [x] **Bug 修复 (Critical Bug Fix)**
- [ ] 破坏性变更 (Breaking Change)

## 问题陈述

### 背景

通过对 `services/common/locks.py` 和相关 GPU 锁使用代码的深度审查，发现了**多个可能导致死锁和资源泄漏的严重缺陷**。这些问题在生产环境中可能导致：
- GPU 资源永久锁定，所有后续任务阻塞
- 系统停机时间长达 1-2 小时
- 多个任务同时使用 GPU 导致 CUDA 错误

### 发现的关键问题

#### 🔴 **Critical 级别问题**

##### 1. **锁释放逻辑存在严重竞态条件**

**位置**: `services/common/locks.py:449-487`

**问题**:
```python
def release_lock(self, task_name: str, lock_key: str, release_reason: str = "normal"):
    lock_value = redis_client.get(lock_key)  # 步骤1
    if lock_value and task_name in lock_value:
        redis_client.delete(lock_key)  # 步骤2 ❌ 非原子操作!
```

**竞态场景**:
```
T0: 任务A 执行 get(lock_key) → "locked_by_task_a"
T1: 任务A 崩溃，锁未释放
T2: Redis 锁自动过期 (3600秒后)
T3: 任务B 获取锁 → set(lock_key, "locked_by_task_b")
T4: 任务A 的 finally 块延迟执行 delete(lock_key)
T5: 任务B 的锁被误删! ❌
T6: 任务C 也获取到锁 → 两个任务同时持有锁!
```

**影响**:
- **GPU 资源竞争**: 两个任务同时使用 GPU
- **CUDA OOM**: 显存不足导致崩溃
- **数据损坏**: 并发写入导致结果错误

##### 2. **IndexTTS 服务调用不存在的方法**

**位置**: `services/workers/indextts_service/app/tasks.py:56`

**问题**:
```python
# 第38行导入 (正确)
from .celery_app import celery_app, gpu_lock_manager

# 第49行使用 (正确)
class IndexTTSTask(Task):
    def __init__(self):
        self.gpu_lock_manager = gpu_lock_manager  # ✅ 变量名正确

# 第56行调用 (错误)
def on_failure(self, exc, task_id, args, kwargs, einfo):
    if self.gpu_lock_manager:
        self.gpu_lock_manager.force_release_lock()  # ❌ 方法不存在!
```

**实际情况**:
- `gpu_lock_manager` 变量名是正确的 (从 `celery_app.py` 导入)
- 但 `SmartGpuLockManager` 类**没有** `force_release_lock()` 方法
- 正确的方法是 `release_lock(task_name, lock_key, reason)`

**后果**:
- IndexTTS 任务失败时，`on_failure` 回调抛出 `AttributeError`
- 锁无法释放 → **永久死锁**

##### 3. **异常处理不完整导致锁泄漏**

**位置**: `services/common/locks.py:726-740`

**问题**:
```python
finally:
    try:
        force_cleanup_gpu_memory(aggressive=True)
    except Exception as cleanup_e:
        logger.warning(f"GPU显存清理失败: {cleanup_e}")

    lock_manager.release_lock(task_name, lock_key, "normal")  # ❌ 可能抛异常!
```

**风险**:
- 如果 `release_lock()` 抛出异常 (如 Redis 连接断开)
- 异常被向上传播，锁永远不会释放
- 所有后续任务永久阻塞

#### 🟡 **High 级别问题**

##### 4. **监控强制释放存在竞态条件**

**位置**: `services/api_gateway/app/monitoring/gpu_lock_monitor.py:247-273`

**问题**:
```python
def _force_release_lock(self, lock_key: str):
    lock_value = self.redis_client.get(lock_key)  # 步骤1
    if lock_value:
        result = self.redis_client.delete(lock_key)  # 步骤2 ❌ 非原子!
```

**竞态场景**:
```
T0: 监控检测到锁超时 (持有者: task_a, 3601秒)
T1: 监控执行 get(lock_key) → "locked_by_task_a"
T2: 任务A 正常完成，释放锁
T3: 任务B 获取锁 → set(lock_key, "locked_by_task_b")
T4: 监控执行 delete(lock_key) → 误删任务B的锁! ❌
```

**后果**:
- 正常运行的任务被误杀
- 多个任务同时获取锁
- GPU 资源冲突

##### 5. **超时配置过长导致死锁恢复缓慢**

**当前配置**:
```yaml
gpu_lock:
  lock_timeout: 3600  # 锁超时 1小时
  max_wait_time: 1800 # 最大等待 30分钟

gpu_lock_monitor:
  timeout_levels:
    hard_timeout: 7200 # 120分钟强制释放
```

**问题**:
- 如果任务崩溃，锁会保留 **1小时**
- 监控系统要等 **2小时** 才强制释放
- 期间所有 GPU 任务阻塞

**实际影响**:
```
场景: PaddleOCR 任务在处理第1帧时崩溃
T0: 任务崩溃，锁未释放
T1-T60分钟: 所有后续 OCR 任务等待
T60分钟: Redis 锁自动过期
T61分钟: 新任务终于可以执行

损失: 1小时的系统停机时间!
```

### 影响范围

#### 受影响的服务 (7个)
- `audio_separator_service`: `separate_vocals`
- `faster_whisper_service`: `_transcribe_audio_with_gpu_lock`
- `indextts_service`: `generate_speech` ❌ **Critical Bug**
- `ffmpeg_service`: `crop_subtitle_images`
- `paddleocr_service`: `detect_subtitle_area`, `perform_ocr`
- `pyannote_audio_service`: 说话人分离任务

#### 业务影响
1. **系统可用性**: 死锁可能导致 1-2 小时的 GPU 任务停机
2. **数据完整性**: 并发锁可能导致 GPU 计算结果错误
3. **资源浪费**: 任务等待期间，GPU 资源闲置
4. **用户体验**: 视频处理任务长时间无响应

### 风险评估

| 问题 | 概率 | 影响 | 风险等级 | 当前缓解 |
|------|------|------|---------|---------|
| 进程崩溃死锁 | **高** | 高 | 🔴 Critical | Redis 自动过期 (1小时) |
| Redis 断连死锁 | 中 | **极高** | 🔴 Critical | 无 |
| 监控误杀任务 | 低 | **极高** | 🟡 High | 心跳检测 (不完善) |
| 锁释放竞态 | **高** | 中 | 🟡 High | 无 |
| IndexTTS 错误 | **高** | 中 | 🟡 High | 无 |

## 提议的解决方案

### 方案概述

采用**分阶段修复策略**，优先解决 Critical 级别问题，逐步增强系统可靠性。

### 核心修复原则

1. **原子性优先**: 所有锁操作必须使用 Redis Lua 脚本保证原子性
2. **防御性编程**: 假设任何操作都可能失败，添加多层保护
3. **快速失败**: 降低超时配置，加快死锁恢复速度
4. **完整监控**: 添加健康检查和告警机制

### 修复方案详解

#### Phase 1: Critical 问题修复 (P0, 必须立即执行)

##### 修复 1: 锁释放原子性

**目标**: 使用 Lua 脚本保证锁释放的原子性和所有权验证

**实现**:
```python
# services/common/locks.py
def release_lock(self, task_name: str, lock_key: str, release_reason: str = "normal") -> bool:
    if not redis_client:
        return False

    try:
        # ✅ Lua 脚本保证原子性
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

        if result == 1:
            logger.info(f"任务 {task_name} 释放锁 '{lock_key}' (原因: {release_reason})")
            pub_sub_manager.publish_lock_release(lock_key, task_name, release_reason)
            return True
        else:
            current_value = redis_client.get(lock_key)
            logger.warning(f"任务 {task_name} 尝试释放不持有的锁 (当前值: {current_value})")
            return False

    except Exception as e:
        logger.error(f"释放锁异常: {e}", exc_info=True)
        return False
```

**验证**:
- 单元测试: 并发释放锁，验证不会误删
- 集成测试: 模拟任务崩溃，验证锁正确释放

##### 修复 2: IndexTTS 服务方法调用错误

**目标**: 修复 `on_failure` 回调中调用不存在方法的错误，确保任务失败时能正确释放锁

**实现**:
```python
# services/workers/indextts_service/app/tasks.py
# 第38行导入已正确，无需修改
from .celery_app import celery_app, gpu_lock_manager

class IndexTTSTask(Task):
    def __init__(self):
        super().__init__()
        self.gpu_lock_manager = gpu_lock_manager  # ✅ 保持不变

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"任务 {task_id} 失败: {exc}")

        # ✅ 修复：使用正确的方法签名
        if self.gpu_lock_manager:
            try:
                # 获取 GPU ID 和构造锁键
                gpu_id = kwargs.get('gpu_id', 0)
                lock_key = f"gpu_lock:{gpu_id}"
                # 使用任务 ID 作为任务名
                task_name = task_id
                # 调用正确的方法
                self.gpu_lock_manager.release_lock(task_name, lock_key, "task_failure")
            except Exception as e:
                logger.error(f"释放锁失败: {e}", exc_info=True)
```

**验证**:
- 单元测试: 触发任务失败，验证 `on_failure` 正常执行
- 集成测试: 验证锁被正确释放

##### 修复 3: 增强异常处理

**目标**: 确保锁一定被释放，即使发生异常

**实现**:
```python
# services/common/locks.py
finally:
    # GPU显存清理
    try:
        force_cleanup_gpu_memory(aggressive=True)
    except Exception as cleanup_e:
        logger.warning(f"GPU显存清理失败: {cleanup_e}")

    # ✅ 多层保护确保锁释放
    lock_released = False
    try:
        lock_released = lock_manager.release_lock(task_name, lock_key, "normal")
    except Exception as release_error:
        logger.critical(f"释放锁失败: {release_error}", exc_info=True)

    # ✅ 如果正常释放失败，使用应急方式
    if not lock_released:
        try:
            logger.warning(f"使用应急方式释放锁 {lock_key}")
            redis_client.delete(lock_key)
        except Exception as emergency_error:
            logger.critical(f"应急释放锁也失败: {emergency_error}", exc_info=True)
            # 记录到监控系统，需要人工干预
```

**验证**:
- 单元测试: 模拟 Redis 连接断开，验证应急释放
- 集成测试: 验证锁泄漏监控告警

#### Phase 2: High 问题修复 (P1, 1周内)

##### 修复 4: 监控强制释放原子性

**目标**: 防止监控系统误删正常任务的锁

**实现**:
```python
# services/api_gateway/app/monitoring/gpu_lock_monitor.py
def _force_release_lock(self, lock_key: str) -> bool:
    try:
        # ✅ Lua 脚本原子删除并返回旧值
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
            # 发布锁释放事件
            from services.common.locks import pub_sub_manager
            pub_sub_manager.publish_lock_release(lock_key, released_value, "forced_by_monitor")
            return True
        else:
            logger.info(f"锁 {lock_key} 已不存在")
            return True

    except Exception as e:
        logger.error(f"强制释放锁异常: {e}")
        return False
```

**验证**:
- 单元测试: 并发场景，验证不会误删
- 集成测试: 验证监控正确释放超时锁

##### 修复 5: 优化超时配置

**目标**: 加快死锁恢复速度，减少系统停机时间

**实现**:
```yaml
# config.yml
gpu_lock:
  poll_interval: 2
  max_wait_time: 300        # ✅ 5分钟 (从30分钟降低)
  lock_timeout: 600         # ✅ 10分钟 (从60分钟降低)
  exponential_backoff: true
  max_poll_interval: 10
  use_event_driven: true
  fallback_timeout: 30

gpu_lock_monitor:
  monitor_interval: 30
  timeout_levels:
    warning: 300            # ✅ 5分钟警告 (从30分钟降低)
    soft_timeout: 600       # ✅ 10分钟软超时 (从60分钟降低)
    hard_timeout: 900       # ✅ 15分钟强制释放 (从120分钟降低)
  heartbeat:
    interval: 60
    timeout: 300
  cleanup:
    max_retry: 3
    retry_delay: 60
  enabled: true
  auto_recovery: true
```

**影响分析**:
- **风险**: 长时间运行的任务 (如大视频 OCR) 可能被误判超时
- **缓解**:
  1. 任务应定期更新心跳
  2. 监控系统检查心跳后再强制释放
  3. 对于超长任务，可在装饰器中覆盖超时参数

**验证**:
- 性能测试: 验证正常任务不会被误杀
- 故障注入: 模拟任务崩溃，验证快速恢复

#### Phase 3: 增强功能 (P2, 1个月内)

##### 增强 1: 锁健康检查

**目标**: 主动发现和修复锁异常

**实现**:
```python
# services/common/locks.py
def health_check(self) -> Dict[str, Any]:
    """检查锁系统健康状态"""
    try:
        # 检查 Redis 连接
        redis_client.ping()

        # 检查是否有僵尸锁 (无过期时间)
        zombie_locks = []
        for key in redis_client.scan_iter("gpu_lock:*"):
            ttl = redis_client.ttl(key)
            if ttl < 0:  # -1 表示永不过期，-2 表示不存在
                zombie_locks.append({
                    "key": key,
                    "value": redis_client.get(key),
                    "ttl": ttl
                })

        # 检查长时间持有的锁
        long_held_locks = []
        for key in redis_client.scan_iter("gpu_lock:*"):
            ttl = redis_client.ttl(key)
            if ttl > 0:
                lock_age = self.lock_stats.get('lock_timeout', 600) - ttl
                if lock_age > 300:  # 持有超过5分钟
                    long_held_locks.append({
                        "key": key,
                        "value": redis_client.get(key),
                        "age": lock_age
                    })

        return {
            "status": "healthy" if not zombie_locks else "warning",
            "redis_connected": True,
            "zombie_locks": zombie_locks,
            "zombie_count": len(zombie_locks),
            "long_held_locks": long_held_locks,
            "long_held_count": len(long_held_locks),
            "timestamp": time.time()
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "redis_connected": False,
            "error": str(e),
            "timestamp": time.time()
        }
```

**验证**:
- 单元测试: 验证健康检查逻辑
- 集成测试: 验证僵尸锁检测

##### 增强 2: 告警机制

**目标**: 及时发现锁异常，触发人工干预

**实现**:
```python
# services/api_gateway/app/monitoring/gpu_lock_monitor.py
def _check_and_alert(self):
    """检查并发送告警"""
    stats = lock_manager.get_statistics()

    # 告警条件
    alerts = []

    # 1. 锁获取失败率过高
    if stats.get('timeout_rate', 0) > 0.1:
        alerts.append({
            "level": "warning",
            "type": "high_timeout_rate",
            "message": f"GPU锁超时率过高: {stats['timeout_rate']:.2%}",
            "value": stats['timeout_rate']
        })

    # 2. 发现僵尸锁
    health = lock_manager.health_check()
    if health.get('zombie_count', 0) > 0:
        alerts.append({
            "level": "critical",
            "type": "zombie_locks_detected",
            "message": f"发现 {health['zombie_count']} 个僵尸锁",
            "locks": health['zombie_locks']
        })

    # 3. Redis 连接断开
    if not health.get('redis_connected', False):
        alerts.append({
            "level": "critical",
            "type": "redis_disconnected",
            "message": "Redis 连接断开",
            "error": health.get('error')
        })

    # 发送告警
    for alert in alerts:
        self._send_alert(alert)

def _send_alert(self, alert: Dict[str, Any]):
    """发送告警 (可扩展到多种通知渠道)"""
    logger.error(f"[GPU锁告警] {alert['message']}")
    # TODO: 集成邮件、Slack、钉钉等通知渠道
```

**验证**:
- 单元测试: 验证告警触发逻辑
- 集成测试: 验证告警通知发送

## 变更范围

### 受影响的能力 (Capabilities)

1. **gpu-lock-atomicity** - GPU锁原子性操作
2. **gpu-lock-error-handling** - GPU锁异常处理
3. **gpu-lock-monitoring** - GPU锁监控系统
4. **gpu-lock-configuration** - GPU锁配置优化

### 文件变更清单

#### 必须变更 (Phase 1 - P0)
- `services/common/locks.py` - 修复锁释放原子性和异常处理
- `services/workers/indextts_service/app/tasks.py` - 修复未定义变量

#### 高优先级变更 (Phase 2 - P1)
- `services/api_gateway/app/monitoring/gpu_lock_monitor.py` - 修复监控强制释放
- `config.yml` - 优化超时配置

#### 可选变更 (Phase 3 - P2)
- `services/common/locks.py` - 添加健康检查
- `services/api_gateway/app/monitoring/gpu_lock_monitor.py` - 添加告警机制
- `tests/integration/test_gpu_lock_deadlock.py` - 新增死锁测试 (新增)

## 成功标准

### Phase 1 (P0 - Critical)
- [ ] 所有锁操作使用 Lua 脚本保证原子性
- [ ] IndexTTS 错误处理正常工作
- [ ] 异常情况下锁100%被释放
- [ ] 通过并发压力测试 (100个并发任务)
- [ ] 通过故障注入测试 (模拟进程崩溃、Redis断连)

### Phase 2 (P1 - High)
- [ ] 监控强制释放使用原子操作
- [ ] 超时配置优化后，死锁恢复时间 < 15分钟
- [ ] 长时间运行任务不会被误杀 (通过心跳检测)
- [ ] 通过性能基准测试

### Phase 3 (P2 - Medium)
- [ ] 健康检查 API 正常工作
- [ ] 告警机制正确触发
- [ ] 僵尸锁自动清理

## 风险评估

### 低风险 (Phase 1 - 代码修复)
- **风险**: Lua 脚本可能有 bug
- **缓解**:
  1. 充分的单元测试
  2. 在测试环境验证
  3. 金丝雀部署

### 中风险 (Phase 2 - 配置变更)
- **风险**: 超时时间降低可能误杀长任务
- **缓解**:
  1. 监控心跳状态
  2. 对超长任务使用自定义超时参数
  3. 灰度发布，观察指标

### 回滚计划
- **Phase 1**: 回滚代码到上一版本
- **Phase 2**: 恢复配置文件到旧值
- **Phase 3**: 禁用健康检查和告警功能

## 替代方案

### 方案A: 仅修复 Critical 问题 (推荐)
- **优点**: 风险最低，快速修复核心问题
- **缺点**: 不解决超时配置问题

### 方案B: 完全重写锁系统
- **优点**: 彻底解决所有问题
- **缺点**: 工作量大，风险高，需要大量测试

### 方案C: 使用第三方分布式锁库 (如 Redlock)
- **优点**: 成熟的解决方案
- **缺点**: 引入新依赖，学习成本高

## 时间估算

- **Phase 1 (P0)**: 2-3 天 (开发 1天 + 测试 1-2天)
- **Phase 2 (P1)**: 3-5 天 (开发 2天 + 测试 1-2天 + 灰度发布 1天)
- **Phase 3 (P2)**: 5-7 天 (开发 3天 + 测试 2-3天 + 集成 1天)

**总计**: 10-15 天 (分阶段执行)

## 依赖关系

### 上游依赖
- 无 (可立即开始)

### 下游依赖
- `audit-gpu-lock-consistency` 提案 (文档修复) 可以并行进行

## 相关规范

- `code-quality` - 代码质量规范 (异常处理要求)
- `project-architecture` - 项目架构规范 (分布式锁设计原则)

## 审批要求

- [ ] 技术负责人审批 (P0 修复)
- [ ] 运维团队审批 (配置变更)
- [ ] 安全审查 (Lua 脚本安全性)
- [ ] 性能测试验证 (Phase 2)

---

**提案作者**: Claude AI
**创建日期**: 2025-12-24
**优先级**: **P0 (Critical)** - 影响系统稳定性和数据完整性
**紧急程度**: **High** - 建议在 1 周内完成 Phase 1 修复
