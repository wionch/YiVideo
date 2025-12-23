## Traceability (Research → Tasks)

- Finding 1 (缺乏自动化检测工具) → 1.1
- Finding 2 (audio_separator 配置加载器重复) → 1.2
- Finding 3 (工作流状态管理重复) → 1.3
- Finding 4 (缺乏代码质量规范) → 已通过 spec.md 解决
- Finding 5 (缺乏定期审计流程) → 1.4, 1.5

## 1. Implementation

- [x] 1.1 创建审计工具使用指南 - 自动化检测部分
  - Evidence: proposal.md → Research → Finding 1 (Decision: 文档+规范)
  - Edit scope: `docs/technical/code-redundancy-audit-guide.md:1-150` (新建文件,工具指南章节)
  - Commands:
    - `ls docs/technical/`
  - Done when: 指南包含 rg/grep/serena 等工具的使用说明,以及如何识别重复代码模式的示例

- [x] 1.2 创建审计案例 - audio_separator 配置加载器
  - Evidence: proposal.md → Research → Finding 2 (Decision: 文档+规范)
  - Edit scope: `docs/technical/code-redundancy-audit-guide.md:151-250` (审计案例章节)
  - Commands:
    - `rg -n "class ConfigLoader" services/workers/audio_separator_service/app/config.py`
    - `rg -n "def get_config" services/common/config_loader.py`
  - Done when: 指南包含 audio_separator ConfigLoader 作为典型案例,说明如何识别和评估冗余代码

- [x] 1.3 创建审计案例 - 工作流状态管理模式
  - Evidence: proposal.md → Research → Finding 3 (Decision: 文档+规范)
  - Edit scope: `docs/technical/code-redundancy-audit-guide.md:251-350` (审计案例章节续)
  - Commands:
    - `rg -c "workflow_context.stages\[stage_name\] = StageExecution" services/workers/*/app/tasks.py`
  - Done when: 指南包含状态管理重复模式的识别方法和统计示例

- [x] 1.4 创建审计流程说明
  - Evidence: proposal.md → Research → Finding 5 (Decision: 文档)
  - Edit scope: `docs/technical/code-redundancy-audit-guide.md:351-500` (流程章节)
  - Commands:
    - `ls docs/technical/`
  - Done when: 指南包含完整的审计流程说明:准备→扫描→分析→评估→报告,以及每个阶段的具体步骤

- [x] 1.5 创建审计清单模板和优先级标准
  - Evidence: proposal.md → Research → Finding 5 (Decision: 文档)
  - Edit scope: `docs/technical/code-redundancy-audit-guide.md:501-650` (模板和标准章节)
  - Commands:
    - `wc -l docs/technical/code-redundancy-audit-guide.md`
  - Done when: 指南包含可复用的审计清单模板(Markdown表格格式)和优先级评估标准(P0-P3定义)

## 2. Validation

- [x] 2.1 OpenSpec 严格验证
  - Evidence: proposal.md → Research → 所有发现
  - Commands:
    - `openspec validate audit-redundant-code --strict`
  - Done when: 命令以 0 状态退出,无任何验证错误

- [x] 2.2 验证审计指南完整性
  - Evidence: proposal.md → Research → 所有发现
  - Commands:
    - `rg -n "## " docs/technical/code-redundancy-audit-guide.md`
    - `rg -n "### " docs/technical/code-redundancy-audit-guide.md`
    - `wc -l docs/technical/code-redundancy-audit-guide.md`
  - Done when: 指南包含所有必需章节(工具指南、审计案例、流程说明、清单模板、优先级标准),总行数 \u003e 600

- [x] 2.3 验证规范增量格式正确性
  - Evidence: proposal.md → Research → 所有发现
  - Commands:
    - `rg -n "## ADDED Requirements" openspec/changes/audit-redundant-code/specs/code-quality/spec.md`
    - `rg -n "### Requirement:" openspec/changes/audit-redundant-code/specs/code-quality/spec.md`
    - `rg -n "#### Scenario:" openspec/changes/audit-redundant-code/specs/code-quality/spec.md`
  - Done when: 规范文件包含正确的增量操作标记、所有需求都有至少一个场景,且格式符合 OpenSpec 标准

## 3. Self-check (ENFORCED)

- [x] 3.1 每个任务在"编辑范围"中仅触及一个文件
- [x] 3.2 每个任务恰好引用一个"发现"
- [x] 3.3 任务中不包含条件性语言(如果需要/必要时/可能/按需/……)
- [x] 3.4 每个任务都包含"命令"和客观的"完成标志"
