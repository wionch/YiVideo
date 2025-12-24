# Spec Delta: GPU锁配置优化 (可选 - Phase 2)

## Capability
`gpu-lock-configuration`

## 变更类型
- [ ] MODIFIED Requirements
- [x] ADDED Requirements
- [ ] REMOVED Requirements

**注意**: 本规范为**可选实施**,仅在 Phase 1 (文档修复) 完成后,经过充分评估和测试后才应执行。

---

## ADDED Requirements

### Requirement: GPU_LOCK_CONFIG_001 - 性能优化配置验证

系统 MUST 支持在测试环境验证优化配置的有效性和安全性,所有生产环境配置变更 SHALL 先在测试环境通过性能基准测试,验证成功率 ≥ 95%、等待时间减少 ≥ 30%、Redis CPU 增长 < 50%、超时率 < 5%。

**添加原因**: 文档中提出的优化配置需要在生产环境应用前进行充分验证。

#### 新增行为
系统必须支持在测试环境验证优化配置的有效性和安全性。

#### Scenario: 在测试环境验证优化配置

**Given**:
- 测试环境已部署完整的 YiVideo 系统
- 准备了代表性的测试任务集 (短/中/长任务)

**When**:
- 运维人员将 `config.yml` 中的 `gpu_lock` 配置更新为优化值:
  ```yaml
  gpu_lock:
    poll_interval: 0.5
    max_wait_time: 300
    lock_timeout: 600
    max_poll_interval: 5
  ```
- 重启所有 GPU 服务
- 执行性能基准测试

**Then**:
- 所有测试任务必须成功完成 (成功率 ≥ 95%)
- 锁获取等待时间相比优化前减少 ≥ 30%
- Redis CPU 使用率增长 < 50%
- 无任务因超时而失败 (超时率 < 5%)

**Acceptance Criteria**:
```python
# tests/integration/test_gpu_lock_performance.py
@pytest.mark.performance
def test_optimized_config_performance():
    """验证优化配置的性能改进"""
    # 1. 应用优化配置
    apply_config(optimized_config)

    # 2. 执行基准测试
    results = run_benchmark_tasks([
        "paddleocr_short_task",
        "ffmpeg_medium_task",
        "faster_whisper_long_task",
    ])

    # 3. 验证性能指标
    assert results["success_rate"] >= 0.95
    assert results["avg_wait_time"] < baseline["avg_wait_time"] * 0.7
    assert results["redis_cpu_increase"] < 0.5
    assert results["timeout_rate"] < 0.05
```

---

### Requirement: GPU_LOCK_CONFIG_002 - 分阶段部署策略

优化配置 MUST 通过金丝雀部署和灰度发布逐步推广到生产环境,禁止直接全量部署未经验证的配置变更,金丝雀节点 SHALL 运行 24 小时无异常后才可扩大范围。

**添加原因**: 配置变更需要分阶段部署以降低风险。

#### 新增行为
优化配置必须通过金丝雀部署和灰度发布逐步推广到生产环境。

#### Scenario: 金丝雀部署优化配置

**Given**:
- 测试环境验证通过
- 准备了回滚脚本和监控告警

**When**:
- 运维人员在 10% 的 Worker 节点上应用优化配置
- 观察 24 小时

**Then**:
- 金丝雀节点的任务成功率 ≥ 95%
- 无 P0/P1 级别的生产事故
- 关键监控指标正常:
  - 锁获取失败率 < 10%
  - 任务超时率 < 5%
  - Redis CPU 使用率 < 80%

**Acceptance Criteria**:
- [ ] 金丝雀部署运行 24 小时无异常
- [ ] 灰度发布 (50% 流量) 运行 48 小时无异常
- [ ] 全量发布前获得技术负责人批准

---

### Requirement: GPU_LOCK_CONFIG_003 - 动态配置支持

GPU锁配置 SHOULD 支持通过环境变量或 API 动态调整,无需重启服务,新启动的任务 MUST 立即使用新配置,正在运行的任务不受影响,所有配置变更 SHALL 记录到日志。

**添加原因**: 支持运行时调整配置,无需重启服务。

#### 新增行为
GPU 锁配置应支持通过环境变量或 API 动态调整,便于快速回滚。

#### Scenario: 运行时调整轮询间隔

**Given**:
- 系统正在运行
- 发现当前 `poll_interval` 导致 Redis 负载过高

**When**:
- 运维人员通过环境变量调整配置:
  ```bash
  export GPU_LOCK_POLL_INTERVAL=1.0
  ```
- 或通过 API 调整:
  ```bash
  curl -X POST http://localhost:8788/api/v1/config/gpu-lock \
    -d '{"poll_interval": 1.0}'
  ```

**Then**:
- 新启动的任务立即使用新配置
- 正在运行的任务不受影响
- 配置变更记录到日志

**Acceptance Criteria**:
```python
# services/common/locks.py
def get_gpu_lock_config():
    """动态加载 GPU 锁配置"""
    return {
        "poll_interval": float(os.getenv("GPU_LOCK_POLL_INTERVAL", config["poll_interval"])),
        "max_wait_time": int(os.getenv("GPU_LOCK_MAX_WAIT_TIME", config["max_wait_time"])),
        # ...
    }
```

---

### Requirement: GPU_LOCK_CONFIG_004 - 配置回滚机制

