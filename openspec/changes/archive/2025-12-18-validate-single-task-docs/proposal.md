# Change: 单任务 API 文档一致性校验与修正

## Why
- `SINGLE_TASK_API_REFERENCE.md` 需要与实际 FastAPI/Pydantic 模型和各 Celery 任务输出保持同步，避免调用方按照过时字段或示例集成导致错误。

## What Changes
- 复核 `/v1/tasks` 通用请求/响应、WorkflowContext 与 callback 载荷示例，对齐 `SingleTaskRequest`/`TaskStatusResponse`/`CallbackResult` 及执行器实际状态字段。
- 按节点逐一核对请求体与 WorkflowContext 输出示例，确保字段、默认值和输出与 worker 任务实现一致，并引用 `WORKFLOW_NODES_REFERENCE` 交叉验证。
- 校准 `/v1/files` 端点的请求与响应示例，使其与 `file_operations.py` 中的安全校验与返回模型保持一致。

## Impact
- Affected specs: `single-task-api-docs`
- Affected code/docs: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`, FastAPI 单任务端点与模型（`services/api_gateway/app/single_task_api.py`, `single_task_models.py`, `single_task_executor.py`），节点实现输出（各 worker 任务）、`WORKFLOW_NODES_REFERENCE.md`
