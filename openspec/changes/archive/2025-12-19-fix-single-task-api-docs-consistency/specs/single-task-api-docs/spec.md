## MODIFIED Requirements
### Requirement: 单任务节点分节示例
系统 SHALL 为所有支持单步任务的节点提供以代码为基准的单任务 HTTP 文档小节（涵盖 `ffmpeg`, `faster_whisper`, `audio_separator`, `pyannote_audio`, `paddleocr`, `indextts`, `wservice` 系列），并与 `/v1/tasks/supported-tasks` 返回列表一致。

#### Scenario: 节点参数准确性验证
- **WHEN** 文档展示 `paddleocr.detect_subtitle_area`
- **THEN** 必须列出 `keyframe_dir` 为输入参数（非 `video_path`）
- **WHEN** 文档展示 `paddleocr.postprocess_and_finalize`
- **THEN** 必须列出 `video_path` 为必需参数（用于FPS计算）
- **WHEN** 文档展示 `indextts.generate_speech`
- **THEN** 必须列出 `reference_audio` 或 `spk_audio_prompt` 为必需参数，移除不支持的 `voice` 参数
- **WHEN** 文档展示 `wservice.ai_optimize_subtitles`
- **THEN** 必须列出 `segments_file` 为输入参数（JSON格式），而非 SRT 文件