系统 MUST 保留配置历史并支持一键回滚到稳定配置,回滚操作 SHALL 在 5 分钟内完成,所有回滚操作 MUST 记录到审计日志,回滚后系统 SHALL 自动验证恢复状态。

**添加原因**: 必须支持快速回滚到稳定配置。

#### 新增行为
系统必须保留配置历史,支持一键回滚。

#### Scenario: 优化配置导致问题需要回滚

**Given**:
- 应用了优化配置
- 发现任务超时率异常升高 (> 10%)

**When**:
- 运维人员执行回滚脚本:
  ```bash
  ./scripts/rollback_gpu_lock_config.sh
  ```

**Then**:
- 配置立即恢复到上一个稳定版本
- 所有 GPU 服务自动重启
- 回滚操作记录到审计日志
- 5 分钟内系统恢复正常

**Acceptance Criteria**:
```bash
#!/bin/bash
# scripts/rollback_gpu_lock_config.sh

# 1. 恢复配置
cp config.yml.backup config.yml

# 2. 重启服务
docker-compose restart api_gateway paddleocr_service faster_whisper_service

# 3. 验证恢复
sleep 30
curl http://localhost:8788/api/v1/monitoring/gpu-lock/health | jq '.overall_status'
```

---

## ADDED Requirements (监控增强)

### Requirement: GPU_LOCK_CONFIG_005 - 配置变更监控

系统 MUST 记录和监控 GPU 锁配置变更及其影响,配置变更 SHALL 自动触发监控基准重置,系统 SHOULD 提供变更前后 7 天的对比数据,并自动生成优化建议。

**添加原因**: 需要监控配置变更对系统的影响。

#### 新增行为
系统必须记录和监控 GPU 锁配置变更及其影响。

#### Scenario: 监控配置变更后的系统表现

**Given**:
- 应用了新的 GPU 锁配置

**When**:
- 运维人员查询配置变更影响:
  ```bash
  curl http://localhost:8788/api/v1/monitoring/gpu-lock/config-impact
  ```

**Then**:
- API 返回配置变更前后的对比数据:
  ```json
  {
    "config_change_time": "2025-12-24T10:00:00Z",
    "before": {
      "poll_interval": 2,
      "avg_wait_time": 15.2,
      "timeout_rate": 0.02
    },
    "after": {
      "poll_interval": 0.5,
      "avg_wait_time": 4.8,
      "timeout_rate": 0.03
    },
    "impact_summary": {
      "wait_time_improvement": "68% ↓",
      "timeout_rate_change": "50% ↑",
      "recommendation": "⚠️ 超时率上升,建议调整 max_wait_time"
    }
  }
  ```

**Acceptance Criteria**:
- [ ] 配置变更自动触发监控基准重置
- [ ] 提供变更前后 7 天的对比数据
- [ ] 自动生成优化建议

---

## 验证方法

### 性能基准测试

```python
# tests/integration/test_gpu_lock_performance.py
import pytest
import time
from services.common.locks import lock_manager

@pytest.mark.performance
@pytest.mark.parametrize("config", [
    {"poll_interval": 2, "max_wait_time": 1800},  # 当前配置
    {"poll_interval": 0.5, "max_wait_time": 300},  # 优化配置
])
def test_lock_acquisition_performance(config):
    """对比不同配置的锁获取性能"""
    # 1. 应用配置
    apply_test_config(config)

    # 2. 模拟并发任务
    results = []
    for _ in range(10):
        start = time.time()
        success = lock_manager.acquire_lock_with_smart_polling(
            task_name="test_task",
            lock_key="gpu_lock:0",
            config=config
        )
        wait_time = time.time() - start
        results.append({"success": success, "wait_time": wait_time})

    # 3. 统计结果
    success_rate = sum(1 for r in results if r["success"]) / len(results)
    avg_wait_time = sum(r["wait_time"] for r in results) / len(results)

    # 4. 断言
    assert success_rate >= 0.95
    print(f"配置 {config}: 成功率 {success_rate:.2%}, 平均等待 {avg_wait_time:.2f}秒")
```

### 压力测试

```python
@pytest.mark.stress
def test_redis_load_under_optimized_config():
    """验证优化配置不会压垮 Redis"""
    # 1. 应用优化配置
    apply_config({"poll_interval": 0.5})

    # 2. 启动 50 个并发任务
    tasks = [simulate_gpu_task() for _ in range(50)]

    # 3. 监控 Redis CPU
    redis_cpu_samples = monitor_redis_cpu(duration=60)

    # 4. 验证 Redis 负载
    max_cpu = max(redis_cpu_samples)
    assert max_cpu < 80, f"Redis CPU 过高: {max_cpu}%"
```

---

## 依赖关系

### 上游依赖
- `gpu-lock-documentation` 能力必须先完成 (Phase 1)

### 下游依赖
- 无

---

## 风险缓解

### 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 长任务超时 | 中 | 高 | 为不同任务类型设置不同 `max_wait_time` |
| Redis 过载 | 低 | 中 | 压力测试验证,监控 Redis CPU |
| 配置回滚失败 | 低 | 高 | 自动化回滚脚本,定期演练 |

---

**规范作者**: Claude AI
**创建日期**: 2025-12-24
**关联提案**: `audit-gpu-lock-consistency`
**实施优先级**: Medium (可选,Phase 2)
