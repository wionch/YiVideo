## ADDED Requirements

### Requirement: 单步任务状态按 task_id+task_name 并存
单步任务模式 SHALL 在同一 `task_id` 下保留所有 `task_name` 的阶段数据而不相互覆盖，`WorkflowContext.stages` 必须累积每个节点的输入/输出。

#### Scenario: 不同 task_name 不覆盖
- **WHEN** 使用同一 `task_id` 依次调用不同的单任务节点（如先 `ffmpeg.extract_audio` 后 `faster_whisper.transcribe_audio`）
- **THEN** Redis 中保存的 `WorkflowContext` SHALL 同时包含两个 `stages` 条目
- **AND** 旧阶段的 `output`/`status`/`duration` 等字段 SHALL 保持不变

#### Scenario: 查询返回全部阶段
- **WHEN** 调用 `GET /v1/tasks/{task_id}/status` 或 `GET /v1/tasks/{task_id}/result` 在上述场景后
- **THEN** 响应 SHALL 展示 `stages` 中所有已执行的 `task_name`，而不仅是最近一次调用

### Requirement: 单步任务按 task_id+task_name 复用
单步任务执行前 MUST 检查 Redis 中是否存在 `(task_id, task_name)` 对应的成功阶段且 `output` 非空；命中时跳过调度并返回存量上下文，未命中则按现有流程执行并写入/合并新阶段。

#### Scenario: 复用命中直接返回
- **WHEN** 调用 `POST /v1/tasks`，且 Redis 中 `stages[task_name]` 的 `status=SUCCESS` 且 `output` 非空
- **THEN** 系统 SHALL 跳过 Celery 调度，直接返回该 `WorkflowContext`
- **AND** 响应/状态/回调 MUST 包含 `reuse_info`，其中 `reuse_hit=true`、`task_name` 为命中节点、`source=redis`

#### Scenario: 未命中继续执行并合并
- **WHEN** Redis 中不存在对应成功阶段或 `output` 为空
- **THEN** 系统 SHALL 正常调度执行节点
- **AND** 成功后 MUST 将新阶段写入 Redis 并保留既有阶段，`reuse_info` 反映 `reuse_hit=false`

#### Scenario: 复用返回与执行结果一致
- **WHEN** 复用命中直接返回存量阶段
- **THEN** 返回的 `stages[task_name].output`/`status`/`duration`/`error` SHALL 与实际成功执行后的内容完全一致（除新增 `reuse_info` 外不增删改字段）

### Requirement: 单步复用全局开关
系统 SHALL 提供全局开关控制单步任务复用能力，默认开启；当开关关闭时单步任务 SHALL 始终执行且不使用复用。

#### Scenario: 开关开启（默认）
- **WHEN** 开关处于开启状态（默认值）
- **THEN** 单步任务 SHALL 按上述复用规则检查并可能直接返回
- **AND** `reuse_info` MUST 准确反映命中与否

#### Scenario: 开关关闭
- **WHEN** 开关被显式关闭
- **THEN** 单步任务 SHALL 总是调度执行并更新阶段
- **AND** 响应/回调 MUST 设置 `reuse_info.reuse_hit=false` 并可标注 `source=disabled`

#### Scenario: 开关配置来源
- **WHEN** 平台读取复用开关配置
- **THEN** 默认值 SHALL 为 `core.single_task_reuse_enabled=true` 来自 `config.yml`
- **AND** 环境变量 `SINGLE_TASK_REUSE_ENABLED` SHALL 可以覆盖该值
