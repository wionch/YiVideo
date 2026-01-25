# AI 字幕优化功能拆分设计

## 背景与目标
将现有 `wservice.ai_optimize_subtitles` 拆分为两个独立节点：
- **AI优化节点**：仅负责全文纠错，输入=合并后的字幕全文，输出=优化后的全文。
- **本地重构节点**：仅负责将优化后的全文映射回原始词级时间戳，保证时间戳不发生偏移。

设计强调 KISS/YAGNI，避免指令集与复杂重排。

## 总体架构与节点拆分
- **AI优化节点**：输出优化后的完整文本（字符串 + 文本文件路径），不处理时间戳。
- **本地重构节点**：以原始 `segments[].words` 为对齐基准，仅替换词文本，维持原 `start/end`。
- **数据传递**：通过 `WorkflowContext.stages` 共享 `segments_file` 与 `optimized_text`。
- **系统提示词**：强约束纠错模式，仅允许错别字/标点/大小写/格式规范化，禁止增删内容、合并/拆分句子、语序重排。
- **模式替换**：AI 输入/输出为纯文本，不再使用指令集 JSON，也不做指令解析。

## 纯文本模式约束（替代指令集）
- **输入**：将所有字幕合并为完整正文文本，仅向模型提供纯文本。
- **输出**：必须返回纯文本正文，不允许 JSON、列表或解释性说明；本地重构默认视为纯文本，不做内容类型判定。
- **允许修改**：错别字、标点、大小写、空格/格式规范化。
- **禁止修改**：增删内容、语序重排、合并/拆分句子。

## 组件划分与核心职责
### AI优化节点
- `SubtitleExtractor`：读取 `segments_file`，输出字幕片段列表。
- `SubtitleTextOptimizer`：对每段 `text` 先做 `strip`，按顺序用单空格拼接为全文并调用 AI。
- `PromptLoader`：加载纠错专用系统提示词。
- `AIProviderFactory/AIProvider`：选择并调用模型提供商。
- `AI优化执行器`：保存 `optimized_text` 文件并返回结果。

### 本地重构节点
- `OptimizedTextLoader`：读取优化全文。
- `WordAligner`：核心对齐逻辑（词级对齐，时间戳不变）。
- `SegmentRebuilder`：按原 segment 边界重建 `segments[].text` 与 `words[].word`。
- `RebuildSaver`：输出 `optimized_segments` 文件。

**对齐输入特性（基于样例数据）**
- `words[].word` 可能包含前导空格与标点（例如 `" Well,"`）。
- 对齐必须保持 **words 数量与顺序不变**，仅替换 `word` 文本。
- 输出 `word` 必须维持原有空格/标点风格，避免二次分词导致漂移。

## 数据流与输入/输出约定
### AI优化节点输入（input_data）
- `segments_file`（必需）
- `provider`（可选）
- `timeout`（可选）
- `max_retries`（可选）
- `system_prompt_override`（可选）

### AI优化节点输出
- `optimized_text`（字符串）
- `optimized_text_file`（文件路径）
- `segments_file`（原始路径回传）
- `stats`（耗时、provider、token 统计等）

### 本地重构节点输入（input_data）
- `segments_file`（必需）
- `optimized_text` 或 `optimized_text_file`

### 本地重构节点输出
- `optimized_segments_file`（文件路径）

### 数据流示例
节点可独立调用，也可串联：
`faster_whisper.transcribe_audio` → `wservice.ai_optimize_text` → `wservice.rebuild_subtitle_with_words`

## 错误处理
### AI优化节点
- 缺少 `segments_file`：返回错误。
- LLM 请求失败：重试 `max_retries`，失败则返回错误。
- 输出为空或异常：直接失败。

### 本地重构节点
- 缺少 `optimized_text/optimized_text_file`：返回错误。
- 对齐失败：返回错误（不修改时间戳）。

## 测试与验证
### 单元测试
- AI优化节点：全文合并、提示词注入、LLM mock 返回验证。
- 本地重构节点：词级对齐后时间戳不变。

### 集成测试
- 使用现有样例 `transcribe_data_task_id.json` 走通两节点。
- 验证输出 `segments[].start/end` 与原始一致。
- 验证 `optimized_text_file` 与 `optimized_segments_file` 均生成。
