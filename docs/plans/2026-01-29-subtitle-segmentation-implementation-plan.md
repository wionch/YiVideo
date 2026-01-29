# 字幕重构断句逻辑实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
> **测试环境:** 所有 pytest 命令必须在 Docker 容器内执行。

**Goal:** 实现三层字幕断句策略（强标点 → PySBD语义 → 通用规则兜底），解决当前字幕重构中的断句问题

**Architecture:** 将断句逻辑从 `rebuild_segments_by_words` 中解耦，创建独立的 `segmenter.py` 模块，支持多语言和渐进增强

**Tech Stack:** Python 3.11, pytest, pysbd (可选依赖)

---

## 前置准备

### 环境确认

已在 `.worktrees/subtitle-segmentation` 创建隔离 worktree，分支 `feat/subtitle-segmentation`

**Docker 容器名称:**
- `api_gateway` - API 网关服务
- `wservice` - 字幕处理服务（也可用于测试）

**路径映射（容器内部）:**
- 代码: `/app/services`
- 测试: `/app/tests`
- worktree: `/app/.worktrees`

**相关文件位置:**
- 现有断句逻辑: `services/common/subtitle/word_level_aligner.py:147-167`
- 调用入口: `services/workers/wservice/executors/rebuild_subtitle_with_words_executor.py:70-76`
- 现有测试: `tests/unit/common/subtitle/test_word_level_aligner.py`

### 测试命令模板

```bash
# 使用 api_gateway 容器运行测试
docker exec -it api_gateway pytest /app/tests/unit/common/subtitle/TEST_NAME.py -v

# 或使用 wservice 容器
docker exec -it wservice pytest /app/tests/unit/common/subtitle/TEST_NAME.py -v
```

---

## Task 1: 创建缩写词识别模块

**目标:** 提取缩写词识别逻辑，避免 "Dr./U.S." 被错误断句

**Files:**
- Create: `services/common/subtitle/abbreviations.py`
- Test: `tests/unit/common/subtitle/test_abbreviations.py`

**Step 1: 编写失败测试**

```python
# tests/unit/common/subtitle/test_abbreviations.py
import pytest
from services.common.subtitle.abbreviations import is_abbreviation, COMMON_ABBREVIATIONS


def test_is_abbreviation_recognizes_dr():
    assert is_abbreviation("Dr.") is True
    assert is_abbreviation("dr.") is True


def test_is_abbreviation_recognizes_us():
    assert is_abbreviation("U.S.") is True
    assert is_abbreviation("u.s.") is True


def test_is_abbreviation_rejects_normal_words():
    assert is_abbreviation("Hello") is False
    assert is_abbreviation("world.") is False


def test_is_abbreviation_handles_empty():
    assert is_abbreviation("") is False
    assert is_abbreviation(None) is False
```

**Step 2: 在 Docker 容器内运行测试，确认失败**

```bash
docker exec -it api_gateway pytest /app/tests/unit/common/subtitle/test_abbreviations.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.common.subtitle.abbreviations'`

**Step 3: 实现最小代码**

```python
# services/common/subtitle/abbreviations.py
"""
缩写词识别模块
用于避免缩写中的句点被误判为句子结束
"""

COMMON_ABBREVIATIONS = frozenset({
    # 头衔
    "mr.", "mrs.", "ms.", "dr.", "prof.", "st.",
    # 国家/地区
    "u.s.", "u.k.", "u.n.", "e.u.",
    # 拉丁缩写
    "e.g.", "i.e.", "etc.", "et al.", "vs.", "cf.",
    # 月份
    "jan.", "feb.", "mar.", "apr.", "jun.", "jul.",
    "aug.", "sep.", "sept.", "oct.", "nov.", "dec.",
    # 时间
    "a.m.", "p.m.", "b.c.", "a.d.", "bce", "ce",
    # 其他
    "vol.", "vols.", "inc.", "ltd.", "jr.", "sr.",
    "pp.", "pg.", "no.", "nos.", "fig.", "figs.",
})


def is_abbreviation(word: str) -> bool:
    """
    判断一个词是否为缩写词

    Args:
        word: 要检查的词（包含标点）

    Returns:
        是否为已知缩写词
    """
    if not word:
        return False
    return word.lower().strip() in COMMON_ABBREVIATIONS
```

**Step 4: 在 Docker 容器内运行测试，确认通过**

```bash
docker exec -it api_gateway pytest /app/tests/unit/common/subtitle/test_abbreviations.py -v
```

Expected: `4 passed`

**Step 5: Commit**

```bash
git add services/common/subtitle/abbreviations.py tests/unit/common/subtitle/test_abbreviations.py
git commit -m "feat(subtitle): add abbreviation recognition module

- Add COMMON_ABBREVIATIONS set with common abbreviations
- Add is_abbreviation() function for case-insensitive checking
- Include titles, countries, months, Latin abbreviations

Closes subtitle segmentation phase 1"
```

