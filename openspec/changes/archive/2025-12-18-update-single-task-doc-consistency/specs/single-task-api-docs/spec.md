## MODIFIED Requirements

### Requirement: 单任务HTTP接口文档化
单任务模式的 HTTP API MUST 展示与实现一致的请求/响应/回调字段，基于 `SingleTaskRequest`、`SingleTaskResponse`、`TaskStatusResponse`、`CallbackResult` 与 `WorkflowContext` 的实际结构，并确保创建时间字段不会在响应序列化过程中丢失。

#### Scenario: 状态/结果/回调一致性
- **WHEN** 文档说明 `GET /v1/tasks/{task_id}/status`、`GET /v1/tasks/{task_id}/result` 或回调载荷
- **THEN** 示例 SHALL 以实际序列化结果为准，包含 `workflow_id`、创建时间字段（`create_at` 或同名字段与模型一致）、`input_params.task_name/input_data/callback_url`、`shared_storage_path`、`stages.<task>.status/input_params/output/error/duration`、顶层 `error` 以及运行时的 `status`、`updated_at`、`minio_files`、`callback_status`/`timestamp`，字段命名与代码保持一一对应且不会被模型过滤

### Requirement: 单任务节点分节示例
系统 SHALL 为所有支持单步任务的节点提供以代码为基准的单任务 HTTP 文档小节（涵盖 `ffmpeg.extract_keyframes/extract_audio/crop_subtitle_images/split_audio_segments`, `faster_whisper.transcribe_audio`, `audio_separator.separate_vocals`, `pyannote_audio.diarize_speakers/get_speaker_segments/validate_diarization`, `paddleocr.detect_subtitle_area/create_stitched_images/perform_ocr/postprocess_and_finalize`, `indextts.generate_speech`, `wservice.generate_subtitle_files/correct_subtitles/ai_optimize_subtitles/merge_speaker_segments/merge_with_word_timestamps/prepare_tts_segments`），并与 `/v1/tasks/supported-tasks` 返回列表一致；不支持单步任务的节点（如 `audio_separator.health_check`, `indextts.list_voice_presets`, `indextts.get_model_info`）不应出现在单任务节点清单中。

#### Scenario: 节点覆盖与示例内容对齐实现
- **WHEN** 文档列出支持的单任务节点或 `/v1/tasks/supported-tasks` 返回列表
- **THEN** 每个节点小节 SHALL 包含：请求体示例与参数表（标明必填/可选/默认值，来源于 `get_param_with_fallback`/节点代码），WorkflowContext 输出示例展示任务真实输出字段（含统计/上传信息）；`supported-tasks` 返回集合 SHALL 与文档节点清单一致且覆盖所有 Celery 任务名称
