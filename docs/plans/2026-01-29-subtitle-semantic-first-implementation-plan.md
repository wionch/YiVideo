# 字幕重构全局语义断句优先 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 以“全局语义句界优先”为主导重构字幕断句，同时修复弱标点导致的极短片段，且保持词级时间戳不偏移。

**Architecture:** 先用 PySBD 在连续文本上分句并映射回词级区间，得到语义候选片段；仅在超限时做弱标点/停顿二次切分，并对 1–2 字符极短片段触发“中段平均分割”或邻近合并。

**Tech Stack:** Python 3.11, pytest, pysbd (可选依赖)

> 说明：宿主机只做文件操作，所有测试/验证一律在容器内执行。

---

### Task 1: PySBD 全局语义分句的单测桩与断言

**Files:**
- Modify: `tests/unit/common/subtitle/test_segmenter_integration.py`

**Step 1: 写失败用例（全局语义句界优先）**

```python
class FakeSegmenter:
    def segment(self, text):
        # 保持原文本长度一致
        return ["U.S. It's famous."]


def test_pysbd_global_sentence_first(monkeypatch, segmenter):
    words = [
        {"word": "U.", "start": 0.0, "end": 0.2},
        {"word": "S.", "start": 0.2, "end": 0.4},
        {"word": " ", "start": 0.4, "end": 0.4},
        {"word": "It's", "start": 0.4, "end": 0.6},
        {"word": " ", "start": 0.6, "end": 0.6},
        {"word": "famous.", "start": 0.6, "end": 1.0},
    ]
    monkeypatch.setattr(segmenter, "_pysbd_available", True)
    monkeypatch.setattr(segmenter, "_get_pysbd_segmenter", lambda _lang: FakeSegmenter())
    result = segmenter.segment(words, language="en")
    assert len(result) == 1
    assert "".join(w["word"] for w in result[0]) == "U.S. It's famous."
    # 时间戳不偏移
    assert [w["start"] for w in result[0]] == [0.0, 0.2, 0.4, 0.4, 0.6, 0.6]
```

**Step 2: 容器内运行测试，确认失败**

Run:
```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-first/tests/unit/common/subtitle/test_segmenter_integration.py::test_pysbd_global_sentence_first -v
```
Expected: FAIL（因为尚未实现全局 PySBD 分句映射逻辑）

**Step 3: 仅提交测试变更**

```bash
git add tests/unit/common/subtitle/test_segmenter_integration.py
git commit -m "test(subtitle): 添加全局语义分句用例"
```

---

### Task 2: 实现 PySBD 全局语义分句 + 句界映射

**Files:**
- Modify: `services/common/subtitle/segmenter.py`
- Test: `tests/unit/common/subtitle/test_segmenter_integration.py::test_pysbd_global_sentence_first`

**Step 1: 写最小实现（全局语义句界优先）**

```python
# 伪代码结构，具体放入 segmenter.py

def _build_text_and_offsets(self, words):
    text_parts = []
    offsets = []
    cursor = 0
    for word in words:
        token = str(word.get("word", ""))
        start = cursor
        cursor += len(token)
        end = cursor
        text_parts.append(token)
        offsets.append((start, end))
    return "".join(text_parts), offsets


def _apply_pysbd_global_split(self, words, language):
    text, offsets = self._build_text_and_offsets(words)
    if not text:
        return []
    segmenter = self._get_pysbd_segmenter(language)
    sentences = segmenter.segment(text)
    if sum(len(s) for s in sentences) != len(text):
        logger.warning("PySBD 句界长度不匹配，回退")
        return []
    result = []
    cursor = 0
    word_idx = 0
    for sent in sentences:
        sent_end = cursor + len(sent)
        seg = []
        while word_idx < len(words) and offsets[word_idx][1] <= sent_end:
            seg.append(words[word_idx])
            word_idx += 1
        if not seg and word_idx < len(words):
            seg.append(words[word_idx])
            word_idx += 1
        if seg:
            result.append(seg)
        cursor = sent_end
    if word_idx < len(words):
        result[-1].extend(words[word_idx:])
    return result
```

**Step 2: 修改 segmenter.segment 流程**
- 若 `_pysbd_available` 且语言支持，优先调用 `_apply_pysbd_global_split`；若返回空则回退到强标点。

**Step 3: 容器内运行测试，确认通过**

Run:
```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-first/tests/unit/common/subtitle/test_segmenter_integration.py::test_pysbd_global_sentence_first -v
```
Expected: PASS

**Step 4: 提交实现**

```bash
git add services/common/subtitle/segmenter.py
git commit -m "feat(subtitle): 全局语义句界优先分句"
```

---

### Task 3: 弱标点导致极短片段的中段平均分割

**Files:**
- Modify: `services/common/subtitle/segmenter.py`
- Modify: `tests/unit/common/subtitle/test_segmenter_integration.py`

**Step 1: 写失败用例（弱标点不产生 1-2 字符片段）**

```python
def test_weak_punctuation_no_tiny_segment(segmenter, monkeypatch):
    # 禁用 PySBD，确保走兜底逻辑
    monkeypatch.setattr(segmenter, "_pysbd_available", False)
    words = [
        {"word": "So,", "start": 0.0, "end": 0.5},
        {"word": " ", "start": 0.5, "end": 0.5},
        {"word": "let", "start": 0.5, "end": 0.8},
        {"word": " ", "start": 0.8, "end": 0.8},
        {"word": "me", "start": 0.8, "end": 1.0},
        {"word": " ", "start": 1.0, "end": 1.0},
        {"word": "answer", "start": 1.0, "end": 1.4},
    ]
    result = segmenter.segment(words, max_cpl=6)
    assert all(len("".join(w["word"] for w in seg).strip()) > 2 for seg in result)
```

