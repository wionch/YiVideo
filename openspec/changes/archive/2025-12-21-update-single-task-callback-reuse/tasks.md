## Traceability (Research → Tasks)
- Finding 1 → 1.4
- Finding 2 → 1.1
- Finding 3 → 1.2, 1.5
- Finding 4 → 1.3, 2.1

## 1. Implementation

- [x] 1.1 单步任务上下文按 task_name 累积存储（避免覆盖）
  - Evidence: proposal.md → Research → Finding 2 (Decision: Code)
  - Edit scope: `services/api_gateway/app/single_task_executor.py:46-268`
  - Commands:
    - `python -m compileall services/api_gateway/app`
  - Done when: 同 task_id 再次创建单步任务时能在写入前合并既有 `stages`，保留其他 task_name 数据且编译通过。

- [x] 1.2 回调判定按 task_name 精确触发并处理 pending
  - Evidence: proposal.md → Research → Finding 3 (Decision: Code)
  - Edit scope: `services/common/state_manager.py:184-325`
  - Commands:
    - `python -m compileall services/common`
  - Done when: 回调触发逻辑按请求的 task_name 选择阶段，pending/running 不推送回调且状态保存正确，编译通过。

- [x] 1.3 单步创建接口命中复用时返回 reuse_info 与 completed 状态
  - Evidence: proposal.md → Research → Finding 4 (Decision: Spec delta)
  - Edit scope: `services/api_gateway/app/single_task_api.py:26-159`
  - Commands:
    - `python -m compileall services/api_gateway/app`
  - Done when: 命中复用请求时同步响应返回 `status=completed` 且包含 `reuse_info` 字段，未命中保持现状，编译通过。

- [x] 1.4 补充单任务文档的复用与 callback 描述
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Code)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:1-120`
  - Commands:
    - `grep -n "reuse_info" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 文档新增命中/未命中/未完成复用流程、同步响应与回调示例，包含 `reuse_info` 与 pending 行为说明。

- [x] 1.5 添加单步复用与回调的行为测试
  - Evidence: proposal.md → Research → Finding 3 (Decision: Code)
  - Edit scope: `tests/test_single_task_callback_reuse.py:1-200`
  - Commands:
    - `pytest tests/test_single_task_callback_reuse.py`
  - Done when: 覆盖命中成功直接回调与 pending 不回调场景的测试用例通过。

## 2. Validation

- [x] 2.1 OpenSpec strict validation
  - Evidence: proposal.md → Research → Finding 4
  - Commands:
    - `openspec validate update-single-task-callback-reuse --strict`
  - Done when: command exits 0.

- [x] 2.2 Project checks
  - Evidence: proposal.md → Research → Finding 2
  - Commands:
    - `pytest tests/test_single_task_callback_reuse.py`
  - Done when: 测试全部通过且无新增警告。

## 3. Self-check (ENFORCED)

- [x] 3.1 Each task touches exactly one file in Edit scope.
- [x] 3.2 Each task references exactly one Finding.
- [x] 3.3 No task contains conditional language (if needed/必要时/可能/按需/...).
- [x] 3.4 Each task includes Commands and an objective Done when.