---

## Task 2: 实现强标点断句层

**目标:** 在强标点处断句，但跳过缩写词

**Files:**
- Create: `services/common/subtitle/segmenter.py` (初始框架)
- Modify: `services/common/subtitle/word_level_aligner.py` (后续集成)
- Test: `tests/unit/common/subtitle/test_segmenter_strong_punct.py`

**Step 1: 编写失败测试**

```python
# tests/unit/common/subtitle/test_segmenter_strong_punct.py
import pytest
from services.common.subtitle.segmenter import split_by_strong_punctuation


def test_split_by_period():
    words = [
        {"word": " Hello", "start": 0.0, "end": 0.5},
        {"word": " world.", "start": 0.5, "end": 1.0},
        {"word": " Next", "start": 1.5, "end": 2.0},
        {"word": " sentence.", "start": 2.0, "end": 2.5}
    ]
    result = split_by_strong_punctuation(words)
    assert len(result) == 2
    assert len(result[0]) == 2  # " Hello world."
    assert len(result[1]) == 2  # " Next sentence."


def test_not_split_abbreviation():
    """Dr. U.S. 等缩写不应被切开"""
    words = [
        {"word": " Dr.", "start": 0.0, "end": 0.3},
        {"word": " Smith", "start": 0.3, "end": 0.8},
        {"word": " lives", "start": 0.8, "end": 1.2},
        {"word": " in", "start": 1.2, "end": 1.5},
        {"word": " U.S.", "start": 1.5, "end": 2.0}
    ]
    result = split_by_strong_punctuation(words)
    assert len(result) == 1  # 不应被切分


def test_split_by_question_mark():
    words = [
        {"word": " What", "start": 0.0, "end": 0.3},
        {"word": " time?", "start": 0.3, "end": 0.8},
        {"word": " Now.", "start": 1.0, "end": 1.5}
    ]
    result = split_by_strong_punctuation(words)
    assert len(result) == 2


def test_empty_input():
    result = split_by_strong_punctuation([])
    assert result == []


def test_no_punctuation():
    words = [
        {"word": " No", "start": 0.0, "end": 0.3},
        {"word": " punctuation", "start": 0.3, "end": 0.8}
    ]
    result = split_by_strong_punctuation(words)
    assert len(result) == 1
```

**Step 2: 在 Docker 容器内运行测试，确认失败**

```bash
docker exec -it api_gateway pytest /app/tests/unit/common/subtitle/test_segmenter_strong_punct.py -v
```

Expected: `ModuleNotFoundError`

**Step 3: 实现代码**

```python
# services/common/subtitle/segmenter.py
"""
字幕断句模块

三层断句策略:
1. 强标点断句（句点/问号/感叹号，但跳过缩写）
2. PySBD 语义断句（可选依赖）
3. 通用规则兜底（弱标点 → 停顿 → 字数）
"""

from typing import Any, Dict, List, Set

from services.common.subtitle.abbreviations import is_abbreviation

# 强标点：句子结束标记
STRONG_PUNCTUATION: Set[str] = {".", "!", "?", "。", "！", "？", "…"}

# 弱标点：潜在断句点
WEAK_PUNCTUATION: Set[str] = {",", "，", "、", ";", ":", "：", "-", "–", "—"}

# 停顿阈值（秒）
PAUSE_THRESHOLD = 0.3


def split_by_strong_punctuation(words: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """
    在强标点处断句，但跳过缩写词

    Args:
        words: 词级时间戳列表

    Returns:
        分段后的词列表
    """
    if not words:
        return []

    segments: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []

    for word in words:
        current.append(word)
        word_text = word.get("word", "").strip()

        # 检查是否以强标点结尾
        if word_text and word_text[-1] in STRONG_PUNCTUATION:
            # 跳过缩写词
            if not is_abbreviation(word_text):
                segments.append(current)
                current = []

    # 添加最后一段
    if current:
        segments.append(current)

    return segments
```

**Step 4: 在 Docker 容器内运行测试，确认通过**

```bash
docker exec -it api_gateway pytest /app/tests/unit/common/subtitle/test_segmenter_strong_punct.py -v
```

Expected: `5 passed`

**Step 5: Commit**

```bash
git add services/common/subtitle/segmenter.py tests/unit/common/subtitle/test_segmenter_strong_punct.py
git commit -m "feat(subtitle): add strong punctuation segmentation layer

- Implement split_by_strong_punctuation() with abbreviation handling
- Skip splitting on Dr./U.S./Mr./Mrs. etc.
- Support multilingual punctuation (., !, ?, 。, ！, ？)

Part of subtitle segmentation implementation"
```

