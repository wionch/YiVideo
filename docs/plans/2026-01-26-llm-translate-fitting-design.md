# LLM 翻译装词功能设计（S2ST）

## 背景与目标

S2ST 场景中，翻译后的字幕必须在不改变时间轴的前提下，尽可能贴合原时长与可读性要求。目标是新增一个“翻译装词”节点，在保证语义忠实的同时，尽量满足行业规范（CPL/CPS/时长），并输出与原始 `segments` 对齐的字幕数据。

## 约束与原则

- **时间轴不变**：严格保留原字幕 `start/end`。
- **仅文本变化**：翻译装词只修改 `text`，不拆分/合并分段。
- **规范优先**：采用 Netflix Timed Text Style Guide 作为基线，默认 CPS=18（折中），CPL=42，最多两行。
- **输出纯文本**：LLM 只输出翻译后的完整正文文本，不输出 JSON 或解释。

## 规范依据（检索结果）

- Netflix Timed Text Style Guide：单条字幕最短约 5/6 秒，最长 7 秒；建议 CPL 42。
- Netflix 英语指南：阅读速度通常按 CPS 17/20 区间控制。
- 本仓库 `services/common/subtitle/README.md` 已采用 CPL 42 / CPS 18 / 1s~7s 作为词级重构的兜底规则。

参考链接：
- https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617-Timed-Text-Style-Guide-General-Requirements
- https://partnerhelp.netflixstudios.com/hc/en-us/articles/217350977-English-USA-Timed-Text-Style-Guide

## 方案概述

采用“**全文翻译 + 本地装词回段**”策略：

1. 读取 `segments_file`，提取全文文本。
2. 按系统提示词 + 提交 prompt 调用 LLM，得到翻译后的全文文本。
3. 基于原字幕段时长计算每段字符预算（CPS=18，CPL=42，2 行上限）。
4. 将翻译全文按预算切分回原段，严格保留原 `start/end`。
5. 输出 `translated_segments_file`（结构与原 `segments` 一致）。

## System Prompt 设计

文件路径：`config/system_prompt/subtitle_translation_fitting.md`

核心要求：

- 角色：字幕翻译装词专家。
- 目标：语义忠实 + 时长/语速对齐。
- 规范：CPL 42，CPS 18，最多 2 行；**不得改变时间轴**。
- 策略：超长时优先简化、同义替换、去冗，不得新增事实。
- 输出：仅输出翻译后的完整正文文本，不含编号、JSON、解释。

## 提交 Prompt 设计（User Prompt）

动态字段：

- 目标语言：支持 ISO 码或语言名
- 可选源语言
- 原文全文
- 总时长、总预算、CPS/CPL/行数
- 时间轴不可变硬约束

示例模板：

```
目标语言: {target_language}
源语言: {source_language or "自动识别"}
CPS 上限: 18
CPL 上限: 42
行数上限: 2
总时长: {total_duration:.3f} 秒
总字符预算: {total_budget}
约束: 时间轴不可变，输出总长度不得超过预算

原文全文:
{source_text}
```

## 组件与数据流

### 新增模块

- `SubtitleTranslationFitter`
  - 复用 `SubtitleTextOptimizer` 的 LLM 调用逻辑
  - 输入：`segments` 或 `segments_file`（本次仅支持 `segments_file`）
  - 输出：翻译后的全文文本 + 回填后的 `segments`

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

`segments_file` → 提取全文 → LLM 翻译 → 预算切分 → 回填到原段 → 输出 JSON

## 装词切分规则

- 预算计算：`segment_budget = min(duration * CPS, CPL * 2)`
- 优先在标点或空格处断开；不足时硬截断
- 若预算为 0，输出空文本并记录日志
- 翻译文本超出总预算时，允许局部硬截断并记录超标比例

## 错误处理

- LLM 调用失败/返回空文本：任务失败并抛错
- `segments_file` 不存在：直接报错
- 预算异常：记录 warning，不调整时间轴

## 测试计划

- 单测：新增 `tests/unit/workers/wservice/test_translate_subtitles_executor.py`
- 集成：更新 `tests/integration/test_node_response_format.py` 新节点输出断言
- 所有测试必须在容器内执行（禁止宿主机运行）

## 实施步骤

1. 新增 system prompt 文件 `config/system_prompt/subtitle_translation_fitting.md`
2. 新增 `SubtitleTranslationFitter` 与辅助切分逻辑
3. 新增 `WServiceTranslateSubtitlesExecutor` 与 Celery task
4. 更新单测与文档参考

