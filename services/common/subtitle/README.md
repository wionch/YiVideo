# 字幕纯文本优化与词级重构

## 概述

本模块将 AI 字幕优化拆分为两个阶段：

1. **纯文本纠错**：AI 仅对全文文本做错别字、标点、大小写与格式修正。
2. **词级重构**：本地将优化后的文本对齐回原始词级时间戳，保持数量、顺序与时间戳不变。

## 核心能力

- 纯文本纠错（无 JSON 指令）
- 词级对齐（时间戳不变）
- 可单独调用，也可在工作流中串联

## 关键组件

- `SubtitleTextOptimizer`：读取片段并合并全文，加载提示词并调用 AI。
- `PromptLoader`：加载 `config/system_prompt/subtitle_optimization.md`。
- `AIProviderFactory`：提供 AI 服务接口实例。
- `align_words_to_text`：将优化文本对齐回词级时间戳结构。

## 使用示例

### 纯文本纠错

```python
from services.common.subtitle.subtitle_text_optimizer import SubtitleTextOptimizer

optimizer = SubtitleTextOptimizer(provider="deepseek")
result = optimizer.optimize_text(
    segments=[{"id": 1, "text": "helllo"}],
    prompt_file_path=None
)

print(result["success"])
print(result["optimized_text"])
```

### 词级对齐

```python
from services.common.subtitle.word_level_aligner import align_words_to_text

words = [
    {"word": "helllo", "start": 1.0, "end": 1.2},
    {"word": "world", "start": 1.3, "end": 1.6},
]
aligned_words = align_words_to_text(words, "hello world")
```

## 关联节点

- `wservice.ai_optimize_text`
- `wservice.rebuild_subtitle_with_words`