---

## Task 3: 实现弱标点断句层

**目标:** 强标点断句后仍有超长片段时，尝试在弱标点处断句

**Files:**
- Modify: `services/common/subtitle/segmenter.py`
- Test: `tests/unit/common/subtitle/test_segmenter_weak_punct.py`

**Step 1: 编写失败测试**

```python
# tests/unit/common/subtitle/test_segmenter_weak_punct.py
import pytest
from services.common.subtitle.segmenter import split_by_weak_punctuation


def test_split_by_comma():
    words = [
        {"word": " Hello", "start": 0.0, "end": 0.3},
        {"word": " world", "start": 0.3, "end": 0.6},
        {"word": ", next", "start": 0.6, "end": 0.9},
        {"word": " part", "start": 0.9, "end": 1.2}
    ]
    result = split_by_weak_punctuation(words, max_cpl=10)
    assert len(result) == 2


def test_no_split_if_within_limit():
    """如果不超过CPL限制，不应断句"""
    words = [
        {"word": " Short", "start": 0.0, "end": 0.3},
        {"word": " text", "start": 0.3, "end": 0.6}
    ]
    result = split_by_weak_punctuation(words, max_cpl=100)
    assert len(result) == 1


def test_split_at_middle_comma():
    """有多个逗号时，选择最接近中间的"""
    words = [
        {"word": " First", "start": 0.0, "end": 0.3},
        {"word": ",", "start": 0.3, "end": 0.4},
        {"word": " middle", "start": 0.4, "end": 0.7},
        {"word": ",", "start": 0.7, "end": 0.8},
        {"word": " last", "start": 0.8, "end": 1.1}
    ]
    result = split_by_weak_punctuation(words, max_cpl=5)
    # 应该在中第二个逗号处断开（接近中间）
    assert len(result) == 2


def test_no_comma_fallback():
    """没有弱标点时，返回原样"""
    words = [
        {"word": " No", "start": 0.0, "end": 0.3},
        {"word": " comma", "start": 0.3, "end": 0.6},
        {"word": " here", "start": 0.6, "end": 0.9}
    ]
    result = split_by_weak_punctuation(words, max_cpl=5)
    assert len(result) == 1
```

**Step 2: 在 Docker 容器内运行测试，确认失败**

```bash
docker exec -it api_gateway pytest /app/tests/unit/common/subtitle/test_segmenter_weak_punct.py -v
```

**Step 3: 添加实现代码**

在 `services/common/subtitle/segmenter.py` 中添加：

```python
def split_by_weak_punctuation(
    words: List[Dict[str, Any]],
    max_cpl: int
) -> List[List[Dict[str, Any]]]:
    """
    在弱标点处断句，保持片段长度不超过 max_cpl
    优先选择接近片段中间的弱标点

    Args:
        words: 词级时间戳列表
        max_cpl: 每行最大字符数

    Returns:
        分段后的词列表
    """
    text = "".join(w.get("word", "") for w in words)

    if len(text) <= max_cpl:
        return [words]

    if len(words) <= 1:
        return [words]

    # 收集所有弱标点位置
    candidates = []
    for i, word in enumerate(words[:-1]):  # 不在最后一个词后断句
        word_text = word.get("word", "").strip()
        if word_text and word_text[-1] in WEAK_PUNCTUATION:
            candidates.append(i)

    if not candidates:
        return [words]  # 无弱标点，进入下一步

    # 选择最接近中间位置的弱标点
    mid = len(words) // 2
    best_split = min(candidates, key=lambda x: abs(x - mid))

    left = words[:best_split + 1]
    right = words[best_split + 1:]

    # 递归处理
    return split_by_weak_punctuation(left, max_cpl) + \
           split_by_weak_punctuation(right, max_cpl)
```

**Step 4: 在 Docker 容器内运行测试，确认通过**

```bash
docker exec -it api_gateway pytest /app/tests/unit/common/subtitle/test_segmenter_weak_punct.py -v
```

Expected: `4 passed`

**Step 5: Commit**

```bash
git add services/common/subtitle/segmenter.py tests/unit/common/subtitle/test_segmenter_weak_punct.py
git commit -m "feat(subtitle): add weak punctuation segmentation layer

- Implement split_by_weak_punctuation() for mid-sentence breaks
- Select break point closest to middle for balanced segments
- Support comma, semicolon, colon, dash etc.

Part of subtitle segmentation implementation"
```

---

## Task 4: 实现停顿时间断句层

**目标:** 基于 ASR 提供的词间停顿进行断句

**Files:**
- Modify: `services/common/subtitle/segmenter.py`
- Test: `tests/unit/common/subtitle/test_segmenter_pause.py`

**Step 1: 编写失败测试**

