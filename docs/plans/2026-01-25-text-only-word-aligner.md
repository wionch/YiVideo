# 纯文本词级对齐与标点断句 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不改变词级时间戳的前提下，支持 LLM 增删改，并按标点与字数/时长规则重构字幕分段。

**Architecture:** 基于编辑距离对齐原始词序列与优化词序列，插入词并入相邻词文本，删除词清空文本但保留时间戳；随后按标点优先、CPL/CPS/时长兜底的规则重新切分 segment，时间轴完全保持不变。

**Tech Stack:** Python, difflib.SequenceMatcher, pytest。

**说明:** 用户要求不使用 git 操作；计划中的“提交”步骤仅作占位，不执行。

### Task 1: 词级对齐插入/删除规则

**Files:**
- Modify: `services/common/subtitle/word_level_aligner.py`
- Test: `tests/unit/common/subtitle/test_word_level_aligner.py`

**Step 1: Write the failing test**

```python
def test_word_aligner_handles_insert_and_delete():
    words = [
        {"word": " hello", "start": 0.0, "end": 0.5},
        {"word": " world", "start": 0.5, "end": 1.0},
    ]
    # 插入“brave”，删除“world”
    result = align_words_to_text(words, "hello brave")
    assert result[0]["word"] == " hello brave"
    assert result[1]["word"] == ""
    assert result[1]["start"] == 0.5
```

**Step 2: Run test to verify it fails**

Run (容器内): `docker exec -it <container_name> pytest /app/tests/unit/common/subtitle/test_word_level_aligner.py -v`
Expected: FAIL (插入/删除未处理)

**Step 3: Write minimal implementation**

```python
# 使用 SequenceMatcher 操作序列，插入词并入相邻词，删除词清空文本但保留时间戳
```

**Step 4: Run test to verify it passes**

Run (容器内): `docker exec -it <container_name> pytest /app/tests/unit/common/subtitle/test_word_level_aligner.py -v`
Expected: PASS

**Step 5: Commit**

```bash
# 按用户要求不执行
```

### Task 2: 标点优先断句 + CPL/CPS/时长兜底

**Files:**
- Modify: `services/common/subtitle/word_level_aligner.py`
- Modify: `services/workers/wservice/executors/rebuild_subtitle_with_words_executor.py`
- Test: `tests/unit/common/subtitle/test_rebuild_executor.py`

**Step 1: Write the failing test**

```python
def test_rebuild_executor_splits_by_punctuation_and_limits():
    context = WorkflowContext(
        workflow_id="t1",
        shared_storage_path="/share",
        input_params={
            "input_data": {
                "segments_data": [
                    {
                        "words": [
                            {"word": " hello", "start": 0.0, "end": 0.5},
                            {"word": " world.", "start": 0.5, "end": 1.0},
                            {"word": " next", "start": 1.0, "end": 1.5},
                            {"word": " line", "start": 1.5, "end": 2.0},
                        ]
                    }
                ],
                "optimized_text": "hello world. next line",
            }
        },
        stages={},
    )
    executor = WServiceRebuildSubtitleWithWordsExecutor(
        "wservice.rebuild_subtitle_with_words",
        context,
    )
    executor._save_optimized_segments = MagicMock(return_value="/share/out.json")

    result = executor.execute_core_logic()
    segments = executor._load_segments(context.input_params["input_data"])
    assert result["optimized_segments_file"]
```

**Step 2: Run test to verify it fails**

Run (容器内): `docker exec -it <container_name> pytest /app/tests/unit/common/subtitle/test_rebuild_executor.py -v`
Expected: FAIL (未重建分段)

**Step 3: Write minimal implementation**

```python
# 基于词列表重建 segment：标点优先分段，CPL/CPS/时长兜底；时间戳取段内首末词
# 删除词 word=="" 不计入文本长度，但保留时间轴
```

**Step 4: Run test to verify it passes**

Run (容器内): `docker exec -it <container_name> pytest /app/tests/unit/common/subtitle/test_rebuild_executor.py -v`
Expected: PASS

**Step 5: Commit**

```bash
# 按用户要求不执行
```

### Task 3: 文档与行为说明更新

**Files:**
- Modify: `services/common/subtitle/README.md`

**Step 1: Write the failing test**

```python
# 文档更新不需要测试
```

**Step 2: Run test to verify it fails**

Run: `# 跳过`
Expected: N/A

**Step 3: Write minimal implementation**

```markdown
# 补充说明：允许文本增删改，词级时间戳不变；断句按标点与CPL/CPS/时长兜底
```

**Step 4: Run test to verify it passes**

Run: `# 跳过`
Expected: N/A

**Step 5: Commit**

```bash
# 按用户要求不执行
```
