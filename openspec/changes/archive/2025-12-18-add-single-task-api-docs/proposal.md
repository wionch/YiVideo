# Change: 单任务节点 HTTP API 文档补全

## Why
- 现有 `WORKFLOW_NODES_REFERENCE.md` 只描述节点参数/输出，缺少与实际 FastAPI 单任务接口 (`/v1/tasks`) 对齐的请求、同步响应、状态查询与 callback 说明，用户需要依赖示例才能正确接入。
- API 返回的 `WorkflowContext` 结构与状态管理逻辑（pending→running→completed/failed，MinIO URL 回填、callback 载荷）未在文档中统一呈现，易造成误用或字段缺失。
- n8n 等编排场景需要标准化的单任务调用示例（curl + n8n），当前缺口导致集成成本高。

## What Changes
- 新增独立的单任务/文件操作 HTTP API 文档（位于 `docs/technical/reference/`），覆盖 `/v1/tasks` 创建、`/v1/tasks/{task_id}/status`、`/v1/tasks/{task_id}/result`、callback 载荷及 `WorkflowContext` 字段说明，以及 `/v1/files` 系列端点（目录删除、文件删除、上传、下载）。
- 为 `get_supported_tasks` 列表中的所有节点分别提供请求/回调 JSON 样例、必填/可选参数表、输出字段表，格式与 `SingleTaskResponse`、`WorkflowContext`、实际节点代码保持一致；示例统一单一格式与标准化时间/URL 值。
- 在节点参考文档中补充入口链接/索引，确保读者可从节点功能跳转到对应的单任务 API 章节。

## Impact
- Affected specs: `single-task-api-docs` (new)
- Affected docs: `docs/technical/reference/WORKFLOW_NODES_REFERENCE.md`（新增单任务 API 链接/索引）、新增/更新的单任务 HTTP API 参考文档文件（待定具体路径）。
- Affected code (引用对齐用): `services/api_gateway/app/single_task_api.py`, `services/api_gateway/app/single_task_executor.py`, `services/common/context.py`, `services/common/state_manager.py`, 各节点任务实现（用于参数/输出交叉校验）。***
