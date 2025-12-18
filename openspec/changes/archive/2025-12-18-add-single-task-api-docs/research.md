# 研究记录

## 工具使用
- `sequential-thinking`: 梳理需求、影响面、风险与方案（见下方“澄清要点”与“风险”）。
- `serena` 代码检索：
  - API 入口与模型：`services/api_gateway/app/single_task_api.py`、`services/api_gateway/app/single_task_executor.py`、`services/api_gateway/app/single_task_models.py`。
  - 工作流上下文：`services/common/context.py`、状态存储与回调：`services/common/state_manager.py`、`services/api_gateway/app/callback_manager.py`。
  - 任务列表：`get_supported_tasks` in `services/api_gateway/app/single_task_api.py`。
  - 节点实现示例：`services/workers/ffmpeg_service/app/tasks.py` 中 `ffmpeg.extract_audio`（输入 `video_path`、输出 `audio_path`、状态写入 `WorkflowContext`）。
  - 其他 HTTP 端点：`services/api_gateway/app/file_operations.py` 提供 `/v1/files/directories`（DELETE 目录，限定 /share）、`DELETE /v1/files/{file_path}`（MinIO 删除）、`POST /v1/files/upload`（流式上传）、`GET /v1/files/download/{file_path}`。
- `context7` 文档：`/fastapi/fastapi` 之 `response_model` 用法，确认 FastAPI 端点依赖 Pydantic 模型生成响应契约与文档。

## 现状与证据
- 单任务 API 行为：
  - `POST /v1/tasks` 返回 `SingleTaskResponse`（字段 `task_id`, `status`, `message`），状态固定 `pending`，不含结果（`services/api_gateway/app/single_task_api.py:17-118`）。
  - 结果查询：`GET /v1/tasks/{task_id}/status` 与 `/result` 返回 Redis 中的工作流状态（`single_task_api.get_task_status/get_task_result` -> `SingleTaskExecutor.get_task_status` -> `state_manager.get_workflow_state`）。
  - 支持的单任务列表：`get_supported_tasks` 返回 13 个节点（ffmpeg.extract_keyframes/extract_audio/crop_subtitle_images/split_audio_segments，faster_whisper.transcribe_audio，audio_separator.separate_vocals，pyannote_audio.diarize_speakers，paddleocr.detect_subtitle_area/perform_ocr，indextts.generate_speech，wservice.generate_subtitle_files/correct_subtitles/ai_optimize_subtitles），位于 `services/api_gateway/app/single_task_api.py:183-219`。
- 工作流上下文结构：
  - `WorkflowContext` 字段：`workflow_id`, `create_at`, `input_params`, `shared_storage_path`, `stages`（StageExecution: `status`, `input_params`, `output`, `error`, `duration`）, `error`（`services/common/context.py`）。
  - 初始 context 创建：`SingleTaskExecutor._create_task_context` 在 `stages` 中预置任务名、`status: pending` 与 `start_time/end_time` 占位（`single_task_executor.py:78-122`）。
  - 状态持久化与回调：`state_manager.update_workflow_state` 在更新时自动上传文件、触发 callback；回调数据由 `callback_manager.send_result` 包装为 `{task_id,status,result,minio_files?,timestamp}`（`services/common/state_manager.py:93-210`，`services/api_gateway/app/callback_manager.py:26-121`）。
- 节点代码示例（交叉验证节点文档所需）：
  - `ffmpeg.extract_audio`: 需 `video_path`，输出 `audio_path` 写入 `WorkflowContext.stages[task].output`，状态 `SUCCESS/FAILED`，记录 `duration`，在 `finally` 中调用 `state_manager.update_workflow_state`（`services/workers/ffmpeg_service/app/tasks.py:275-425`）。
- 文档现状：
  - 节点功能文档集中在 `docs/technical/reference/WORKFLOW_NODES_REFERENCE.md`，已描述参数/输出、单任务模式示例，但缺少针对 HTTP API 的统一章节与按节点分拆的请求/回调示例。
  - 文档规范：`docs/DOCUMENT_WRITING_GUIDELINES.md` 要求端口统一 `8788`、示例带完整路径、文件末尾“最后更新”标识；本次将统一采用单一示例格式（curl/JSON 二选一），时间与 URL 采用固定示例值。

## 澄清要点 / 未决问题
1. “支持单步任务的所有功能节点”是否以 `get_supported_tasks` 列表为准？若还有其他 Celery 任务允许单步触发，需确认是否纳入。
2. 新增的 HTTP API 文档放置路径：是否置于 `docs/technical/reference/` 下（新文件），或在现有 `WORKFLOW_NODES_REFERENCE.md` 中新增独立章节/子文件？
3. 回调/结果示例中的时间与 URL 是否需要统一示例值（例如 `host.docker.internal`/`localhost`），是否需给出失败场景示例？
4. 是否需要同步提供 curl 与 n8n 配置示例两套格式，或统一为一种？
5. 文件操作类 HTTP 端点（目录/文件删除、上传、下载）是否一并纳入文档？——已确认需要。

## 风险
- 节点参数/输出若仅依赖节点文档，可能与代码默认值或 `get_param_with_fallback` 的优先级不一致，导致请求样例错误。
- 任务状态文档若未严格对齐 `WorkflowContext`（如 StageExecution 字段名、大小写），会导致回调解析错误。
- 支持任务列表若与实际 Celery 注册的任务不同，会给用户错误指引。

## 推荐方案与取舍
- 方案：以 `get_supported_tasks` 为单步节点清单，逐一在 HTTP API 文档中生成结构化章节：`概述 -> 请求 (POST /v1/tasks) -> 同步响应 -> 结果查询 (/status,/result) -> callback payload -> 输入参数表 -> 输出字段表 -> 请求/回调 JSON 示例`。每个节点的输入/输出示例需通过节点代码与现有节点文档交叉校验。文件操作端点单独章节说明。
- 文档承载方式：在 `docs/technical/reference/` 下新增独立文件（如 `SINGLE_TASK_API_REFERENCE.md`），并从 `WORKFLOW_NODES_REFERENCE` 链接。
- 示例格式：统一一套（例如 curl+JSON），时间/URL 使用固定示例值，不提供失败场景。
- 验证：生成后的 OpenSpec 变更需通过 `openspec validate add-single-task-api-docs --strict`，同时对照代码样例（如 `ffmpeg.extract_audio` 等）确保请求/回调字段与 `WorkflowContext` 完整一致。
