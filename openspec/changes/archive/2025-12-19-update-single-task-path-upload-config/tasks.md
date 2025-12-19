## Traceability (Research → Tasks)
- Finding 1 → 1.1, 1.2
- Finding 2 → 1.3, 1.4, 1.5
- Finding 3 → 1.6
- Finding 4 → 1.7
- Finding 5 → 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.14, 1.15, 1.16, 1.17, 1.18

## 1. Implementation

- [x] 1.1 为自动上传新增全局开关
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Code+Spec)
  - Edit scope: `config.yml:1-120`
  - Commands:
    - `grep -n "auto_upload_to_minio" config.yml`
  - Done when: 配置文件包含 `core.auto_upload_to_minio`（默认 true）及说明注释，grep 输出命中新增开关键值。

- [x] 1.2 state_manager 读取开关控制上传
  - Evidence: proposal.md → Research → Finding 5 (Decision: Doc+Code+Spec)
  - Edit scope: `services/common/state_manager.py:59-320`
  - Commands:
    - `python -m compileall services/common/state_manager.py`
  - Done when: `_upload_files_to_minio` 仅在 `core.auto_upload_to_minio` 为 true 时执行，上传时保留本地字段并将远程 URL 写入 `*_minio_url`/`minio_files` 等专用字段；编译通过且不影响其他逻辑。

- [x] 1.3 更新 `ffmpeg.extract_audio` 输出示例为本地+可选远程
  - Evidence: proposal.md → Research → Finding 2 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:162-185`
  - Commands:
    - `grep -n "ffmpeg.extract_audio" -C2 docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 该段输出包含本地音频路径和“上传开启时的 MinIO URL”描述，且声明依赖 `core.auto_upload_to_minio`/节点上传参数。

- [x] 1.4 更新 `ffmpeg.split_audio_segments` 输出示例为本地+可选远程
  - Evidence: proposal.md → Research → Finding 2 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:240-310`
  - Commands:
    - `grep -n "ffmpeg.split_audio_segments" -A30 docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 输出字段显示本地分段目录/文件且增加远程 URL 说明仅在上传开启时返回。

- [x] 1.5 更新 `faster_whisper.transcribe_audio` 输出示例为本地+可选远程
  - Evidence: proposal.md → Research → Finding 2 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:324-382`
  - Commands:
    - `grep -n "faster_whisper.transcribe_audio" -A30 docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 输出示例包含本地 `segments_file` 与可选远程 URL/说明，明确依赖上传开关。

- [x] 1.6 更新 `pyannote_audio.diarize_speakers` 输出示例为本地+可选远程
  - Evidence: proposal.md → Research → Finding 3 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:464-520`
  - Commands:
    - `grep -n "pyannote_audio.diarize_speakers" -A30 docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 输出同时展示本地 `diarization_file` 与可选 `diarization_file_minio_url`，并标注依赖上传开关。

- [x] 1.7 更新 `wservice.correct_subtitles` 输出示例为本地+可选远程
  - Evidence: proposal.md → Research → Finding 4 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:934-980`
  - Commands:
    - `grep -n "wservice.correct_subtitles" -A20 docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 输出示例显示本地 `corrected_subtitle_path` 并仅将远程 URL 作为“上传开启时返回”的可选项。

- [x] 1.8 更新 `audio_separator.separate_vocals` 输出示例为本地+可选远程
  - Evidence: proposal.md → Research → Finding 5 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:390-452`
  - Commands:
    - `grep -n "audio_separator.separate_vocals" -A40 docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 输出保留本地轨迹字段，并将 MinIO URL 置于 `*_minio_url`/`minio_files` 可选字段，标注依赖上传开关。

- [x] 1.9 更新 `paddleocr.detect_subtitle_area` 输出示例（本地+可选远程）
  - Evidence: proposal.md → Research → Finding 5 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:596-640`
  - Commands:
    - `grep -n "paddleocr.detect_subtitle_area" -A30 docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 输出/说明区分本地 `keyframe_dir` 与可选远程 URL，标注依赖上传开关。

