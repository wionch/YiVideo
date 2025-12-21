## MODIFIED Requirements
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
