## MODIFIED Requirements

### Requirement: 单任务HTTP接口文档化
单任务模式的 HTTP API MUST 展示与实现一致的请求/响应/回调字段，基于 `SingleTaskRequest`、`SingleTaskResponse`、`TaskStatusResponse`、`CallbackResult` 与 `WorkflowContext` 的实际结构（含运行时 `status`、`updated_at`、`minio_files`、`callback_status` 等）。

#### Scenario: 创建与同步响应一致性
- **WHEN** 文档描述 `POST /v1/tasks` 的单任务创建
- **THEN** 请求示例 SHALL 覆盖 `task_name`、可选 `task_id`/`callback`、必填 `input_data`，并声明状态枚举来源于 `TaskStatus`（`pending`/`running`/`completed`/`failed`，允许取消时的 `cancelled` 说明）；同步响应示例 SHALL 与 `SingleTaskResponse` 字段完全匹配

#### Scenario: 状态/结果/回调一致性
- **WHEN** 文档说明 `GET /v1/tasks/{task_id}/status`、`GET /v1/tasks/{task_id}/result` 或回调载荷
- **THEN** 示例 SHALL 以 `WorkflowContext` 实际序列化为准，包含 `workflow_id`、`create_at`、`input_params.task_name/input_data/callback_url`、`shared_storage_path`、`stages.<task>.status/input_params/output/error/duration`、顶层 `error` 以及运行时的 `updated_at`、`minio_files`、`callback_status`/`timestamp`，字段命名与代码保持一一对应

### Requirement: 文件操作HTTP接口文档化
文件操作端点 `/v1/files` 系列 MUST 与 `file_operations.py` 的行为及 Pydantic 模型一致，涵盖路径安全限制、必填参数和返回字段（含可能的 `file_size`/`content_type`）。

#### Scenario: 目录与文件操作一致性
- **WHEN** 文档描述 `DELETE /v1/files/directories` 或 `DELETE /v1/files/{file_path}`、`POST /v1/files/upload`、`GET /v1/files/download/{file_path}` 行为
- **THEN** 它 SHALL 明确 `/share` 路径限定/禁止路径遍历、bucket 默认值、幂等行为，并给出匹配 `FileOperationResponse`/`FileUploadResponse` 的标准化请求与响应示例（包括可返回的 `file_size`、`content_type` 字段）

### Requirement: 单任务节点分节示例
系统 SHALL 为所有支持单步任务的节点提供以代码为基准的单任务 HTTP 文档小节（涵盖 `ffmpeg.extract_keyframes/extract_audio/crop_subtitle_images/split_audio_segments`, `faster_whisper.transcribe_audio`, `audio_separator.separate_vocals`, `pyannote_audio.diarize_speakers`, `paddleocr.detect_subtitle_area/perform_ocr`, `indextts.generate_speech`, `wservice.generate_subtitle_files/correct_subtitles/ai_optimize_subtitles`）。

#### Scenario: 节点覆盖与示例内容对齐实现
- **WHEN** 文档列出支持的单任务节点
- **THEN** 每个节点小节 SHALL 包含：请求体示例与参数表（标明必填/可选/默认值，来源于 `get_param_with_fallback`/节点代码），WorkflowContext 输出示例展示任务真实输出字段（含统计/上传信息），并与 `WORKFLOW_NODES_REFERENCE.md` 及对应 Celery 任务实现交叉验证
