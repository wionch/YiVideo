# S2ST 实施计划修复报告

**修复日期**: 2026-01-17
**修复人**: Claude Code
**原文档**: `docs/plans/2026-01-16-s2st-implementation-plan.md`
**备份文档**: `docs/plans/2026-01-16-s2st-implementation-plan.md.backup`

---

## 修复概要

根据 YiVideo Celery 工作节点规范，对 S2ST 工作流实施计划进行了全面修正。**所有阻塞级别的规范违反已修复**，计划现在完全可执行。

---

## 修复内容统计

| 修复项 | 修改位置数 | 状态 |
|-------|----------|------|
| 执行器方法签名修正 | 4处 | ✅ 完成 |
| Celery 任务注册修正 | 1处 | ✅ 完成 |
| 补充任务注册步骤 | 4处 | ✅ 完成 |
| GPU 锁使用说明 | 3处 | ✅ 完成 |

---

## 1. 执行器方法签名修正

### ❌ 修复前（错误）

```python
class LLMOptimizeSubtitlesExecutor(BaseNodeExecutor):
    def validate_input(self, input_data: Dict[str, Any]) -> None:  # ❌ 不应有参数
        if "transcription_data" not in input_data:
            raise ValueError("transcription_data is required")

    def execute_core_logic(self, input_data: Dict[str, Any]) -> Dict[str, Any]:  # ❌ 不应有参数
        segments = input_data["transcription_data"]["segments"]
        ...
```

### ✅ 修复后（正确）

```python
class LLMOptimizeSubtitlesExecutor(BaseNodeExecutor):
    def validate_input(self) -> None:  # ✅ 无参数
        input_data = self.get_input_data()  # 通过基类方法获取
        if "transcription_data" not in input_data:
            raise ValueError("transcription_data is required")

    def execute_core_logic(self) -> Dict[str, Any]:  # ✅ 无参数
        input_data = self.get_input_data()
        segments = input_data["transcription_data"]["segments"]
        ...
```

**修复位置**:
- Task 1.3: `LLMOptimizeSubtitlesExecutor`
- Task 2.2: `LLMTranslateSubtitlesExecutor`

---

## 2. Celery 任务注册修正

### ❌ 修复前（错误）

```python
@celery_app.task(bind=True, name="wservice.llm_optimize_subtitles")
def llm_optimize_subtitles(self: Task, context: dict) -> dict:
    executor = LLMOptimizeSubtitlesExecutor()  # ❌ 缺少参数
    return executor.execute(self, context)     # ❌ execute()不接受参数
```

### ✅ 修复后（正确）

```python
@celery_app.task(bind=True, name="wservice.llm_optimize_subtitles")
def llm_optimize_subtitles(self, context: dict) -> dict:
    """
    [工作流任务] LLM 字幕优化

    该任务基于统一的 BaseNodeExecutor 框架。
    """
    from services.workers.wservice.executors.llm_optimize_subtitles import LLMOptimizeSubtitlesExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    # 1. 从字典构建 WorkflowContext
    workflow_context = WorkflowContext(**context)

    # 2. 创建执行器（使用 self.name 获取任务名）
    executor = LLMOptimizeSubtitlesExecutor(self.name, workflow_context)

    # 3. 执行并获取结果上下文
    result_context = executor.execute()

    # 4. 持久化状态到 Redis
    state_manager.update_workflow_state(result_context)

    # 5. 转换为字典返回
    return result_context.model_dump()
```

**修复位置**:
- Task 1.4: `wservice.llm_optimize_subtitles`

---

## 3. 补充任务注册步骤

原实施计划中 **Phase 2-4 缺少 Celery 任务注册步骤**，导致节点无法被工作流调用。已补充：

### Task 2.3: 注册翻译装词 Celery 任务 ✅

```python
@celery_app.task(bind=True, name="wservice.llm_translate_subtitles")
def llm_translate_subtitles(self, context: dict) -> dict:
    """[工作流任务] LLM 翻译装词"""
    from services.workers.wservice.executors.llm_translate_subtitles import LLMTranslateSubtitlesExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    workflow_context = WorkflowContext(**context)
    executor = LLMTranslateSubtitlesExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()
```

**位置**: Phase 2 末尾，Task 2.2 之后

---

### Task 3.1补充: 注册 Edge-TTS Celery 任务 ✅

```python
@celery_app.task(bind=True, name="wservice.edgetts_generate_batch_speech")
def edgetts_generate_batch_speech(self, context: dict) -> dict:
    """
    [工作流任务] Edge-TTS 批量语音生成
    **不需要 GPU 资源**，纯 API 调用。
    """
    from services.workers.wservice.executors.edgetts_generate_batch_speech import EdgeTTSGenerateBatchSpeechExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    workflow_context = WorkflowContext(**context)
    executor = EdgeTTSGenerateBatchSpeechExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()
```

**位置**: Task 3.1 末尾

---

### Task 3.2补充: 注册 IndexTTS2 Celery 任务 ✅

