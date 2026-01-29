# 字幕语义保护断句设计

## 1. 设计目标

在保持 CPL=42 行业标准的前提下，通过语义保护机制确保字幕片段的完整性。

## 2. 核心策略

### 2.1 三层断句流程（修订版）

```
输入词列表
    ↓
第一层: PySBD 全局语义分句（已实施）
    ↓ 得到语义片段（句子级别）
第二层: 语义保护切分（新增）
    ├─ 2.1 检查片段是否超过 CPL
    ├─ 2.2 在语义边界处切分（弱标点/停顿）
    ├─ 2.3 检查是否产生超短片段
    └─ 2.4 若超短则回退到字数平均切分
    ↓
第三层: 极短片段修复（已实施）
    ↓
输出片段
```

### 2.2 语义边界优先级（多语言）

| 优先级 | 边界类型 | 英文示例 | 中文示例 | 说明 |
|--------|----------|----------|----------|------|
| 1 | 强标点 | `.` `!` `?` | `。` `！` `？` | 句子结束，不跳过 |
| 2 | 弱标点 | `,` `;` `:` | `，` `；` `：` | 首选切分点 |
| 3 | 连词/停顿 | `and` `but` `or` | 和、但、或 | 次选切分点 |
| 4 | 停顿间隙 | >0.3s 间隔 | >0.3s 间隔 | 兜底切分点 |

### 2.3 超短片段定义

```python
# 超短片段判定条件（满足任一即视为超短）
def is_too_short(words, min_chars=3, min_duration=0.8):
    text = "".join(w.get("word", "") for w in words).strip()
    duration = words[-1]["end"] - words[0]["start"] if len(words) >= 2 else 0
    return len(text) <= min_chars or duration < min_duration
```

### 2.4 回退策略

当语义边界切分会产生超短片段时：

```python
# 回退到字数平均切分，但保持单词完整性
def split_by_word_count_balanced(words, max_cpl, min_chars=3):
    """
    按字数平均分割，确保：
    1. 每个片段不超过 max_cpl
    2. 每个片段至少 min_chars 字符
    3. 不在单词中间切断
    """
    # 实现逻辑...
```

## 3. 多语言支持

### 3.1 语言特定处理

```python
LANGUAGE_SPECIFIC_PATTERNS = {
    "en": {
        "conjunctions": ["and", "but", "or", "so", "yet", "for", "nor"],
        "weak_punct": [",", ";", ":", "-"],
    },
    "zh": {
        "conjunctions": ["和", "但", "或", "所以", "然而"],
        "weak_punct": ["，", "；", "：", "、"],
    },
    "ja": {
        "conjunctions": ["と", "しかし", "または"],
        "weak_punct": ["、", "；", "："],
    },
    # ... 其他语言
}
```

### 3.2 字符长度计算

```python
def get_text_length(text: str, language: str) -> int:
    """
    多语言字符长度计算
    - CJK字符（中日韩）：每个字符计为1.5-2个英文字符宽度
    - 英文/拉丁：每个字符计为1
    """
    if language in {"zh", "ja", "ko"}:
        # CJK字符通常占两个英文字符宽度
        return sum(2 if ord(c) > 127 else 1 for c in text)
    return len(text)
```

## 4. 关键算法

### 4.1 语义保护切分算法

```python
def split_with_semantic_protection(
    words: List[Dict],
    max_cpl: int,
    language: str = "en",
    min_chars: int = 3,
    min_duration: float = 0.8
) -> List[List[Dict]]:
    """
    语义保护切分：优先在语义边界处切分，避免超短片段
    """
    text = "".join(w.get("word", "") for w in words)

    # 如果不超过限制，无需切分
    if len(text) <= max_cpl:
        return [words]

    # 1. 收集所有语义边界候选点
    candidates = collect_semantic_boundaries(words, language)

    # 2. 选择最佳切分点（最接近中间，且不会产生超短片段）
    best_split = find_best_boundary(
        words, candidates, max_cpl, min_chars, min_duration
    )

    if best_split is not None:
        # 使用语义边界切分
        left = words[:best_split + 1]
        right = words[best_split + 1:]
    else:
        # 回退到字数平均切分
        return split_by_word_count_balanced(words, max_cpl, min_chars)

    # 递归处理左右两部分
    return (
        split_with_semantic_protection(left, max_cpl, language, min_chars, min_duration) +
        split_with_semantic_protection(right, max_cpl, language, min_chars, min_duration)
    )
```

### 4.2 收集语义边界

```python
def collect_semantic_boundaries(words: List[Dict], language: str) -> List[Tuple[int, float]]:
    """
    收集所有语义边界候选点，返回 (索引, 分数) 列表
    分数越高表示越适合切分
    """
    candidates = []
    patterns = LANGUAGE_SPECIFIC_PATTERNS.get(language, LANGUAGE_SPECIFIC_PATTERNS["en"])

    for i in range(len(words) - 1):
        word_text = words[i].get("word", "").strip().lower()
        next_word = words[i + 1].get("word", "").strip()

        score = 0.0

        # 1. 弱标点（最高优先级）
        if any(word_text.endswith(p) for p in patterns["weak_punct"]):
            score = 3.0

        # 2. 连词
        elif word_text in patterns["conjunctions"]:
            score = 2.0

        # 3. 停顿间隙
        elif i < len(words) - 1:
            gap = words[i + 1].get("start", 0) - words[i].get("end", 0)
            if gap > PAUSE_THRESHOLD:
                score = 1.0 + min(gap, 1.0)  # 停顿越长分数越高

        if score > 0:
            candidates.append((i, score))

    return candidates
```

