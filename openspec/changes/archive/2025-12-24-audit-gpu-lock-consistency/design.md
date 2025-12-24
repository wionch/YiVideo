# Design Document: GPU锁文档与配置一致性审计

## 设计目标

确保 GPU 锁系统的文档与实际代码配置完全一致,消除误导性信息,为后续性能优化奠定可信基础。

## 🔗 关联变更影响

### 死锁风险修复 (已完成)

在本提案执行过程中,发现了严重的死锁风险问题,已通过 `fix-gpu-lock-deadlock-risks` 提案完成修复:

**已修复的关键问题**:
1. ✅ 锁释放原子性 - 使用 Lua 脚本消除竞态条件
2. ✅ IndexTTS 服务错误 - 修复 `AttributeError` 导致的锁泄漏
3. ✅ 异常处理增强 - 三层保护机制确保锁永不泄漏

**对本设计的影响**:
- **Phase 1 (文档修复)**: 需要同步反映已完成的死锁修复
- **Phase 2 (配置优化)**: 必要性降低,应更加谨慎,优先保证稳定性
- **超时配置**: 应参考 `fix-gpu-lock-deadlock-risks` Phase 2 的配置建议

**参考**: `openspec/changes/archive/2025-12-24-fix-gpu-lock-deadlock-risks/PHASE1_SUMMARY.md`

## 架构决策

### ADR-001: 采用双阶段策略而非一次性修复

**决策**: 将变更分为两个独立阶段:
1. Phase 1: 文档修复 (立即执行)
2. Phase 2: 配置优化 (可选,需独立评估)

**理由**:

#### 技术考量
1. **风险隔离**: 文档修复零风险,配置变更有潜在风险
2. **验证需求**: 文档声称的"优化"缺乏测试证据,需要独立验证
3. **生产稳定性**: 当前配置已在生产环境稳定运行,贸然变更可能引入问题

#### 业务考量
1. **快速价值交付**: Phase 1 可在数小时内完成,立即消除误导
2. **灵活性**: Phase 2 可根据业务优先级和资源情况独立决策
3. **可追溯性**: 分阶段变更便于问题定位和回滚

**替代方案及拒绝理由**:
- ❌ **一次性应用所有变更**: 风险过高,缺乏验证
- ❌ **仅应用配置不修复文档**: 治标不治本,未解决根本问题
- ❌ **删除优化章节**: 丢失潜在有价值的优化思路

### ADR-002: 文档修复策略 - 对齐而非删除

**决策**: 将文档中的配置值更新为与 `config.yml` 一致,而非删除优化相关章节。

**理由**:

1. **保留优化思路**: 文档中的优化建议可能有价值,应保留为"待验证的优化方向"
2. **透明度**: 明确标记当前状态,而非隐藏历史信息
3. **可追溯性**: 保留优化思路便于后续评估和实施

**实施方式**:
```markdown
# 修改前
gpu_lock:
  poll_interval: 0.5  # 快速响应

# 修改后
gpu_lock:
  poll_interval: 2  # 当前生产配置
  # 优化建议: 可考虑降低至 0.5 秒以提升响应速度 (需性能测试验证)
```

### ADR-003: 配置优化评估方法论

**决策**: 如果执行 Phase 2,必须遵循以下评估流程:

**⚠️ 重要更新**: 鉴于 `fix-gpu-lock-deadlock-risks` 已完成死锁风险修复,Phase 2 的配置优化应:
1. 等待 `fix-gpu-lock-deadlock-risks` Phase 2 完成后再评估
2. 参考其性能基准测试结果
3. 避免重复测试和配置冲突

#### 1. 性能基准测试
```python
# 测试场景设计
test_scenarios = [
    "短任务 (PaddleOCR 单帧)",      # < 5秒
    "中等任务 (FFmpeg 裁剪)",       # 30-60秒
    "长任务 (Faster-Whisper 长音频)", # > 5分钟
]

# 测试指标
metrics = [
    "锁获取等待时间",
    "任务执行总时间",
    "Redis CPU 使用率",
    "锁超时率",
    "系统吞吐量 (任务/小时)",
]
```

#### 2. 分阶段部署
1. **测试环境验证** (1-2天)
2. **金丝雀部署** (10% 流量, 1天)
3. **灰度发布** (50% 流量, 2天)
4. **全量发布** (100% 流量)

