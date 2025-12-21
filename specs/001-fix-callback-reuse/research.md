# Research: callback 复用覆盖修复

## Inputs
- Feature spec: `specs/001-fix-callback-reuse/spec.md`
- 归档提案：`openspec/changes/archive/2025-12-21-update-single-task-callback-reuse/specs/single-task-state-reuse/spec.md`
- 文档：`docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
- 代码结构参考：`services/api_gateway/app/`（单任务执行/回调/状态落盘）、`services/workers/`（各节点）
- FastAPI 背景任务参考：context7 `/fastapi/fastapi`（强调重任务应使用 Celery，而非 BackgroundTasks）

## Findings & Decisions

1) **Redis 状态需累积多阶段且不可覆盖**
   - Evidence: 归档 spec `single-task-state-reuse` 要求按 `task_id` 追加 `stages`，不得覆盖其他阶段。
   - Decision: 复用与写入逻辑必须先读取现有 `stages` 再更新目标 `task_name`，保持其他节点数据与 TTL。
   - Alternatives: 覆盖式写入（当前问题根源）已否决。

2) **复用判定覆盖全部单任务节点**
   - Evidence: 归档 spec `single-task-state-reuse` 与文档 `SINGLE_TASK_API_REFERENCE.md` 说明所有节点需按 `task_id+task_name` 判定复用，成功短路调度并回调。
   - Decision: 在 api_gateway 单任务入口对所有节点统一复用判定；workers 侧仅保持输出完整性，不单独重写覆盖逻辑。
   - Alternatives: 按节点白名单实现复用（风险遗漏）被否决。

3) **等待态不重复调度**
   - Evidence: 文档复用段说明 `pending/running` 时返回 `status=pending`、`reuse_info.state=pending`，不重复调度。
   - Decision: 发现等待态需直接返回等待响应，不创建新的 Celery 任务。
   - Alternatives: 再次排队等待（可能导致重复执行）被否决。

4) **文档需与行为同步**
   - Evidence: 归档 `single-task-api-docs` 要求各节点小节包含复用判定字段与示例。
   - Decision: 修复时同步更新 `SINGLE_TASK_API_REFERENCE.md` 节点小节，确保命中/等待/未命中返回形态与真实行为一致。
   - Alternatives: 仅改代码不改文档被否决。

5) **重任务使用 Celery，避免 FastAPI BackgroundTasks**
   - Evidence: context7 FastAPI 背景任务文档指出重任务应交给 Celery 等队列。
   - Decision: 复用短路只返回缓存，不引入新的 FastAPI BackgroundTasks；保持现有 Celery 流程。
   - Alternatives: 在 FastAPI 内直接后台执行被否决（违背现有架构，难以扩展）。

## Open Questions

无 [NEEDS CLARIFICATION]。
