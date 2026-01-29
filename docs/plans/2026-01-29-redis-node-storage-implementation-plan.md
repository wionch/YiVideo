# Redis 任务节点存储拆分实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 将任务状态从单一键拆分为按节点存储，并保持对外接口格式不变且 TTL 固定 1 天。

**架构:** 在 `state_manager` 中改写读写逻辑，写入 `{task_id}:node:{task_name}` 单节点键；读取时扫描并聚合多个节点键形成统一 `WorkflowContext` 视图；删除时按前缀批量清理。

**技术栈:** Python, Redis (redis-py), FastAPI API Gateway, Celery, pytest

---

### 任务 1：新增节点键行为的单元测试

**文件:**
- 新增: `tests/unit/common/state_manager/test_node_storage.py`
- 新增: `tests/unit/common/state_manager/__init__.py`

**步骤 1：编写失败用例（测试骨架 + FakeRedis）**

```python
# tests/unit/common/state_manager/test_node_storage.py
# -*- coding: utf-8 -*-

import pytest

import services.common.state_manager as state_manager
from services.common.context import WorkflowContext


class FakeRedis:
    def __init__(self):
        self.storage = {}
        self.ttl = {}

    def setex(self, key, ttl_seconds, value):
        self.storage[key] = value
        self.ttl[key] = ttl_seconds
        return True

    def set(self, key, value, keepttl=False):
        self.storage[key] = value
        if not keepttl:
            self.ttl.pop(key, None)
        return True

    def get(self, key):
        return self.storage.get(key)

    def delete(self, *keys):
        removed = 0
        for key in keys:
            if key in self.storage:
                removed += 1
                self.storage.pop(key, None)
                self.ttl.pop(key, None)
        return removed

    def scan_iter(self, match=None, count=10):
        if not match:
            for key in list(self.storage.keys()):
                yield key
            return
        prefix = match[:-1] if match.endswith("*") else match
        for key in list(self.storage.keys()):
            if key.startswith(prefix):
                yield key


def _build_context(task_id="task-1", task_name="ffmpeg.extract_audio"):
    return WorkflowContext(
        workflow_id=task_id,
        create_at="2026-01-29T00:00:00",
        input_params={
            "task_name": task_name,
            "input_data": {"video_path": "demo.mp4"},
            "callback_url": None,
        },
        shared_storage_path=f"/share/workflows/{task_id}",
        stages={
            task_name: {
                "status": "SUCCESS",
                "output": {"audio_path": "/share/workflows/demo.wav"},
                "error": None,
                "duration": 1.0,
            }
        },
        error=None,
    )


def test_create_workflow_state_writes_node_key(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(state_manager, "redis_client", fake)

    context = _build_context()
    state_manager.create_workflow_state(context)

    key = f"{context.workflow_id}:node:{context.input_params['task_name']}"
    assert key in fake.storage
    assert fake.ttl[key] == 24 * 60 * 60


def test_get_workflow_state_aggregates_nodes(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(state_manager, "redis_client", fake)

    ctx_a = _build_context(task_name="ffmpeg.extract_audio")
    ctx_b = _build_context(task_name="faster_whisper.transcribe")

    state_manager.create_workflow_state(ctx_a)
    state_manager.create_workflow_state(ctx_b)

    merged = state_manager.get_workflow_state(ctx_a.workflow_id)
    assert merged["workflow_id"] == ctx_a.workflow_id
    assert "stages" in merged
    assert "ffmpeg.extract_audio" in merged["stages"]
    assert "faster_whisper.transcribe" in merged["stages"]


def test_create_workflow_state_requires_task_name(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(state_manager, "redis_client", fake)

    context = WorkflowContext(
        workflow_id="task-2",
        create_at="2026-01-29T00:00:00",
        input_params={
            "input_data": {"video_path": "demo.mp4"},
            "callback_url": None,
        },
        shared_storage_path="/share/workflows/task-2",
        stages={
            "ffmpeg.extract_audio": {
                "status": "SUCCESS",
                "output": {"audio_path": "/share/workflows/demo.wav"},
                "error": None,
                "duration": 1.0,
            },
            "faster_whisper.transcribe": {
                "status": "SUCCESS",
                "output": {"text": "demo"},
                "error": None,
                "duration": 2.0,
            },
        },
        error=None,
    )

    with pytest.raises(ValueError):
        state_manager.create_workflow_state(context)
```

