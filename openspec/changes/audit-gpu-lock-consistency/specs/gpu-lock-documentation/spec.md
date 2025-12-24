# Spec Delta: GPU锁文档准确性

## Capability
`gpu-lock-documentation`

## 变更类型
- [x] MODIFIED Requirements
- [ ] ADDED Requirements
- [ ] REMOVED Requirements

---

## MODIFIED Requirements

### Requirement: GPU_LOCK_DOC_001 - 配置参数文档准确性

GPU锁系统文档 MUST 准确反映 `config.yml` 中的实际配置值,所有配置参数的文档描述 SHALL 与代码配置完全一致,不得出现误导性的"已优化"声明。

**修改原因**: 现有文档中的配置参数与实际 `config.yml` 严重不一致,导致误导。

#### 修改前行为
文档声称已应用优化配置:
- `poll_interval: 0.5` 秒
- `max_wait_time: 300` 秒
- `lock_timeout: 600` 秒

#### 修改后行为
文档必须反映实际生产配置:
- `poll_interval: 2` 秒
- `max_wait_time: 1800` 秒
- `lock_timeout: 3600` 秒

#### Scenario: 开发者查阅GPU锁配置文档

**Given**: 开发者需要了解当前GPU锁的配置参数

**When**: 开发者打开 `docs/technical/reference/GPU_LOCK_COMPLETE_GUIDE.md`

**Then**:
- 文档中显示的所有配置值必须与 `config.yml` 中的实际值**完全一致**
- 任何优化建议必须明确标记为"待验证"或"建议值"
- 不得出现"已完成"、"已验证"等误导性状态标记

**Acceptance Criteria**:
```bash
# 验证脚本
doc_poll_interval=$(grep -A 1 "poll_interval:" docs/technical/reference/GPU_LOCK_COMPLETE_GUIDE.md | grep -oP '\d+(\.\d+)?')
config_poll_interval=$(grep -A 1 "^gpu_lock:" config.yml | grep "poll_interval:" | grep -oP '\d+(\.\d+)?')

if [ "$doc_poll_interval" != "$config_poll_interval" ]; then
    echo "❌ FAIL: 文档与配置不一致"
    exit 1
fi
echo "✅ PASS: 文档与配置一致"
```

---

### Requirement: GPU_LOCK_DOC_002 - 优化历史表格准确性

文档中的配置优化表格 MUST 明确区分"当前值"和"建议值",所有未实施的优化 SHALL 标记为"待验证"状态,不得使用"优化前/优化后"等暗示已完成的表述。

**修改原因**: 文档中的"配置优化历史"表格声称已完成优化,但实际未应用。

#### 修改前行为
文档包含虚假的优化历史表格:
```markdown
| 配置参数 | 优化前 | 优化后 | 改进幅度 |
|---------|--------|--------|----------|
| 轮询间隔 | 2秒 | 0.5秒 | 75% ↓ |
```

#### 修改后行为
表格必须准确反映实际状态:
```markdown
| 配置参数 | 当前值 | 建议优化值 | 预期改进 | 验证状态 |
|---------|--------|-----------|---------|---------|
| 轮询间隔 | 2秒 | 0.5秒 | 75% ↓ | ⚠️ 待验证 |
```

#### Scenario: 运维人员基于文档进行性能调优

**Given**: 运维人员需要优化GPU锁性能

**When**: 运维人员查阅文档中的"配置优化历史"

**Then**:
- 表格必须明确区分"当前值"和"建议值"
- 所有未验证的优化必须标记为"待验证"状态
- 不得声称已完成未实施的优化

**Acceptance Criteria**:
- [ ] 表格包含"验证状态"列
- [ ] 所有未应用的优化标记为"⚠️ 待验证"
- [ ] 移除"优化前/优化后"误导性表述

---

### Requirement: GPU_LOCK_DOC_003 - 实施状态标记准确性

文档的实施状态标记 MUST 准确反映实际完成情况,未实施的优化 SHALL 使用"待处理"或"进行中"状态,禁止对未完成的工作使用"✅ 已完成并验证"等误导性标记。

**修改原因**: 文档标记为"✅ 已完成并验证",但核心优化未实施。

#### 修改前行为
```markdown
**文档状态**: ✅ 已完成GPU锁集成
**实施状态**: ✅ 已完成并验证
```

