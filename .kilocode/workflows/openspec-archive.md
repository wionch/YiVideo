<!-- OPENSPEC:START -->

**防护栏 (Guardrails)**

-   优先采用简单、最小化的实现，仅在被要求或明确需要时才增加复杂性。
-   确保变更范围严格限定在请求的结果内。
-   如果需要额外的 OpenSpec 约定或说明，请参考 `openspec/AGENTS.md`（位于 `openspec/` 目录中——如果没看到，请运行 `ls openspec` 或 `openspec update`）。

**步骤 (Steps)**

1. 确定要归档的变更 ID：
    - 如果此提示已包含特定的变更 ID（例如在由斜杠命令参数填充的 `<ChangeId>` 块中），请在修剪空白后使用该值。
    - 如果对话中对变更的引用较为模糊（例如通过标题或摘要），请运行 `openspec list` 以显示可能的 ID，共享相关候选者，并确认用户意图归档哪一个。
    - 否则，请回顾对话，运行 `openspec list`，并询问用户要归档哪个变更；在进行下一步之前，请等待确认的变更 ID。
    - 如果仍然无法识别单一的变更 ID，请停止并告知用户目前无法归档任何内容。
2. 通过运行 `openspec list`（或 `openspec show <id>`）验证变更 ID，如果变更缺失、已归档或尚未准备好归档，则停止操作。
3. 运行 `openspec archive <id> --yes`，以便 CLI 在不提示的情况下移动变更并应用规范更新（仅针对工具类工作使用 `--skip-specs`）。
4. 检查命令输出，以确认目标规范已更新且变更已进入 `changes/archive/`。
5. 使用 `openspec validate --strict` 进行验证，并使用 `openspec show <id>` 检查是否有异常。

**参考 (Reference)**

-   在归档前使用 `openspec list` 确认变更 ID。
-   使用 `openspec list --specs` 检查更新后的规范，并在交付前解决任何验证问题。
<!-- OPENSPEC:END -->
