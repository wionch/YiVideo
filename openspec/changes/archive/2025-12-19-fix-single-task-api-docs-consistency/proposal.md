# Change: Fix Single Task API Docs Consistency

## Why
Current API documentation (`SINGLE_TASK_API_REFERENCE.md`) contains discrepancies against the actual codebase implementation, specifically for `paddleocr`, `indextts`, and `wservice` tasks. Incorrect parameter names and input requirements confuse developers and lead to integration failures.

## Research

### What was inspected
- **Docs**: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
- **Code**:
  - `services/workers/ffmpeg_service/app/tasks.py`
  - `services/workers/faster_whisper_service/app/tasks.py`
  - `services/workers/audio_separator_service/app/tasks.py`
  - `services/workers/pyannote_audio_service/app/tasks.py`
  - `services/workers/paddleocr_service/app/tasks.py`
  - `services/workers/indextts_service/app/tasks.py`
  - `services/workers/wservice/app/tasks.py`

### Findings

- **Finding 1: `paddleocr.detect_subtitle_area` Input Mismatch**
  - **Evidence**:
    - Doc: Shows `input_data: { "video_path": "..." }`
    - Code (`paddleocr_service/app/tasks.py:108`): `keyframe_dir = get_param_with_fallback("keyframe_dir", ...)`
    - Code logic: Requires `keyframe_dir` (either from params or upstream). Does NOT accept `video_path` to perform extraction itself.
  - **Decision**: Update docs to require `keyframe_dir` in Single Task mode or clarify dependency on `extract_keyframes`.

- **Finding 2: `paddleocr.postprocess_and_finalize` Missing Required Parameter**
  - **Evidence**:
    - Doc: Shows only `ocr_results_file`, `manifest_file`.
    - Code (`paddleocr_service/app/tasks.py:657`): `video_path = get_param_with_fallback("video_path", ...)` followed by `if not video_path: raise ValueError(...)`. Used for `_get_video_fps`.
  - **Decision**: Add `video_path` to documentation request body.

- **Finding 3: `indextts.generate_speech` Parameter Confusion**
  - **Evidence**:
    - Doc: Shows `"voice": "zh_female_1"`.
    - Code (`indextts_service/app/tasks.py:126`): Logic relies on `reference_audio` (or `spk_audio_prompt`). No explicit `voice` parameter mapping found in this task version (IndexTTS2).
  - **Decision**: Remove `voice` from example, emphasize `spk_audio_prompt` / `reference_audio`.

- **Finding 4: `wservice.ai_optimize_subtitles` Input Mismatch**
  - **Evidence**:
    - Doc: Shows `subtitle_path` (SRT file) as input.
    - Code (`wservice/app/tasks.py:688`): Uses `segments_file` (JSON Transcribe Result) via `SubtitleOptimizer`.
  - **Decision**: Update input parameter to `segments_file` and description.

## What Changes
- Update `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md` to reflect actual code behavior.
- Correct Input/Output examples for affected nodes.
- Update Parameter tables.

## Impact
- **Affected Specs**: `single-task-api-docs` (Refined requirement for accuracy).
- **Affected Docs**: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
- **Risk**: Low (Documentation only).
