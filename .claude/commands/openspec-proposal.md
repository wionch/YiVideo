---
description: 构建新的 OpenSpec 变更脚手架并进行严格验证。
argument-hint: 请求或功能描述
---

$ARGUMENTS
<!-- OPENSPEC:START -->
**保护栏 (Guardrails)**
- 优先选择直接、最小化的实现方式，仅在明确要求或确实需要时才增加复杂性。
- 将变更范围严格限制在所要求的结果内。
- 如果需要额外的 OpenSpec 惯例或澄清，请参考 `openspec/AGENTS.md`（位于 `openspec/` 目录中 —— 如果没看到，请运行 `ls openspec` 或 `openspec update`）。
- 识别任何模糊或不明确的细节，并在编辑文件前提出必要的后续问题。
- 在提案阶段不要编写任何代码。仅创建设计文档（proposal.md, tasks.md, design.md 和规范增量）。实施发生在获得批准后的应用 (apply) 阶段。

**步骤**
1. 查看 `openspec/project.md`，运行 `openspec list` 和 `openspec list --specs`，并检查相关代码或文档（例如通过 `rg`/`ls`），使提案基于当前行为；注意任何需要澄清的差距。
2. 选择一个以动词开头的唯一 `change-id`，并在 `openspec/changes/<id>/` 下构建 `proposal.md`、`tasks.md` 和 `design.md`（需要时）的脚手架。
3. 将变更映射为具体的能力或要求，将多范围的工作分解为具有明确关系和顺序的独立规范增量 (spec deltas)。
4. 当解决方案跨越多个系统、引入新模式或在提交规范前需要讨论权衡时，在 `design.md` 中记录架构决策理由。
5. 在 `changes/<id>/specs/<capability>/spec.md` 中起草规范增量（每个能力一个文件夹），使用 `## ADDED|MODIFIED|REMOVED Requirements`，每个要求至少包含一个 `#### Scenario:`，并在相关时交叉引用相关能力。
6. 将 `tasks.md` 起草为一个有序的小型、可验证工作项列表，这些工作项应能交付用户可见的进展，包括验证（测试、工具），并突出依赖关系或可并行化的工作。
7. 使用 `openspec validate <id> --strict` 进行验证，并在分享提案前解决每一个问题。

**参考**
- 当验证失败时，使用 `openspec show <id> --json --deltas-only` 或 `openspec show <spec> --type spec` 检查详细信息。
- 在编写新要求前，使用 `rg -n "Requirement:|Scenario:" openspec/specs` 搜索现有要求。
- 通过 `rg <keyword>`、`ls` 或直接读取文件来探索代码库，确保提案与当前的实现现状保持一致。
<!-- OPENSPEC:END -->