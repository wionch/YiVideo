# 变更：重构以移除冗余代码

## 为何变更
在近期的代码分析中，我们发现了两处严重的代码冗余实例。这些冗余增加了维护成本，并导致了系统内的不一致性。本次重构旨在通过将共享功能集中到 `common` 模块来消除这些重复逻辑，严格遵循 DRY（Don't Repeat Yourself）原则。

## 变更内容
- **移除冗余的配置加载器**：位于 `services/workers/paddleocr_service/app/utils/config_loader.py` 的配置加载逻辑将被移除。所有相关调用将重定向至 `services/common/config_loader.py` 中更健壮、更集中的加载器。
- **整合字幕解析器**：位于 `services/workers/ffmpeg_service/app/modules/subtitle_parser.py` 的字幕解析功能将被移除。我们将转而使用 `services/common/subtitle/subtitle_parser.py` 中功能更丰富、更强大的解析器。同时，`ffmpeg_service` 解析器中处理多种格式的能力将被合并到通用的解析器中。

## 影响范围
- **受影响的规约 (Specs)**：`config`, `subtitle`。
- **受影响的代码**:
  - `services/workers/paddleocr_service/**`: 所有当前从本地 `config_loader` 导入的文件都将被更新。
  - `services/workers/ffmpeg_service/**`: 所有使用本地 `subtitle_parser` 的文件都将被更新，以使用通用版本。
  - `services/common/subtitle/subtitle_parser.py`: 将被更新，以包含处理多种字幕格式的能力。
