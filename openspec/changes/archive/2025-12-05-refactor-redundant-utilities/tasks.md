## 1. PaddleOCR Service Cleanup

- [x] 1.1 Replace local `config_loader` imports in `paddleocr_service` with `services.common.config_loader`.
- [x] 1.2 Delete `services/workers/paddleocr_service/app/utils/config_loader.py`.
- [x] 1.3 Refactor `detect_subtitle_area` and `postprocess_and_finalize` in `tasks.py` to use `services.common.subtitle.subtitle_parser` instead of local helpers.
- [x] 1.4 Move `services/workers/paddleocr_service/app/utils/progress_logger.py` to `services/common/progress_logger.py` (or `utils/`).

## 2. FFmpeg Service Cleanup

- [x] 2.1 Analyze unique features in `services/workers/ffmpeg_service/app/modules/subtitle_parser.py`.
- [x] 2.2 Merge unique features (like `SubtitleSegment` dataclass if needed) into `services/common/subtitle/subtitle_parser.py`.
- [x] 2.3 Update `ffmpeg_service` to use the common `subtitle_parser`.
- [x] 2.4 Delete `services/workers/ffmpeg_service/app/modules/subtitle_parser.py`.

## 3. Verification

- [x] 3.1 Run unit tests for `paddleocr_service`.
- [x] 3.2 Run unit tests for `ffmpeg_service`.
- [x] 3.3 Verify standard workflow execution.
