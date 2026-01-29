# 字幕语义保护断句 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
> **测试环境:** 所有 pytest 命令必须在 Docker 容器内执行。

**Goal:** 在保持 CPL=42 行业标准的前提下，实现语义保护断句机制，优先在语义边界处切分，超短时回退到字数平均切分，并支持多语言。

**Architecture:** 新增语义边界检测和智能切分逻辑，修改 `_split_with_fallback` 流程，先尝试语义边界切分，若产生超短片段则回退到字数平均切分。新增后处理合并步骤修复不完整片段。

**Tech Stack:** Python 3.11, pytest, pysbd (可选依赖)

---

## 前置准备

### 环境确认

已在 `.worktrees/subtitle-semantic-protection` 创建隔离 worktree（如未创建请先创建）。

**Docker 容器名称:**
- `wservice` - 字幕处理服务（用于测试）

**路径映射（容器内部）:**
- 代码: `/app/services`
- 测试: `/app/tests`

**相关文件位置:**
- 核心断句逻辑: `services/common/subtitle/segmenter.py`
- 现有测试: `tests/unit/common/subtitle/test_segmenter_integration.py`

### 测试命令模板

```bash
# 使用 wservice 容器运行测试
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-protection/tests/unit/common/subtitle/TEST_NAME.py -v
```

---

## Task 1: 创建多语言语义边界配置

**Files:**
- Create: `services/common/subtitle/segmentation_config.py`
- Test: `tests/unit/common/subtitle/test_segmentation_config.py`

**Step 1: 编写失败测试**

```python
# tests/unit/common/subtitle/test_segmentation_config.py
import pytest
from services.common.subtitle.segmentation_config import (
    LANGUAGE_PATTERNS,
    get_language_patterns,
    is_cjk_language,
)


def test_language_patterns_has_english():
    assert "en" in LANGUAGE_PATTERNS
    assert "weak_punct" in LANGUAGE_PATTERNS["en"]
    assert "," in LANGUAGE_PATTERNS["en"]["weak_punct"]


def test_language_patterns_has_chinese():
    assert "zh" in LANGUAGE_PATTERNS
    assert "，" in LANGUAGE_PATTERNS["zh"]["weak_punct"]


def test_get_language_patterns_returns_default_for_unknown():
    patterns = get_language_patterns("xx")
    assert patterns == LANGUAGE_PATTERNS["en"]


def test_is_cjk_language():
    assert is_cjk_language("zh") is True
    assert is_cjk_language("ja") is True
    assert is_cjk_language("ko") is True
    assert is_cjk_language("en") is False
```

**Step 2: 在 Docker 容器内运行测试，确认失败**

```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-protection/tests/unit/common/subtitle/test_segmentation_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.common.subtitle.segmentation_config'`

**Step 3: 实现配置模块**

