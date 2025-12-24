<!-- OPENSPEC:START -->

**防护栏 (Guardrails)**

-   优先采用简单、最小化的实现，仅在被要求或明确需要时才增加复杂性。
-   确保变更范围严格限定在请求的结果内。
-   如果需要额外的 OpenSpec 约定或说明，请参考 `openspec/AGENTS.md`（位于 `openspec/` 目录中——如果没看到，请运行 `ls openspec` 或 `openspec update`）。
-   识别任何模糊或不确定的细节，并在编辑文件前提出必要的后续问题。
-   在提案阶段不要编写任何代码。仅创建设计文档（proposal.md, tasks.md, design.md 以及规范增量 spec deltas）。实现应在批准后的应用（apply）阶段进行。

**步骤 (Steps)**

1. 查看 `openspec/project.md`，运行 `openspec list` 和 `openspec list --specs`，并检查相关代码或文档（例如通过 `rg`/`ls`）以基于当前行为制定提案；记录任何需要澄清的差距。
2. 选择一个以动词开头的唯一 `change-id`，并在 `openspec/changes/<id>/` 下搭建 `proposal.md`、`tasks.md` 和 `design.md`（需要时）的框架。
3. 将变更映射为具体的各部分能力或需求，将跨多个范围的任务分解为具有明确关系和顺序的独立规范增量（spec deltas）。
4. 当解决方案跨越多个系统、引入新模式或在提交规范前需要讨论权衡时，在 `design.md` 中记录架构推理。
5. 在 `changes/<id>/specs/<capability>/spec.md` 中起草规范增量（每个能力一个文件夹），使用 `## ADDED|MODIFIED|REMOVED Requirements`，每个需求至少包含一个 `#### Scenario:`，并在相关时交叉引用相关的能力。
6. 将 `tasks.md` 起草为有序的小型可验证工作项列表，这些工作项应能交付用户可见的进展，包括验证（测试、工具），并突出依赖关系或可并行化的工作。
7. 使用 `openspec validate <id> --strict` 进行验证，并在分享提案前解决所有问题。

**参考 (Reference)**

-   当验证失败时，使用 `openspec show <id> --json --deltas-only` 或 `openspec show <spec> --type spec` 查看详情。
-   在编写新需求前，使用 `rg -n "Requirement:|Scenario:" openspec/specs` 搜索现有需求。
-   通过 `rg <keyword>`、`ls` 或直接读取文件来探索 codebase，使提案与当前的实现情况保持一致。
<!-- OPENSPEC:END -->