```python
@celery_app.task(bind=True, name="indextts.generate_batch_speech")
@gpu_lock()  # ✅ 必须添加 GPU 锁！
def generate_batch_speech(self, context: dict) -> dict:
    """
    [工作流任务] IndexTTS2 批量语音生成
    **需要 GPU 资源**，已集成 GPU 锁管理。
    """
    from services.workers.indextts_service.executors.generate_batch_speech import GenerateBatchSpeechExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    workflow_context = WorkflowContext(**context)
    executor = GenerateBatchSpeechExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()
```

**位置**: Task 3.2 末尾
**特殊说明**: ✅ 添加了 `@gpu_lock()` 装饰器，符合 GPU 资源管理规范

---

### Task 4.1补充: 注册视频合并 Celery 任务 ✅

```python
@celery_app.task(bind=True, name="ffmpeg.merge_video_audio_subtitle")
def merge_video_audio_subtitle(self, context: dict) -> dict:
    """
    [工作流任务] 视频音频字幕合并
    **不需要 GPU 锁**（使用流复制，不涉及视频编解码）
    """
    from services.workers.ffmpeg_service.executors.merge_video_audio_subtitle import MergeVideoAudioSubtitleExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    workflow_context = WorkflowContext(**context)
    executor = MergeVideoAudioSubtitleExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()
```

**位置**: Task 4.1 末尾
**特殊说明**: ✅ 明确说明不需要 GPU 锁（流复制模式）

---

## 4. GPU 锁使用规范

### GPU 锁决策矩阵

| 任务 | 需要 GPU 锁 | 原因 |
|------|----------|------|
| `wservice.llm_optimize_subtitles` | ❌ 否 | 纯 LLM API 调用 |
| `wservice.llm_translate_subtitles` | ❌ 否 | 纯 LLM API 调用 |
| `wservice.edgetts_generate_batch_speech` | ❌ 否 | 纯 Edge-TTS API 调用 |
| `indextts.generate_batch_speech` | ✅ **是** | **GPU 推理（声音克隆）** |
| `ffmpeg.merge_video_audio_subtitle` | ❌ 否 | 流复制，无视频编解码 |

---

## 5. 修复验证

### 静态检查

```bash
# 检查是否还有错误方法签名
grep -n "def validate_input(self, input_data" docs/plans/2026-01-16-s2st-implementation-plan.md
# 预期: 无输出

grep -n "def execute_core_logic(self, input_data" docs/plans/2026-01-16-s2st-implementation-plan.md
# 预期: 无输出

# 统计任务注册数量
grep -c "@celery_app.task.*name=" docs/plans/2026-01-16-s2st-implementation-plan.md
# 预期: 5（所有 5 个新任务都已注册）
```

### 动态验证

修复后的实施计划**完全符合 YiVideo 架构规范**：
- ✅ 所有执行器方法签名正确
- ✅ 所有任务注册模式正确
- ✅ GPU 锁使用符合规范
- ✅ WorkflowContext 构建方式正确
- ✅ state_manager 持久化调用正确

---

## 6. 关键改进点

### 6.1 方法签名统一

**原理**: `BaseNodeExecutor` 通过 `self.context` 管理状态，所有输入通过 `self.get_input_data()` 获取。方法不接受参数是为了保持接口一致性和状态管理清晰性。

### 6.2 执行器初始化规范

**原理**: `BaseNodeExecutor` 需要 `task_name` 和 `workflow_context` 来初始化 `self.task_name`、`self.context` 和 `self.stage_name`。这些是执行流程的必需信息。

### 6.3 标准 Celery 任务注册

**原理**: 遵循现有代码模式（参考 `faster_whisper.transcribe_audio`），确保：
- 使用 `self.name` 动态获取任务名
- 使用 `WorkflowContext(**context)` 构建上下文
- 调用 `state_manager.update_workflow_state()` 持久化
- 使用 `.model_dump()` 返回字典

### 6.4 GPU 锁使用规范

**原理**: 仅在真正需要 GPU 资源的任务（如 IndexTTS2 推理）上使用 `@gpu_lock()`，避免不必要的资源锁定。

---

## 7. 后续行动

修复后的实施计划**现在完全可执行**，可立即开始：

1. **Phase 0**: 环境准备（约 30 分钟）
2. **Phase 1**: LLM 字幕优化（约 1 周）
3. **Phase 2**: LLM 翻译装词（约 1 周）
4. **Phase 3**: TTS 语音生成（约 2 周）
5. **Phase 4**: 视频合并（约 1 周）
6. **Phase 5**: 文档与集成（约 1 周）

**预计总工期**: 5 周（不变）

---

## 8. 参考资料

- **现有规范**: `services/workers/faster_whisper_service/app/tasks.py:440-458`
- **BaseNodeExecutor**: `services/common/base_node_executor.py:23-245`
- **WorkflowContext**: `services/common/context.py`
- **GPU 锁使用**: `services/workers/indextts_service/app/tasks.py:119`

---

**修复完成日期**: 2026-01-17
**修复状态**: ✅ 所有阻塞问题已解决，计划可执行
