## 1. 重构 `paddleocr_service` 中的 `config_loader`

- [ ] 1.1. 识别 `services/workers/paddleocr_service/` 目录下所有导入并使用本地 `config_loader.py` 的文件。
- [ ] 1.2. 修改这些文件，使其从 `services.common.config_loader` 导入 `get_config`。
- [ ] 1.3. 将对本地函数的调用（例如 `get_config_section("paddleocr_config")`）替换为使用通用加载器的等效调用（例如 `get_config().get("paddleocr_config", {})`）。
- [ ] 1.4. 运行 `paddleocr_service` 的单元测试和集成测试，确保功能没有发生变化。
- [ ] 1.5. 删除冗余文件：`services/workers/paddleocr_service/app/utils/config_loader.py`。

## 2. 重构 `ffmpeg_service` 中的 `subtitle_parser`

- [ ] 2.1. 识别 `services/workers/ffmpeg_service/` 目录下所有导入并使用本地 `subtitle_parser.py` 的文件。
- [ ] 2.2. **功能合并**：将 `ffmpeg_service` 解析器中处理多种格式（特别是带说话人标签的 SRT 和 JSON）的能力，合并到 `common/subtitle/subtitle_parser.py` 中。
  - [ ] 2.2.1. 统一数据模型：弃用 `SubtitleSegment` 类，全面使用更丰富的 `SubtitleEntry` 类。将 `speaker`、`confidence`、`words` 等缺失的字段添加到 `SubtitleEntry` 中。
  - [ ] 2.2.2. 将 `parse_speaker_srt_file` 的逻辑移植到 `common.SRTParser` 中。
  - [ ] 2.2.3. 将 `parse_subtitle_json_file` 的逻辑移植到 `common.SRTParser` 中。
  - [ ] 2.2.4. 在 `common.SRTParser` 中创建一个新的、统一的 `parse_file` 方法，该方法能自动检测文件格式（标准 SRT、带说话人的 SRT、JSON）并调用相应的内部解析方法。
- [ ] 2.3. 修改步骤 2.1 中识别出的文件，使其从 `services.common.subtitle.subtitle_parser` 导入 `SRTParser`。
- [ ] 2.4. 将所有对本地解析器的调用替换为对功能增强后的通用 `SRTParser` 的调用。
- [ ] 2.5. 运行 `ffmpeg_service` 的单元测试和集成测试，确保功能没有发生变化。
- [ ] 2.6. 删除冗余文件：`services/workers/ffmpeg_service/app/modules/subtitle_parser.py`。

## 3. 验证

- [ ] 3.1. 运行所有项目范围的集成测试和端到端测试，确认重构没有引入任何功能退化。
- [ ] 3.2. 手动触发一个同时涉及 `paddleocr_service` 和 `ffmpeg_service` 的工作流，以验证真实场景下的行为。