```python
# tests/unit/common/subtitle/test_segmenter_pause.py
import pytest
from services.common.subtitle.segmenter import split_by_pause


def test_split_at_long_pause():
    words = [
        {"word": " First", "start": 0.0, "end": 0.3},
        {"word": " part", "start": 0.3, "end": 0.6},
        # 0.5秒停顿
        {"word": " Second", "start": 1.1, "end": 1.4},
        {"word": " part", "start": 1.4, "end": 1.7}
    ]
    result = split_by_pause(words, max_cpl=100)  # CPL宽松，但检测停顿
    assert len(result) == 2


def test_no_split_at_short_pause():
    words = [
        {"word": " First", "start": 0.0, "end": 0.3},
        {"word": " part", "start": 0.35, "end": 0.6},  # 仅0.05秒停顿
        {"word": " here", "start": 0.6, "end": 0.9}
    ]
    result = split_by_pause(words, max_cpl=100)
    assert len(result) == 1


def test_select_longest_pause_near_middle():
    """多个停顿时，选择中间附近最长的"""
    words = [
        {"word": " A", "start": 0.0, "end": 0.2},
        {"word": " B", "start": 0.3, "end": 0.5},   # 0.1s pause
        {"word": " C", "start": 1.0, "end": 1.2},   # 0.5s pause (longest)
        {"word": " D", "start": 1.4, "end": 1.6},   # 0.2s pause
        {"word": " E", "start": 1.7, "end": 1.9}
    ]
    result = split_by_pause(words, max_cpl=100)
    assert len(result) == 2
    # 应该在 C 后断开（最长停顿且在中间区域）
    assert len(result[0]) == 3  # A B C
    assert len(result[1]) == 2  # D E
```

**Step 2: 在 Docker 容器内运行测试，确认失败**

**Step 3: 添加实现代码**

在 `services/common/subtitle/segmenter.py` 中添加：

```python
def split_by_pause(words: List[Dict[str, Any]], max_cpl: int) -> List[List[Dict[str, Any]]]:
    """
    基于词间停顿时间进行断句
    停顿超过 PAUSE_THRESHOLD (0.3s) 视为潜在断句点

    Args:
        words: 词级时间戳列表
        max_cpl: 每行最大字符数（主要检查用）

    Returns:
        分段后的词列表
    """
    text = "".join(w.get("word", "") for w in words)

    if len(text) <= max_cpl:
        return [words]

    if len(words) <= 1:
        return [words]

    # 找出所有超过阈值的停顿
    candidates = []
    for i in range(len(words) - 1):
        current_word_end = words[i].get("end", 0)
        next_word_start = words[i + 1].get("start", current_word_end)
        gap = next_word_start - current_word_end

        if gap > PAUSE_THRESHOLD:
            candidates.append((i, gap))

    if not candidates:
        return [words]  # 无合适停顿，进入下一步

    # 选择中间附近且停顿最长的
    mid = len(words) // 2

    def score_pause(item):
        idx, gap = item
        # 分数 = 停顿长度 - 偏离中间的惩罚
        distance_penalty = abs(idx - mid) * 0.1
        return gap - distance_penalty

    best_split, _ = max(candidates, key=score_pause)

    left = words[:best_split + 1]
    right = words[best_split + 1:]

    return split_by_pause(left, max_cpl) + split_by_pause(right, max_cpl)
```

**Step 4: 在 Docker 容器内运行测试，确认通过**

```bash
docker exec -it api_gateway pytest /app/tests/unit/common/subtitle/test_segmenter_pause.py -v
```

**Step 5: Commit**

```bash
git add services/common/subtitle/segmenter.py tests/unit/common/subtitle/test_segmenter_pause.py
git commit -m "feat(subtitle): add pause-based segmentation layer

- Implement split_by_pause() using ASR word timestamps
- Detect pauses > 0.3s as potential break points
- Prefer pauses near middle of long segments

Part of subtitle segmentation implementation"
```

---

## Task 5: 实现字数平均分割（最终兜底）

**目标:** 所有策略都失败时，按字数平均分割但保持单词完整性

**Files:**
- Modify: `services/common/subtitle/segmenter.py`
- Test: `tests/unit/common/subtitle/test_segmenter_word_count.py`

**Step 1: 编写失败测试**

