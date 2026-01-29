# 字幕重构断句逻辑设计方案

## 1. 背景与问题

### 1.1 当前问题

当前 `wservice.rebuild_subtitle_with_words` 执行器在处理优化后的字幕时，存在以下断句问题：

1. **词级对齐错误**: "U.S." 被错误断开为 "U." 和 "S.It's"
2. **单词合并错误**: "snap--trap" 出现双连字符
3. **新增词时间戳缺失**: 优化文本新增词汇（如 "a hundred" 中的 "a"）无法正确分配时间戳
4. **缩写误判**: "Dr./Mr./Mrs." 等缩写中的句点被误判为句子结束

### 1.2 需求目标

设计一套**多语言支持**的字幕断句逻辑，满足：
- 保持语义完整性（不在从句中间断开）
- 保持单词完整性（不切开单词）
- 满足 CPL/CPS 限制
- 支持中英日韩等主流语言

---

## 2. 设计原则

| 原则 | 说明 |
|------|------|
| **KISS** | 优先使用规则而非复杂 ML 模型 |
| **渐进增强** | 先实现基础层，再引入增强层 |
| **语言无关兜底** | 提供不依赖特定语言模型的 fallback 方案 |
| **时间戳保真** | 断句必须保持词级时间戳的精确性 |

---

## 3. 三层断句策略

### 3.1 第一层：强标点断句

**触发条件**: 遇到句子结束标点

**强标点定义**:
```python
STRONG_PUNCTUATION = {".", "!", "?", "。", "！", "？", "…"}
```

**逻辑**:
```python
def split_by_strong_punctuation(words: list[dict]) -> list[list[dict]]:
    """在强标点处断句"""
    segments = []
    current = []

    for word in words:
        current.append(word)
        text = word.get("word", "").strip()

        # 检查是否以强标点结尾（排除缩写）
        if text and text[-1] in STRONG_PUNCTUATION:
            if not is_abbreviation(text):
                segments.append(current)
                current = []

    if current:
        segments.append(current)

    return segments
```

**缩写识别规则**:
```python
COMMON_ABBREVIATIONS = {
    "mr.", "mrs.", "ms.", "dr.", "prof.", "st.",
    "u.s.", "u.k.", "e.g.", "i.e.", "etc.",
    "jan.", "feb.", "mar.", "apr.", "jun.", "jul.",
    "aug.", "sep.", "oct.", "nov.", "dec."
}

def is_abbreviation(word: str) -> bool:
    return word.lower() in COMMON_ABBREVIATIONS
```

---

### 3.2 第二层：PySBD 语义断句

**适用场景**: 强标点断句后，仍存在超过 CPL 限制的片段

**支持语言** (22种):
```python
PYSBD_LANGS = {
    "en", "de", "es", "fr", "it", "pt", "ru", "nl", "da", "fi",
    "zh", "ja", "ko", "ar", "hi", "pl", "cs", "sk", "tr", "el",
    "he", "fa"
}
```

**实现**:
```python
from pysbd import Segmenter

class PySBDSemanticSplitter:
    def __init__(self):
        self._segmenters = {}

    def split(self, words: list[dict], language: str) -> list[list[dict]]:
        if language not in PYSBD_LANGS:
            return [words]  # 不支持的语言，直接返回

        segmenter = self._get_segmenter(language)
        text = "".join(w.get("word", "") for w in words)

        # PySBD 返回句子边界（字符位置）
        sentences = segmenter.segment(text)

        # 将字符位置映射回词索引
        return self._map_to_word_segments(words, sentences)

    def _map_to_word_segments(self, words: list[dict], sentences: list[str]) -> list[list[dict]]:
        """将 PySBD 的字符级分割映射为词级分割"""
        segments = []
        word_idx = 0

        for sent in sentences:
            sent_words = []
            sent_text = ""

            while word_idx < len(words) and sent_text.strip() != sent.strip():
                word = words[word_idx]
                sent_words.append(word)
                sent_text += word.get("word", "")
                word_idx += 1

            if sent_words:
                segments.append(sent_words)

        return segments

    def _get_segmenter(self, language: str) -> Segmenter:
        if language not in self._segmenters:
            self._segmenters[language] = Segmenter(language=language, clean=False)
        return self._segmenters[language]
```

