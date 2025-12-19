# Change: 对单任务API文档与代码输出的校准

## Why
当前 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md` 中多处请求体/WorkflowContext 示例与实现不符（参数名称、返回结构、是否上传到 MinIO 等），已偏离实际行为，易导致集成方按错误字段调用。

## Research (REQUIRED)
### What was inspected
- Specs:
  - `openspec/specs/single-task-api-docs/spec.md`（现有要求：文档需与模型/序列化一致，节点示例需与支持任务列表对应）
- Docs:
  - `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:1-1600`（各节点请求体与 WorkflowContext 示例）
- Code:
  - `services/workers/ffmpeg_service/app/tasks.py:275-425`（`ffmpeg.extract_audio` 仅写本地 `audio_path`，无 MinIO 上传）
  - `services/workers/ffmpeg_service/app/tasks.py:760-1027`（`ffmpeg.split_audio_segments` 输出本地目录/源路径，不生成 MinIO URL）
  - `services/workers/faster_whisper_service/app/tasks.py:440-673`（`faster_whisper.transcribe_audio` 输出 `segments_file` 为本地 `/share` 路径）
  - `services/workers/paddleocr_service/app/tasks.py:88-370`（`paddleocr.detect_subtitle_area` 需要 `keyframe_dir`/上游抽帧目录，未消费 `video_path`）
  - `services/workers/paddleocr_service/app/tasks.py:1014-1133`（`paddleocr.postprocess_and_finalize` 必需 `video_path` 获取 FPS，未实现 MinIO 上传）
  - `services/workers/paddleocr_service/app/tasks.py:694-1012`（`paddleocr.perform_ocr` 输出 `ocr_results_path` 本地路径，上传时额外返回 `ocr_results_minio_url`）
  - `services/workers/pyannote_audio_service/app/tasks.py:365-624`（`get_speaker_segments`/`validate_diarization` 返回 `success/data` 字典且不写入 WorkflowContext）
  - `services/workers/indextts_service/app/tasks.py:106-337`（`indextts.generate_speech` 返回普通 dict、不更新 WorkflowContext，强制要求 `spk_audio_prompt`/`output_path`）
  - `services/workers/wservice/app/tasks.py:1030-1181`（`wservice.ai_optimize_subtitles` 受 `subtitle_optimization.enabled` 开关控制，读取 `segments_file`/转录 JSON 而非 SRT）
- Commands:
  - `openspec list`, `openspec list --specs`（确认无进行中的 change，定位相关 spec）

### Findings (with evidence)
- Finding 1: `paddleocr.detect_subtitle_area` 请求应传 `keyframe_dir`（或依赖上游 `ffmpeg.extract_keyframes` 输出），当前文档使用 `video_path` 示例，易导致必填参数缺失。
  - Evidence: 文档 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:632-679` 请求/示例使用 `video_path`; 代码 `services/workers/paddleocr_service/app/tasks.py:132-192` 通过 `get_param_with_fallback('keyframe_dir', ..., fallback_from_stage='ffmpeg.extract_keyframes')` 解析目录，未读取 `video_path`。
  - Decision: Doc+Spec delta（更新文档与 `single-task-api-docs` 场景），突出 `keyframe_dir`/可下载 MinIO 目录。
- Finding 2: `paddleocr.postprocess_and_finalize` 实际需要 `video_path` 计算 FPS，且未实现 `upload_final_results_to_minio`；文档缺少 video_path 并宣称上传。
  - Evidence: 文档 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:805-859` 请求体仅含 `ocr_results_file`/`manifest_file` 与上传开关；代码 `services/workers/paddleocr_service/app/tasks.py:1053-1086` 通过 `get_param_with_fallback("video_path")` 校验，未调用 MinIO 上传。
  - Decision: Doc-only 更新请求体/参数表/示例，添加 `video_path`、移除未实现的上传开关。
- Finding 3: 多个节点示例使用 MinIO URL，但实现仅返回本地 `/share` 路径（无自动上传）。
  - Evidence: `ffmpeg.extract_audio` 输出只有本地 `audio_path`（tasks.py:275-425）；`ffmpeg.split_audio_segments` 输出本地 `audio_segments_dir`/源路径（tasks.py:760-1027）；`faster_whisper.transcribe_audio` 输出 `segments_file` 本地路径（tasks.py:440-673）。文档示例分别在 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:1-120`（通用 `/status` 示例）、`200-340`（ffmpeg 段）、`350-386`（faster_whisper 段）展示 MinIO URL。
  - Decision: Doc-only 将相关输出字段改为本地路径描述，并仅在实际上传字段存在时展示可选 MinIO URL。
- Finding 4: `pyannote_audio.get_speaker_segments` 与 `pyannote_audio.validate_diarization` 返回 `{"success":..., "data":...}` 简单结果且未更新 WorkflowContext，文档当前展示完整 WorkflowContext 示例。
  - Evidence: 文档 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:520-620` 与 `680-760` 展示 WorkflowContext；代码 `services/workers/pyannote_audio_service/app/tasks.py:365-624` 返回简单 dict，未调用 `state_manager.update_workflow_state`。
  - Decision: Doc-only 改为 TaskStatusResponse/结果载荷示例，标注返回结构。
- Finding 5: `indextts.generate_speech` 返回普通 dict（不写 WorkflowContext），且 `spk_audio_prompt`/`output_path` 必填、`voice` 参数未被消费；文档展示 WorkflowContext 并将 `voice` 作为主要输入。
  - Evidence: 文档 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:863-925`; 代码 `services/workers/indextts_service/app/tasks.py:106-337` 校验 `spk_audio_prompt`/`output_path`，直接返回 dict，无 `state_manager.update_workflow_state`，未使用 `voice`。
  - Decision: Doc-only 更新请求/返回示例为实际字段，说明必填/未使用字段。
- Finding 6: `wservice.ai_optimize_subtitles` 依赖 `subtitle_optimization.enabled` 与 `segments_file`（转录 JSON）输入，当前文档以 SRT `subtitle_path` 为必填并未提及开关。
  - Evidence: 文档 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:1033-1090` 请求体/示例均为 SRT；代码 `services/workers/wservice/app/tasks.py:1030-1181` 读取 `subtitle_optimization` 配置并要求 `segments_file` / 转录 JSON，缺失开关则直接 `SKIPPED`。
  - Decision: Doc-only 更新请求参数与返回示例，强调开关与 JSON 输入。

### Why this approach (KISS/YAGNI check)
- 优先修正文档以反映现有实现，避免引入上传/状态持久化等新逻辑。
- 不修改任务实现或引入新上传流程，避免超出需求的工程改动。
- 非目标：不调整 Celery 任务行为或添加新的回调/存储特性；不修改配置/部署流程。

## What Changes
- 更新 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md` 中各节点请求体与 WorkflowContext/结果示例，使之与当前实现的输入解析和输出字段一致（重点：PaddleOCR、ffmpeg、faster_whisper、pyannote、indextts、wservice）。
- 在 `openspec/changes/update-single-task-doc-consistency/specs/single-task-api-docs/spec.md` 对节点示例一致性要求补充具体场景，覆盖上述差异。

## Impact
- Affected specs:
  - `single-task-api-docs`（MODIFIED Requirements：节点示例参数/输出一致性细化）
- Affected docs:
  - `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
- Risks: 主要为文档改动，无代码运行风险；需确保行文与真实字段完全对应，避免遗漏本地路径/开关描述。