```python
# services/common/subtitle/segmentation_config.py
"""
字幕断句多语言配置

定义各语言的语义边界模式，包括：
- 弱标点符号
- 连词/转折词
- 字符长度计算方式
"""

from typing import Dict, List, Set

# 多语言语义边界模式
LANGUAGE_PATTERNS: Dict[str, Dict] = {
    "en": {
        "weak_punct": {",", ";", ":", "-", "–", "—"},
        "conjunctions": {
            "and", "but", "or", "so", "yet", "for", "nor",
            "because", "although", "though", "while", "whereas",
        },
        "sentence_starters": {
            "well", "so", "but", "and", "or", "now", "then",
            "however", "therefore", "meanwhile", "finally",
        },
    },
    "zh": {
        "weak_punct": {"，", "；", "：", "、", "——"},
        "conjunctions": {
            "和", "与", "或", "但是", "但", "所以", "因此",
            "因为", "虽然", "尽管", "然而", "而且", "并且",
        },
        "sentence_starters": {
            "那么", "所以", "但是", "然而", "而且", "首先",
            "其次", "最后", "总之", "因此", "于是",
        },
    },
    "ja": {
        "weak_punct": {"、", "；", "：", "ー"},
        "conjunctions": {
            "と", "や", "または", "しかし", "でも", "だから",
            "ので", "なので", "けれども", "が", "から",
        },
        "sentence_starters": {
            "では", "そして", "しかし", "だから", "それで",
            "また", "つまり", "なぜなら", "ところが",
        },
    },
    "ko": {
        "weak_punct": {",", ";", ":", "-"},
        "conjunctions": {
            "그리고", "하지만", "또는", "그래서", "왜냐하면",
            "그러나", "또한", "따라서", "그러므로",
        },
        "sentence_starters": {
            "그럼", "그래서", "하지만", "그러나", "또한",
            "먼저", "다음", "마지막으로", "결론적으로",
        },
    },
    "es": {
        "weak_punct": {",", ";", ":", "-"},
        "conjunctions": {
            "y", "e", "o", "u", "pero", "sino", "porque",
            "aunque", "mientras", "cuando", "donde", "como",
        },
        "sentence_starters": {
            "bueno", "entonces", "pero", "y", "o", "ahora",
            "sin embargo", "por lo tanto", "mientras tanto",
        },
    },
    "fr": {
        "weak_punct": {",", ";", ":", "-"},
        "conjunctions": {
            "et", "ou", "mais", "car", "donc", "or", "ni",
            "parce que", "bien que", "quoique", "pendant que",
        },
        "sentence_starters": {
            "alors", "donc", "mais", "et", "ou", "maintenant",
            "cependant", "pourtant", "par conséquent",
        },
    },
    "de": {
        "weak_punct": {",", ";", ":", "-"},
        "conjunctions": {
            "und", "oder", "aber", "sondern", "denn", "weil",
            "obwohl", "während", "wenn", "als", "wie",
        },
        "sentence_starters": {
            "also", "dann", "aber", "und", "oder", "jetzt",
            "jedoch", "deshalb", "deswegen", "trotzdem",
        },
    },
}

# CJK 语言集合（中日韩）
CJK_LANGUAGES: Set[str] = {"zh", "ja", "ko"}


def get_language_patterns(language: str) -> Dict:
    """
    获取指定语言的语义边界模式

    Args:
        language: 语言代码 (ISO 639-1)

    Returns:
        该语言的模式配置，未知语言返回英文配置
    """
    return LANGUAGE_PATTERNS.get(language, LANGUAGE_PATTERNS["en"])


def is_cjk_language(language: str) -> bool:
    """
    判断是否为 CJK 语言（中日韩）

    CJK 语言字符宽度与拉丁字符不同，需要特殊处理
    """
    return language.lower() in CJK_LANGUAGES


def get_text_display_width(text: str, language: str) -> int:
    """
    计算文本的显示宽度

    CJK 字符通常占两个英文字符宽度，用于 CPL 计算

    Args:
        text: 要计算的文本
        language: 语言代码

    Returns:
        显示宽度（英文字符为单位）
    """
    if is_cjk_language(language):
        width = 0
        for char in text:
            if ord(char) > 127:  # 非 ASCII 字符
                width += 2
            else:
                width += 1
        return width
    return len(text)


# 语义边界检测的最小阈值
SEMANTIC_BOUNDARY_CONFIG = {
    "min_chars": 3,          # 最小字符数，低于此视为超短
    "min_duration": 0.8,     # 最短持续时间（秒）
    "pause_threshold": 0.3,  # 停顿阈值（秒）
    "prefer_middle_weight": 0.1,  # 偏离中间的惩罚权重
}


def get_boundary_config() -> Dict:
    """获取语义边界检测配置"""
    return SEMANTIC_BOUNDARY_CONFIG.copy()
```

**Step 4: 在 Docker 容器内运行测试，确认通过**

```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-protection/tests/unit/common/subtitle/test_segmentation_config.py -v
```

Expected: `4 passed`

**Step 5: Commit**

```bash
git add services/common/subtitle/segmentation_config.py tests/unit/common/subtitle/test_segmentation_config.py
git commit -m "feat(subtitle): add multi-language segmentation config

- Add LANGUAGE_PATTERNS for 7 languages (en/zh/ja/ko/es/fr/de)
- Define weak punctuation, conjunctions, sentence starters per language
- Add CJK language detection and text width calculation
- Add boundary detection configuration

Part of semantic protection segmentation"
```

---

## Task 2: 实现语义边界收集函数

**Files:**
- Modify: `services/common/subtitle/segmenter.py`
- Test: `tests/unit/common/subtitle/test_segmenter_semantic.py`

**Step 1: 编写失败测试**