**Step 2: 容器内运行测试，确认失败**

Run:
```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-first/tests/unit/common/subtitle/test_segmenter_integration.py::test_weak_punctuation_no_tiny_segment -v
```
Expected: FAIL（当前弱标点切分会产生极短片段）

**Step 3: 实现中段平均分割逻辑**
- 在 `_fallback_split` 或 `split_by_weak_punctuation` 返回结果后检查：若任一片段字符数 ≤ 2，则改用 `split_by_word_count` 强制平均切分。
- 只调整词的归属片段，不改变 `start/end`。

**Step 4: 容器内运行测试，确认通过**

Run:
```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-first/tests/unit/common/subtitle/test_segmenter_integration.py::test_weak_punctuation_no_tiny_segment -v
```
Expected: PASS

**Step 5: 提交实现**

```bash
git add services/common/subtitle/segmenter.py
git add tests/unit/common/subtitle/test_segmenter_integration.py
git commit -m "fix(subtitle): 弱标点极短片段改用平均分割"
```

---

### Task 4: 缩写/连字符与空格修复（不改时间戳）

**Files:**
- Modify: `services/common/subtitle/word_level_aligner.py`
- Modify: `services/common/subtitle/segmenter.py`
- Modify: `services/common/subtitle/abbreviations.py`
- Test: `tests/unit/common/subtitle/test_word_level_aligner.py`
- Test: `tests/unit/common/subtitle/test_segmenter_integration.py`

**Step 1: 写失败用例（"S. It's" 与连字符不切分）**

```python
# test_word_level_aligner.py

def test_aligner_inserts_space_after_period():
    words = [
        {"word": " U.", "start": 0.0, "end": 0.2},
        {"word": " S.", "start": 0.2, "end": 0.4},
        {"word": " It's", "start": 0.4, "end": 0.6},
    ]
    result = align_words_to_text(words, "U.S. It's")
    assert "".join(w["word"] for w in result).strip() == "U.S. It's"

# test_segmenter_integration.py

def test_hyphen_not_split_as_weak_punct(segmenter, monkeypatch):
    monkeypatch.setattr(segmenter, "_pysbd_available", False)
    words = [
        {"word": "snap-", "start": 0.0, "end": 0.4},
        {"word": "-trap", "start": 0.4, "end": 0.8},
        {"word": " ", "start": 0.8, "end": 0.8},
        {"word": "jaws", "start": 0.8, "end": 1.2},
    ]
    result = segmenter.segment(words, max_cpl=6)
    assert len(result) == 1
    assert len(result[0]) == 4
```

**Step 2: 容器内运行测试，确认失败**

Run:
```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-first/tests/unit/common/subtitle/test_word_level_aligner.py::test_aligner_inserts_space_after_period -v
```
Expected: FAIL

Run:
```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-first/tests/unit/common/subtitle/test_segmenter_integration.py::test_hyphen_not_split_as_weak_punct -v
```
Expected: FAIL

**Step 3: 实现修复**
- 调整 `_WORD_PATTERN` 支持带撇号的英文词（如 `It's`），让空格插入逻辑生效。
- 在 `split_by_strong_punctuation` 增加“单字母缩写 + 下一词首字母缩写”判定，避免 `U.` 被当句末。
- 在 `split_by_weak_punctuation` 中将 `-` 仅视为弱标点当 `word_text` 仅为 `-`/`–`/`—`，否则不切分。
- 扩充 `COMMON_ABBREVIATIONS`（如 `u.s.`）以兼容回退路径。

**Step 4: 容器内运行测试，确认通过**

Run:
```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-first/tests/unit/common/subtitle/test_word_level_aligner.py::test_aligner_inserts_space_after_period -v
```
Expected: PASS

Run:
```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-first/tests/unit/common/subtitle/test_segmenter_integration.py::test_hyphen_not_split_as_weak_punct -v
```
Expected: PASS

**Step 5: 提交实现**

```bash
git add services/common/subtitle/word_level_aligner.py
git add services/common/subtitle/segmenter.py
git add services/common/subtitle/abbreviations.py
git add tests/unit/common/subtitle/test_word_level_aligner.py
git add tests/unit/common/subtitle/test_segmenter_integration.py
git commit -m "fix(subtitle): 修复缩写/连字符断句与空格"
```

---

### Task 5: 全量回归（容器内）

**Files:**
- Test: `tests/unit/common/subtitle/*`

**Step 1: 运行字幕相关单测**

Run:
```bash
docker exec -i wservice pytest /app/.worktrees/subtitle-semantic-first/tests/unit/common/subtitle -v
```
Expected: PASS

**Step 2: 记录结果**
- 若失败，回到对应 Task 修复并补充用例。

---

Plan complete and saved to `docs/plans/2026-01-29-subtitle-semantic-first-implementation-plan.md`.
Two execution options:

1. Subagent-Driven (this session) — I dispatch a fresh subagent per task, review between tasks, fast iteration
2. Parallel Session (separate) — Open new session with executing-plans, batch execution with checkpoints

Which approach?
