# 字幕优化功能重构方案 (第二版)

**日期**: 2026-01-30
**状态**: 设计完成，待实现
**关联**: `faster-whisper` ASR 字幕后处理优化

---

## 1. 问题背景

基于 `faster-whisper` 等 ASR 工具转录的字幕文件存在以下问题：
- 语义错误（错别字、语法问题）
- 断句错误（句子被截断或合并不当）
- 少译、多译

**现有方案的问题**：本地重构方案经过多次调试仍无法解决断句错位问题。

---

## 2. 核心创新：行数锚定策略

### 2.1 设计思想

**以字幕行数作为不可变锚定ID**，让LLM在固定结构内进行修正，避免断句错位。

- 输入格式：`[ID]字幕文本`（一行一条）
- LLM职责：修正内容，但**严禁增减行数**
- 输出格式：`[ID]优化后文本`（一行一条）

### 2.2 约束条件

| 约束 | 说明 |
|------|------|
| **行数守恒** | 输出字幕行数必须与输入完全一致 |
| **ID对应** | `[ID]` 必须与输入一一对应 |
| **置空保留** | 如因修正导致某行内容为空，保留 `[ID]` 但文本留空 |
| **纯文本输出** | 禁止输出字幕文本以外的内容 |

---

## 3. 系统架构

### 3.1 整体流程

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  输入字幕JSON   │────▶│   分段提取文本   │────▶│  并发LLM优化    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                        │
                              ┌─────────────────────────┼─────────────────────────┐
                              ▼                         ▼                         ▼
                        ┌─────────┐               ┌─────────┐               ┌─────────┐
                        │ 段1处理 │               │ 段2处理 │               │ 段3处理 │
                        └────┬────┘               └────┬────┘               └────┬────┘
                             │                         │                         │
                             └─────────────────────────┼─────────────────────────┘
                                                       ▼
                                              ┌──────────────────┐
                                              │   重叠区去重     │
                                              └────────┬─────────┘
                                                       ▼
                                              ┌──────────────────┐
                                              │  时间戳重建      │
                                              └────────┬─────────┘
                                                       ▼
                                              ┌──────────────────┐
                                              │  生成新JSON文件  │
                                              └──────────────────┘
```

### 3.2 模块职责

| 模块 | 职责 |
|------|------|
| `SubtitleExtractor` | 从 `segments` 提取 `text` 字段，生成 `[ID]文本` 格式 |
| `SegmentManager` | 分段管理：切分、调度、合并、重叠区处理 |
| `LLMOptimizer` | LLM调用、格式校验、重试机制 |
| `TimestampReconstructor` | 基于稳定词的两阶段时间戳重建 |
| `SubtitleRebuilder` | 重构JSON文件，生成新文件 |
| `DebugLogger` | 所有请求/响应持久化，可读格式 |

---

## 4. 详细设计

### 4.1 分段并发策略

#### 配置参数

```yaml
subtitle_optimizer:
  segment_size: 100        # 每段处理字幕条数
  overlap_lines: 20        # 重叠行数
  max_concurrent: 3        # 最大并发数
```

#### 分段示例

```
段1: 行1-120   (处理1-100, 101-120为重叠区)
段2: 行101-220 (处理101-200, 201-220为重叠区)
段3: 行201-320 (处理201-300, 301-320为重叠区)
```

#### 并发控制

采用**集中式调度**：
- 维护待处理队列
- 最多同时发送 `max_concurrent` 个请求
- 收到一个结果后再发送下一个
- 统一处理重试和失败

### 4.2 LLM Prompt 设计

#### System Prompt

```
你是一个专业的字幕校对专家。你的任务是修正字幕中的错误，但必须严格遵守以下规则：

【修正内容】
1. 修正错别字和语义错误
2. 修正标点符号使用
3. 修复断句错误：
   - **整行移动**：如果某行内容从语义上明显属于另一行，将该行内容移动到正确行。**注意：源行必须保留[ID]，文本留空**
   - **部分内容移动**：如果某行的部分内容（如单个词或短语）从语义上属于另一行，将该部分内容移动到正确位置
   - **示例1（部分内容移动）**：输入 `[1]今天天气不 [2]错,你好啊` → 输出 `[1]今天天气不错 [2],你好啊`
   - **示例2（整行移动）**：输入 `[1]这句话应该 [2]放在这里` → 输出 `[1] [2]这句话应该放在这里`