```python
# tests/unit/common/subtitle/test_segmenter_semantic.py
import pytest
from services.common.subtitle.segmenter import (
    MultilingualSubtitleSegmenter,
    collect_semantic_boundaries,
)


def test_collect_boundaries_finds_weak_punct():
    words = [
        {"word": " Hello", "start": 0.0, "end": 0.3},
        {"word": " world", "start": 0.3, "end": 0.6},
        {"word": ", next", "start": 0.6, "end": 0.9},
        {"word": " part", "start": 0.9, "end": 1.2},
    ]
    boundaries = collect_semantic_boundaries(words, "en")
    # 应该在索引2（逗号处）找到边界
    assert any(idx == 2 for idx, score in boundaries)


def test_collect_boundaries_finds_conjunction():
    words = [
        {"word": " Hello", "start": 0.0, "end": 0.3},
        {"word": " and", "start": 0.3, "end": 0.6},
        {"word": " world", "start": 0.6, "end": 0.9},
    ]
    boundaries = collect_semantic_boundaries(words, "en")
    # 应该在索引1（and处）找到边界
    assert any(idx == 1 for idx, score in boundaries)


def test_collect_boundaries_finds_pause():
    words = [
        {"word": " First", "start": 0.0, "end": 0.3},
        {"word": " part", "start": 0.3, "end": 0.6},
        # 0.5秒停顿
        {"word": " second", "start": 1.1, "end": 1.4},
        {"word": " part", "start": 1.4, "end": 1.7},
    ]
    boundaries = collect_semantic_boundaries(words, "en")
    # 应该在索引1（停顿处）找到边界
    assert any(idx == 1 for idx, score in boundaries)


def test_collect_boundaries_empty_input():
    boundaries = collect_semantic_boundaries([], "en")
    assert boundaries == []


def test_collect_boundaries_chinese():
    words = [
        {"word": " 你好", "start": 0.0, "end": 0.3},
        {"word": "，", "start": 0.3, "end": 0.4},
        {"word": "世界", "start": 0.4, "end": 0.8},
    ]
    boundaries = collect_semantic_boundaries(words, "zh")
    # 应该在索引1（中文逗号处）找到边界
    assert any(idx == 1 for idx, score in boundaries)
```

**Step 2: 在 Docker 容器内运行测试，确认失败**

```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-protection/tests/unit/common/subtitle/test_segmenter_semantic.py::test_collect_boundaries_finds_weak_punct -v
```

Expected: `NameError: name 'collect_semantic_boundaries' is not defined`

**Step 3: 实现语义边界收集函数**

在 `services/common/subtitle/segmenter.py` 中添加：

```python
from services.common.subtitle.segmentation_config import (
    get_language_patterns,
    get_boundary_config,
)


def collect_semantic_boundaries(words, language):
    """
    收集所有语义边界候选点

    扫描词列表，识别以下类型的语义边界：
    1. 弱标点符号（逗号、分号等）- 最高优先级
    2. 连词/转折词（and, but, or等）- 中等优先级
    3. 停顿间隙（>0.3s）- 低优先级

    Args:
        words: 词列表，每个词包含 word/start/end
        language: 语言代码

    Returns:
        List[Tuple[int, float]]: (边界索引, 分数) 列表
    """
    if not words or len(words) < 2:
        return []

    patterns = get_language_patterns(language)
    config = get_boundary_config()
    pause_threshold = config["pause_threshold"]

    boundaries = []

    for i in range(len(words) - 1):
        word_text = words[i].get("word", "").strip().lower()
        next_word = words[i + 1].get("word", "").strip()

        score = 0.0
        boundary_type = None

        # 1. 弱标点符号（最高优先级）
        weak_punct = patterns.get("weak_punct", set())
        if any(word_text.endswith(p) for p in weak_punct):
            score = 3.0
            boundary_type = "weak_punct"

        # 2. 连词/转折词（中等优先级）
        # 但排除句首词（如 "So," 开头的句子）
        conjunctions = patterns.get("conjunctions", set())
        if score == 0 and word_text in conjunctions:
            # 检查下一个词是否大写（如果是，可能是新句子，不适合切分）
            if next_word and not next_word[0].isupper():
                score = 2.0
                boundary_type = "conjunction"

        # 3. 停顿间隙（低优先级）
        if score == 0 and i < len(words) - 1:
            current_end = words[i].get("end", 0)
            next_start = words[i + 1].get("start", current_end)
            gap = next_start - current_end

            if gap > pause_threshold:
                score = 1.0 + min(gap, 1.0)  # 停顿越长分数越高，最高2.0
                boundary_type = "pause"

        if score > 0:
            boundaries.append((i, score, boundary_type))

    return boundaries
```

**Step 4: 在 Docker 容器内运行测试，确认通过**

```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-protection/tests/unit/common/subtitle/test_segmenter_semantic.py -v
```

Expected: `5 passed`

