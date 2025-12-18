## 背景
- 需求：校验并纠正 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md` 中各节点的请求体、WorkflowContext 示例和代码实现的一致性，覆盖 `/v1/tasks` 与 `/v1/files` 相关内容。

## 思考拆解（sequential-thinking）
- 模糊点：是否只改文档还是需同步补齐缺失示例；节点范围是否仅当前清单还是需要补全新增节点。
- 影响面：FastAPI 单任务端点与 Pydantic 模型（`services/api_gateway/app/single_task_api.py`, `single_task_models.py`），单任务执行器状态结构（`single_task_executor.py`），工作流上下文定义（`services/common/context.py`），节点实现输出/输入字段（各 worker 任务），以及参考文档 `WORKFLOW_NODES_REFERENCE.md`。
- 风险：文档字段命名/默认值与 `get_param_with_fallback` 解析结果不符；WorkflowContext 示例缺少 `updated_at`/`status`/`minio_files` 等运行时字段；回调载荷字段（status/result/timestamp/minio_files）可能与代码差异。
- 候选方案：基于 Pydantic 模型与任务实现的真实字段做逐节点对照，形成差异清单后更新文档；WorkflowContext 示例以 `state_manager`/executor 实际字段为准；同步检查文件操作端点的请求/响应示例。

## 代码与文档线索（serena）
- 单任务模型与响应字段：`services/api_gateway/app/single_task_models.py`（`SingleTaskRequest`、`SingleTaskResponse`、`TaskStatusResponse`、`CallbackResult`、文件操作模型）。
- 单任务端点与状态/结果语义：`services/api_gateway/app/single_task_api.py`（POST/GET status/result/retry/cancel/supported-tasks）。
- 任务状态存储与回调字段：`services/api_gateway/app/single_task_executor.py`（context 创建含 `create_at`/`stages`，状态更新写入 `updated_at`、`minio_files`、`callback_status`；回调由 `callback_manager.send_result`）。
- WorkflowContext 结构：`services/common/context.py`（字段 `workflow_id`/`create_at`/`input_params`/`shared_storage_path`/`stages`/`error`，extra 允许额外字段如 `updated_at`）。
- 文档现状：`docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`（各节点请求/WorkflowContext 示例、文件操作示例）。
- 参考节点说明：`docs/technical/reference/WORKFLOW_NODES_REFERENCE.md`（节点参数与输出描述，需交叉验证）。

## 外部文档（context7）
- FastAPI `response_model` 行为强调返回结构由 Pydantic 过滤/校验，需确保文档示例字段与 `response_model` 定义一致（来源：/fastapi/fastapi tutorial/response-model）。

## 结论与差异关注
- 文档需核对的字段来源：`SingleTaskRequest`/`SingleTaskResponse`/`TaskStatusResponse`/`CallbackResult`，以及 `WorkflowContext` 运行时新增字段（`updated_at`、`minio_files`、`callback_status` 等）。
- 节点示例应以实际任务输出为准（参考各 worker 任务的 `StageExecution.output`），避免遗漏如 `cropped_images_uploaded_files`、`speaker_summary`、`statistics` 等。
- 文件操作示例需对齐 `FileOperationResponse`/`FileUploadResponse` 实际字段（包含 `file_size`/`content_type` 等可选字段）。

## 开放问题
- 是否需要为当前未列出的节点（若有新任务）补充单任务示例？
- 文档中的时间/URL占位是否需统一为现有规范（当前使用 `2025-12-17` 等示例）。

## 推荐方案（提案方向）
- 以 `SingleTaskRequest`/`TaskStatusResponse`/`CallbackResult` 为基准梳理通用接口字段；将 WorkflowContext 示例补齐运行时字段并与 executor/state_manager 行为一致。
- 按节点逐个对照 worker 任务的输入解析与输出字段，更新文档参数表与示例。
- 校验 `/v1/files` 端点示例与 `file_operations.py` 的返回字段，修正文档不一致处。
