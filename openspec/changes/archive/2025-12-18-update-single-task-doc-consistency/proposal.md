# Change: 对齐单任务 API 文档与节点/代码实际行为

## Why
单任务 API 文档的节点覆盖与示例存在缺口，部分节点未在 API 文档中出现，且个别示例与实际任务参数/输出不一致，导致使用方无法依据文档正确调用。

## Research (REQUIRED)
记录用于支撑决策的证据。

### What was inspected
- Specs: `openspec/specs/single-task-api-docs/spec.md`
- Docs: `docs/technical/reference/WORKFLOW_NODES_REFERENCE.md`, `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
- Code: `services/api_gateway/app/single_task_api.py`, `services/api_gateway/app/single_task_models.py`, `services/api_gateway/app/single_task_executor.py`, `services/workers/*/tasks.py`

### Findings (with evidence)
- Finding 1: API 文档未覆盖多个已实现且支持单步任务的节点，`/v1/tasks/supported-tasks` 也只暴露了子集。
  - Evidence: 支持单步任务且签名为 `def task(self, context: dict)` 的节点包括 `pyannote_audio.get_speaker_segments`/`validate_diarization`(docs/technical/reference/WORKFLOW_NODES_REFERENCE.md:1262-1450)、`paddleocr.postprocess_and_finalize`(docs/technical/reference/WORKFLOW_NODES_REFERENCE.md:1942-2004)、`wservice.merge_speaker_segments`/`merge_with_word_timestamps`/`prepare_tts_segments`(services/workers/wservice/app/tasks.py:708-815, 818-999, 1233-1286)，以及已存在的 ffmpeg/faster_whisper/audio_separator.separate_vocals/pyannote_audio.diarize_speakers/paddleocr.detect_subtitle_area/create_stitched_images/perform_ocr/indextts.generate_speech/wservice.generate_subtitle_files/correct_subtitles/ai_optimize_subtitles。API 文档仅包含子集且缺少上述节点（docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:389-694）；`/supported-tasks` 返回列表也缺少这些节点并遗漏 `paddleocr.create_stitched_images`(services/api_gateway/app/single_task_api.py:315-343)。
  - Evidence (not supported for single-task): `audio_separator.health_check`(services/workers/audio_separator_service/app/tasks.py:376-393) 和 `indextts.list_voice_presets`/`indextts.get_model_info`(services/workers/indextts_service/app/tasks.py:341-380, 381-395) 函数签名缺少 `context`，直接接受单步任务会 TypeError。
  - Decision: 仅补充支持单步任务的节点到 API 文档与 `/supported-tasks`，明确排除当前不支持的节点（`audio_separator.health_check`, `indextts.list_voice_presets`, `indextts.get_model_info`）。
- Finding 2: `paddleocr.perform_ocr` 的请求体与输出示例与实现不一致。
  - Evidence: 文档示例仍使用 `cropped_images_path`/`subtitle_area` 并输出 `subtitle_path`/`ocr_json_path`(docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:642-688)；实际任务要求 `manifest_path`/`multi_frames_path` 并产出 `ocr_results_path`/`ocr_results_minio_url`(services/workers/paddleocr_service/app/tasks.py:700-777, 920-934)；节点文档已描述新参数/输出( docs/technical/reference/WORKFLOW_NODES_REFERENCE.md:1865-1920)。
  - Decision: 更新 API 文档中该节点的请求体、WorkflowContext 示例与参数表，改为 manifest/multi_frames + ocr_results 产出。
- Finding 3: `/v1/tasks/{task_id}/status` 示例字段与模型不一致，导致文档字段无法在响应中出现。
  - Evidence: 状态模型使用 `created_at` 字段(services/api_gateway/app/single_task_models.py:38-47)；执行器上下文记录的是 `create_at` 并返回给响应(services/api_gateway/app/single_task_executor.py:196-222)；文档示例使用 `create_at`(docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:33-72)，但 Pydantic 会忽略该字段，实际响应缺失创建时间。
  - Decision: 统一模型与文档字段，确保创建时间字段在响应中保留（倾向新增/接受 `create_at`），并同步示例。

### Why this approach (KISS/YAGNI check)
- 仅修正文档与现有实现的不一致，不引入新流程或抽象。
- 节点覆盖直接对齐已存在的 Celery 任务，避免重复定义。
- 改动集中在文档与少量网关模型/路由，保持最小影响面。

## What Changes
- 扩充单任务 API 文档，补全缺失节点并对齐节点文档/代码。
- 调整 `paddleocr.perform_ocr` 单任务示例以匹配现有参数和输出。
- 统一状态响应的创建时间字段，使文档、模型与执行器一致。
- 更新 `single-task-api-docs` 规格要求与 `/supported-tasks` 展示列表。

## Impact
- Affected specs: `single-task-api-docs`（MODIFIED）
- Affected docs: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
- Affected code: `services/api_gateway/app/single_task_api.py`, `services/api_gateway/app/single_task_models.py`（视字段统一方案而定）
- Rollout risks: 文档/模型字段变更需确认下游解析器兼容性
