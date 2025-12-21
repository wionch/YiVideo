# Data Model: callback 复用覆盖修复

## Entities

### WorkflowContext
- `workflow_id` (string): 单任务 ID（同 `task_id`）。
- `create_at` (datetime): 创建时间。
- `input_params` (object): 包含 `task_name`、`input_data`、`callback_url`。
- `shared_storage_path` (string): `/share/workflows/{task_id}` 路径。
- `stages` (map<string, StageEntry>): 以 `task_name` 为键的阶段集合，必须累积且不可覆盖其他键。
- `status` (string): overall 状态。
- `error` (object|null): 顶层错误。
- `updated_at` (datetime, optional): 最近更新时间。
- `minio_files` (array, optional): 上传文件描述。

Validation/Rules:
- 更新任何阶段时，必须先读取现有 `stages`，只更新对应键，保持其他键内容与 TTL 不变。
- 查询或回调需返回完整 `stages` 集合。

### StageEntry
- `status` (enum): `PENDING` | `RUNNING` | `SUCCESS` | `FAILED`。
- `input_params` (object): 节点入参（本地路径/下载后路径）。
- `output` (object|null): 节点产出；复用命中需确保非空。
- `error` (object|null): 错误信息。
- `duration` (number|null): 执行耗时秒。

Validation/Rules:
- 复用命中要求 `status=SUCCESS` 且 `output` 非空；否则视为未命中。
- 写入时不得清空其他 `task_name` 的 `StageEntry`。

### ReuseInfo (响应/回调附带)
- `reuse_hit` (bool): 是否命中复用。
- `task_name` (string): 命中或检查的节点名。
- `source` (string, optional): 缓存来源，如 `redis`。
- `cached_at` (datetime, optional): 命中缓存时间。
- `state` (string, optional): `pending` 用于等待态。

Validation/Rules:
- 命中成功：`reuse_hit=true`，含 `cached_at`；同步响应 `status=completed`。
- 等待态：`reuse_hit=true` 且 `state=pending`，同步响应 `status=pending`，不重复调度。
- 未命中：`reuse_hit=false`，按常规执行。

## Relationships
- `WorkflowContext.stages` 包含多个 `StageEntry`，键为 `task_name`。
- `ReuseInfo` 作为响应或回调的补充字段，不写回 Redis 但与 `StageEntry` 命中结果对应。