**步骤 2：运行测试，确认失败**

宿主机：

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
```

容器内：

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/common/state_manager/test_node_storage.py -v
```

预期：失败（当前实现仍是 `workflow_state:{task_id}` 或未强制 task_name）。

**步骤 3：补齐 `__init__.py`（如 pytest 导入需要）**

```python
# tests/unit/common/state_manager/__init__.py
# -*- coding: utf-8 -*-
```

**步骤 4：再次运行测试确认仍失败**

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/common/state_manager/test_node_storage.py -v
```

**步骤 5：提交**

```bash
git add tests/unit/common/state_manager/__init__.py tests/unit/common/state_manager/test_node_storage.py
git commit -m "test(common): 添加节点键存储单测"
```

---

### 任务 2：state_manager 按节点键读写与聚合

**文件:**
- 修改: `services/common/state_manager.py`

**步骤 1：实现节点键生成与节点视图构建（最小实现）**

```python
NODE_TTL_SECONDS = 24 * 60 * 60


def _get_node_key(task_id: str, task_name: str) -> str:
    """生成用于Redis的节点键。"""
    return f"{task_id}:node:{task_name}"


def _build_node_view(context: WorkflowContext) -> WorkflowContext:
    """仅保留当前 task_name 的阶段数据，生成单节点视图。"""
    task_name = (context.input_params or {}).get("task_name")
    if not task_name:
        raise ValueError("task_name 缺失，无法生成节点视图")
    ...
```

**步骤 2：修改 create/update 使用节点键 + setex**

```python
node_context = _build_node_view(context)
key = _get_node_key(node_context.workflow_id, task_name)
redis_client.setex(key, NODE_TTL_SECONDS, node_context.model_dump_json())
```

**步骤 3：修改 get_workflow_state 聚合逻辑**

```python
def _merge_states(states: list[Dict[str, Any]], workflow_id: str) -> Dict[str, Any]:
    ...

for key in redis_client.scan_iter(match=f"{workflow_id}:node:*"):
    states.append(json.loads(redis_client.get(key)))
return _merge_states(states, workflow_id)
```

**步骤 4：运行测试确认通过**

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/common/state_manager/test_node_storage.py -v
```

**步骤 5：提交**

```bash
git add services/common/state_manager.py
git commit -m "feat(common): 按节点键存储任务状态"
```

---

### 任务 3：删除任务时清理节点键

**文件:**
- 修改: `services/api_gateway/app/single_task_executor.py`

**步骤 1：替换删除计划中的 Redis 键**

```python
redis_key_prefix = f"{task_id}:node:"
```

**步骤 2：修改 `_delete_redis_state` 支持前缀扫描**

```python
keys = list(client.scan_iter(match=f"{redis_key_prefix}*"))
removed = client.delete(*keys)
```

**步骤 3：运行受影响测试（如有）**

若没有现成测试，跳过并注明原因。

**步骤 4：提交**

```bash
git add services/api_gateway/app/single_task_executor.py
git commit -m "fix(api_gateway): 删除任务清理节点键"
```

---

### 任务 4：容器内回归验证与收尾

**步骤 1：运行基础单测**

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/common/state_manager/test_node_storage.py -v
```

**步骤 2：如需手工验证**

- 创建任务 → 执行节点 → 查询 `/v1/tasks/{id}/status`
- 确认 `stages` 聚合与旧格式一致

**步骤 3：检查 git 状态**

```bash
git status --short
```

---

## 注意事项
- 所有测试命令必须在 Docker 容器内执行。
- 宿主机仅做文件操作，不安装依赖。
- 日志与注释保持中文、简洁。