【绝对约束】
1. 字幕行数绝对不允许增减
2. 输出格式必须严格为：每行一条，格式 `[ID]字幕文本`
3. 如因修正导致某行内容为空，保留 `[ID]` 但文本留空
4. 禁止输出任何其他内容（解释、注释、空行等）

【格式检查】
输出前必须检查：
- 行数是否与输入一致
- 每行是否以 `[数字]` 开头
- `[数字]` 的ID必须与本段范围一致（如本段范围1-120，则ID应为[1]到[120]）
```

#### User Prompt 结构

```
【任务信息】
- 视频描述: {description}
- 字幕总行数: {total_lines}
- 本段范围: 第{start_line}行 至 第{end_line}行

【字幕文本】
{formatted_text}
```

### 4.3 校验与重试机制

#### 校验层级

| 层级 | 检查内容 | 失败处理 |
|------|----------|----------|
| L1 | 行数是否匹配 | 触发重试 |
| L2 | 每行是否 `[ID]内容` 格式 | 触发重试 |
| L3 | ID是否与本段范围一致（如本段1-120，ID应为[1]-[120]）| 触发重试 |

#### 重试策略

- **自动重试次数**: 3次
- **重试间隔**: 指数退避 (1s, 2s, 4s)
- **失败处理**: 任一段失败则整体任务失败

### 4.4 重叠区去重（混合策略）

#### 核心逻辑

```python
# 伪代码
for overlap_region in all_overlaps:
    segment_a_result = get_result(segment_n, overlap_region)
    segment_b_result = get_result(segment_n+1, overlap_region)

    # 计算差异度
    diff_score = edit_distance(segment_a_result, segment_b_result)

    if diff_score < threshold:
        # 差异小，优先后段（上下文更完整）
        use_result = segment_b_result
    else:
        # 差异大，扩大重叠区重试
        expand_overlap_and_retry(segment_n, segment_n+1)
```

#### 去重决策

| 场景 | 处理 |
|------|------|
| 差异小 | 优先后段结果 |
| 差异大 | 扩大重叠区（如从20行→50行），重新处理 |
| 扩大后仍失败 | 整体任务失败 |

### 4.5 时间戳重建

#### 输入数据

- `segments`: 原始字幕段列表，每段包含 `id`, `start`, `end`, `text`, `words`
- `segments[i].words`: 该段的词级时间戳列表（`word`, `start`, `end`）
- `optimized_lines`: LLM优化后的字幕文本（按行）

**说明**：时间戳重建按 segment 进行，每个 segment 独立处理自己的 `words` 列表。

#### 两阶段重建

**阶段1：稳定词锚定**

```python
# 伪代码
for line_idx, line_text in enumerate(optimized_lines):
    # 对每行文本，在words中查找匹配的词序列
    stable_words = find_lcs(line_text, words)

    # 锁定这些词的时间戳
    for word in stable_words:
        locked_timestamps[word.text] = (word.start, word.end)
```

**阶段2：间隙填充**

```python
# 伪代码
for gap in find_gaps(locked_timestamps):
    if gap.has_space():
        # 有空隙：将新增词均分在间隙中
        distribute_evenly(gap.new_words, gap.start, gap.end)
    else:
        # 无空隙（紧邻）：将文本合并到前置稳定词
        merge_to_previous(gap.new_words, gap.prev_word)
```

#### 时间边界计算

| 情况 | 处理方式 |
|------|----------|
| 两个稳定词之间有空隙 | 新增词均分间隙时间 |
| 两个稳定词紧邻 | 新增词文本合并到前置稳定词（`A`→`A的`）|
| 行首新增 | 继承第一稳定词的开始时间 |
| 行尾新增 | 继承最后一稳定词的结束时间 |

### 4.6 调试日志

#### 保存位置

```
tmp/subtitle_optimizer_logs/
├── {task_id}_seg0_request.txt
├── {task_id}_seg0_response.txt
├── {task_id}_seg1_request.txt
├── {task_id}_seg1_response.txt
└── ...
```

#### 内容格式（可读文本）

**Request 示例**:
```
========================================
任务ID: task_001
段索引: 0
时间: 2026-01-30 14:32:15
========================================