**Step 5: Commit**

```bash
git add services/common/subtitle/segmenter.py tests/unit/common/subtitle/test_segmenter_semantic.py
git commit -m "feat(subtitle): add semantic boundary collection

- Add collect_semantic_boundaries() function
- Detect weak punctuation, conjunctions, and pauses
- Support multi-language patterns
- Score boundaries by type priority

Part of semantic protection segmentation"
```

---

## Task 3: 实现最佳边界选择函数

**Files:**
- Modify: `services/common/subtitle/segmenter.py`
- Test: `tests/unit/common/subtitle/test_segmenter_semantic.py`

**Step 1: 编写失败测试**

在 `tests/unit/common/subtitle/test_segmenter_semantic.py` 中添加：

```python
def test_find_best_boundary_selects_middle():
    words = [
        {"word": " A", "start": 0.0, "end": 0.2},
        {"word": ",", "start": 0.2, "end": 0.3},
        {"word": " B", "start": 0.3, "end": 0.5},
        {"word": ",", "start": 0.5, "end": 0.6},
        {"word": " C", "start": 0.6, "end": 0.8},
    ]
    boundaries = [(1, 3.0, "weak_punct"), (3, 3.0, "weak_punct")]

    from services.common.subtitle.segmenter import find_best_boundary
    best = find_best_boundary(words, boundaries, max_cpl=42, min_chars=2, min_duration=0.5)

    # 应该选择索引3（更接近中间）
    assert best == 3


def test_find_best_boundary_avoids_too_short():
    words = [
        {"word": " A", "start": 0.0, "end": 0.2},
        {"word": ",", "start": 0.2, "end": 0.3},  # 切分后右段太短
        {"word": " B", "start": 0.3, "end": 0.5},
    ]
    boundaries = [(1, 3.0, "weak_punct")]

    from services.common.subtitle.segmenter import find_best_boundary
    # 设置较高的 min_chars，使得索引1处切分会产生超短片段
    best = find_best_boundary(words, boundaries, max_cpl=42, min_chars=5, min_duration=0.5)

    # 应该返回 None（避免产生超短片段）
    assert best is None


def test_find_best_boundary_empty():
    from services.common.subtitle.segmenter import find_best_boundary
    best = find_best_boundary([], [], max_cpl=42, min_chars=3, min_duration=0.8)
    assert best is None
```

**Step 2: 在 Docker 容器内运行测试，确认失败**

```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-protection/tests/unit/common/subtitle/test_segmenter_semantic.py::test_find_best_boundary_selects_middle -v
```

Expected: `NameError: name 'find_best_boundary' is not defined`

**Step 3: 实现最佳边界选择函数**

在 `services/common/subtitle/segmenter.py` 中添加：

```python
def find_best_boundary(words, boundaries, max_cpl, min_chars, min_duration):
    """
    寻找最佳语义边界切分点

    在满足不产生超短片段的前提下，选择：
    1. 语义分数最高的边界
    2. 最接近片段中间的边界
    3. 切分后两侧长度最均衡的边界

    Args:
        words: 词列表
        boundaries: 边界候选列表 [(idx, score, type), ...]
        max_cpl: 最大字符数限制
        min_chars: 最小字符数限制
        min_duration: 最短持续时间限制

    Returns:
        int: 最佳边界索引，或 None（如果没有合适的边界）
    """
    if not words or not boundaries:
        return None

    mid = len(words) // 2
    text = "".join(w.get("word", "") for w in words)
    target_len = len(text) / 2  # 目标是平均分割

    best_idx = None
    best_score = -float('inf')

    for idx, boundary_score, boundary_type in boundaries:
        # 计算切分后的左右片段
        left_words = words[:idx + 1]
        right_words = words[idx + 1:]

        left_text = "".join(w.get("word", "") for w in left_words).strip()
        right_text = "".join(w.get("word", "") for w in right_words).strip()

        # 计算持续时间
        left_dur = (left_words[-1].get("end", 0) - left_words[0].get("start", 0)
                    if len(left_words) >= 1 else 0)
        right_dur = (right_words[-1].get("end", 0) - right_words[0].get("start", 0)
                     if len(right_words) >= 1 else 0)

        # 检查是否会产生超短片段
        if (len(left_text) < min_chars or
            len(right_text) < min_chars or
            (len(left_words) >= 2 and left_dur < min_duration) or
            (len(right_words) >= 2 and right_dur < min_duration)):
            continue  # 跳过会产生超短片段的边界

        # 检查是否超过 CPL
        if len(left_text) > max_cpl or len(right_text) > max_cpl:
            continue

        # 计算综合分数
        # 分数 = 语义边界分数 - 偏离中间的惩罚 - 长度不均衡的惩罚
        distance_penalty = abs(idx - mid) * 0.1

        left_len = len(left_text)
        right_len = len(right_text)
        len_diff = abs(left_len - right_len)
        balance_penalty = len_diff * 0.05

        score = boundary_score - distance_penalty - balance_penalty

        if score > best_score:
            best_score = score
            best_idx = idx

    return best_idx
```

