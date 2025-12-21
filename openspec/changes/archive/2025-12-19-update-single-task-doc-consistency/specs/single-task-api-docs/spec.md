## MODIFIED Requirements
### Requirement: 单任务节点分节示例
系统 SHALL 为所有支持单步任务的节点提供以代码为基准的单任务 HTTP 文档小节（涵盖 `ffmpeg`, `faster_whisper`, `audio_separator`, `pyannote_audio`, `paddleocr`, `indextts`, `wservice` 系列），并与 `/v1/tasks/supported-tasks` 返回列表一致；示例中的请求体、参数表与输出字段 MUST 与对应任务实现的输入解析和返回结构一致（包括仅返回本地路径、是否需要上游目录、是否写入 WorkflowContext）。

#### Scenario: 节点参数准确性验证
- **WHEN** 文档展示 `paddleocr.detect_subtitle_area`
- **THEN** 必须列出 `keyframe_dir` 为输入参数（可来自 `ffmpeg.extract_keyframes` 或 MinIO/HTTP 下载），而非 `video_path`
- **WHEN** 文档展示 `paddleocr.postprocess_and_finalize`
- **THEN** 必须列出 `video_path` 为必需参数（用于FPS计算），且不得宣称未实现的 MinIO 上传开关
- **WHEN** 文档展示 `indextts.generate_speech`
- **THEN** 必须标记 `spk_audio_prompt`/`output_path` 为必填，说明 `voice` 当前未被消费，并按实际返回结构展示
- **WHEN** 文档展示 `wservice.ai_optimize_subtitles`
- **THEN** 必须说明依赖 `subtitle_optimization.enabled` 开关，输入源为 `segments_file`/转录 JSON 而非 SRT 文件

#### Scenario: 输出路径与返回结构校验
- **WHEN** 文档描述 `ffmpeg.extract_audio`、`ffmpeg.split_audio_segments`、`faster_whisper.transcribe_audio`、`wservice.generate_subtitle_files` 或 `paddleocr.perform_ocr`
- **THEN** 示例输出 SHALL 以本地 `/share` 路径为主，只有实际存在的 `*_minio_url` 字段才展示为可选项，不得默认使用 MinIO URL
- **WHEN** 文档描述 `pyannote_audio.get_speaker_segments` 或 `pyannote_audio.validate_diarization`
- **THEN** 返回示例 SHALL 反映实际 `{"success":..., "data"|"error":...}` 结构，而非完整 WorkflowContext