【Meta信息】
- 总行数: 500
- 本段范围: 1-120
- 实际处理: 1-100

【Prompt】
你是一个专业的字幕校对专家...

【字幕文本】
[1]这是第一句话
[2]这是第二句话
...
```

**Response 示例**:
```
========================================
任务ID: task_001
段索引: 0
时间: 2026-01-30 14:32:25
校验状态: PASS / FAIL (原因)
重试次数: 0 / 1 / 2
========================================

【原始响应】
[1]这是修正后的第一句话
[2]这是修正后的第二句话
...

【解析结果】
- 行数: 120 (期望: 120)
- 格式检查: PASS
- 提取的文本行数: 120
```

#### 配置管理

```yaml
subtitle_optimizer:
  debug:
    enabled: true           # 是否启用调试日志
    log_dir: "tmp/subtitle_optimizer_logs"
    # 清理策略：不自动清理，由运维手动处理
```

---

## 5. 数据流

### 5.1 输入格式

参考文件：`share/workflows/video_to_subtitle_task/nodes/faster_whisper.transcribe_audio/data/transcribe_data_task_id.json`

```json
{
  "metadata": {
    "task_name": "faster_whisper.transcribe_audio",
    "workflow_id": "task_id",
    "audio_file": "audio.flac",
    "total_duration": 341.8,
    "language": "en",
    "word_timestamps_enabled": true
  },
  "segments": [
    {
      "id": 1,
      "start": 11.4,
      "end": 19.56,
      "text": " Well, little kitty, if you really want to learn...",
      "words": [
        {"word": " Well,", "start": 11.4, "end": 12.24, "probability": 0.64},
        {"word": " little", "start": 12.32, "end": 12.56, "probability": 0.88},
        {"word": " kitty,", "start": 12.56, "end": 12.92, "probability": 0.83}
      ]
    }
  ]
}
```

**关键字段说明**：
- `segments`: 字幕段列表，每段包含 `id`, `start`, `end`, `text`
- `segments[i].words`: 该段的词级时间戳，包含 `word`, `start`, `end`

### 5.2 输出格式

生成新文件：`{original_name}_optimized.json`

```json
{
  "metadata": {
    "task_name": "faster_whisper.transcribe_audio",
    "workflow_id": "task_id",
    "audio_file": "audio.flac",
    "total_duration": 341.8,
    "language": "en",
    "word_timestamps_enabled": true,
    "optimized_at": "2026-01-30T14:35:00Z",
    "original_file": "original.json",
    "segments_processed": 5,
    "total_retry_count": 2
  },
  "segments": [
    {
      "id": 1,
      "start": 11.4,
      "end": 19.56,
      "text": " Well, little kitty, if you really want to learn...",
      "words": [
        {"word": " Well,", "start": 11.4, "end": 12.24, "probability": 0.64},
        {"word": " little", "start": 12.32, "end": 12.56, "probability": 0.88},
        {"word": " kitty,", "start": 12.56, "end": 12.92, "probability": 0.83}
      ]
    }
  ]
}
```

**说明**：输出保持与输入相同的 `segments` 结构，保留原始 `metadata` 并添加优化相关信息。

---

## 6. 错误处理

### 6.1 错误分类

| 错误类型 | 示例 | 处理 |
|----------|------|------|
| 格式错误 | LLM返回行数不匹配 | 重试3次，失败则整体失败 |
| 网络错误 | API超时 | 重试3次，失败则整体失败 |
| 解析错误 | 无法解析LLM输出 | 重试3次，失败则整体失败 |
| 对齐错误 | 时间戳重建失败 | 记录日志，整体失败 |
| 去重错误 | 重叠区差异过大 | 扩大重叠区重试，失败则整体失败 |

### 6.2 失败响应

```json
{
  "success": false,
  "error": {
    "type": "FORMAT_MISMATCH",
    "message": "Segment 3 line count mismatch: expected 120, got 118",
    "segment_idx": 3,
    "retry_count": 3
  },
  "debug_log_path": "tmp/subtitle_optimizer_logs/task_001_error.log"
}
```

---

## 7. 配置项汇总

```yaml
subtitle_optimizer:
  # 分段处理
  segment_size: 100        # 每段字幕条数
  overlap_lines: 20        # 重叠行数
  max_concurrent: 3        # 最大并发数

  # 重试机制
  max_retries: 3           # 最大重试次数
  retry_backoff_base: 1    # 退避基数（秒）

  # 去重策略
  diff_threshold: 0.3      # 差异阈值（编辑距离比例）
  max_overlap_expand: 50   # 最大重叠扩展行数

  # 调试日志
  debug:
    enabled: true
    log_dir: "tmp/subtitle_optimizer_logs"

  # LLM配置
  llm:
    model: "gemini-pro"    # 或其他模型
    max_tokens: 4096
    temperature: 0.1       # 低温度，更稳定