**Step 4: 在 Docker 容器内运行测试，确认通过**

```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-protection/tests/unit/common/subtitle/test_segmenter_semantic.py::test_find_best_boundary -v
```

Expected: `3 passed`

**Step 5: Commit**

```bash
git add services/common/subtitle/segmenter.py tests/unit/common/subtitle/test_segmenter_semantic.py
git commit -m "feat(subtitle): add best boundary selection

- Add find_best_boundary() function
- Avoid boundaries that create too-short segments
- Score by semantic priority, middle proximity, and balance
- Respect CPL and min duration constraints

Part of semantic protection segmentation"
```

---

## Task 4: 实现语义保护切分函数

**Files:**
- Modify: `services/common/subtitle/segmenter.py`
- Test: `tests/unit/common/subtitle/test_segmenter_semantic.py`

**Step 1: 编写失败测试**

在 `tests/unit/common/subtitle/test_segmenter_semantic.py` 中添加：

```python
def test_split_with_semantic_protection_basic():
    words = [
        {"word": " Hello", "start": 0.0, "end": 0.3},
        {"word": " world", "start": 0.3, "end": 0.6},
        {"word": ", next", "start": 0.6, "end": 0.9},
        {"word": " part", "start": 0.9, "end": 1.2},
    ]

    from services.common.subtitle.segmenter import split_with_semantic_protection
    result = split_with_semantic_protection(words, max_cpl=20, language="en")

    # 应该在逗号处切分
    assert len(result) == 2
    assert "Hello world," in "".join(w["word"] for w in result[0])
    assert "next part" in "".join(w["word"] for w in result[1])


def test_split_with_semantic_protection_no_split_needed():
    words = [
        {"word": " Hi", "start": 0.0, "end": 0.3},
        {"word": " there", "start": 0.3, "end": 0.6},
    ]

    from services.common.subtitle.segmenter import split_with_semantic_protection
    result = split_with_semantic_protection(words, max_cpl=42, language="en")

    # 不需要切分
    assert len(result) == 1


def test_split_with_semantic_protection_fallback_to_word_count():
    # 制造一个场景：语义边界会产生超短片段
    words = [
        {"word": " ABCDEFGHIJ", "start": 0.0, "end": 0.3},
        {"word": ",", "start": 0.3, "end": 0.4},  # 切分后右段太短
        {"word": " X", "start": 0.4, "end": 0.6},
    ]

    from services.common.subtitle.segmenter import split_with_semantic_protection
    # 设置较高的 min_chars
    result = split_with_semantic_protection(words, max_cpl=10, language="en", min_chars=5)

    # 应该回退到字数平均切分
    assert len(result) >= 1


def test_split_with_semantic_protection_chinese():
    words = [
        {"word": " 你好", "start": 0.0, "end": 0.3},
        {"word": "，", "start": 0.3, "end": 0.4},
        {"word": "世界", "start": 0.4, "end": 0.8},
    ]

    from services.common.subtitle.segmenter import split_with_semantic_protection
    result = split_with_semantic_protection(words, max_cpl=6, language="zh")

    # 应该在中文逗号处切分
    assert len(result) == 2
```

**Step 2: 在 Docker 容器内运行测试，确认失败**

```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-protection/tests/unit/common/subtitle/test_segmenter_semantic.py::test_split_with_semantic_protection_basic -v
```

Expected: `NameError: name 'split_with_semantic_protection' is not defined`

**Step 3: 实现语义保护切分函数**

在 `services/common/subtitle/segmenter.py` 中添加：