#### 修改后行为
```markdown
**文档状态**: ✅ GPU锁基础功能已集成
**配置状态**: ⚠️ 使用保守配置,性能优化待验证
**实施状态**: 🔄 基础功能完成,优化配置待评估
```

#### Scenario: 项目经理评估GPU锁系统状态

**Given**: 项目经理需要了解GPU锁系统的实施进度

**When**: 项目经理查看文档的状态标记

**Then**:
- 状态标记必须准确反映实际实施情况
- 区分"已完成"和"待完成"的功能
- 提供清晰的后续行动建议

**Acceptance Criteria**:
- [ ] 移除所有虚假的"✅ 已完成"标记
- [ ] 使用分级状态标记 (✅ 完成 / 🔄 进行中 / ⚠️ 待处理)
- [ ] 包含"下一步行动"章节

---

## MODIFIED Requirements (跨文档引用)

### Requirement: GPU_LOCK_DOC_004 - 配置文件注释准确性

`config.yml` 中的GPU锁配置注释 MUST 与文档保持一致,所有配置项 SHALL 包含清晰的用途说明,优化建议 MUST 明确标注为"建议"而非"已应用"。

**修改原因**: `config.yml` 中的注释应与文档保持一致。

#### 修改前行为
```yaml
gpu_lock:
  poll_interval: 2  # 无注释或过时注释
```

#### 修改后行为
```yaml
gpu_lock:
  poll_interval: 2  # 轮询间隔(秒) - 当前生产配置
  # 优化建议: 可考虑降低至 0.5 秒 (需性能测试验证)
```

#### Scenario: 开发者直接查看配置文件

**Given**: 开发者在 `config.yml` 中查看GPU锁配置

**When**: 开发者阅读配置注释

**Then**:
- 注释必须说明当前值的用途
- 如有优化建议,必须标注"需验证"
- 注释风格与文档保持一致

**Acceptance Criteria**:
- [ ] 所有 `gpu_lock` 配置项包含清晰注释
- [ ] 优化建议明确标记为"建议"而非"已应用"
- [ ] 注释语言与文档一致 (中文)

---

## 验证方法

### 自动化验证脚本

```bash
#!/bin/bash
# tests/validation/validate_gpu_lock_docs.sh

set -e

echo "🔍 验证 GPU 锁文档与配置一致性..."

# 1. 提取文档中的配置值
DOC_FILE="docs/technical/reference/GPU_LOCK_COMPLETE_GUIDE.md"
CONFIG_FILE="config.yml"

# 2. 对比关键配置参数
params=("poll_interval" "max_wait_time" "lock_timeout" "max_poll_interval")

for param in "${params[@]}"; do
    doc_value=$(grep "$param:" "$DOC_FILE" | head -1 | grep -oP '\d+(\.\d+)?')
    config_value=$(grep -A 10 "^gpu_lock:" "$CONFIG_FILE" | grep "$param:" | grep -oP '\d+(\.\d+)?')

    if [ "$doc_value" != "$config_value" ]; then
        echo "❌ FAIL: $param 不一致 (文档: $doc_value, 配置: $config_value)"
        exit 1
    fi
    echo "✅ PASS: $param 一致 ($doc_value)"
done

# 3. 检查误导性状态标记
if grep -q "✅ 已完成并验证" "$DOC_FILE"; then
    if grep -q "poll_interval: 2" "$CONFIG_FILE"; then
        echo "❌ FAIL: 文档声称已优化,但配置未变更"
        exit 1
    fi
fi

echo "✅ 所有验证通过"
```

### 手动审查清单

- [ ] 文档中所有配置值与 `config.yml` 一致
- [ ] 所有优化建议标记为"待验证"
- [ ] 移除虚假的"已完成"状态
- [ ] 配置文件注释清晰准确
- [ ] 至少 2 名团队成员审查通过

---

## 依赖关系

### 上游依赖
- 无 (可立即实施)

### 下游依赖
- `gpu-lock-configuration` 能力 (Phase 2 配置优化) 依赖本规范完成

---

## 影响范围

### 受影响的文件
- `docs/technical/reference/GPU_LOCK_COMPLETE_GUIDE.md` (主要)
- `config.yml` (注释优化)

### 受影响的用户
- 开发者 (查阅配置文档)
- 运维人员 (性能调优)
- 项目经理 (评估实施进度)

---

**规范作者**: Claude AI
**创建日期**: 2025-12-24
**关联提案**: `audit-gpu-lock-consistency`
