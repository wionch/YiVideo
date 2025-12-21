## MODIFIED Requirements
### Requirement: 单任务节点分节示例
系统 SHALL 为所有支持单步任务的节点提供以代码为基准的单任务 HTTP 文档小节（涵盖 `ffmpeg.extract_keyframes/extract_audio/crop_subtitle_images/split_audio_segments`, `faster_whisper.transcribe_audio`, `audio_separator.separate_vocals`, `pyannote_audio.diarize_speakers/get_speaker_segments/validate_diarization`, `paddleocr.detect_subtitle_area/create_stitched_images/perform_ocr/postprocess_and_finalize`, `indextts.generate_speech`, `wservice.generate_subtitle_files/correct_subtitles/ai_optimize_subtitles/merge_speaker_segments/merge_with_word_timestamps/prepare_tts_segments`），并与 `/v1/tasks/supported-tasks` 返回列表一致；不支持单步任务的节点（如 `audio_separator.health_check`, `indextts.list_voice_presets`, `indextts.get_model_info`）不应出现在单任务节点清单中。每个节点小节必须在请求示例前提供功能概述，简述节点的主要能力、预期输入、核心输出/上传副作用以及适用注意事项，文字需与实现与参数/输出示例保持一致。

#### Scenario: 节点覆盖与示例内容对齐实现
- **WHEN** 文档列出支持的单任务节点或 `/v1/tasks/supported-tasks` 返回列表
- **THEN** 每个节点小节 SHALL 包含功能概述段落、请求体示例与参数表（标明必填/可选/默认值，来源于 `get_param_with_fallback`/节点代码），WorkflowContext 输出示例展示任务真实输出字段（含统计/上传信息）；`supported-tasks` 返回集合 SHALL 与文档节点清单一致且覆盖所有 Celery 任务名称

#### Scenario: 节点功能概述与实现一致
- **WHEN** 文档展示任意单任务节点小节
- **THEN** 在请求示例前出现明确的功能概述文字，描述节点目标、依赖输入/默认值、核心输出或上传行为以及适用限制；该描述 SHALL 与节点实现的参数/输出字段一致且不与 `/v1/tasks/supported-tasks` 清单矛盾
