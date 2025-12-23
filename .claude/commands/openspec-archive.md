---
description: 归档已部署的 OpenSpec 变更并更新规范。
argument-hint: 变更 ID (change-id)
---

$ARGUMENTS
<!-- OPENSPEC:START -->
**保护栏 (Guardrails)**
- 优先选择直接、最小化的实现方式，仅在明确要求或确实需要时才增加复杂性。
- 将变更范围严格限制在所要求的结果内。
- 如果需要额外的 OpenSpec 惯例或澄清，请参考 `openspec/AGENTS.md`（位于 `openspec/` 目录中 —— 如果没看到，请运行 `ls openspec` 或 `openspec update`）。

**步骤**
1. 确定要归档的变更 ID：
   - 如果此提示已包含特定的变更 ID（例如在由斜杠命令参数填充的 `<ChangeId>` 块中），请在修剪空白后使用该值。
   - 如果对话中对变更的引用较为模糊（例如通过标题或摘要），请运行 `openspec list` 以显示可能的 ID，分享相关的候选 ID，并确认用户意图归档哪一个。
   - 否则，查看对话，运行 `openspec list`，并询问用户要归档哪个变更；在继续之前等待确认的变更 ID。
   - 如果仍无法确定单个变更 ID，请停止并告诉用户目前无法归档任何内容。
2. 通过运行 `openspec list`（或 `openspec show <id>`）验证变更 ID，如果变更缺失、已归档或尚未准备好归档，请停止。
3. 运行 `openspec archive <id> --yes`，以便 CLI 移动变更并应用规范更新而无需提示（仅针对仅涉及工具的工作使用 `--skip-specs`）。
4. 检查命令输出以确认目标规范已更新，并且变更已进入 `changes/archive/`。
5. 使用 `openspec validate --strict` 进行验证，如果发现任何异常，请使用 `openspec show <id>` 进行检查。

**参考**
- 在归档前使用 `openspec list` 确认变更 ID。
- 使用 `openspec list --specs` 检查刷新后的规范，并在交付前解决任何验证问题。
<!-- OPENSPEC:END -->