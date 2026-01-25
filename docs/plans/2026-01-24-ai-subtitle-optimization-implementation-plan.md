# AI字幕优化拆分（纯文本AI优化 + 词级重构）Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 拆分现有 AI 字幕优化为“AI纯文本纠错”和“本地词级重构”两个节点，并移除旧节点。

**Architecture:** 新增 `wservice.ai_optimize_text` 负责全文纠错（LLM 输入/输出均为全文文本），新增 `wservice.rebuild_subtitle_with_words` 负责基于原始词级时间戳做文本映射与重建。旧节点 `wservice.ai_optimize_subtitles` 从任务入口、执行器与文档中移除。

**Scope Note:** 拆分后节点不再支持跳过逻辑，是否调用由上层流程决定。

**Parameter Note:** 新节点仅使用 `input_data` 参数，不读取 `params/subtitle_optimization`，不使用 `get_param_with_fallback` 的多层回退；不再支持 `_skipped` 跳过逻辑。

**Text Merge Note:** 全文拼接按 `segments[].text` 原样顺序拼接，拼接前对每段 `text` 做 `strip`，segments 之间用单空格拼接，不换行、不插入其他字符。

**Tech Stack:** Python 3.11、Celery、BaseNodeExecutor、pytest、AIProviderFactory、PromptLoader。

---

### Task 1: 更新节点入口与响应格式测试

**Files:**
- Modify: `services/workers/wservice/app/tasks.py:602-613`（移除旧任务，新增两个新任务）
- Modify: `services/workers/wservice/executors/__init__.py:5-20`（移除旧执行器导入，新增新执行器）
- Modify: `tests/integration/test_node_response_format.py:517-543`（移除旧测试，新增两个新节点测试）

**Step 1: Write the failing test**

在 `tests/integration/test_node_response_format.py` 新增两段测试：

```python
    def test_wservice_ai_optimize_text_response_format(self, validator, base_context):
        from services.workers.wservice.executors import WServiceAIOptimizeTextExecutor

        context = WorkflowContext(**base_context)
        context.input_params["input_data"] = {
            "segments_file": "/share/transcribe.json"
        }

        with patch.object(WServiceAIOptimizeTextExecutor, "execute_core_logic", return_value={
            "optimized_text": "hello world",
            "optimized_text_file": "/share/optimized_text.txt",
            "segments_file": "/share/transcribe.json",
            "stats": {"provider": "deepseek"}
        }):
            executor = WServiceAIOptimizeTextExecutor("wservice.ai_optimize_text", context)
            result_context = executor.execute()

        stage = result_context.stages["wservice.ai_optimize_text"]
        assert stage.status == "SUCCESS"
        assert "optimized_text" in stage.output
        assert "optimized_text_file" in stage.output
        assert "segments_file" in stage.output
        assert "stats" in stage.output

    def test_wservice_rebuild_subtitle_with_words_response_format(self, validator, base_context):
        from services.workers.wservice.executors import WServiceRebuildSubtitleWithWordsExecutor

        context = WorkflowContext(**base_context)
        context.input_params["input_data"] = {
            "segments_file": "/share/transcribe.json",
            "optimized_text": "hello world"
        }

        with patch.object(WServiceRebuildSubtitleWithWordsExecutor, "execute_core_logic", return_value={
            "optimized_segments_file": "/share/optimized_segments.json"
        }):
            executor = WServiceRebuildSubtitleWithWordsExecutor("wservice.rebuild_subtitle_with_words", context)
            result_context = executor.execute()

        stage = result_context.stages["wservice.rebuild_subtitle_with_words"]
        assert stage.status == "SUCCESS"
        assert "optimized_segments_file" in stage.output
```

**Step 2: Run test to verify it fails**

（容器内执行；容器名未知时先 `docker ps`）

```bash
# 宿主机
# docker ps

# 容器内
# docker exec -it <container_name> pytest /app/tests/integration/test_node_response_format.py::TestNodeResponseFormat::test_wservice_ai_optimize_text_response_format -v
```

Expected: FAIL（缺少新执行器/任务注册）。

**Step 3: Write minimal implementation**

- 在 `tasks.py` 添加两个 Celery 任务入口（临时只创建 executor 并执行）。
- 在 `executors/__init__.py` 注册两个新执行器。
- 新建执行器文件（可先返回空结果占位，后续任务再完善）。

**Step 4: Run test to verify it passes**

```bash
# docker exec -it <container_name> pytest /app/tests/integration/test_node_response_format.py::TestNodeResponseFormat::test_wservice_ai_optimize_text_response_format -v
```


---

### Task 2: 纯文本 AI 优化模块与提示词

**Files:**
- Create: `services/common/subtitle/subtitle_text_optimizer.py`
- Modify: `config/system_prompt/subtitle_optimization.md`
- Modify: `services/common/subtitle/prompt_loader.py:92-140`（默认提示词）
- Test: `tests/unit/common/subtitle/test_text_optimizer.py`

