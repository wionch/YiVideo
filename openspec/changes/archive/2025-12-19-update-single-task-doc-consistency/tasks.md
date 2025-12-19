## Traceability (Research → Tasks)
- Finding 1 → 1.1, 1.12
- Finding 2 → 1.2
- Finding 3 → 1.3, 1.4, 1.5, 1.6, 1.7
- Finding 4 → 1.8, 1.9
- Finding 5 → 1.10
- Finding 6 → 1.11

## 1. Implementation

- [x] 1.1 更新 `paddleocr.detect_subtitle_area` 文档请求与示例为 `keyframe_dir`/本地输出
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec delta)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:632-679`
  - Commands:
    - `grep -n "paddleocr.detect_subtitle_area" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 示例与参数表使用 `keyframe_dir`（支持 MinIO/本地），输出描述为本地目录并可选 `keyframe_minio_url`。

- [x] 1.2 补充 `paddleocr.postprocess_and_finalize` 所需 `video_path` 并移除未实现的上传开关
  - Evidence: proposal.md → Research → Finding 2 (Decision: Doc-only)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:805-859`
  - Commands:
    - `grep -n "postprocess_and_finalize" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 请求/参数表包含 `video_path`，示例不再宣称 `upload_final_results_to_minio`，输出保持本地 srt/json。

- [x] 1.3 将通用 `/status` 示例与 `ffmpeg.extract_audio` 描述改为本地 `audio_path`
  - Evidence: proposal.md → Research → Finding 3 (Decision: Doc-only)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:20-120`
  - Commands:
    - `grep -n "extract_audio" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md | head -n 5`
  - Done when: `/status` 示例中的 `audio_path` 为 `/share` 本地路径且不默认展示 MinIO URL。

- [x] 1.4 更新 `faster_whisper.transcribe_audio` 示例输出为本地 `segments_file`
  - Evidence: proposal.md → Research → Finding 3 (Decision: Doc-only)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:350-386`
  - Commands:
    - `grep -n "faster_whisper.transcribe_audio" -n docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: `segments_file`/统计字段示例使用 `/share` 路径，MinIO URL 仅作为可选说明。

- [x] 1.5 调整 `ffmpeg.split_audio_segments` 输出字段为本地目录/源路径
  - Evidence: proposal.md → Research → Finding 3 (Decision: Doc-only)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:240-360`
  - Commands:
    - `grep -n "split_audio_segments" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 示例显示 `/share` 路径的 `audio_segments_dir`/`audio_source`/`subtitle_source`，去除默认 MinIO URL。

- [x] 1.6 调整 `wservice.generate_subtitle_files` 输出为本地字幕文件集合
  - Evidence: proposal.md → Research → Finding 3 (Decision: Doc-only)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:928-1015`
  - Commands:
    - `grep -n "wservice.generate_subtitle_files" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 示例 `subtitle_path`/`subtitle_files`/`json_path` 使用本地 `/share` 路径且不默认给出 MinIO URL。

- [x] 1.7 明确 `paddleocr.perform_ocr` 输出本地 `ocr_results_path`，`ocr_results_minio_url` 为可选
  - Evidence: proposal.md → Research → Finding 3 (Decision: Doc-only)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:749-820`
  - Commands:
    - `grep -n "perform_ocr" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 输出示例以本地结果路径为主，并单独注明上传后才出现的 `ocr_results_minio_url`。

- [x] 1.8 将 `pyannote_audio.get_speaker_segments` 返回示例改为 `success/data` 结构
  - Evidence: proposal.md → Research → Finding 4 (Decision: Doc-only)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:532-570`
  - Commands:
    - `grep -n "get_speaker_segments" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 示例展示 `{ "success": true, "data": { ... } }` 响应，并说明不包含完整 WorkflowContext。

- [x] 1.9 将 `pyannote_audio.validate_diarization` 返回示例改为 `success/data` 结构
  - Evidence: proposal.md → Research → Finding 4 (Decision: Doc-only)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:580-630`
  - Commands:
    - `grep -n "validate_diarization" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 示例响应为 `success`/`data.validation` 结构，不再展示 WorkflowContext。

- [x] 1.10 更新 `indextts.generate_speech` 请求/返回示例，强调必填与实际返回
  - Evidence: proposal.md → Research → Finding 5 (Decision: Doc-only)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:863-925`
  - Commands:
    - `grep -n "indextts.generate_speech" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 请求标注 `spk_audio_prompt`/`output_path` 必填，说明 `voice` 未使用，返回示例为任务字典而非 WorkflowContext。

- [x] 1.11 调整 `wservice.ai_optimize_subtitles` 输入为转录 JSON + 开关，输出与实际一致
  - Evidence: proposal.md → Research → Finding 6 (Decision: Doc-only)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:1033-1090`
  - Commands:
    - `grep -n "ai_optimize_subtitles" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 请求体体现 `subtitle_optimization.enabled` 与 `segments_file`/JSON 输入，输出/状态示例与实际字段匹配。

- [x] 1.12 更新 spec delta 以覆盖节点参数/返回一致性场景
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec delta)
  - Edit scope: `openspec/changes/update-single-task-doc-consistency/specs/single-task-api-docs/spec.md:1-50`
  - Commands:
    - `grep -n "MODIFIED Requirements" -n openspec/changes/update-single-task-doc-consistency/specs/single-task-api-docs/spec.md`
  - Done when: Spec delta包含新增场景（keyframe_dir、video_path、MinIO 可选、本地输出/非 WorkflowContext 返回、AI 优化开关），格式满足 OpenSpec 校验。

## 2. Validation

- [x] 2.1 OpenSpec strict validation
  - Evidence: proposal.md → Research → Finding 1
  - Commands:
    - `openspec validate update-single-task-doc-consistency --strict`
  - Done when: 命令退出码为 0，未出现校验错误。

- [x] 2.2 Project checks
  - Evidence: proposal.md → Research → Finding 3
  - Commands:
    - `python -m compileall services/api_gateway/app`
  - Done when: 命令成功且无编译错误。

## 3. Self-check (ENFORCED)

- [x] 3.1 Each task touches exactly one file in Edit scope.
- [x] 3.2 Each task references exactly one Finding.
- [x] 3.3 No task contains conditional language (if needed/必要时/可能/按需/...).
- [x] 3.4 Each task includes Commands and an objective Done when.
