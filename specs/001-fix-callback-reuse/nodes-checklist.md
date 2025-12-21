# 单任务节点复用排查清单

来源：`docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`（行号供定位）

| 节点 | 文档位置 |
| --- | --- |
| ffmpeg.extract_keyframes | 行 124 |
| ffmpeg.extract_audio | 行 185 |
| ffmpeg.crop_subtitle_images | 行 208 |
| ffmpeg.split_audio_segments | 行 278 |
| faster_whisper.transcribe_audio | 行 368 |
| audio_separator.separate_vocals | 行 435 |
| pyannote_audio.diarize_speakers | 行 509 |
| pyannote_audio.get_speaker_segments | 行 573 |
| pyannote_audio.validate_diarization | 行 606 |
| paddleocr.detect_subtitle_area | 行 644 |
| paddleocr.create_stitched_images | 行 705 |
| paddleocr.perform_ocr | 行 774 |
| paddleocr.postprocess_and_finalize | 行 831 |
| indextts.generate_speech | 行 892 |
| wservice.generate_subtitle_files | 行 940 |
| wservice.correct_subtitles | 行 999 |
| wservice.ai_optimize_subtitles | 行 1048 |
| wservice.merge_speaker_segments | 行 1124 |
| wservice.merge_with_word_timestamps | 行 1186 |
| wservice.prepare_tts_segments | 行 1249 |