**Contract Notes:**
- 纯文本模式：请求与响应均为纯文本，禁止 JSON 指令输出。
- 本地重构不做输出格式判定，默认视为纯文本。
- 允许修改：错别字、标点、大小写、格式规范化。
- 禁止修改：增删内容、合并/拆分句子、语序重排。

**Step 1: Write the failing test**

```python
def test_text_optimizer_calls_ai_provider(mocker):
    from services.common.subtitle.subtitle_text_optimizer import SubtitleTextOptimizer

    optimizer = SubtitleTextOptimizer(provider="deepseek")
    mocker.patch.object(optimizer, "_call_ai", return_value="fixed text")

    result = optimizer.optimize_text(
        segments=[{"id": 1, "text": "helllo"}],
        prompt_file_path=None
    )

    assert result["success"] is True
    assert result["optimized_text"] == "fixed text"
```

**Step 2: Run test to verify it fails**

（容器内执行；容器名未知时先 `docker ps`）

```bash
# 宿主机
# docker ps

# 容器内
# docker exec -it <container_name> pytest /app/tests/unit/common/subtitle/test_text_optimizer.py -v
```

Expected: FAIL（模块不存在）。

**Step 3: Write minimal implementation**

- `SubtitleTextOptimizer`：
  - 通过 `SubtitleExtractor` 读取 segments。
  - 合并全文（按 `segments[].text` 原样顺序拼接，不插入额外字符/换行），调用 `AIProviderFactory.create_provider`。
  - `PromptLoader` 加载强约束纠错提示词。
  - 调用 provider `chat_completion(messages=[system,user])`。
  - 输出 `optimized_text` 与统计信息。

**强约束提示词（示例要点）**
- 仅允许纠错/标点/大小写/格式修正。
- 禁止增删内容、禁止语序重排、禁止合并/拆分句子。
- 输出必须是**完整正文文本**，不允许 JSON 或解释。

**Step 4: Run test to verify it passes**

（容器内执行；容器名未知时先 `docker ps`）

```bash
# 宿主机
# docker ps

# 容器内
# docker exec -it <container_name> pytest /app/tests/unit/common/subtitle/test_text_optimizer.py -v
```


---

### Task 3: 词级对齐算法（时间戳不变）

**Files:**
- Create: `services/common/subtitle/word_level_aligner.py`
- Test: `tests/unit/common/subtitle/test_word_level_aligner.py`

**Alignment Notes:**
- `words[].word` 可能带前导空格与标点（如样例中的 `" Well,"`）。
- 对齐需保持 **words 数量与顺序不变**，仅替换 `word` 文本。
- 输出 `word` 保持原空格/标点风格，避免二次分词导致对齐漂移。

**Step 1: Write the failing test**

```python
def test_word_aligner_preserves_timestamps():
    from services.common.subtitle.word_level_aligner import align_words_to_text

    words = [
        {"word": "helllo", "start": 1.0, "end": 1.2},
        {"word": "world", "start": 1.3, "end": 1.6},
    ]
    result = align_words_to_text(words, "hello world")

    assert result[0]["start"] == 1.0
    assert result[0]["end"] == 1.2
    assert result[0]["word"] == "hello"
```

**Step 2: Run test to verify it fails**

（容器内执行；容器名未知时先 `docker ps`）

```bash
# 宿主机
# docker ps

# 容器内
# docker exec -it <container_name> pytest /app/tests/unit/common/subtitle/test_word_level_aligner.py -v
```

Expected: FAIL（模块不存在）。

**Step 3: Write minimal implementation**

- 基于 `difflib.SequenceMatcher` 对比原词序列与优化文本 token 序列。
- token 规则：字母数字单词 + 标点分离；标点优先合并到前一个词。
- 若对齐置信度低于阈值，保留原词文本并返回错误。
- 返回更新后的 word 列表（数量与顺序保持不变，时间戳不变）。
- 输出 `word` 保留前导空格与标点风格（与输入 `words[].word` 一致）。

**Step 4: Run test to verify it passes**

（容器内执行；容器名未知时先 `docker ps`）

```bash
# 宿主机
# docker ps

# 容器内
# docker exec -it <container_name> pytest /app/tests/unit/common/subtitle/test_word_level_aligner.py -v
```


---

### Task 4: 本地重构执行器

**Files:**
- Create: `services/workers/wservice/executors/rebuild_subtitle_with_words_executor.py`
- Modify: `services/workers/wservice/app/tasks.py`（注册新任务）
- Test: `tests/unit/common/subtitle/test_rebuild_executor.py`（可选）

**Step 1: Write the failing test**

```python
def test_rebuild_executor_outputs_file(mocker):
    from services.workers.wservice.executors.rebuild_subtitle_with_words_executor import WServiceRebuildSubtitleWithWordsExecutor

    context = WorkflowContext(workflow_id="t1", input_params={"input_data": {"segments_file": "/share/a.json", "optimized_text": "hello"}}, stages={})
    executor = WServiceRebuildSubtitleWithWordsExecutor("wservice.rebuild_subtitle_with_words", context)
    mocker.patch.object(executor, "_save_optimized_segments", return_value="/share/out.json")

    result = executor.execute_core_logic()
    assert "optimized_segments_file" in result
```

