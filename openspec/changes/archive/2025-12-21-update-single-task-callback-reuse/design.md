## Context
- 单步任务当前按 task_id 覆盖写 Redis，stages 只保留最新 task_name，callback 模式无法复用历史阶段结果。
- 回调触发 `_check_and_trigger_callback` 仅取首个 stage 且只处理 SUCCESS/FAILED，若开始累积多阶段会选错阶段，pending 时无反馈。
- 文档未描述 callback 复用与 `reuse_info` 字段，现有规范 `single-task-api-docs` 要求复用说明但未落地。

## Goals / Non-Goals
- Goals:
  - Redis 状态按 task_id 累积 task_name 阶段，不覆盖已有阶段数据。
  - 单步任务二次请求（含 callback）按 task_id+task_name 判定复用：成功时直接回调返回缓存结果，并标注 reuse_info。
  - 明确 pending/running/failed 情况下的处理与同步响应；/status 兼容返回所有阶段。
  - 文档同步说明复用判定、字段与 callback 行为。
- Non-Goals:
  - 不改工作流模式写入策略和接口形态。
  - 不新增 TaskStatus 枚举值或额外 API。
  - 不重构 Celery 任务执行链，仅在网关/状态管理层处理复用。

## Decisions
- 状态持久化：创建/更新单步任务时先读取 task_id 的现有 WorkflowContext，将新的 task_name 阶段追加到 `stages` 中（同名阶段允许被新执行结果覆盖，但其他阶段保留）；写回时保留 TTL，并确保 input_params/callback_url 保留最新请求值。
- 复用命中：当 Redis 存在 `stages[task_name]` 且 `status=SUCCESS`、`output` 非空时，跳过 Celery 调度，构造回调 payload 与状态返回，`reuse_info={reuse_hit:true, task_name, source:redis, cached_at}`；同步响应使用 `status=completed` 以指示无需等待。
- 复用未完成：当同 task_name 状态为 `pending`/`running`，不推送回调、不重复调度；同步响应 `status=pending`，`reuse_info.reuse_hit=true` 且 `state=pending` 提示等待 `/status` 或后续回调。
- 复用失败/缺失：`FAILED` 或 `output` 为空视为未命中，按现有流程调度新执行，`reuse_info.reuse_hit=false` 并记录 miss 原因；成功后写入新阶段。
- 回调筛选：callback 触发需按本次请求的 task_name 精确选择阶段数据，默认使用当前请求提供的 callback_url（若为空则回退缓存的 input_params.callback_url），回调 payload 与正常执行成功时一致并附带 reuse_info。
- /status 兼容：`GET /v1/tasks/{task_id}/status/result` 继续返回完整 WorkflowContext，包含所有 stages；如果最近一次请求命中复用且已完成，返回体与 callback 载荷保持一致性。

## Risks / Trade-offs
- 多阶段累积后若未按 task_name 过滤可能造成误回调；需在实现中显式传递请求 task_name。
- 重复请求 pending 状态若直接重跑会产生重复任务，本设计选择等待，可能延长等待时间但避免重复执行。
- input_params 只保存最新请求，历史回调地址可能被覆盖；回调使用当前请求回调地址可缓解。

## Migration Plan
- 直接上线代码改动即可，无历史数据迁移；现有 Redis 状态依旧可读。
- 验证路径：创建同 task_id 不同 task_name，确认 stages 保留；命中 SUCCESS 复用时立即触发回调；pending 时无重复调度。

## Open Questions
- 是否需要在同步响应中返回 `reuse_info.state` 字段（pending/failed原因）以便客户端区分？（暂定：返回）