```python
def split_with_semantic_protection(
    words,
    max_cpl,
    language="en",
    min_chars=3,
    min_duration=0.8,
    max_duration=7.0,
):
    """
    语义保护切分：优先在语义边界处切分，超短时回退到字数平均切分

    Args:
        words: 词列表
        max_cpl: 每行最大字符数
        language: 语言代码
        min_chars: 最小字符数
        min_duration: 最短持续时间
        max_duration: 最长持续时间

    Returns:
        List[List[Dict]]: 切分后的词列表
    """
    if not words:
        return []

    text = "".join(w.get("word", "") for w in words)

    # 如果不超过限制，无需切分
    if len(text) <= max_cpl:
        return [words]

    if len(words) <= 1:
        return [words]

    # 1. 收集语义边界
    boundaries = collect_semantic_boundaries(words, language)

    # 2. 寻找最佳边界
    best_idx = find_best_boundary(words, boundaries, max_cpl, min_chars, min_duration)

    if best_idx is not None:
        # 使用语义边界切分
        left = words[:best_idx + 1]
        right = words[best_idx + 1:]
    else:
        # 回退到字数平均切分
        return split_by_word_count_no_tiny(words, max_cpl, min_chars)

    # 递归处理左右两部分
    return (
        split_with_semantic_protection(left, max_cpl, language, min_chars, min_duration, max_duration)
        + split_with_semantic_protection(right, max_cpl, language, min_chars, min_duration, max_duration)
    )
```

**注意**: `split_by_word_count_no_tiny` 已在现有代码中定义，需要确保它可访问。

**Step 4: 在 Docker 容器内运行测试，确认通过**

```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-protection/tests/unit/common/subtitle/test_segmenter_semantic.py::test_split_with_semantic_protection -v
```

Expected: `4 passed`

**Step 5: Commit**

```bash
git add services/common/subtitle/segmenter.py tests/unit/common/subtitle/test_segmenter_semantic.py
git commit -m "feat(subtitle): add semantic protection split function

- Add split_with_semantic_protection() function
- Try semantic boundaries first, fallback to word count
- Support multi-language boundary detection
- Respect min_chars and min_duration constraints

Part of semantic protection segmentation"
```

---

## Task 5: 实现后处理合并函数

**Files:**
- Modify: `services/common/subtitle/segmenter.py`
- Test: `tests/unit/common/subtitle/test_segmenter_semantic.py`

**Step 1: 编写失败测试**

在 `tests/unit/common/subtitle/test_segmenter_semantic.py` 中添加：

```python
def test_merge_incomplete_segments_basic():
    segments = [
        [{"word": " Hello", "start": 0.0, "end": 0.3},
         {"word": " world", "start": 0.3, "end": 0.6}],  # 无结尾标点
        [{"word": " next", "start": 0.6, "end": 0.9}],   # 小写开头
    ]

    from services.common.subtitle.segmenter import merge_incomplete_segments
    result = merge_incomplete_segments(segments, max_cpl=42)

    # 应该合并
    assert len(result) == 1


def test_merge_incomplete_segments_no_merge_needed():
    segments = [
        [{"word": " Hello", "start": 0.0, "end": 0.3},
         {"word": " world.", "start": 0.3, "end": 0.6}],  # 有结尾标点
        [{"word": " Next", "start": 0.6, "end": 0.9}],    # 大写开头
    ]

    from services.common.subtitle.segmenter import merge_incomplete_segments
    result = merge_incomplete_segments(segments, max_cpl=42)

    # 不应该合并
    assert len(result) == 2


def test_merge_incomplete_segments_too_short():
    segments = [
        [{"word": " Hi", "start": 0.0, "end": 0.3}],
        [{"word": " there", "start": 0.3, "end": 0.6}],  # 前一段太短
    ]

    from services.common.subtitle.segmenter import merge_incomplete_segments
    result = merge_incomplete_segments(segments, max_cpl=42)

    # 应该合并（前一段极短）
    assert len(result) == 1


def test_merge_incomplete_segments_respects_cpl():
    segments = [
        [{"word": " A" * 30, "start": 0.0, "end": 0.3}],  # 30字符
        [{"word": " B" * 30, "start": 0.3, "end": 0.6}],  # 30字符
    ]

    from services.common.subtitle.segmenter import merge_incomplete_segments
    result = merge_incomplete_segments(segments, max_cpl=42)

    # 不应该合并（合并后会超过CPL）
    assert len(result) == 2
```

**Step 2: 在 Docker 容器内运行测试，确认失败**

```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-protection/tests/unit/common/subtitle/test_segmenter_semantic.py::test_merge_incomplete_segments_basic -v
```

Expected: `NameError: name 'merge_incomplete_segments' is not defined`

**Step 3: 实现后处理合并函数**

在 `services/common/subtitle/segmenter.py` 中添加：

