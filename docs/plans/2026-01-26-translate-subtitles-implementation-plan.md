# 翻译装词逐行回填 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 新增 `wservice.translate_subtitles` 节点，实现逐行翻译装词并按原分段回填，时间轴不变。

**Architecture:** 新增逐行翻译模块封装 LLM 调用与行数/预算校验；新增 executor 读取 `segments_file`、生成逐行 prompt、调用翻译并回填；输出 `translated_segments_file`。

**Tech Stack:** Python、Celery、现有 `SubtitleTextOptimizer`/PromptLoader/AIProviderFactory、JSON 段文件。

### Task 1: 新增 system prompt 文件

**Files:**
- Create: `config/system_prompt/subtitle_translation_fitting.md`

**Step 1: 写入提示词内容**

```
你是专业的字幕翻译装词助手。

目标：在不改变时间轴、不改变分段数量与顺序的前提下，将字幕逐行翻译为目标语言，并尽量满足阅读速度与行长约束。

强制规则：
1. 输入为多行字幕，每行对应一个字幕段；输出必须逐行对应，行数与顺序严格一致。
2. 行内禁止出现换行符或空行；不要输出编号、列表、JSON、解释或任何多余内容。
3. 每行字符数不得超过该行“字符预算”（预算包含空格与标点）。
4. 若超长，优先通过压缩表达、删语气词、同义替换、缩写来满足预算，但不得新增事实、不得改变语义。
5. 术语与专有名词保持一致。
6. 若原文含有格式标记/标签/说话人标记（如 []、<>、{}、SPEAKER_XX），保持原样不改动。
7. 若目标语言不使用空格，去除不必要空格。

输出：仅输出逐行翻译文本，行数必须与输入一致。
```

**Step 2: 提交**

```bash
git add config/system_prompt/subtitle_translation_fitting.md
git commit -m "feat: 新增翻译装词系统提示词"
```

### Task 2: 逐行翻译模块（TDD）

**Files:**
- Create: `services/common/subtitle/subtitle_line_translator.py`
- Modify: `services/common/subtitle/subtitle_text_optimizer.py`
- Test: `tests/unit/common/subtitle/test_subtitle_line_translator.py`

**Step 1: 写失败测试（行数校验 + 预算校验 + 输出回填）**

```python
from services.common.subtitle.subtitle_line_translator import SubtitleLineTranslator


def test_line_translation_validates_line_count_and_budget():
    segments = [
        {"start": 0.0, "end": 1.0, "text": "Hello"},
        {"start": 1.0, "end": 2.0, "text": "World"},
    ]

    translator = SubtitleLineTranslator(provider="deepseek")

    def fake_ai(_system_prompt, _user_prompt):
        return "".join(["你好\n", "世界太长超预算\n"])

    result = translator.translate_lines(
        segments=segments,
        target_language="zh",
        source_language=None,
        prompt_file_path="/app/config/system_prompt/subtitle_translation_fitting.md",
        ai_call=fake_ai,
        cps_limit=18,
        cpl_limit=42,
        max_retries=1,
    )

    assert result["success"] is False
    assert "超出字符预算" in result["error"]
```

**Step 2: 运行测试确认失败**

Run:
```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
docker exec -it <container_name> bash
pytest /app/tests/unit/common/subtitle/test_subtitle_line_translator.py -v
```
Expected: FAIL，提示模块不存在或校验未实现。

**Step 3: 写最小实现**

```python
class SubtitleLineTranslator:
    def translate_lines(...):
        # 生成逐行输入、调用 AI、校验行数与预算、返回结果
        return {"success": True, "translated_lines": lines}
```

**Step 4: 运行测试确认通过**

Run:
```bash
pytest /app/tests/unit/common/subtitle/test_subtitle_line_translator.py -v
```
Expected: PASS

**Step 5: 提交**

```bash
git add services/common/subtitle/subtitle_line_translator.py \
  services/common/subtitle/subtitle_text_optimizer.py \
  tests/unit/common/subtitle/test_subtitle_line_translator.py
git commit -m "feat: 新增逐行翻译模块"
```

### Task 3: 新增节点执行器（TDD）

**Files:**
- Create: `services/workers/wservice/executors/translate_subtitles_executor.py`
- Modify: `services/workers/wservice/executors/__init__.py`
- Test: `tests/unit/workers/wservice/test_translate_subtitles_executor.py`