```

---

## 8. 测试策略

### 8.1 单元测试

| 测试项 | 覆盖点 |
|--------|--------|
| `SubtitleExtractor` | 各种格式的字幕提取 |
| `SegmentManager` | 分段逻辑、边界处理 |
| `LLMOptimizer` | 重试机制、格式校验 |
| `TimestampReconstructor` | 时间戳重建准确性 |
| `OverlapDeduplicator` | 去重逻辑、扩展重试 |

### 8.2 集成测试

| 场景 | 验证点 |
|------|--------|
| 短字幕 (< 100行) | 不分段，直接处理 |
| 长字幕 (1000行+) | 分段并发正确性 |
| 高差异重叠区 | 扩展重试机制 |
| 格式错误恢复 | 3次重试后失败 |
| 并发限流 | max_concurrent 生效 |

---

## 9. 后续优化方向

1. **自适应分段** - 根据内容复杂度动态调整段大小
2. **多模型投票** - 关键重叠区用多个模型交叉验证
3. **增量优化** - 只处理修改过的字幕段
4. **质量评分** - 给优化结果打分，低分标记人工复核

---

## 10. 澄清记录

### 2026-01-30 关键澄清

| 澄清项 | 说明 |
|--------|------|
| **断句修复粒度** | 支持部分内容移动和整行移动。整行移动后**源行必须保留[ID]但文本留空**。如 `[1]今天天气不 [2]错,你好啊` → `[1]今天天气不错 [2],你好啊`；整行移动示例：`[1]这句话应该 [2]放在这里` → `[1] [2]这句话应该放在这里` |
| **ID校验范围** | `[数字]` ID 必须与 user prompt 中的**本段范围**一致（如本段范围1-120，则ID应为[1]到[120]） |
| **输入数据结构** | 参考 `faster_whisper.transcribe_audio` 输出：`segments` 列表，每段包含 `id`, `start`, `end`, `text`, `words` |
| **words位置** | `words` 是每个 segment 内嵌的列表，不是全局列表 |
| **时间戳重建单位** | 按 segment 独立处理，每个 segment 使用自己的 `words` 列表重建时间戳 |

---

## 11. 决策记录 (ADR)

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 锚定策略 | 时间戳 / 行数ID | 行数ID | 时间戳在LLM处理中可能变化，行数更稳定 |
| 并发控制 | 集中式 / 分布式 | 集中式 | 精细控制重试和限流 |
| 时间戳间隙 | 均分 / 继承 / 合并 | 均分+合并 | 有空隙则均分，紧邻则合并，避免零宽度 |
| 失败处理 | 整体失败 / 降级 | 整体失败 | 保证输出质量，避免部分未优化 |
| 去重策略 | 后段优先 / 投票 / 混合 | 混合 | 兼顾效率和准确性 |
| 日志清理 | 自动 / 手动 | 手动 | 便于问题追溯 |

---

*设计完成并已根据澄清更新，等待实现评审。*