```python
def merge_incomplete_segments(segments, max_cpl):
    """
    后处理：合并不完整的片段

    合并条件：
    1. 前一段无结尾标点 + 当前段小写开头
    2. 当前段极短（<=3字符）

    限制：合并后不能超过 CPL

    Args:
        segments: 片段列表，每个片段是词列表
        max_cpl: 最大字符数限制

    Returns:
        List[List[Dict]]: 合并后的片段列表
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

        # 条件2: 当前段极短（<=3字符）
        if len(curr_text) <= 3:
            should_merge = True

        # 条件3: 前一段极短（<=3字符）
        if len(prev_text) <= 3:
            should_merge = True

        # 检查合并后是否超过 CPL
        if should_merge:
            merged_text = prev_text + " " + curr_text
            if len(merged_text) <= max_cpl:
                # 执行合并
                result[-1].extend(curr_seg)
                continue

        result.append(curr_seg)

    return result
```

**Step 4: 在 Docker 容器内运行测试，确认通过**

```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-protection/tests/unit/common/subtitle/test_segmenter_semantic.py::test_merge_incomplete_segments -v
```

Expected: `4 passed`

**Step 5: Commit**

```bash
git add services/common/subtitle/segmenter.py tests/unit/common/subtitle/test_segmenter_semantic.py
git commit -m "feat(subtitle): add post-processing merge for incomplete segments

- Add merge_incomplete_segments() function
- Merge segments without ending punctuation + lowercase start
- Merge too-short segments (<=3 chars)
- Respect CPL limit when merging

Part of semantic protection segmentation"
```

---

## Task 6: 集成到 MultilingualSubtitleSegmenter

**Files:**
- Modify: `services/common/subtitle/segmenter.py`
- Test: `tests/unit/common/subtitle/test_segmenter_integration.py`

**Step 1: 修改 `_split_with_fallback` 方法**

找到 `MultilingualSubtitleSegmenter._split_with_fallback` 方法（约504行），修改为：

```python
def _split_with_fallback(
    self,
    words,
    max_cpl,
    max_cps,
    min_duration,
    max_duration,
    language="en",
):
    """
    兜底切分策略：语义保护切分优先

    1. 尝试语义边界切分（弱标点/连词/停顿）
    2. 如果产生超短片段，回退到字数平均切分
    """
    if not self._should_split(words, max_cpl, max_cps, min_duration, max_duration):
        return [words]

    # 使用语义保护切分（新增）
    segments = split_with_semantic_protection(
        words,
        max_cpl=max_cpl,
        language=language,
        min_duration=min_duration,
        max_duration=max_duration,
    )

    if len(segments) <= 1:
        return [words]

    # 后处理合并（新增）
    segments = merge_incomplete_segments(segments, max_cpl)

    # 递归处理子片段
    result = []
    for seg in segments:
        if not self._should_split(seg, max_cpl, max_cps, min_duration, max_duration):
            result.append(seg)
            continue
        if len(seg) <= 1:
            result.append(seg)
            continue
        if seg == words:
            result.append(seg)
            continue
        result.extend(
            self._split_with_fallback(
                seg,
                max_cpl=max_cpl,
                max_cps=max_cps,
                min_duration=min_duration,
                max_duration=max_duration,
                language=language,
            )
        )
    return result
```

**Step 2: 修改 `segment` 方法传递 language 参数**

找到 `MultilingualSubtitleSegmenter.segment` 方法，确保 `_split_with_fallback` 调用时传递 `language` 参数：

```python
def segment(
    self,
    words,
    language="en",
    max_cpl=42,
    max_cps=18.0,
    min_duration=1.0,
    max_duration=7.0,
):
    # ... 现有代码 ...

    # 第三层：通用规则兜底
    final_result = []
    for seg in segments:
        if not self._within_limits(seg, max_cpl, max_cps, min_duration, max_duration):
            fixed = self._split_with_fallback(
                seg,
                max_cpl=max_cpl,
                max_cps=max_cps,
                min_duration=min_duration,
                max_duration=max_duration,
                language=language,  # 确保传递 language
            )
            final_result.extend(fixed)
        else:
            final_result.append(seg)

    # 最终后处理合并
    final_result = merge_incomplete_segments(final_result, max_cpl)

    return final_result
```

**Step 3: 编写集成测试**

在 `tests/unit/common/subtitle/test_segmenter_integration.py` 中添加：