```python
# tests/unit/common/subtitle/test_segmenter_word_count.py
import pytest
from services.common.subtitle.segmenter import split_by_word_count


def test_split_long_text():
    words = [
        {"word": " This", "start": 0.0, "end": 0.2},
        {"word": " is", "start": 0.2, "end": 0.4},
        {"word": " a", "start": 0.4, "end": 0.6},
        {"word": " very", "start": 0.6, "end": 0.8},
        {"word": " long", "start": 0.8, "end": 1.0},
        {"word": " text", "start": 1.0, "end": 1.2}
    ]
    result = split_by_word_count(words, max_cpl=15)
    # " This is a very long text" = 25 chars
    # 应该分成两段
    assert len(result) == 2


def test_keep_word_intact():
    """不能在单词中间切开"""
    words = [
        {"word": " Hello", "start": 0.0, "end": 0.5},
        {"word": " world", "start": 0.5, "end": 1.0}
    ]
    result = split_by_word_count(words, max_cpl=5)
    # 即使超过限制，也不能切开单词
    # 应该返回原样或合理分割
    assert all(len(seg) >= 1 for seg in result)


def test_single_word_no_split():
    """单个词不应分割"""
    words = [{"word": " Supercalifragilistic", "start": 0.0, "end": 1.0}]
    result = split_by_word_count(words, max_cpl=5)
    assert len(result) == 1
    assert len(result[0]) == 1
```

**Step 2: 在 Docker 容器内运行测试，确认失败**

**Step 3: 添加实现代码**

在 `services/common/subtitle/segmenter.py` 中添加：

```python
def split_by_word_count(words: List[Dict[str, Any]], max_cpl: int) -> List[List[Dict[str, Any]]]:
    """
    按字数平均分割，保持单词完整性
    最终兜底策略，当其他方法都失败时使用

    Args:
        words: 词级时间戳列表
        max_cpl: 每行最大字符数

    Returns:
        分段后的词列表
    """
    text = "".join(w.get("word", "") for w in words)

    if len(text) <= max_cpl or len(words) <= 1:
        return [words]

    # 计算需要的分段数
    num_segments = max(2, (len(text) + max_cpl - 1) // max_cpl)
    target_len = len(text) // num_segments

    # 寻找最接近目标长度的单词边界
    best_split = 0
    current_len = 0

    for i, word in enumerate(words):
        word_len = len(word.get("word", ""))
        # 如果加上当前词超过目标长度的一半，选择在此处断开
        if current_len + word_len / 2 >= target_len and i > 0:
            best_split = i
            break
        current_len += word_len

    if best_split == 0:
        best_split = len(words) // 2

    left = words[:best_split]
    right = words[best_split:]

    return split_by_word_count(left, max_cpl) + split_by_word_count(right, max_cpl)
```

**Step 4: 在 Docker 容器内运行测试，确认通过**

```bash
docker exec -it api_gateway pytest /app/tests/unit/common/subtitle/test_segmenter_word_count.py -v
```

**Step 5: Commit**

```bash
git add services/common/subtitle/segmenter.py tests/unit/common/subtitle/test_segmenter_word_count.py
git commit -m "feat(subtitle): add word-count based segmentation layer

- Implement split_by_word_count() as final fallback
- Keep words intact, never split in middle of word
- Distribute text evenly across segments

Part of subtitle segmentation implementation"
```

---

## Task 6: 整合三层策略

**目标:** 创建统一的 `MultilingualSubtitleSegmenter` 类，按顺序调用三层策略

**Files:**
- Modify: `services/common/subtitle/segmenter.py`
- Test: `tests/unit/common/subtitle/test_segmenter_integration.py`

**Step 1: 编写失败测试**

```python
# tests/unit/common/subtitle/test_segmenter_integration.py
import pytest
from services.common.subtitle.segmenter import MultilingualSubtitleSegmenter


@pytest.fixture
def segmenter():
    return MultilingualSubtitleSegmenter()


def test_basic_segmentation(segmenter):
    words = [
        {"word": " Hello", "start": 0.0, "end": 0.5},
        {"word": " world.", "start": 0.5, "end": 1.0},
        {"word": " Next", "start": 1.5, "end": 2.0},
        {"word": " line.", "start": 2.0, "end": 2.5}
    ]
    result = segmenter.segment(words, language="en", max_cpl=42)
    assert len(result) == 2


def test_long_text_split(segmenter):
    """超长文本应该被分割"""
    words = [
        {"word": " This", "start": 0.0, "end": 0.2},
        {"word": " is", "start": 0.2, "end": 0.4},
        {"word": " a", "start": 0.4, "end": 0.6},
        {"word": " very", "start": 0.6, "end": 0.8},
        {"word": " long", "start": 0.8, "end": 1.0},
        {"word": " sentence", "start": 1.0, "end": 1.2},
        {"word": " without", "start": 1.2, "end": 1.4},
        {"word": " punctuation", "start": 1.4, "end": 1.6}
    ]
    result = segmenter.segment(words, language="en", max_cpl=20)
    # 应该被分割成多段
    assert len(result) >= 2


def test_abbreviation_preserved(segmenter):
    """缩写词应该被正确处理"""
    words = [
        {"word": " Dr.", "start": 0.0, "end": 0.3},
        {"word": " Smith", "start": 0.3, "end": 0.8},
        {"word": " lives", "start": 0.8, "end": 1.2},
        {"word": " in", "start": 1.2, "end": 1.5},
        {"word": " U.S.", "start": 1.5, "end": 2.0}
    ]
    result = segmenter.segment(words, language="en", max_cpl=42)
    # 不应在 Dr. 或 U.S. 处断开
    assert len(result) == 1


def test_respects_cps_limit(segmenter):
    """应该尊重 CPS 限制"""
    words = [
        {"word": " Fast", "start": 0.0, "end": 0.1},
        {"word": " text", "start": 0.1, "end": 0.2}
    ]
    result = segmenter.segment(words, language="en", max_cpl=100, max_cps=5.0)
    # CPS = 9 chars / 0.2s = 45, 超过 5.0，应该触发分割
    # 但由于只有2个词，无法进一步分割，保持原样
    assert len(result) == 1
```