#### 3. 回滚准则
触发立即回滚的条件:
- 任务超时率 > 5%
- Redis CPU 使用率 > 80%
- 锁获取失败率 > 10%
- 任何 P0/P1 级别的生产事故

## 系统交互分析

### 当前 GPU 锁机制工作流

```mermaid
graph TD
    A[Celery 任务启动] --> B[@gpu_lock 装饰器]
    B --> C[SmartGpuLockManager.acquire_lock_with_smart_polling]
    C --> D{锁可用?}
    D -->|是| E[获取锁成功]
    D -->|否| F[等待 poll_interval]
    F --> G{超过 max_wait_time?}
    G -->|否| C
    G -->|是| H[抛出超时异常]
    E --> I[执行 GPU 任务]
    I --> J[释放锁]

    style C fill:#f9f,stroke:#333,stroke-width:2px
    style F fill:#ff9,stroke:#333,stroke-width:2px
```

### 配置参数影响分析

| 参数 | 当前值 | 文档建议值 | 影响分析 |
|------|--------|----------|---------|
| `poll_interval` | 2秒 | 0.5秒 | **降低**: 更快响应,但增加 Redis 负载 (4倍请求量) |
| `max_wait_time` | 1800秒 | 300秒 | **降低**: 更快失败,但可能导致长任务超时 |
| `lock_timeout` | 3600秒 | 600秒 | **降低**: 更快释放死锁,但可能误杀正常长任务 |
| `max_poll_interval` | 10秒 | 5秒 | **降低**: 指数退避上限更低,保持更高响应性 |

### 风险点识别

#### 1. Redis 压力风险
- **场景**: 多个任务同时等待锁,`poll_interval` 从 2秒降至 0.5秒
- **影响**: Redis QPS 增加 4倍
- **缓解**: 监控 Redis CPU/内存,必要时调整 `poll_interval`

#### 2. 长任务超时风险
- **场景**: 大视频 OCR 任务执行超过 5分钟,但 `max_wait_time` 仅 300秒
- **影响**: 任务在获取锁阶段就超时失败
- **缓解**:
  - 方案A: 为不同任务类型设置不同的 `max_wait_time`
  - 方案B: 保持 `max_wait_time: 1800` 不变

#### 3. 死锁检测误判风险
- **场景**: 正常长任务 (如 1小时的视频处理) 被 `lock_timeout: 600` 误判为死锁
- **影响**: 任务被强制终止,浪费已完成的计算
- **缓解**:
  - 结合 `gpu_lock_monitor.timeout_levels` 的分级超时机制
  - 确保 `lock_timeout` > 预期最长任务时间

## 数据结构变更

### 文档结构调整

#### 修改前
```markdown
## ⚙️ 配置系统
gpu_lock:
  poll_interval: 0.5  # 轮询间隔（秒）- 快速响应
  max_wait_time: 300  # 最大等待时间（秒）- 5分钟
  ...

### 配置优化历史
| 配置参数 | 优化前 | 优化后 | 改进幅度 |
|---------|--------|--------|----------|
| 轮询间隔 | 2秒 | 0.5秒 | 75% ↓ |
```

#### 修改后
```markdown
## ⚙️ 配置系统

### 当前生产配置
gpu_lock:
  poll_interval: 2  # 轮询间隔（秒）
  max_wait_time: 1800  # 最大等待时间（秒）- 30分钟
  ...

### 配置优化建议 (待验证)
以下配置经过理论分析,可能提升系统响应速度,但**尚未在生产环境验证**:

| 参数 | 当前值 | 建议值 | 预期改进 | 风险评估 |
|------|--------|--------|---------|---------|
| poll_interval | 2秒 | 0.5秒 | 响应速度 ↑ | Redis 负载 ↑ |
| max_wait_time | 1800秒 | 300秒 | 快速失败 | 长任务超时风险 |

**注意**: 应用这些优化前,必须在测试环境进行充分验证。
```

## 可观测性增强

### 新增监控指标 (Phase 2)

如果应用配置优化,需要新增以下监控:

```python
# services/common/locks.py
class SmartGpuLockManager:
    def _record_lock_metrics(self, event: str, duration: float):
        """记录锁相关指标到 Prometheus"""
        metrics = {
            "gpu_lock_wait_time": duration,
            "gpu_lock_poll_count": self.poll_count,
            "gpu_lock_config_poll_interval": self.config["poll_interval"],
        }
        # 发送到 Prometheus
```