---

### 3.3 第三层：通用规则兜底

**触发条件**: 前两层处理后，仍存在超 CPL/CPS 限制的片段

**策略 3.1: 弱标点断句**

```python
WEAK_PUNCTUATION = {
    ",", "，", "、", ";", ":", "：", "-", "–", "—"
}

def split_by_weak_punctuation(words: list[dict], max_cpl: int) -> list[list[dict]]:
    """在弱标点处断句，保持单词完整性"""
    text = "".join(w.get("word", "") for w in words)

    if len(text) <= max_cpl:
        return [words]

    # 收集所有弱标点位置
    candidates = []
    for i, word in enumerate(words[:-1]):
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

**策略 3.2: 基于停顿时间的断句**

```python
PAUSE_THRESHOLD = 0.3  # 300ms 停顿视为潜在断句点

def split_by_pause(words: list[dict], max_cpl: int) -> list[list[dict]]:
    """在长时间停顿处断句"""
    text = "".join(w.get("word", "") for w in words)

    if len(text) <= max_cpl:
        return [words]

    # 找出所有超过阈值的停顿
    candidates = []
    for i in range(len(words) - 1):
        gap = words[i + 1]["start"] - words[i]["end"]
        if gap > PAUSE_THRESHOLD:
            candidates.append((i, gap))

    if not candidates:
        return [words]  # 无合适停顿，进入下一步

    # 选择最接近中间位置且停顿最长的
    mid = len(words) // 2
    best_split = max(candidates, key=lambda x: (x[1], -abs(x[0] - mid)))[0]

    left = words[:best_split + 1]
    right = words[best_split + 1:]

    return split_by_pause(left, max_cpl) + split_by_pause(right, max_cpl)
```

**策略 3.3: 字数平均分割（最终兜底）**

```python
def split_by_word_count(words: list[dict], max_cpl: int) -> list[list[dict]]:
    """
    按字数平均分割，保持单词完整性
    分割策略: 22+21 而非 21+22（前半部分略长更自然）
    """
    text = "".join(w.get("word", "") for w in words)

    if len(text) <= max_cpl:
        return [words]

    # 计算需要的分段数
    num_segments = (len(text) + max_cpl - 1) // max_cpl
    target_len = len(text) // num_segments

    # 寻找最接近目标长度的单词边界
    best_split = 0
    current_len = 0

    for i, word in enumerate(words):
        word_len = len(word.get("word", ""))
        if current_len + word_len / 2 >= target_len:
            best_split = i
            break
        current_len += word_len

    if best_split == 0:
        best_split = len(words) // 2

    left = words[:best_split]
    right = words[best_split:]

    return split_by_word_count(left, max_cpl) + split_by_word_count(right, max_cpl)
```

---

## 4. 整合流程

```python
class MultilingualSubtitleSegmenter:
    """多语言字幕断句器"""

    def __init__(self):
        self.pysbd_splitter = PySBDSemanticSplitter()

    def segment(
        self,
        words: list[dict],
        language: str = "en",
        max_cpl: int = 42,
        max_cps: float = 18.0
    ) -> list[list[dict]]:
        """
        三层断句策略整合
        """
        # 第1层: 强标点断句
        segments = split_by_strong_punctuation(words)

        # 第2层: 对超长片段使用 PySBD
        result = []
        for seg in segments:
            text = "".join(w.get("word", "") for w in seg)
            if len(text) > max_cpl and language in PYSBD_LANGS:
                sub_segments = self.pysbd_splitter.split(seg, language)
                result.extend(sub_segments)
            else:
                result.append(seg)

        # 第3层: 兜底处理
        final_result = []
        for seg in result:
            if not self._within_limits(seg, max_cpl, max_cps):
                fixed = self._fallback_split(seg, max_cpl)
                final_result.extend(fixed)
            else:
                final_result.append(seg)

        return final_result

    def _fallback_split(self, words: list[dict], max_cpl: int) -> list[list[dict]]:
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

    def _within_limits(self, words: list[dict], max_cpl: int, max_cps: float) -> bool:
        """检查是否满足 CPL/CPS 限制"""
        text = "".join(w.get("word", "") for w in words)
        if len(text) > max_cpl:
            return False

        if len(words) >= 2:
            duration = words[-1]["end"] - words[0]["start"]
            if duration > 0 and len(text) / duration > max_cps:
                return False

        return True