**Step 2: 在 Docker 容器内运行测试，确认失败**

**Step 3: 添加整合类**

在 `services/common/subtitle/segmenter.py` 末尾添加：

```python
class MultilingualSubtitleSegmenter:
    """
    多语言字幕断句器

    三层断句策略:
    1. 强标点断句（句点/问号/感叹号，跳过缩写）
    2. PySBD 语义断句（可选，支持22种语言）
    3. 通用规则兜底（弱标点 → 停顿 → 字数）
    """

    # PySBD 支持的语言
    PYSBD_LANGS = {
        "en", "de", "es", "fr", "it", "pt", "ru", "nl", "da", "fi",
        "zh", "ja", "ko", "ar", "hi", "pl", "cs", "sk", "tr", "el",
        "he", "fa"
    }

    def __init__(self):
        self._pysbd_splitter = None
        self._try_import_pysbd()

    def _try_import_pysbd(self):
        """尝试导入 PySBD，失败则跳过"""
        try:
            from pysbd import Segmenter
            self._pysbd_available = True
            self._pysbd_segmenters = {}
        except ImportError:
            self._pysbd_available = False
            logger.info("PySBD not available, using fallback segmentation")

    def _get_pysbd_segmenter(self, language: str):
        """获取或创建 PySBD segmenter"""
        if language not in self._pysbd_segmenters:
            from pysbd import Segmenter
            self._pysbd_segmenters[language] = Segmenter(language=language, clean=False)
        return self._pysbd_segmenters[language]

    def segment(
        self,
        words: List[Dict[str, Any]],
        language: str = "en",
        max_cpl: int = 42,
        max_cps: float = 18.0,
        min_duration: float = 1.0,
        max_duration: float = 7.0
    ) -> List[List[Dict[str, Any]]]:
        """
        执行三层断句策略

        Args:
            words: 词级时间戳列表
            language: 语言代码 (ISO 639-1)
            max_cpl: 每行最大字符数
            max_cps: 每秒最大字符数
            min_duration: 最短持续时间（秒）
            max_duration: 最长持续时间（秒）

        Returns:
            分段后的词列表
        """
        if not words:
            return []

        # 第1层: 强标点断句
        segments = split_by_strong_punctuation(words)

        # 第2层: 对超长片段使用 PySBD（如果可用且语言支持）
        if self._pysbd_available and language in self.PYSBD_LANGS:
            segments = self._apply_pysbd_split(segments, language, max_cpl)

        # 第3层: 兜底处理
        final_result = []
        for seg in segments:
            if not self._within_limits(seg, max_cpl, max_cps, max_duration):
                fixed = self._fallback_split(seg, max_cpl)
                final_result.extend(fixed)
            else:
                final_result.append(seg)

        return final_result

    def _apply_pysbd_split(
        self,
        segments: List[List[Dict[str, Any]]],
        language: str,
        max_cpl: int
    ) -> List[List[Dict[str, Any]]]:
        """应用 PySBD 语义断句"""
        result = []
        segmenter = self._get_pysbd_segmenter(language)

        for seg in segments:
            text = "".join(w.get("word", "") for w in seg)
            if len(text) > max_cpl:
                # 使用 PySBD 分割
                sentences = segmenter.segment(text)
                # 将字符位置映射回词索引
                sub_segments = self._map_sentences_to_words(seg, sentences)
                result.extend(sub_segments)
            else:
                result.append(seg)

        return result

    def _map_sentences_to_words(
        self,
        words: List[Dict[str, Any]],
        sentences: List[str]
    ) -> List[List[Dict[str, Any]]]:
        """将 PySBD 的句子分割映射为词级分割"""
        if len(sentences) <= 1:
            return [words]

        segments = []
        word_idx = 0
        current_text = ""
        current_segment = []

        for sent in sentences:
            sent = sent.strip()
            while word_idx < len(words) and current_text.strip() != sent:
                word = words[word_idx]
                current_segment.append(word)
                current_text += word.get("word", "")
                word_idx += 1

            if current_segment:
                segments.append(current_segment)
                current_segment = []
                current_text = ""

        # 添加剩余词
        if word_idx < len(words):
            if segments:
                segments[-1].extend(words[word_idx:])
            else:
                segments.append(words[word_idx:])

        return segments if segments else [words]

    def _fallback_split(self, words: List[Dict[str, Any]], max_cpl: int) -> List[List[Dict[str, Any]]]:
        """兜底断句策略链"""
        # 3.1 弱标点
        segments = split_by_weak_punctuation(words, max_cpl)
        if len(segments) > 1:
            return segments

        # 3.2 停顿时间
        segments = split_by_pause(words, max_cpl)
        if len(segments) > 1:
            return segments

        # 3.3 字数平均
        return split_by_word_count(words, max_cpl)

    def _within_limits(
        self,
        words: List[Dict[str, Any]],
        max_cpl: int,
        max_cps: float,
        max_duration: float
    ) -> bool:
        """检查是否满足 CPL/CPS/时长限制"""
        text = "".join(w.get("word", "") for w in words)
        if len(text) > max_cpl:
            return False

        if len(words) >= 2:
            duration = words[-1]["end"] - words[0]["start"]
            if duration > max_duration:
                return False
            if duration > 0 and len(text) / duration > max_cps:
                return False

        return True
```