### 告警规则 (Phase 2)

```yaml
# prometheus/alerts/gpu_lock.yml
groups:
  - name: gpu_lock_alerts
    rules:
      - alert: GPULockHighWaitTime
        expr: gpu_lock_wait_time_seconds > 60
        for: 5m
        annotations:
          summary: "GPU锁等待时间过长"

      - alert: GPULockHighTimeoutRate
        expr: rate(gpu_lock_timeout_total[5m]) > 0.05
        annotations:
          summary: "GPU锁超时率过高 (>5%)"
```

## 测试策略

### Phase 1 (文档修复) - 测试需求

1. **文档准确性验证**
   ```bash
   # 提取文档中的配置值
   grep -A 10 "^gpu_lock:" docs/technical/reference/GPU_LOCK_COMPLETE_GUIDE.md

   # 对比 config.yml
   grep -A 10 "^gpu_lock:" config.yml

   # 确保完全一致
   ```

2. **链接和引用检查**
   - 确保所有代码文件路径引用正确
   - 验证 API 端点示例可用

### Phase 2 (配置优化) - 测试需求

1. **单元测试** (新增)
   ```python
   # tests/unit/test_gpu_lock_config.py
   def test_poll_interval_reduces_wait_time():
       """验证降低 poll_interval 确实减少等待时间"""
       pass
   ```

2. **集成测试** (新增)
   ```python
   # tests/integration/test_gpu_lock_performance.py
   @pytest.mark.parametrize("poll_interval", [0.5, 1, 2])
   def test_lock_acquisition_performance(poll_interval):
       """对比不同 poll_interval 的性能"""
       pass
   ```

3. **压力测试** (新增)
   ```python
   def test_redis_load_under_high_polling():
       """验证 0.5秒轮询不会压垮 Redis"""
       pass
   ```

## 向后兼容性

### Phase 1 (文档修复)
- ✅ **完全兼容**: 仅文档变更,无代码或配置变更

### Phase 2 (配置优化)
- ⚠️ **行为变更**: 锁获取行为会改变
- **影响范围**: 所有使用 `@gpu_lock()` 的任务
- **缓解措施**:
  - 通过环境变量支持动态配置
  - 保留回滚配置文件

## 部署注意事项

### Phase 1 部署
1. 更新文档文件
2. 提交 PR 审查
3. 合并到主分支
4. 无需重启服务

### Phase 2 部署 (如执行)
1. **准备工作**
   - 备份当前 `config.yml`
   - 准备回滚脚本
   - 通知运维团队

2. **部署步骤**
   ```bash
   # 1. 更新配置
   vim config.yml

   # 2. 重启受影响的服务
   docker-compose restart api_gateway
   docker-compose restart paddleocr_service
   docker-compose restart faster_whisper_service
   # ... 其他 GPU 服务

   # 3. 监控关键指标
   watch -n 5 'curl http://localhost:8788/api/v1/monitoring/gpu-lock/health'
   ```

3. **回滚步骤**
   ```bash
   # 恢复配置
   cp config.yml.backup config.yml

   # 重启服务
   docker-compose restart api_gateway paddleocr_service faster_whisper_service
   ```

## 文档更新清单

### 必须更新的文档
- [x] `docs/technical/reference/GPU_LOCK_COMPLETE_GUIDE.md` - 主要修复目标

### 可能需要更新的文档 (Phase 2)
- [ ] `README.md` - 如有性能声明
- [ ] `docs/deployment/configuration.md` - 配置指南
- [ ] `CHANGELOG.md` - 记录配置变更

## 成功指标

### Phase 1 成功标准
- [ ] 文档中所有配置值与 `config.yml` 一致 (100% 准确)
- [ ] 移除所有未实施的"已完成"标记
- [ ] 至少 2 名团队成员审查通过

### Phase 2 成功标准 (如执行)
- [ ] 测试环境验证通过 (无超时,无异常)
- [ ] 性能基准测试显示改进 (等待时间 ↓ 至少 30%)
- [ ] 生产环境灰度发布 7 天无事故
- [ ] Redis 负载增长 < 50%

---

**设计作者**: Claude AI
**创建日期**: 2025-12-24
**审查状态**: Pending Review