```

---

## 5. 数据结构

### 5.1 输入

```python
words: list[dict] = [
    {
        "word": " Hello",
        "start": 0.0,
        "end": 0.5,
        "probability": 0.95  # 可选
    },
    # ...
]
```

### 5.2 输出

```python
segments: list[list[dict]] = [
    [
        {"word": " Hello", "start": 0.0, "end": 0.5},
        {"word": " world.", "start": 0.5, "end": 1.0}
    ],
    # ...
]
```

---

## 6. 依赖管理

### 6.1 必需依赖

无。基础实现完全使用 Python 标准库。

### 6.2 可选依赖

```txt
# requirements-extra.txt
pysbd>=0.3.4  # 用于第二层语义断句
```

### 6.3 动态导入

```python
def _try_import_pysbd():
    try:
        from pysbd import Segmenter
        return Segmenter
    except ImportError:
        return None
```

---

## 7. 测试策略

### 7.1 单元测试

```python
def test_strong_punctuation_split():
    words = [
        {"word": " Hello", "start": 0.0, "end": 0.5},
        {"word": " world.", "start": 0.5, "end": 1.0},
        {"word": " Next", "start": 1.5, "end": 2.0},
        {"word": " sentence.", "start": 2.0, "end": 2.5}
    ]
    result = split_by_strong_punctuation(words)
    assert len(result) == 2
```

### 7.2 多语言测试用例

| 语言 | 测试文本 | 期望断句点 |
|------|----------|-----------|
| 英文 | "Hello world. This is a test." | 在 "world." 后 |
| 中文 | "你好世界。这是一个测试。" | 在 "世界。" 后 |
| 日文 | "こんにちは世界。これはテストです。" | 在 "世界。" 后 |
| 混合 | "Hello 世界. This is 测试." | 在 "世界." 后 |

### 7.3 边界测试

```python
def test_abbreviation_not_split():
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
```

---

## 8. 实施计划

### Phase 1: 基础层实现 (优先级: 高)
- [ ] 实现 `split_by_strong_punctuation`
- [ ] 实现 `split_by_word_count`
- [ ] 集成到 `word_level_aligner.py`
- [ ] 编写单元测试

### Phase 2: 增强层实现 (优先级: 中)
- [ ] 实现 `PySBDSemanticSplitter`
- [ ] 添加 `pysbd` 可选依赖
- [ ] 实现弱标点/停顿时间断句
- [ ] 多语言测试用例

### Phase 3: 优化与完善 (优先级: 低)
- [ ] 性能优化（大文件处理）
- [ ] 添加更多缩写词
- [ ] 支持用户自定义断句规则

---

## 9. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| PySBD 不支持目标语言 | 中 | 中 | 有通用规则兜底 |
| 缩写词识别不完整 | 高 | 低 | 用户可配置扩展列表 |
| 时间戳精度丢失 | 低 | 高 | 严格基于词级时间戳操作 |
| 性能瓶颈（大文件） | 低 | 中 | 使用生成器惰性处理 |

---

## 10. 附录

### 10.1 相关文件

- `services/common/subtitle/word_level_aligner.py` - 现有断句逻辑
- `services/workers/wservice/executors/rebuild_subtitle_with_words_executor.py` - 调用入口

### 10.2 参考链接

- [PySBD 文档](https://github.com/nipunsadvilkar/pySBD)
- [spaCy Sentence Segmentation](https://spacy.io/usage/linguistic-features#sbd)

---

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