**Step 1: 写失败测试（输入校验 + 输出文件路径）**

```python
from unittest.mock import patch

from services.common.context import WorkflowContext
from services.workers.wservice.executors.translate_subtitles_executor import (
    WServiceTranslateSubtitlesExecutor,
)


def test_translate_subtitles_executor_returns_translated_segments_file(tmp_path):
    context = WorkflowContext(
        workflow_id="test-workflow",
        shared_storage_path="/share",
        input_params={"input_data": {
            "segments_file": "/share/segments.json",
            "target_language": "zh"
        }},
        stages={},
    )

    with patch(
        "services.workers.wservice.executors.translate_subtitles_executor.SubtitleLineTranslator"
    ) as translator_cls:
        translator = translator_cls.return_value
        translator.translate_lines.return_value = {
            "success": True,
            "translated_segments": [{"start": 0.0, "end": 1.0, "text": "你好"}],
        }

        executor = WServiceTranslateSubtitlesExecutor("wservice.translate_subtitles", context)
        result_context = executor.execute()

    stage = result_context.stages["wservice.translate_subtitles"]
    assert stage.status == "SUCCESS"
    assert "translated_segments_file" in stage.output
```

**Step 2: 运行测试确认失败**

Run:
```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/workers/wservice/test_translate_subtitles_executor.py -v
```
Expected: FAIL，模块不存在或执行器未实现。

**Step 3: 写最小实现**

```python
class WServiceTranslateSubtitlesExecutor(BaseNodeExecutor):
    def validate_input(self):
        # segments_file 与 target_language
        pass

    def execute_core_logic(self):
        # 读取 segments_file → 调用 SubtitleLineTranslator → 保存 translated_segments_file
        return {"translated_segments_file": output_path}
```

**Step 4: 运行测试确认通过**

Run:
```bash
pytest /app/tests/unit/workers/wservice/test_translate_subtitles_executor.py -v
```
Expected: PASS

**Step 5: 提交**

```bash
git add services/workers/wservice/executors/translate_subtitles_executor.py \
  services/workers/wservice/executors/__init__.py \
  tests/unit/workers/wservice/test_translate_subtitles_executor.py
git commit -m "feat: 新增翻译装词执行器"
```

### Task 4: 任务注册与接口文档（TDD）

**Files:**
- Modify: `services/workers/wservice/app/tasks.py`
- Modify: `services/api_gateway/app/single_task_api.py`
- Modify: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
- Test: `tests/integration/test_node_response_format.py`

**Step 1: 写失败测试（节点返回字段）**

```python
from unittest.mock import patch

from services.common.context import WorkflowContext
from services.workers.wservice.executors import WServiceTranslateSubtitlesExecutor


def test_wservice_translate_subtitles_response_format(validator, base_context):
    context = WorkflowContext(**base_context)
    context.input_params["input_data"] = {
        "segments_file": "/share/segments.json",
        "target_language": "zh"
    }

    with patch.object(
        WServiceTranslateSubtitlesExecutor,
        "execute_core_logic",
        return_value={"translated_segments_file": "/share/translated_segments.json"},
    ):
        executor = WServiceTranslateSubtitlesExecutor("wservice.translate_subtitles", context)
        result_context = executor.execute()

    stage = result_context.stages["wservice.translate_subtitles"]
    assert stage.status == "SUCCESS"
    assert "translated_segments_file" in stage.output
```

**Step 2: 运行测试确认失败**

Run:
```bash
docker exec -it <container_name> bash
pytest /app/tests/integration/test_node_response_format.py -v
```
Expected: FAIL，节点未注册或未实现。

**Step 3: 写最小实现**

- 在 `tasks.py` 注册 `wservice.translate_subtitles` Celery 任务
- 在 `single_task_api.py` 增加节点路由
- 更新 `SINGLE_TASK_API_REFERENCE.md` 的入参/出参说明

**Step 4: 运行测试确认通过**

Run:
```bash
pytest /app/tests/integration/test_node_response_format.py -v
```
Expected: PASS

**Step 5: 提交**

```bash
git add services/workers/wservice/app/tasks.py \
  services/api_gateway/app/single_task_api.py \
  docs/technical/reference/SINGLE_TASK_API_REFERENCE.md \
  tests/integration/test_node_response_format.py
git commit -m "feat: 注册翻译装词节点"
```
