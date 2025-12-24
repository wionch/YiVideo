# 变更日志 - GPU 锁死锁风险修复

## [Phase 1] - 2025-12-24

### ✅ 新增功能

#### 原子锁释放机制
- 实现 Redis Lua 脚本原子锁释放
- 添加锁所有权验证
- 消除 GET + DEL 竞态条件

#### 三层异常保护
- 第一层：GPU 显存清理（独立异常捕获）
- 第二层：正常锁释放（记录失败统计）
- 第三层：应急强制释放（Redis DELETE + 告警）

#### 异常监控
- 新增 4 个异常统计指标：
  - `normal_release_failures`: 正常释放失败次数
  - `emergency_releases`: 应急释放次数
  - `ownership_violations`: 所有权验证失败次数
  - `release_script_errors`: Lua 脚本执行失败次数

#### 告警系统框架
- 实现 `send_alert()` 函数（当前为日志告警）
- 实现 `record_critical_failure()` 持久化记录
- 关键失败写入 `/var/log/yivideo/gpu_lock_critical_failures.log`

### 🐛 Bug 修复

#### IndexTTS 服务
- 修复 `IndexTTSTask.on_failure` 中的 `AttributeError`
- 将 `force_release_lock()` 改为 `release_lock(task_name, lock_key, reason)`
- 添加异常处理防止释放失败向上传播

### 🧪 测试

#### 单元测试（23 个用例）
- `test_gpu_lock_atomicity.py` - 7 个测试
- `test_indextts_error_handling.py` - 8 个测试
- `test_gpu_lock_error_handling.py` - 8 个测试

#### 集成测试（5 个用例）
- `test_gpu_lock_deadlock.py` - 5 个测试

**测试结果**: 28/28 通过 ✅

### 📝 文档

- 创建 Phase 1 代码审查清单
- 创建 Spec Delta 文件（原子性、错误处理）
- 创建 Phase 1 实施总结

### 🔧 代码质量

- 修复 `locks.py:237` 注释错误
- 优化 `locks.py:503` 异常类型检查

---

## 📊 影响范围

### 修改的文件
- `services/common/locks.py` (~150 行变更)
- `services/workers/indextts_service/app/tasks.py` (~17 行变更)

### 新增的文件
- `tests/unit/test_gpu_lock_atomicity.py` (221 行)
- `tests/unit/test_indextts_error_handling.py` (165 行)
- `tests/unit/test_gpu_lock_error_handling.py` (228 行)
- `tests/integration/test_gpu_lock_deadlock.py` (279 行)
- `openspec/changes/fix-gpu-lock-deadlock-risks/PHASE1_REVIEW_CHECKLIST.md`
- `openspec/changes/fix-gpu-lock-deadlock-risks/PHASE1_SUMMARY.md`
- `openspec/changes/fix-gpu-lock-deadlock-risks/specs/gpu-lock-atomicity/delta.md`
- `openspec/changes/fix-gpu-lock-deadlock-risks/specs/gpu-lock-error-handling/delta.md`

---

## ⚠️ 破坏性变更

**无破坏性变更**

所有 API 签名保持不变，现有代码无需修改。

---

## 🔄 迁移指南

**无需迁移**

Phase 1 变更完全向后兼容。

---

## 📋 部署注意事项

1. **日志目录**: 确保 `/var/log/yivideo/` 目录存在且有写权限
2. **Redis 连接**: 确保 Redis 可用（锁功能依赖 Redis）
3. **监控配置**: 建议配置日志监控以接收告警（可选）

---

## 🎯 后续计划

### Phase 2 (P1) - 监控与优化
- 实现 Prometheus 指标导出
- 优化锁超时参数
- 实现心跳机制

### Phase 3 (P2) - 健康检查与告警
- 实现健康检查 API
- 集成邮件/Slack/钉钉告警
- 实现自动恢复机制

---

## 🙏 致谢

感谢所有参与代码审查和测试的团队成员。
