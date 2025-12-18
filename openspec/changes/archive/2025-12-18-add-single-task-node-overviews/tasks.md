## Traceability (Research → Tasks)
- Finding 1 → 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.14, 1.15, 1.16, 1.17, 1.18, 1.19, 1.20, 1.21, 2.2
- Finding 2 → 1.1, 2.1

## 1. Implementation

- [x] 1.1 更新单任务节点规范以包含功能概述要求
  - Evidence: proposal.md → Research → Finding 2 (Decision: Spec delta)
  - Edit scope: `openspec/changes/add-single-task-node-overviews/specs/single-task-api-docs/spec.md:1-40`
  - Commands:
    - `grep -n "功能概述" openspec/changes/add-single-task-node-overviews/specs/single-task-api-docs/spec.md`
  - Done when: 命令输出展示 MODIFIED requirement 包含在请求示例前要求功能概述的文字。

- [x] 1.2 为 ffmpeg.extract_keyframes 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:100-159`
  - Commands:
    - `grep -n "功能概述.*ffmpeg.extract_keyframes" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示在请求体前新增的功能概述段落，说明关键帧提取目的、输入要求与输出目录/压缩信息。

- [x] 1.3 为 ffmpeg.extract_audio 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:161-168`
  - Commands:
    - `grep -n "功能概述.*ffmpeg.extract_audio" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示在请求体前新增的功能概述段落，描述音频抽取用途、输入视频要求与输出音频文件。

- [x] 1.4 为 ffmpeg.crop_subtitle_images 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:169-236`
  - Commands:
    - `grep -n "功能概述.*ffmpeg.crop_subtitle_images" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示功能概述段落，说明字幕区域裁剪作用、输入字幕框限制及上传/压缩副作用。

- [x] 1.5 为 ffmpeg.split_audio_segments 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:237-324`
  - Commands:
    - `grep -n "功能概述.*ffmpeg.split_audio_segments" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示功能概述段落，说明按字幕/说话人切分音频的目的、输入依赖及输出片段目录。

- [x] 1.6 为 faster_whisper.transcribe_audio 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:327-389`
  - Commands:
    - `grep -n "功能概述.*faster_whisper.transcribe_audio" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示功能概述段落，说明语音转文字目的、输入音频要求与输出段落/统计信息。

- [x] 1.7 为 audio_separator.separate_vocals 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:391-461`
  - Commands:
    - `grep -n "功能概述.*audio_separator.separate_vocals" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示功能概述段落，描述人声/伴奏分离目的、输入音频要求与输出路径或上传行为。

- [x] 1.8 为 pyannote_audio.diarize_speakers 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:463-525`
  - Commands:
    - `grep -n "功能概述.*pyannote_audio.diarize_speakers" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示功能概述段落，说明说话人分离目标、输入音频限制与输出分段/统计。

- [x] 1.9 为 pyannote_audio.get_speaker_segments 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:525-572`
  - Commands:
    - `grep -n "功能概述.*pyannote_audio.get_speaker_segments" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示功能概述段落，描述基于分离结果生成分段的用途、输入/输出格式。

- [x] 1.10 为 pyannote_audio.validate_diarization 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:572-621`
  - Commands:
    - `grep -n "功能概述.*pyannote_audio.validate_diarization" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示功能概述段落，说明校验分离结果的目的、输入依赖与输出评分/统计。

- [x] 1.11 为 paddleocr.detect_subtitle_area 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:623-671`
  - Commands:
    - `grep -n "功能概述.*paddleocr.detect_subtitle_area" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示功能概述段落，说明字幕区域检测目的、输入帧/视频要求与输出坐标/置信度。

- [x] 1.12 为 paddleocr.create_stitched_images 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:671-738`
  - Commands:
    - `grep -n "功能概述.*paddleocr.create_stitched_images" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示功能概述段落，描述字幕区域拼图目的、输入/输出目录与上传行为。

- [x] 1.13 为 paddleocr.perform_ocr 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:738-793`
  - Commands:
    - `grep -n "功能概述.*paddleocr.perform_ocr" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示功能概述段落，说明字幕 OCR 识别目标、输入图片来源与输出文本/统计。

- [x] 1.14 为 paddleocr.postprocess_and_finalize 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:793-848`
  - Commands:
    - `grep -n "功能概述.*paddleocr.postprocess_and_finalize" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示功能概述段落，描述字幕后处理/对齐输出与上传信息。

- [x] 1.15 为 indextts.generate_speech 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:850-912`
  - Commands:
    - `grep -n "功能概述.*indextts.generate_speech" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示功能概述段落，说明文本转语音用途、输入文本/音色选择与输出音频/上传。

- [x] 1.16 为 wservice.generate_subtitle_files 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:914-971`
  - Commands:
    - `grep -n "功能概述.*wservice.generate_subtitle_files" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示功能概述段落，描述生成字幕文件的目标、输入依赖与输出文件/上传。

- [x] 1.17 为 wservice.correct_subtitles 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:971-1017`
  - Commands:
    - `grep -n "功能概述.*wservice.correct_subtitles" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示功能概述段落，描述字幕纠错/修订的用途、输入字幕要求与输出更新版本。

- [x] 1.18 为 wservice.ai_optimize_subtitles 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:1017-1063`
  - Commands:
    - `grep -n "功能概述.*wservice.ai_optimize_subtitles" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示功能概述段落，说明 AI 优化字幕的目标、输入限制与输出质量改进点。

- [x] 1.19 为 wservice.merge_speaker_segments 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:1063-1123`
  - Commands:
    - `grep -n "功能概述.*wservice.merge_speaker_segments" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示功能概述段落，描述按说话人合并片段的目的、输入依赖与输出合并结果。

- [x] 1.20 为 wservice.merge_with_word_timestamps 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:1123-1184`
  - Commands:
    - `grep -n "功能概述.*wservice.merge_with_word_timestamps" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示功能概述段落，说明按词级时间戳合并字幕/音频的目标与输出格式。

- [x] 1.21 为 wservice.prepare_tts_segments 节点添加功能概述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:1184-1240`
  - Commands:
    - `grep -n "功能概述.*wservice.prepare_tts_segments" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 命令输出显示功能概述段落，描述 TTS 片段准备的目的、输入字幕要求与输出片段/上传路径。

## 2. Validation

- [x] 2.1 OpenSpec strict validation
  - Evidence: proposal.md → Research → Finding 2 (Decision: Spec delta)
  - Commands:
    - `openspec validate add-single-task-node-overviews --strict`
  - Done when: 命令退出码为 0，确认变更的 spec 与文档 delta 通过严格校验。

- [x] 2.2 项目基础检查（确保文档改动未破坏 Python 语法引用）
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Spec)
  - Commands:
    - `python -m compileall services`
  - Done when: 命令成功完成且无新的语法错误输出。

## 3. Self-check (ENFORCED)

- [x] 3.1 Each task touches exactly one file in Edit scope.
- [x] 3.2 Each task references exactly one Finding.
- [x] 3.3 No task contains conditional language (if needed/必要时/可能/按需/...).
- [x] 3.4 Each task includes Commands and an objective Done when.
