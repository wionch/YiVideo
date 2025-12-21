## ADDED Requirements

### Requirement: 单任务HTTP接口文档化
单任务模式的 HTTP API MUST 提供完整、对齐实现的文档，覆盖任务创建、状态查询、结果获取与 callback 载荷，并以 `WorkflowContext` 结构为准。

#### Scenario: 创建任务接口文档
- **WHEN** 文档描述 `POST /v1/tasks` 的单任务创建
- **THEN** 它 SHALL 展示请求字段 `task_name`、可选 `task_id`、可选 `callback`、`input_data`，并给出同步响应示例 `{task_id,status,message}`，状态为 `pending/running/failed/cancelled` 之一，与 `SingleTaskResponse` 模型保持一致

#### Scenario: 状态与结果文档
- **WHEN** 文档说明 `GET /v1/tasks/{task_id}/status`、`GET /v1/tasks/{task_id}/result` 或 callback 返回体
- **THEN** 它 SHALL 展示基于 `WorkflowContext` 的字段：`workflow_id`、`create_at`、`input_params.task_name/input_data/callback_url`、`shared_storage_path`、`stages.<task>.status/input_params/output/error/duration`、顶层 `error`，并在适用时包含 `minio_files`、`timestamp`；需提供成功示例，字段命名与代码一致且示例时间/URL 采用统一占位

### Requirement: 文件操作HTTP接口文档化
文件操作端点 `/v1/files` 系列 MUST 提供与实现一致的请求/响应文档，覆盖目录删除、文件删除、上传、下载，示例需使用统一的时间与 URL 占位。

#### Scenario: 目录删除接口文档
- **WHEN** 文档描述 `DELETE /v1/files/directories?directory_path=` 行为
- **THEN** 它 SHALL 说明路径限制（仅 /share 下，禁止路径遍历）、幂等成功返回结构 `FileOperationResponse`（含 `success`、`message`、`file_path`），并给出标准化示例

### Requirement: 单任务节点分节示例
系统 SHALL 为所有支持单步任务的节点提供独立的单任务 HTTP 文档小节（涵盖 `ffmpeg.extract_keyframes/extract_audio/crop_subtitle_images/split_audio_segments`, `faster_whisper.transcribe_audio`, `audio_separator.separate_vocals`, `pyannote_audio.diarize_speakers`, `paddleocr.detect_subtitle_area/perform_ocr`, `indextts.generate_speech`, `wservice.generate_subtitle_files/correct_subtitles/ai_optimize_subtitles`）。

#### Scenario: 节点覆盖与示例内容
- **WHEN** 文档列出支持的单任务节点
- **THEN** 每个节点小节 SHALL 包含：用途概述；`POST /v1/tasks` 请求样例（curl 与 n8n JSON 至少一种，含 node-specific `input_data` 与 `callback`）；同步响应示例；状态/结果或 callback 示例（展示 `stages.<task>.output` 的关键字段）；以及输入/输出参数表（必填/可选/默认值）

#### Scenario: 源码与节点文档交叉校验
- **WHEN** 文档记录某节点的输入或输出字段
- **THEN** 这些字段 SHALL 已经与对应 Celery 任务实现及 `WORKFLOW_NODES_REFERENCE.md` 交叉验证，确保字段名、默认值与 `get_param_with_fallback`/StageExecution 输出一致，避免仅依赖节点文档推断
