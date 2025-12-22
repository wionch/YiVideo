# 数据模型: 任务删除 API 节点

## 实体概览
- **TaskDeletionRequest**：删除任务数据的请求体。
- **TaskDeletionResult**：删除结果聚合。
- **ResourceDeletionItem**：分资源删除结果条目。

## TaskDeletionRequest
- `task_id` (string, 必填)：任务唯一标识。
- `force` (boolean, 默认 false)：是否允许在运行/排队中强制删除。

验证与规则：
- `task_id` 必须符合现有任务 ID 约定（与 `/v1/tasks` 保持一致）。
- `force=false` 时检测到运行/排队任务需返回拒绝信息，不执行删除。

## TaskDeletionResult
- `status` (enum: `success` | `partial_failed` | `failed`)：整体删除结果。
- `results` (ResourceDeletionItem[])：各资源的删除结果。
- `warnings` (string[], 可选)：非阻断提示（如部分对象缺失、可重试建议）。
- `timestamp` (string, ISO 8601)：结果生成时间。

## ResourceDeletionItem
- `resource` (enum: `local_directory` | `redis` | `minio`)：资源类型。
- `status` (enum: `deleted` | `skipped` | `failed`)：该资源的处理结果。
- `message` (string, 可选)：补充说明（缺失/权限/网络问题）。
- `retriable` (boolean, 可选)：是否建议重试。
- `details` (object, 可选)：可包含被删除路径/键/对象前缀列表或错误代码。

关系与状态说明：
- TaskDeletionResult.status 取决于 results：全部 `deleted` 或允许的 `skipped` → `success`；存在 `failed` → `partial_failed` 或 `failed`（视是否还有其他成功项）。
- 幂等性：目标不存在时对应 ResourceDeletionItem.status=skipped，并不影响 overall `success`。
