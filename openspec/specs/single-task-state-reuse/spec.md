# single-task-state-reuse Specification

## Purpose
TBD - created by archiving change update-single-task-callback-reuse. Update Purpose after archive.
## Requirements
### Requirement: 单步任务按 task_id 累积 task_name 阶段
单步任务的 Redis 状态 SHALL 按 task_id 累积多次调用产生的各 task_name 阶段数据，追加新阶段时不得删除或覆盖同一 task_id 下已存在的其他 task_name 阶段。

#### Scenario: 同一 task_id 多阶段持久化
- **WHEN** 先后以相同 `task_id` 调用不同或相同 `task_name` 的单步任务
- **THEN** 写入 Redis 时 SHALL 读取现有 `stages` 并在其中追加/更新对应 `task_name`，保持其他阶段原样存在且 TTL 保持

#### Scenario: 状态查询返回完整阶段集
- **WHEN** 调用 `GET /v1/tasks/{task_id}/status` 或 `/result` 查询已累积多个阶段的单步任务
- **THEN** 响应 SHALL 返回该 task_id 下全部 `stages`，并保留每个阶段的 `status/output/error/duration`，不因最近一次调用而丢失历史阶段

### Requirement: 单步任务 callback 复用判定
单步任务收到带 callback 的二次请求时 SHALL 按 `task_id+task_name` 判定复用：命中成功阶段直接推送回调，未完成保持等待，失败/缺失走正常调度，并在响应与回调中标注 `reuse_info`。

#### Scenario: 命中成功阶段直接回调
- **WHEN** Redis 中存在 `stages[task_name]` 且 `status=SUCCESS`、`output` 非空，并收到同 `task_id` 的单步请求（含 callback）
- **THEN** 系统 SHALL 跳过 Celery 调度，使用当前请求的 `callback`/`callback_url` 直接发送回调，负载包含命中阶段的数据与 `reuse_info={reuse_hit:true, task_name, source:redis, cached_at}`
- **AND** 同步响应 SHALL 返回 `status=completed` 与相同的 `reuse_info`，表明无需等待执行

#### Scenario: 阶段未完成仅返回等待
- **WHEN** Redis 中存在 `stages[task_name]` 但其 `status` 为 `pending` 或 `running`
- **THEN** 系统 SHALL 不触发回调且不重复调度，复用请求的同步响应返回 `status=pending`、`reuse_info.reuse_hit=true` 并携带 `state=pending`，指示等待已有执行完成后再回调

#### Scenario: 失败或未命中按原流程执行
- **WHEN** 对应 `task_name` 不存在、`output` 为空或 `status=FAILED`
- **THEN** 系统 SHALL 视为未命中复用并按现有流程调度执行；成功后写入新阶段且保留既有阶段，`reuse_info.reuse_hit=false` 反映 miss 原因
