# Design: 工具类重构

## Context

项目中存在配置加载和字幕解析的代码重复问题。本次重构旨在将这些代码统一整合到 `services/common` 中。

## Decisions

### 1. 字幕解析器整合

我们将增强 `services.common.subtitle.subtitle_parser.SubtitleEntry` 以支持目前仅在 `ffmpeg_service` 实现中存在的功能：
- 添加 `confidence` (float, 可选) 字段。
- 添加 `words` (List[Dict], 可选) 字段用于词级时间戳。
- 添加别名 `id` 属性指向 `index`（或者将 `index` 重命名为 `id` 以匹配 `ffmpeg_service`，但 `index` 对于 SRT 更标准）。我们将保留 `index` 并更新 `ffmpeg_service` 使用 `index`。

### 2. 配置加载器

- `paddleocr_service` 的配置加载器明显较差，将被删除。
- 所有代码将导入 `from services.common.config_loader import CONFIG`。

## Risks / Trade-offs

- **风险**: `ffmpeg_service` 依赖于其本地解析器的特定行为。
- **缓解措施**: 我们将验证通用解析器在需要的地方产生相同的输出结构，或者更新 `ffmpeg_service` 逻辑以适应通用结构。

## Migration Plan

1. 首先增强 `services/common` 解析器。
2. 更新 `paddleocr_service`（较容易的目标）。
3. 更新 `ffmpeg_service`（复杂目标）。
4. 删除旧文件。