# LLM 翻译装词功能设计（S2ST）

## 背景与目标

S2ST 场景中，翻译后的字幕必须在不改变时间轴的前提下，尽可能贴合原时长与可读性要求。目标是新增一个“翻译装词”节点，在保证语义忠实的同时，尽量满足行业规范（CPL/CPS/时长），并输出与原始 `segments` 对齐的字幕数据。

## 约束与原则

- **时间轴不变**：严格保留原字幕 `start/end`。
- **仅文本变化**：翻译装词只修改 `text`，不拆分/合并分段。
- **上游已断句**：`segments_file` 由 `wservice.ai_optimize_text` + `wservice.rebuild_subtitle_with_words` 产出，断句质量已保障。
- **规范优先**：采用 Netflix Timed Text Style Guide 作为基线，默认 CPS=18（折中），CPL=42，最多两行。
- **输出逐行文本**：LLM 必须按“行对行”输出，不得新增/删除行，不得输出 JSON 或解释。

## 规范依据（检索结果）

- Netflix Timed Text Style Guide：单条字幕最短约 5/6 秒，最长 7 秒；建议 CPL 42。
- Netflix 英语指南：阅读速度通常按 CPS 17/20 区间控制。
- Netflix Subtitle Templates：模板字幕是已定时、已分段的源语字幕，供多语种翻译复用，应保持分段与断行的语法完整性。
- 本仓库 `services/common/subtitle/README.md` 已采用 CPL 42 / CPS 18 / 1s~7s 作为词级重构的兜底规则。

参考链接：
- https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617-Timed-Text-Style-Guide-General-Requirements
- https://partnerhelp.netflixstudios.com/hc/en-us/articles/217350977-English-USA-Timed-Text-Style-Guide
- https://partnerhelp.netflixstudios.com/hc/en-us/articles/219375728-Timed-Text-Style-Guide-Subtitle-Templates

## 方案概述

采用“**行对行翻译 + 原段回填**”策略：

1. 读取 `segments_file`，提取每段文本为一行。
2. 计算每段字符预算（`min(duration * CPS, CPL * 2)`）。
3. 按系统提示词 + 提交 prompt 调用 LLM，要求逐行输出、行数一致。
4. 校验行数与预算，失败则重试（次数沿用 `subtitle_correction.max_retry_attempts`）。
5. 按行回填 `text`，严格保留原 `start/end`，输出 `translated_segments_file`。

## System Prompt 设计

文件路径：`config/system_prompt/subtitle_translation_fitting.md`

核心要求：

- 角色：字幕翻译装词专家。
- 目标：语义忠实 + 时长/语速对齐。
- 规范：CPL 42，CPS 18，最多 2 行；**不得改变时间轴**。
- 策略：超长时优先简化、同义替换、去冗，不得新增事实。
- 输出：仅输出逐行翻译文本，不含编号、JSON、解释；不允许换行符。

最终版本：

```
你是专业的字幕翻译装词助手。

目标：在不改变时间轴、不改变分段数量与顺序的前提下，将字幕逐行翻译为目标语言，并尽量满足阅读速度与行长约束。

强制规则：
1. 输入为多行字幕，每行对应一个字幕段；输出必须逐行对应，行数与顺序严格一致。
2. 行内禁止出现换行符或空行；不要输出编号、列表、JSON、解释或任何多余内容。
3. 每行字符数不得超过该行“字符预算”（预算包含空格与标点）。
4. 若超长，优先通过压缩表达、删语气词、同义替换、缩写来满足预算，但不得新增事实、不得改变语义。
5. 术语与专有名词保持一致。
6. 若原文含有格式标记/标签/说话人标记（如 []、<>、{}、SPEAKER_XX），保持原样不改动。
7. 若目标语言不使用空格，去除不必要空格。

输出：仅输出逐行翻译文本，行数必须与输入一致。
```

## 提交 Prompt 设计（User Prompt）

动态字段：

- 目标语言：支持 ISO 码或语言名
- 可选源语言
- 每段原文（按行）
- 每段时长与字符预算（CPS/CPL/行数上限）
- 时间轴不可变硬约束

示例模板：

```
任务：字幕逐行翻译装词（行对行回填）
目标语言: {target_language} （可为 ISO 码或语言名称）
源语言: {source_language or "自动识别"}
CPS 上限: 18
CPL 上限: 42
行数上限: 2
字符预算说明：每行字符预算包含空格与标点；行内禁止换行符。

输出要求：
- 仅输出翻译后的字幕文本行
- 行数必须与输入一致
- 不要输出序号、时长、预算或任何说明

逐行字幕（格式: 序号 | 时长秒 | 字符预算 | 原文）:
{line_items}
```

`line_items` 示例：

```
1 | 2.40 | 32 | We need to move fast.
2 | 1.10 | 18 | That's it.
```

## 组件与数据流

### 新增模块

- `SubtitleLineTranslator`
  - 复用 `SubtitleTextOptimizer` 的 LLM 调用逻辑
  - 输入：`segments_file`（仅支持文件）
  - 输出：逐行翻译结果 + 回填后的 `segments`

### 新增节点

- `wservice.translate_subtitles`
  - 输入：
    - `segments_file` (必填)
    - `target_language` (必填，支持 ISO 码或语言名)
    - `source_language` (可选)
    - `provider` (可选)
    - `prompt_file_path` (可选，默认 `subtitle_translation_fitting.md`)
  - 输出：`translated_segments_file`

### 数据流

`segments_file` → 提取逐行文本 → 计算每行预算 → LLM 逐行翻译 → 校验行数/预算 → 回填到原段 → 输出 JSON

## 行对行回填规则

- 预算计算：`segment_budget = min(duration * CPS, CPL * 2)`
- LLM 输出行数必须与输入行数一致
- 单行超预算视为失败并触发重试
- 若预算为 0，输出空文本并记录日志
- 不允许 `\\n` 换行符，保持单行文本

## 错误处理

- LLM 调用失败/返回空文本：任务失败并抛错
- `segments_file` 不存在：直接报错
- 行数不一致或单行超预算：触发重试，重试次数沿用 `subtitle_correction.max_retry_attempts`
  - 超过次数仍失败则任务失败

## 测试计划

- 单测：新增 `tests/unit/workers/wservice/test_translate_subtitles_executor.py`
- 集成：更新 `tests/integration/test_node_response_format.py` 新节点输出断言
- 所有测试必须在容器内执行（禁止宿主机运行）

## 实施步骤

1. 新增 system prompt 文件 `config/system_prompt/subtitle_translation_fitting.md`
2. 新增 `SubtitleLineTranslator` 与逐行校验/重试逻辑
3. 新增 `WServiceTranslateSubtitlesExecutor` 与 Celery task
4. 更新单测与文档参考