**Step 4: 在 Docker 容器内运行测试，确认通过**

```bash
docker exec -it api_gateway pytest /app/tests/unit/common/subtitle/test_segmenter_integration.py -v
```

**Step 5: Commit**

```bash
git add services/common/subtitle/segmenter.py tests/unit/common/subtitle/test_segmenter_integration.py
git commit -m "feat(subtitle): integrate three-layer segmentation strategy

- Add MultilingualSubtitleSegmenter class
- Implement 3-layer pipeline: strong punct -> PySBD -> fallback
- Support 22 languages via PySBD with graceful fallback
- Add CPS/CPL/duration limit checks

Closes subtitle segmentation core implementation"
```

---

## Task 7: 重构 `word_level_aligner.py` 使用新模块

**目标:** 替换现有的 `rebuild_segments_by_words` 实现，使用新的 segmenter 模块

**Files:**
- Modify: `services/common/subtitle/word_level_aligner.py`
- Test: 在 Docker 内运行现有测试确保兼容性

**Step 1: 修改导入和函数**

在 `services/common/subtitle/word_level_aligner.py` 顶部添加：

```python
from services.common.subtitle.segmenter import MultilingualSubtitleSegmenter
```

修改 `rebuild_segments_by_words` 函数（约 147-167 行）：

```python
def rebuild_segments_by_words(
    segments: List[Dict[str, Any]],
    max_cpl: int = 42,
    max_cps: float = 18.0,
    min_duration: float = 1.0,
    max_duration: float = 7.0,
    language: str = "en"
) -> List[Dict[str, Any]]:
    """
    基于词级时间戳重建字幕片段

    使用三层断句策略：
    1. 强标点断句（跳过缩写）
    2. PySBD 语义断句（可选）
    3. 通用规则兜底
    """
    words = _flatten_segment_words(segments)
    if not words:
        return []

    # 使用新的 segmenter
    segmenter = MultilingualSubtitleSegmenter()
    word_segments = segmenter.segment(
        words,
        language=language,
        max_cpl=max_cpl,
        max_cps=max_cps,
        min_duration=min_duration,
        max_duration=max_duration
    )

    # 转换为片段格式
    rebuilt_segments = []
    for idx, word_seg in enumerate(word_segments):
        segment = _create_segment_from_words(word_seg)
        segment["id"] = idx + 1
        rebuilt_segments.append(segment)

    return rebuilt_segments


def _create_segment_from_words(words: List[Dict[str, Any]]) -> Dict[str, Any]:
    """从词列表创建片段"""
    text = "".join(w.get("word", "") for w in words).strip()
    start = words[0].get("start", 0.0)
    end = words[-1].get("end", start)

    segment: Dict[str, Any] = {
        "start": start,
        "end": end,
        "duration": max(end - start, 0.0),
        "text": text,
        "words": words
    }

    # 保留说话人信息
    speakers = {w.get("speaker") for w in words if w.get("speaker")}
    if len(speakers) == 1:
        segment["speaker"] = speakers.pop()

    return segment
```

**Step 2: 删除旧的分割逻辑**

删除 `_split_words_by_punctuation_and_limits` 及相关辅助函数（如果不再使用）

**Step 3: 在 Docker 容器内运行测试，确认兼容性**