### 4.3 寻找最佳边界

```python
def find_best_boundary(
    words, candidates, max_cpl, min_chars, min_duration
) -> Optional[int]:
    """
    寻找最佳切分点，确保不会产生超短片段
    """
    if not candidates:
        return None

    mid = len(words) // 2
    text = "".join(w.get("word", "") for w in words)
    target_len = len(text) / 2  # 目标是平均分割

    best_idx = None
    best_score = -float('inf')

    for idx, boundary_score in candidates:
        # 检查切分后是否会产生超短片段
        left_text = "".join(w.get("word", "") for w in words[:idx + 1])
        right_text = "".join(w.get("word", "") for w in words[idx + 1:])
        left_dur = words[idx]["end"] - words[0]["start"] if idx >= 0 else 0
        right_dur = words[-1]["end"] - words[idx + 1]["start"] if idx + 1 < len(words) else 0

        # 如果会产生超短片段，跳过这个边界
        if (len(left_text.strip()) <= min_chars or
            len(right_text.strip()) <= min_chars or
            left_dur < min_duration or
            right_dur < min_duration):
            continue

        # 计算综合分数
        # 分数 = 语义边界分数 - 偏离中间的惩罚
        distance_penalty = abs(idx - mid) * 0.1
        len_diff = abs(len(left_text) - len(right_text))
        balance_penalty = len_diff * 0.05

        score = boundary_score - distance_penalty - balance_penalty

        if score > best_score:
            best_score = score
            best_idx = idx

    return best_idx
```

## 5. 后处理：片段完整性合并

### 5.1 合并策略

切分后，检查后处理合并：

```python
def merge_incomplete_segments(segments: List[List[Dict]], max_cpl: int) -> List[List[Dict]]:
    """
    合并不完整的片段：
    1. 当前片段无结尾标点 + 下一片段小写开头 → 合并
    2. 当前片段极短（<=3字符）→ 与相邻片段合并
    """
    if not segments:
        return segments

    result = [segments[0]]

    for i in range(1, len(segments)):
        prev_seg = result[-1]
        curr_seg = segments[i]

        prev_text = "".join(w.get("word", "") for w in prev_seg).strip()
        curr_text = "".join(w.get("word", "") for w in curr_seg).strip()

        should_merge = False

        # 条件1: 前一段无结尾标点 + 当前段小写开头
        if prev_text and prev_text[-1] not in '.!?。！？…':
            if curr_text and curr_text[0].islower():
                should_merge = True

        # 条件2: 当前段极短
        if len(curr_text) <= 3:
            should_merge = True

        # 条件3: 合并后不超过 CPL
        if should_merge:
            merged_text = prev_text + " " + curr_text
            if len(merged_text) <= max_cpl:
                # 执行合并
                result[-1].extend(curr_seg)
                continue

        result.append(curr_seg)

    return result
```

## 6. 验收标准

### 6.1 核心指标

| 指标 | 当前值 | 目标值 |
|------|--------|--------|
| 无结尾标点比例 | 61.4% | < 20% |
| 小写开头比例 | 60.5% | < 15% |
| 极短片段（<=3字符）| 0.9% | < 5% |
| 平均片段长度 | 25.8字符 | 30-35字符 |

### 6.2 多语言测试用例

```python
# 英文测试
{
    "input": "Well, little kitty, if you really want to learn how to catch flies",
    "expected": ["Well, little kitty,", "if you really want to", "learn how to catch flies"]
}

# 中文测试
{
    "input": "今天天气很好，我想去公园散步，但是有点远",
    "expected": ["今天天气很好，", "我想去公园散步，", "但是有点远"]
}
```

## 7. 影响范围

- **修改文件**: `services/common/subtitle/segmenter.py`
- **新增函数**: `split_with_semantic_protection`, `collect_semantic_boundaries`, `find_best_boundary`, `merge_incomplete_segments`
- **修改函数**: `_split_with_fallback`（调用语义保护切分）
- **测试文件**: `tests/unit/common/subtitle/test_segmenter_semantic.py`

## 8. 实施计划

### Phase 1: 语义保护切分
- [ ] 实现 `collect_semantic_boundaries`（多语言支持）
- [ ] 实现 `find_best_boundary`
- [ ] 实现 `split_with_semantic_protection`
- [ ] 单元测试

### Phase 2: 后处理合并
- [ ] 实现 `merge_incomplete_segments`
- [ ] 集成到 segmenter.segment 流程
- [ ] 单元测试

### Phase 3: 回归验证
- [ ] 多语言测试（英/中/日）
- [ ] 性能测试
- [ ] 验收指标验证