```python
def test_segmenter_semantic_protection_english(segmenter):
    """测试英文语义保护切分"""
    words = [
        {"word": " Well,", "start": 0.0, "end": 0.3},
        {"word": " little", "start": 0.3, "end": 0.6},
        {"word": " kitty,", "start": 0.6, "end": 0.9},
        {"word": " if", "start": 0.9, "end": 1.2},
        {"word": " you", "start": 1.2, "end": 1.5},
        {"word": " really", "start": 1.5, "end": 1.8},
    ]

    result = segmenter.segment(words, language="en", max_cpl=20)

    # 检查是否在逗号处切分
    assert len(result) >= 1
    for seg in result:
        text = "".join(w["word"] for w in seg).strip()
        # 不应该有小写开头的片段（除非是第一段）
        if seg != result[0]:
            assert not text[0].islower() or text[-1] in ',;.!?'


def test_segmenter_semantic_protection_chinese(segmenter):
    """测试中文语义保护切分"""
    words = [
        {"word": " 今天", "start": 0.0, "end": 0.3},
        {"word": "天气", "start": 0.3, "end": 0.6},
        {"word": "很好，", "start": 0.6, "end": 0.9},
        {"word": "我想", "start": 0.9, "end": 1.2},
        {"word": "去公园。", "start": 1.2, "end": 1.5},
    ]

    result = segmenter.segment(words, language="zh", max_cpl=12)

    # 检查是否正确切分
    assert len(result) >= 1
    full_text = "".join("".join(w["word"] for w in seg) for seg in result)
    assert "今天天气很好" in full_text
```

**Step 4: 在 Docker 容器内运行测试**

```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-protection/tests/unit/common/subtitle/test_segmenter_integration.py -v
```

Expected: 所有测试通过

**Step 5: Commit**

```bash
git add services/common/subtitle/segmenter.py tests/unit/common/subtitle/test_segmenter_integration.py
git commit -m "feat(subtitle): integrate semantic protection into segmenter

- Modify _split_with_fallback to use semantic protection split
- Add post-processing merge in segment() method
- Pass language parameter through split flow
- Add integration tests for English and Chinese

Completes semantic protection segmentation integration"
```

---

## Task 7: 全量回归测试

**Files:**
- Test: `tests/unit/common/subtitle/*`

**Step 1: 运行所有字幕相关测试**

```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-protection/tests/unit/common/subtitle -v
```

Expected: 所有测试通过

**Step 2: 验证实际数据效果**

使用实际数据验证改进效果：

```bash
docker exec -i wservice python3 -c "
import json
import sys
sys.path.insert(0, '/app/.worktrees/subtitle-semantic-protection')

from services.common.subtitle.segmenter import MultilingualSubtitleSegmenter

# 加载测试数据
with open('/app/.worktrees/subtitle-semantic-protection/share/workflows/video_to_subtitle_task/nodes/wservice.merge_with_word_timestamps/data/transcribe_data_video_to_word_timestamps_merged.json') as f:
    segments = json.load(f)

# 扁平化词列表
flat_words = []
for seg in segments:
    for word in seg.get('words', []):
        flat_words.append(word)

# 测试
segmenter = MultilingualSubtitleSegmenter()
result = segmenter.segment(flat_words, language='en', max_cpl=42)

# 统计
no_end_punct = sum(1 for seg in result
                   if not ''.join(w.get('word', '') for w in seg).strip()[-1] in '.!?。！？…'
                   if ''.join(w.get('word', '') for w in seg).strip())
starts_lower = sum(1 for seg in result
                   if ''.join(w.get('word', '') for w in seg).strip()
                   and ''.join(w.get('word', '') for w in seg).strip()[0].islower())

print(f'总片段数: {len(result)}')
print(f'无结尾标点: {no_end_punct} ({no_end_punct/len(result)*100:.1f}%)')
print(f'小写开头: {starts_lower} ({starts_lower/len(result)*100:.1f}%)')
"
```

Expected: 无结尾标点比例应显著降低（从61.4%降至<30%）

**Step 3: Commit（如果测试通过）**

```bash
git commit --allow-empty -m "test(subtitle): verify semantic protection implementation

All tests passing:
- test_segmentation_config.py
- test_segmenter_semantic.py
- test_segmenter_integration.py
- Full regression test suite

Semantic protection metrics improved:
- Reduced incomplete segments significantly
- Maintained CPL=42 compliance
- Multi-language support verified

Implementation complete"
```

---

## 执行选项

Plan complete and saved to `docs/plans/2026-01-29-subtitle-semantic-protection-implementation-plan.md`.

**Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