**Step 2: Run test to verify it fails**

（容器内执行；容器名未知时先 `docker ps`）

```bash
# 宿主机
# docker ps

# 容器内
# docker exec -it <container_name> pytest /app/tests/unit/common/subtitle/test_rebuild_executor.py -v
```

**Step 3: Write minimal implementation**

- 读取 `segments_file` 或 `segments_data`。
- 读取 `optimized_text` 或 `optimized_text_file`。
- 扁平化 words → 调用 `align_words_to_text` → 回填到原 segments。
- 生成 `optimized_segments_file`（用 `build_node_output_path`）。

**Step 4: Run test to verify it passes**

（容器内执行；容器名未知时先 `docker ps`）

```bash
# 宿主机
# docker ps

# 容器内
# docker exec -it <container_name> pytest /app/tests/unit/common/subtitle/test_rebuild_executor.py -v
```


---

### Task 5: 移除旧节点/旧模块与文档更新

**Files:**
- Remove: `services/workers/wservice/executors/ai_optimize_subtitles_executor.py`（旧执行器）
- Remove: `services/common/subtitle/subtitle_optimizer.py`
- Remove: `services/common/subtitle/ai_request_builder.py`
- Remove: `services/common/subtitle/ai_command_parser.py`
- Remove: `services/common/subtitle/command_executor.py`
- Remove: `services/common/subtitle/command_statistics.py`
- Remove: `services/common/subtitle/sliding_window_splitter.py`
- Remove: `services/common/subtitle/concurrent_batch_processor.py`
- Remove: `services/common/subtitle/subtitle_segment_processor.py`
- Remove: `services/common/subtitle/optimized_file_generator.py`
- Remove: `services/common/subtitle/metrics.py`
- Modify: `services/workers/wservice/app/tasks.py:602-613`（删除旧任务）
- Modify: `services/workers/wservice/executors/__init__.py:5-20`（删除旧导入）
- Modify: `services/workers/wservice/executors/prepare_tts_segments_executor.py`（移除旧节点名引用）
- Modify: `services/api_gateway/app/single_task_api.py:400-430`（移除旧节点并新增两节点）
- Modify: `docs/features/AI_SUBTITLE_OPTIMIZATION.md`（改为纯文本流程与新节点）
- Modify: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`（移除旧节点，新增两个新节点）
- Modify: `docs/technical/reference/WORKFLOW_NODES_REFERENCE.md`（移除旧节点说明）
- Modify: `docs/technical/reference/WORKFLOW_EXAMPLES_GUIDE.md`（移除旧节点示例）
- Modify: `docs/technical/IMPLEMENTATION_SUMMARY.md`（移除旧节点清单）
- Modify: `docs/technical/参数统一管理重构施工方案.md`（移除旧节点条目）
- Modify: `docs/migration/node-response-format-v2.md`（移除旧节点条目）
- Modify: `services/common/subtitle/README.md`（移除旧节点示例）

**Step 1: Write the failing test**

- 删除旧节点测试后，运行全量相关测试确保没有旧引用。

**Step 2: Run test to verify it fails**

（容器内执行；容器名未知时先 `docker ps`）

```bash
# 宿主机
# docker ps

# 容器内
# docker exec -it <container_name> pytest /app/tests/integration/test_node_response_format.py -v
```

Expected: FAIL（旧节点引用未清理）。

**Step 3: Write minimal implementation**

- 从 `tasks.py` 移除 `wservice.ai_optimize_subtitles` 任务入口。
- 从 `executors/__init__.py` 移除旧执行器导出。
- 删除旧模块并清理其所有引用（含 `tasks.py` 与 `prepare_tts_segments_executor.py`）。
- 更新 API 网关支持列表：移除旧节点并新增 `wservice.ai_optimize_text` 与 `wservice.rebuild_subtitle_with_words`。
- 更新文档与示例，确保不再出现 `wservice.ai_optimize_subtitles`：
  - `docs/features/AI_SUBTITLE_OPTIMIZATION.md`：更新整体流程、输入输出与提示词。
  - `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`：新增两节点参数表与示例。
  - `docs/technical/reference/WORKFLOW_NODES_REFERENCE.md`、`docs/technical/reference/WORKFLOW_EXAMPLES_GUIDE.md`、`docs/technical/IMPLEMENTATION_SUMMARY.md`、`docs/technical/参数统一管理重构施工方案.md`、`docs/migration/node-response-format-v2.md`、`services/common/subtitle/README.md`。

**Step 4: Run test to verify it passes**

（容器内执行；容器名未知时先 `docker ps`）

```bash
# 宿主机
# docker ps

# 容器内
# docker exec -it <container_name> pytest /app/tests/integration/test_node_response_format.py -v
```


---

## 执行说明
- 基线测试已按用户要求跳过。
- 所有测试与调试必须在 Docker 容器内执行（参考 `@yivideo-docker-testing`）。

---

### 执行交接

Plan complete and saved to `docs/plans/2026-01-24-ai-subtitle-optimization-implementation-plan.md`. Two execution options:

1. **Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration
2. **Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
