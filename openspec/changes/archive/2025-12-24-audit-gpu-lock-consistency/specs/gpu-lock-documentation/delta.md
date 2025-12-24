# Spec Delta: GPU锁文档准确性

## Capability
`gpu-lock-documentation`

## 变更类型
- [ ] MODIFIED Requirements
- [x] ADDED Requirements
- [ ] REMOVED Requirements

---

## ADDED Requirements

### Requirement: GPU_LOCK_DOC_001 - 配置参数文档准确性

GPU锁系统文档 MUST 准确反映 `config.yml` 中的实际配置值,所有配置参数的文档描述 SHALL 与代码配置完全一致,不得出现误导性的"已优化"声明。

**添加原因**: 确保文档与代码配置一致,防止误导开发者和运维人员。

#### 行为描述
文档必须反映实际生产配置:
- `poll_interval: 2` 秒 (当前生产配置)
- `max_wait_time: 1800` 秒 (30分钟)
- `lock_timeout: 3600` 秒 (60分钟)
- `max_poll_interval: 10` 秒

#### Scenario: 开发者查阅GPU锁配置文档

**Given**: 开发者需要了解当前GPU锁的配置参数

**When**: 开发者打开 `docs/technical/reference/GPU_LOCK_COMPLETE_GUIDE.md`

**Then**:
- 文档中显示的所有配置值必须与 `config.yml` 中的实际值**完全一致**
- 任何优化建议必须明确标记为"待验证"或"建议值"
- 不得出现"已完成"、"已验证"等误导性状态标记

**Acceptance Criteria**:
```bash
# 自动化验证脚本
bash tests/validation/validate_gpu_lock_docs.sh

# 预期输出:
# ✅ poll_interval 一致 (2)
# ✅ max_wait_time 一致 (1800)
# ✅ lock_timeout 一致 (3600)
# ✅ max_poll_interval 一致 (10)
# ✅ 所有验证通过!
```

---

### Requirement: GPU_LOCK_DOC_002 - 优化建议标记规范

文档中的配置优化建议 MUST 明确标记为"建议"而非"已应用",并 SHALL 包含风险评估和验证要求说明。

**添加原因**: 防止将未验证的优化建议误认为已实施的配置。

#### 行为描述
优化建议表格必须包含以下列:
- 当前值 (实际生产配置)
- 建议优化值 (理论优化值)
- 预期改进 (理论收益)
- 风险评估 (潜在风险)
- 验证状态 (⚠️ 待验证)

#### Scenario: 运维人员评估配置优化

**Given**: 运维人员需要评估是否应用文档中的优化建议

**When**: 运维人员查看优化建议表格

**Then**:
- 表格必须清晰区分"当前值"和"建议优化值"
- 每个建议必须包含风险评估
- 验证状态必须标记为"⚠️ 待验证"

**Acceptance Criteria**:
- 表格包含"当前值"、"建议优化值"、"预期改进"、"风险评估"、"验证状态"五列
- 所有建议的验证状态为"⚠️ 待验证"
- 风险评估明确指出潜在影响 (如 "Redis 负载 ↑ 4倍")

---

### Requirement: GPU_LOCK_DOC_003 - 实施状态分级标记

文档 MUST 使用分级状态标记系统,明确区分"文档状态"、"配置状态"和"实施状态"。

**添加原因**: 提供准确的系统实施状态信息,避免误导。

#### 行为描述
文档必须包含三级状态标记:
- **文档状态**: ✅ GPU锁基础功能已集成
- **配置状态**: ⚠️ 使用保守配置,性能优化待验证
- **实施状态**: 🔄 基础功能完成,优化配置待评估

#### Scenario: 项目经理评估GPU锁系统状态

**Given**: 项目经理需要了解GPU锁系统的完成度

**When**: 项目经理查看文档状态标记

**Then**:
- 文档、配置、实施三个维度的状态清晰可见
- 每个状态使用适当的图标 (✅/⚠️/🔄)
- 状态描述准确反映实际情况

**Acceptance Criteria**:
- 文档包含三级状态标记
- 使用 ✅ (已完成)、⚠️ (待优化)、🔄 (进行中) 图标
- 状态描述与实际代码状态一致

---

### Requirement: GPU_LOCK_DOC_004 - 自动化验证机制

项目 MUST 提供自动化脚本验证文档与配置的一致性,防止未来再次出现不一致。

**添加原因**: 建立持续验证机制,防止文档与代码漂移。

#### 行为描述
提供 `tests/validation/validate_gpu_lock_docs.sh` 脚本:
- 自动提取文档和配置中的参数值
- 对比 4 个关键参数的一致性
- 彩色输出验证结果
- 验证失败时返回非零退出码

#### Scenario: CI/CD 流程验证文档一致性

**Given**: 代码提交触发 CI/CD 流程

**When**: CI 执行文档验证步骤

**Then**:
- 验证脚本自动运行
- 所有参数一致性检查通过
- 验证失败时 CI 流程中断

**Acceptance Criteria**:
```bash
# 脚本执行成功
$ bash tests/validation/validate_gpu_lock_docs.sh
$ echo $?
0

# 脚本检查所有关键参数
# - poll_interval
# - max_wait_time
# - lock_timeout
# - max_poll_interval
```

---

### Requirement: GPU_LOCK_DOC_005 - 关联变更同步

文档 MUST 同步反映关联提案的修复成果,特别是死锁风险修复的关键信息。

**添加原因**: 确保文档反映最新的系统状态,包括关联提案的修复。

#### 行为描述
文档必须包含"最近更新"章节,列出:
- 锁释放竞态条件修复 (Lua 脚本原子操作)
- IndexTTS 服务锁泄漏修复
- 三层异常保护机制
- 测试覆盖情况 (28 个测试用例)

#### Scenario: 开发者了解GPU锁系统最新状态

**Given**: 开发者需要了解GPU锁系统的最新改进

**When**: 开发者查看文档"最近更新"章节

**Then**:
- 章节列出所有关键修复
- 包含修复日期 (2025-12-24)
- 提供关联提案引用

**Acceptance Criteria**:
- "最近更新"章节存在
- 列出 4 项关键修复 (竞态条件、锁泄漏、异常保护、测试覆盖)
- 包含关联提案引用: `fix-gpu-lock-deadlock-risks`