```bash
docker exec -it api_gateway pytest /app/tests/unit/common/subtitle/test_word_level_aligner.py -v
```

Expected: 所有测试通过

**Step 4: Commit**

```bash
git add services/common/subtitle/word_level_aligner.py
git commit -m "refactor(subtitle): use new segmenter in rebuild_segments_by_words

- Replace old segmentation logic with MultilingualSubtitleSegmenter
- Add language parameter support
- Maintain backward compatibility

Integrates new segmentation implementation"
```

---

## Task 8: 更新执行器传递语言参数

**目标:** 修改 `rebuild_subtitle_with_words_executor.py` 传递语言参数

**Files:**
- Modify: `services/workers/wservice/executors/rebuild_subtitle_with_words_executor.py`

**Step 1: 找到调用点**

约第 70-76 行：

```python
rebuilt_segments = rebuild_segments_by_words(
    segments,
    max_cpl=42,
    max_cps=18.0,
    min_duration=1.0,
    max_duration=7.0
)
```

**Step 2: 添加语言参数**

```python
# 从输入数据获取语言，默认为 "en"
language = input_data.get("language", "en")

rebuilt_segments = rebuild_segments_by_words(
    segments,
    max_cpl=42,
    max_cps=18.0,
    min_duration=1.0,
    max_duration=7.0,
    language=language
)
```

**Step 3: Commit**

```bash
git add services/workers/wservice/executors/rebuild_subtitle_with_words_executor.py
git commit -m "feat(wservice): add language parameter to rebuild executor

- Accept 'language' input parameter (default: 'en')
- Pass language to rebuild_segments_by_words
- Support multilingual segmentation

Enables language-aware segmentation"
```

---

## Task 9: 运行完整测试套件

**目标:** 确保所有测试通过，没有回归

**Step 1: 运行所有字幕相关测试**

```bash
docker exec -it api_gateway pytest /app/tests/unit/common/subtitle/ -v
```

Expected: 所有测试通过

**Step 2: 运行重建执行器测试**

```bash
docker exec -it api_gateway pytest /app/tests/unit/common/subtitle/test_rebuild_executor.py -v
```

Expected: 所有测试通过

**Step 3: Commit（如果测试全部通过）**

```bash
git commit --allow-empty -m "test(subtitle): verify complete segmentation implementation

All tests passing:
- test_abbreviations.py
- test_segmenter_strong_punct.py
- test_segmenter_weak_punct.py
- test_segmenter_pause.py
- test_segmenter_word_count.py
- test_segmenter_integration.py
- test_word_level_aligner.py
- test_rebuild_executor.py

Implementation complete"
```

---

## Task 10: 更新文档

**目标:** 更新设计文档，标记实施完成

**Files:**
- Modify: `docs/plans/2026-01-29-subtitle-rebuild-segmentation-design.md`

**Step 1: 在文档末尾添加实施状态**

```markdown
## 实施状态

### Phase 1: 基础层 ✅
- [x] 缩写词识别模块
- [x] 强标点断句层
- [x] 通用规则兜底（弱标点、停顿、字数）
- [x] 单元测试覆盖

### Phase 2: 增强层 ✅
- [x] PySBD 语义断句集成
- [x] 多语言支持（22种语言）
- [x] 语言参数传递

### Phase 3: 集成 ✅
- [x] 重构 word_level_aligner.py
- [x] 更新 rebuild_subtitle_with_words_executor.py
- [x] 完整测试套件通过

## 实施文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `services/common/subtitle/abbreviations.py` | 新建 | 缩写词识别 |
| `services/common/subtitle/segmenter.py` | 新建 | 三层断句策略 |
| `tests/unit/common/subtitle/test_abbreviations.py` | 新建 | 缩写词测试 |
| `tests/unit/common/subtitle/test_segmenter_*.py` | 新建 | 各层策略测试 |
| `services/common/subtitle/word_level_aligner.py` | 修改 | 使用新模块 |
| `services/workers/wservice/executors/rebuild_subtitle_with_words_executor.py` | 修改 | 传递语言参数 |
```

**Step 2: Commit**

```bash
git add docs/plans/2026-01-29-subtitle-rebuild-segmentation-design.md
git commit -m "docs: update segmentation design with implementation status

- Mark all phases as complete
- Add implementation file checklist
- Document test coverage

Closes implementation plan"
```

---

## 执行选项

Plan complete and saved to `docs/plans/2026-01-29-subtitle-segmentation-implementation-plan.md`.

**Two execution options:**

**1. Subagent-Driven (this session)** - 我使用 superpowers:subagent-driven-development 分派新鲜子代理执行每个任务，在任务之间审查，快速迭代

**2. Parallel Session (separate)** - 打开新会话在 worktree 中批量执行，带有检查点

**Which approach?**
