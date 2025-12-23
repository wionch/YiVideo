# 变更：建立代码冗余审计流程和规范

## 为什么 (Why)

YiVideo 项目缺乏系统化的代码冗余审计机制,导致在快速迭代过程中可能积累重复代码。需要建立:
- 定期的冗余代码审计流程
- 明确的代码质量规范和最佳实践
- 自动化检测工具和人工审查相结合的机制
- 为后续重构提供明确的指导和优先级

## 调研 (Research)

### 已检查的内容

- 代码库结构:
  - `services/common/config_loader.py:48-61` - 统一配置加载器 `get_config()` 函数
  - `services/workers/audio_separator_service/app/config.py:284-361` - 独立的 ConfigLoader 类实现
  - `services/workers/*/app/tasks.py` - 7个服务的任务文件,共24处状态管理模式
  - 全局搜索: 18个文件包含 `except Exception as e:` 模式

- 规范:
  - `openspec/project.md:76-79` - 项目核心设计原则(SOLID, KISS, DRY, YAGNI)
  - `openspec/specs/project-architecture/spec.md` - 架构模式规范

- 工具可用性:
  - 无自动化代码重复检测工具
  - 无定期审计流程
  - 无冗余代码清单文档

### 发现 (Findings)

| 发现 | 证据 | 决策 | 备注 |
|------|------|------|------|
| **发现 1**: 缺乏自动化冗余代码检测工具 | 项目中无 `pylint`/`radon`/`jscpd` 等工具配置 | 文档+规范 | 需要建立自动化检测流程 |
| **发现 2**: audio_separator_service 有独立的 ConfigLoader 类 | `services/workers/audio_separator_service/app/config.py:284-361` | 文档+规范 | 作为审计案例,需要规范统一配置加载模式 |
| **发现 3**: 工作流状态管理模式在多个服务中重复 | 7个服务的 tasks.py 文件,共24处 `StageExecution` 状态管理 | 文档+规范 | 需要规范工作流任务基类模式 |
| **发现 4**: 缺乏代码质量规范文档 | 无 `specs/code-quality/spec.md` | 规范 | 需要创建代码质量规范 |
| **发现 5**: 缺乏定期审计流程 | 无审计计划和清单文档 | 文档 | 需要建立定期审计机制 |

### 为什么采用此方法 (KISS/YAGNI 检查)

- **满足场景的最小变更**:
  - 本提案建立审计流程和规范,不进行实际代码重构
  - 遵循 OpenSpec 流程:先规范后实施
  - 为后续重构提供明确的指导和优先级
  - 使用简单的文档和规范,而非复杂的自动化系统

- **明确拒绝的替代方案**:
  - ❌ 直接进行代码重构:违反 OpenSpec 流程,应先创建规范
  - ❌ 引入复杂的CI/CD集成工具:违反 KISS 原则,应从简单的手动流程开始
  - ❌ 一次性审计所有代码:工作量过大,应建立持续审计机制

- **超出范围的内容 (非目标)**:
  - 实际的代码重构实施(将在后续独立变更中进行)
  - 自动化CI/CD集成(可在流程验证后再考虑)
  - 性能优化(除非与冗余代码直接相关)
  - 新功能开发

## 变更内容

本变更将创建以下内容:

1. **新增规范**: 代码质量和冗余消除规范 (`specs/code-quality/spec.md`)
   - 配置加载统一性要求
   - 工作流任务基类要求
   - 异常处理最佳实践要求
   - 代码冗余审计流程要求

2. **审计工具指南**: 代码冗余审计操作指南 (`docs/technical/code-redundancy-audit-guide.md`)
   - 审计流程说明
   - 工具使用指南(rg, grep, serena等)
   - 审计清单模板
   - 优先级评估标准

## 影响 (Impact)

- **受影响的规范**:
  - `specs/code-quality/spec.md` (ADDED: 新增代码质量规范)
  - `specs/project-architecture/spec.md` (可能需要: 补充 DRY 原则实施要求)

- **受影响的文档**:
  - `docs/technical/code-redundancy-audit-guide.md` (新增: 审计操作指南)
  - `openspec/project.md` (可能需要: 补充代码质量约定)

- **发布 / 迁移说明**:
  - 本变更仅创建文档和规范,不影响现有代码
  - 团队需要学习和采用新的审计流程
  - 后续重构将基于本规范创建独立的变更提案

- **风险**:
  - 低风险:仅文档和规范变更
  - 需要确保规范要求明确且可执行
  - 需要与团队对齐审计流程和优先级