- [x] 1.10 更新 `paddleocr.create_stitched_images` 输出示例（本地+可选远程）
  - Evidence: proposal.md → Research → Finding 5 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:647-705`
  - Commands:
    - `grep -n "paddleocr.create_stitched_images" -A40 docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 输出包含本地 `multi_frames_path/manifest_path`，远程 URL 使用 `*_minio_url` 专用字段并说明上传开关。

- [x] 1.11 更新 `paddleocr.perform_ocr` 输出示例（本地+可选远程）
  - Evidence: proposal.md → Research → Finding 5 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:715-772`
  - Commands:
    - `grep -n "paddleocr.perform_ocr" -A40 docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 输出显示本地 `ocr_results_path`，远程字段为可选 `ocr_results_minio_url`，注明上传开关。

- [x] 1.12 更新 `paddleocr.postprocess_and_finalize` 输出示例（本地+可选远程）
  - Evidence: proposal.md → Research → Finding 5 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:772-827`
  - Commands:
    - `grep -n "paddleocr.postprocess_and_finalize" -A30 docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 输出保留本地结果文件，远程 URL 如有以专用字段呈现，并标注依赖上传开关。

- [x] 1.13 更新 `indextts.generate_speech` 输出示例（本地+可选远程）
  - Evidence: proposal.md → Research → Finding 5 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:828-874`
  - Commands:
    - `grep -n "indextts.generate_speech" -A30 docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 输出保留本地 `output_path`，远程 URL 仅以可选字段呈现并注明依赖开关。

- [x] 1.14 更新 `wservice.generate_subtitle_files` 输出示例（本地+可选远程）
  - Evidence: proposal.md → Research → Finding 5 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:876-934`
  - Commands:
    - `grep -n "wservice.generate_subtitle_files" -A40 docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 输出保留本地字幕文件路径，远程 URL 若有使用专用字段并标注开关。

- [x] 1.15 更新 `wservice.ai_optimize_subtitles` 输出示例（本地+可选远程）
  - Evidence: proposal.md → Research → Finding 5 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:981-1056`
  - Commands:
    - `grep -n "wservice.ai_optimize_subtitles" -A40 docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 输出显示本地路径，远程 URL 仅作为可选字段并注明依赖开关。

- [x] 1.16 更新 `wservice.merge_speaker_segments` 输出示例（本地+可选远程）
  - Evidence: proposal.md → Research → Finding 5 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:1056-1108`
  - Commands:
    - `grep -n "wservice.merge_speaker_segments" -A40 docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 输出保持本地输入/输出字段，远程字段如有以专用字段呈现并标注开关。

- [x] 1.17 更新 `wservice.merge_with_word_timestamps` 输出示例（本地+可选远程）
  - Evidence: proposal.md → Research → Finding 5 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:1110-1178`
  - Commands:
    - `grep -n "wservice.merge_with_word_timestamps" -A40 docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 输出保持本地字段，远程字段如有以专用字段呈现并标注开关。

- [x] 1.18 更新 `wservice.prepare_tts_segments` 输出示例（本地+可选远程）
  - Evidence: proposal.md → Research → Finding 5 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:1180-1228`
  - Commands:
    - `grep -n "wservice.prepare_tts_segments" -A30 docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 输出保持本地字段，远程字段如有以专用字段呈现并标注开关。

## 2. Validation

- [x] 2.1 OpenSpec strict validation
  - Evidence: proposal.md → Research → Finding 1
  - Commands:
    - `openspec validate update-single-task-path-upload-config --strict`
  - Done when: 命令退出码为 0。

- [x] 2.2 Project checks
  - Evidence: proposal.md → Research → Findings 1-4
  - Commands:
    - `pytest tests`
  - Done when: 所有命令通过且无新增警告/失败。

## 3. Self-check (ENFORCED)

- [x] 3.1 Each task touches exactly one file in Edit scope.
- [x] 3.2 Each task references exactly one Finding.
- [x] 3.3 No task contains conditional language (if needed/必要时/可能/按需/...).
- [x] 3.4 Each task includes Commands and an objective Done when.
