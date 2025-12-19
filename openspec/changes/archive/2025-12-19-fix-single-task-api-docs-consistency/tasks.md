## Traceability (Research → Tasks)
- Finding 1 → 1.1
- Finding 2 → 1.2
- Finding 3 → 1.3
- Finding 4 → 1.4

## 1. Implementation

- [x] 1.1 Update paddleocr.detect_subtitle_area inputs
  - Evidence: proposal.md → Research → Finding 1 (Decision: Update docs to require keyframe_dir)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:270-290` (approx)
  - Commands:
    - `rg "paddleocr.detect_subtitle_area" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: Request body and parameter table for `paddleocr.detect_subtitle_area` show `keyframe_dir` instead of `video_path`.

- [x] 1.2 Update paddleocr.postprocess_and_finalize inputs
  - Evidence: proposal.md → Research → Finding 2 (Decision: Add video_path)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:360-380` (approx)
  - Commands:
    - `rg "paddleocr.postprocess_and_finalize" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: Request body and parameter table for `paddleocr.postprocess_and_finalize` include `video_path`.

- [x] 1.3 Update indextts.generate_speech inputs
  - Evidence: proposal.md → Research → Finding 3 (Decision: Remove voice, emphasize reference_audio)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:390-410` (approx)
  - Commands:
    - `rg "indextts.generate_speech" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: `voice` parameter is removed or marked as unsupported, and `spk_audio_prompt` is emphasized in examples.

- [x] 1.4 Update wservice.ai_optimize_subtitles inputs
  - Evidence: proposal.md → Research → Finding 4 (Decision: Update input to segments_file)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:470-490` (approx)
  - Commands:
    - `rg "wservice.ai_optimize_subtitles" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: Request body shows `segments_file` input, and parameter table reflects JSON requirement.

## 2. Validation

- [x] 2.1 OpenSpec strict validation
  - Evidence: proposal.md → Impact → Affected Specs
  - Commands:
    - `openspec validate fix-single-task-api-docs-consistency --strict`
  - Done when: command exits 0.

## 3. Self-check (ENFORCED)

- [x] 3.1 Each task touches exactly one file in Edit scope.
- [x] 3.2 Each task references exactly one Finding.
- [x] 3.3 No task contains conditional language.
- [x] 3.4 Each task includes Commands and an objective Done when.
