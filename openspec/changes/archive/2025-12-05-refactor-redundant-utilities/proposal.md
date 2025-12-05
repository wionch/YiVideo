# Change: 重构冗余工具类

## Why

当前代码库在多个区域违反了 DRY（Don't Repeat Yourself，不要重复自己）原则：
- `paddleocr_service` 拥有自己的一套较差的 `config_loader.py` 实现。
- `paddleocr_service` 重新实现了 SRT 文件写入逻辑。
- `ffmpeg_service` 有一个 `subtitle_parser.py`，它复制了 `services/common` 的逻辑。
- 像 `progress_logger.py` 这样的通用工具被隐藏在特定的服务中。

这些冗余导致了维护噩梦、不一致的行为（例如配置加载优先级）和代码腐烂。

## What Changes

- **移除** `services/workers/paddleocr_service/app/utils/config_loader.py` 并将其使用替换为 `services/common/config_loader.py`。
- **移除** `paddleocr_service/app/tasks.py` 中的 `_write_srt_file`，改用 `services/common/subtitle/subtitle_parser.py`。
- **移动** `services/workers/paddleocr_service/app/utils/progress_logger.py` 到 `services/common/utils/`。
- **合并** `services/workers/ffmpeg_service/app/modules/subtitle_parser.py` 到 `services/common/subtitle/subtitle_parser.py`（合并独特的功能）。

## Impact

- **受影响的规格**: `project-architecture`（强制执行这些模式的新能力）。
- **受影响的代码**:
    - `services/workers/paddleocr_service/`
    - `services/workers/ffmpeg_service/`
    - `services/common/`