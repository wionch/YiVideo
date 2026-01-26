# 删除工作流模式 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 删除工作流模式与相关文档/示例，仅保留单节点 `/v1/tasks` 接口与其文档。

**Architecture:** API Gateway 仅保留单任务路由与执行器；工作流构建与增量执行模块下线；文档统一调整为单节点模式。

**Tech Stack:** FastAPI, Celery, Redis, Pytest, Markdown 文档

### Task 1: 添加工作流路由移除的测试

**Files:**
- Create: `tests/unit/api_gateway/test_workflow_routes_removed.py`
- Test: `tests/unit/api_gateway/test_workflow_routes_removed.py`

**Step 1: Write the failing test**

```python
from services.api_gateway.app.main import app


def test_workflow_routes_removed():
    paths = {route.path for route in app.router.routes}
    assert "/v1/workflows" not in paths
    assert "/v1/workflows/status/{workflow_id}" not in paths
```

**Step 2: Run test to verify it fails**

Run (宿主机执行): `docker exec -it api_gateway pytest /app/tests/unit/api_gateway/test_workflow_routes_removed.py -v`
Expected: FAIL with paths still present

**Step 3: Write minimal implementation**

见 Task 2 移除路由后使测试通过。

**Step 4: Run test to verify it passes**

Run (宿主机执行): `docker exec -it api_gateway pytest /app/tests/unit/api_gateway/test_workflow_routes_removed.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/api_gateway/test_workflow_routes_removed.py

git commit -m "test: 校验工作流路由已移除"
```

### Task 2: 移除 API Gateway 中的工作流入口

**Files:**
- Modify: `services/api_gateway/app/main.py`
- Test: `tests/unit/api_gateway/test_workflow_routes_removed.py`

**Step 1: Write the failing test**

已在 Task 1 完成。

**Step 2: Run test to verify it fails**

已在 Task 1 完成。

**Step 3: Write minimal implementation**

```python
# 删除 WorkflowRequest/WorkflowResponse 与相关校验
# 删除 /v1/workflows 与 /v1/workflows/status/{workflow_id} 路由
# 删除 workflow_factory 与 incremental_utils 相关引用

app = FastAPI(
    title="YiVideo Single Task API",
    description="仅提供单节点任务执行与文件操作接口。",
    version="1.1.0"
)
```

**Step 4: Run test to verify it passes**

Run (宿主机执行): `docker exec -it api_gateway pytest /app/tests/unit/api_gateway/test_workflow_routes_removed.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services/api_gateway/app/main.py

git commit -m "refactor(api_gateway): 移除工作流入口仅保留单任务"
```

### Task 3: 删除工作流构建与增量模块

**Files:**
- Delete: `services/api_gateway/app/workflow_factory.py`
- Delete: `services/api_gateway/app/incremental_utils.py`

**Step 1: Write the failing test**

不新增测试，依赖 Task 1 的路由测试与后续回归。

**Step 2: Run test to verify it fails**

不适用。

**Step 3: Write minimal implementation**

```bash
git rm services/api_gateway/app/workflow_factory.py

git rm services/api_gateway/app/incremental_utils.py
```

**Step 4: Run test to verify it passes**

Run (宿主机执行): `docker exec -it api_gateway pytest /app/tests/unit/api_gateway/test_workflow_routes_removed.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add -u

git commit -m "refactor(api_gateway): 删除工作流构建与增量模块"
```

### Task 4: 更新核心文档为单节点模式

**Files:**
- Modify: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
- Modify: `docs/product/SDD.md`
- Modify: `docs/product/SYSTEM_ARCHITECTURE.md`
- Modify: `docs/technical/IMPLEMENTATION_SUMMARY.md`

**Step 1: Write the failing test**

不新增测试，改用文档审阅与回归测试。

**Step 2: Run test to verify it fails**

不适用。

**Step 3: Write minimal implementation**

示例调整要点（保持中文描述）：

```markdown
- SINGLE_TASK_API_REFERENCE.md: 在开头声明“仅支持单任务模式”，删除/改写工作流模式描述段落
- SDD.md: 将“核心工作流”章节改为“核心单任务流程”，示例改为 /v1/tasks
- SYSTEM_ARCHITECTURE.md: 将 API 设计端点改为 /v1/tasks，删除 workflow_config 描述
- IMPLEMENTATION_SUMMARY.md: 移除“保持 /v1/workflows 兼容性”的表述
```

**Step 4: Run test to verify it passes**

Run (宿主机执行): `docker exec -it api_gateway pytest /app/tests -v`
Expected: PASS

**Step 5: Commit**

```bash
git add docs/technical/reference/SINGLE_TASK_API_REFERENCE.md docs/product/SDD.md docs/product/SYSTEM_ARCHITECTURE.md docs/technical/IMPLEMENTATION_SUMMARY.md

git commit -m "docs: 文档切换为单节点模式"
```

### Task 5: 删除工作流文档/示例并清理引用

**Files:**
- Delete: `docs/technical/reference/WORKFLOW_NODES_REFERENCE.md`
- Delete: `docs/technical/reference/WORKFLOW_EXAMPLES_GUIDE.md`
- Delete: `config/examples/workflow_examples.yml`
- Modify: `docs/tasks/log.md`
- Modify: `docs/technical/参数统一管理重构施工方案.md`

**Step 1: Write the failing test**

不新增测试，改用文档链接审阅。

**Step 2: Run test to verify it fails**

不适用。

**Step 3: Write minimal implementation**

```bash
git rm docs/technical/reference/WORKFLOW_NODES_REFERENCE.md

git rm docs/technical/reference/WORKFLOW_EXAMPLES_GUIDE.md

git rm config/examples/workflow_examples.yml
```

并将引用替换为单任务文档或删除相关段落。

**Step 4: Run test to verify it passes**

Run (宿主机执行): `docker exec -it api_gateway pytest /app/tests -v`
Expected: PASS

**Step 5: Commit**

```bash
git add -u

git commit -m "docs: 删除工作流文档与示例"
```
