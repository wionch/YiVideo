# Change: 单步任务 callback 复用与数据保留方案

## Why
单步任务在 callback 模式下无法按 task_id+task_name 直接复用已有结果：Redis 仅保留最后一次覆盖写入的阶段数据，二次请求只能轮询 `/v1/tasks/{task_id}/status`，无法自动回调推送缓存结果。需要使单步任务与工作流一致地累计阶段数据，并在命中复用时按 task_name 直接回调返回。

## Research (REQUIRED)
记录了文档、规范与代码的现状，用于支撑后续任务拆分。

### What was inspected
- Specs: `openspec/specs/single-task-api-docs/spec.md` 复用文档要求 (45-57)
- Docs: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md` 通用/回调示例 (11-95)，未涵盖复用
- Code: `services/api_gateway/app/single_task_executor.py` 创建/写入上下文 (195-231)，状态查询 (144-173)
- Code: `services/common/state_manager.py` 回调触发逻辑 (184-249)，Redis setex 覆盖写入 (255-272)
- Change in-flight: `openspec/changes/fix-reuse-callback-trigger/specs/single-task-state-reuse/spec.md` 复用命中与回调要求 (1-22)

### Findings (with evidence)
- Finding 1: API 文档只描述创建/查询/回调基础流程，未给出复用/`reuse_info`/按 task_name 命中说明，违背 `single-task-api-docs` 的复用覆盖要求。  
  - Evidence: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:11-95` 无复用段落；`openspec/specs/single-task-api-docs/spec.md:45-57` 要求文档说明 Redis 判定与 `reuse_info`。  
  - Decision: Doc+Code（需要补文档并与实现对齐）

- Finding 2: 单步任务创建总是调用 `_create_task_context` → `create_workflow_state`（setex），`stages` 只包含当前 task_name，后续同 task_id 请求直接覆盖 Redis 键，导致之前 task_name 的数据被丢弃。  
  - Evidence: `services/api_gateway/app/single_task_executor.py:195-231` 初始化 context 仅含当前阶段并写入；`services/common/state_manager.py:255-272` `create_workflow_state` 对同 key 直接 setex。  
  - Decision: Code（改为按 task_name 累积/合并而非覆盖）

- Finding 3: 回调触发 `_check_and_trigger_callback` 仅取 `stages` 第一个元素判定 `SUCCESS/FAILED`，未按 task_name 精确匹配，pending/running 时无处理；若改为多阶段累积会选错阶段或在未完成时也无法明确响应。  
  - Evidence: `services/common/state_manager.py:184-249` 遍历首个 stage 即 break，状态非终态不触发且无 pending 反馈。  
  - Decision: Code（回调需按请求 task_name 判定，明确 pending/failed 复用策略）

- Finding 4: 现有变更 `fix-reuse-callback-trigger` 已提出“按 task_id+task_name 复用并回调”要求，但缺少 proposal/tasks，且未覆盖 pending 行为与文档落地，需要本次变更同步完善并避免规范分叉。  
  - Evidence: `openspec/changes/fix-reuse-callback-trigger/specs/single-task-state-reuse/spec.md:1-22` 仅描述命中/未命中与回调地址替换。  
  - Decision: Spec delta（补充 pending 行为与文档要求，对齐新实现）

### Why this approach (KISS/YAGNI check)
- 直接将单步 Redis 存储改为“按 task_id 累积 task_name 阶段”即可解决复用命中与数据丢失问题，无需引入新存储或队列。
- 回调复用仅在命中成功阶段时触发，未完成/失败保持静默可避免误推送；同步响应标记 reuse 状态即可告知客户端后续动作。
- 文档更新以现有 `SINGLE_TASK_API_REFERENCE.md` 结构补充复用与字段示例，避免新文档格式。
- 非目标：不改动工作流模式、不新增状态枚举、不引入新接口。

## What Changes
- 定义单步任务 Redis 写入从覆盖改为按 task_name 累积，保留同一 task_id 下所有阶段数据。
- 定义 callback 模式下的复用判定：按 task_id+task_name 查找成功阶段并直接回调推送，pending/running/failed 的处理策略与同步响应约定。
- 更新 `SINGLE_TASK_API_REFERENCE.md`，在通用与节点小节中补充复用流程、`reuse_info` 字段与 pending 行为描述。
- 对现有 `single-task-api-docs` 与新增 `single-task-state-reuse` 能力给出 spec delta。

## Impact
- Affected specs:  
  - `single-task-state-reuse`（ADDED: 单步任务累积与回调复用规则）  
  - `single-task-api-docs`（MODIFIED: 文档需覆盖 callback 复用与 pending 行为）
- Affected code (later apply):  
  - `services/api_gateway/app/single_task_executor.py`（创建/写入/复用判定策略）  
  - `services/common/state_manager.py`（按 task_name 触发回调与 pending/failed 策略）  
  - `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`（复用与字段示例）
- Risks: 多阶段存储后回调需要精确到 task_name，需避免旧逻辑只看首阶段导致误回调；状态响应兼容性需验证 `/v1/tasks/{task_id}/status`。
