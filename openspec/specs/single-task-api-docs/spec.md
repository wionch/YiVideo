# single-task-api-docs Specification

## Purpose
TBD - created by archiving change add-single-task-api-docs. Update Purpose after archive.
## Requirements
### Requirement: 单任务HTTP接口文档化
单任务模式的 HTTP API MUST 展示与实现一致的请求/响应/回调字段，基于 `SingleTaskRequest`、`SingleTaskResponse`、`TaskStatusResponse`、`CallbackResult` 与 `WorkflowContext` 的实际结构，并确保创建时间字段不会在响应序列化过程中丢失。

#### Scenario: 状态/结果/回调一致性
- **WHEN** 文档说明 `GET /v1/tasks/{task_id}/status`、`GET /v1/tasks/{task_id}/result` 或回调载荷
- **THEN** 示例 SHALL 以实际序列化结果为准，包含 `workflow_id`、创建时间字段（`create_at` 或同名字段与模型一致）、`input_params.task_name/input_data/callback_url`、`shared_storage_path`、`stages.<task>.status/input_params/output/error/duration`、顶层 `error` 以及运行时的 `status`、`updated_at`、`minio_files`、`callback_status`/`timestamp`，字段命名与代码保持一一对应且不会被模型过滤

### Requirement: 文件操作HTTP接口文档化
文件操作端点 `/v1/files` 系列 MUST 与 `file_operations.py` 的行为及 Pydantic 模型一致，涵盖路径安全限制、必填参数和返回字段（含可能的 `file_size`/`content_type`）。

#### Scenario: 目录与文件操作一致性
- **WHEN** 文档描述 `DELETE /v1/files/directories` 或 `DELETE /v1/files/{file_path}`、`POST /v1/files/upload`、`GET /v1/files/download/{file_path}` 行为
- **THEN** 它 SHALL 明确 `/share` 路径限定/禁止路径遍历、bucket 默认值、幂等行为，并给出匹配 `FileOperationResponse`/`FileUploadResponse` 的标准化请求与响应示例（包括可返回的 `file_size`、`content_type` 字段）

### Requirement: 单任务节点分节示例
系统 SHALL 为所有支持单步任务的节点提供以代码为基准的单任务 HTTP 文档小节（涵盖 `ffmpeg`, `faster_whisper`, `audio_separator`, `pyannote_audio`, `paddleocr`, `indextts`, `wservice` 系列），并与 `/v1/tasks/supported-tasks` 返回列表一致；示例中的请求体、参数表与输出字段 MUST 与对应任务实现的输入解析和返回结构一致（包括本地路径恒定存在、可选 MinIO URL 由上传开关控制、是否需要上游目录、是否写入 WorkflowContext，且远程 URL 使用 `*_minio_url`/`minio_files` 等专用字段，不得覆盖本地字段）。

#### Scenario: 节点参数准确性验证
- **WHEN** 文档展示 `paddleocr.detect_subtitle_area`
- **THEN** 必须列出 `keyframe_dir` 为输入参数（可来自 `ffmpeg.extract_keyframes` 或 MinIO/HTTP 下载），而非 `video_path`
- **WHEN** 文档展示 `paddleocr.postprocess_and_finalize`
- **THEN** 必须列出 `video_path` 为必需参数（用于FPS计算），且不得宣称未实现的 MinIO 上传开关
- **WHEN** 文档展示 `indextts.generate_speech`
- **THEN** 必须标记 `spk_audio_prompt`/`output_path` 为必填，说明 `voice` 当前未被消费，并按实际返回结构展示
- **WHEN** 文档展示 `wservice.ai_optimize_subtitles`
- **THEN** 必须说明依赖 `subtitle_optimization.enabled` 开关，输入源为 `segments_file`/转录 JSON 而非 SRT 文件

#### Scenario: 输出路径与返回结构校验（含上传开关）
- **WHEN** 文档描述 `ffmpeg.extract_audio`、`ffmpeg.split_audio_segments`、`faster_whisper.transcribe_audio`、`wservice.generate_subtitle_files` 或 `paddleocr.perform_ocr`
- **THEN** 示例输出 SHALL 同时展示本地 `/share` 路径字段，并仅在 `core.auto_upload_to_minio=true` 以及节点 upload_* 参数开启时附带 `*_minio_url`/`minio_files` 可选字段；本地路径不得被远程 URL 覆盖
- **WHEN** 文档描述 `pyannote_audio.diarize_speakers`
- **THEN** MUST 展示 `diarization_file` 本地路径，并仅在上传开启时附带 `diarization_file_minio_url`
- **WHEN** 文档描述 `wservice.correct_subtitles`
- **THEN** MUST 展示 `corrected_subtitle_path` 本地路径，远程 URL 仅作为可选字段并标注依赖 `core.auto_upload_to_minio`
- **WHEN** 文档描述 `audio_separator`, `paddleocr.*`, `indextts.generate_speech` 或 `wservice.*` 系列节点
- **THEN** 远程 URL 字段 MUST 采用 `*_minio_url`/`minio_files` 专用字段呈现，保持原始本地字段为实际路径；如未上传则远程字段缺省或为空
- **WHEN** 文档描述 `pyannote_audio.get_speaker_segments` 或 `pyannote_audio.validate_diarization`
- **THEN** 返回示例 SHALL 反映实际 `{"success":..., "data"|"error":...}` 结构，而非完整 WorkflowContext

### Requirement: 单任务复用文档覆盖
`SINGLE_TASK_API_REFERENCE.md` SHALL 描述按 `task_id+task_name` 的复用流程、回调短路逻辑与返回字段，并在所有单任务节点小节中给出复用判定规则与示例字段（含成功命中、未完成等待、未命中执行）。

#### Scenario: 通用接口复用说明
- **WHEN** 文档描述 `POST /v1/tasks`、`GET /v1/tasks/{task_id}/status`、`GET /v1/tasks/{task_id}/result` 或回调载荷
- **THEN** 必须说明在执行前检查 Redis 中 `(task_id, task_name)` 成功阶段的逻辑以及复用全局开关的默认开启/关闭效果
- **AND** 示例 SHALL 展示 `reuse_info`（含 `reuse_hit`、`task_name`、`source`、`cached_at` 可选）在命中/未命中情况下的取值，并标注回调命中时同步响应 `status=completed`
- **AND** 文档 SHALL 说明缓存阶段为 `pending`/`running` 时不会立即回调，复用响应返回 `status=pending` 且 `reuse_info.state=pending`，需要等待既有执行完成后再查看 `/status` 或接收后续回调
- **AND** 命中复用的响应/回调输出字段（含 `stages[task_name].output/status/duration/error` 与顶层字段） SHALL 与实际执行成功时一致，仅附加 `reuse_info`

#### Scenario: 节点级复用判定字段
- **WHEN** 文档展示任一单任务节点小节（`ffmpeg.extract_keyframes/extract_audio/crop_subtitle_images/split_audio_segments`、`faster_whisper.transcribe_audio`、`audio_separator.separate_vocals`、`pyannote_audio.*`、`paddleocr.*`、`indextts.generate_speech`、`wservice.*`）
- **THEN** 小节 SHALL 说明该节点用于复用判定的主要输出字段（至少表明需要成功状态且 `output` 非空），并给出命中时的返回形态与 `reuse_info` 取值；若缓存状态为 `pending`/`running`，需说明不会推送回调且可等待已有执行

