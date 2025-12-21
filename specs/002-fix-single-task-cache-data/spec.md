# 规范: 修复单步任务缓存复用数据返回 (Fix Single Task Cache Data Return)

## 1. 概述

### 1.1 背景
当前 `single-task` 模式下，当请求命中 Redis 缓存（即任务已执行过且结果有效）时，接口返回的 `result` 字段包含完整的 `WorkflowContext`，其中可能包含该 `task_id` 下所有历史执行过的 `stages` 数据。
用户期望在请求特定的 `task_name` 时，即使命中缓存，返回的数据也应聚焦于当前请求的 `task_name`，而不是返回整个工作流的所有任务历史数据。

### 1.2 目标
修改单步任务（Single Task）的缓存复用逻辑，确保当命中缓存时，返回的 `WorkflowContext` 中的 `stages` 字段仅包含当前请求的 `task_name` 的数据，过滤掉其他无关任务的阶段信息。

### 1.3 范围
- **服务**: `api_gateway` (处理 `/v1/tasks` 请求的逻辑)
- **场景**: 单步任务请求 (`POST /v1/tasks`) 且命中 Redis 缓存 (`reuse_hit=true`)
- **受影响接口**: `POST /v1/tasks`

## 2. 参与者 (Actors)

- **API Client**: 调用 `/v1/tasks` 接口的客户端。
- **API Gateway**: 接收请求，检查缓存，返回响应。
- **Redis**: 存储任务执行状态 (`WorkflowContext`)。

## 3. 用户场景 (User Scenarios)

### 场景 1: 单任务缓存命中 (Cache Hit)
1.  客户端发起 `POST /v1/tasks` 请求，`task_id="job-123"`, `task_name="task_A"`.
2.  系统检查 Redis 中 `job-123` 的状态。
3.  系统发现 `job-123` 中 `task_A` 已成功完成 (`status="SUCCESS"` 且 `output` 非空)。
4.  系统构造响应，状态为 `completed`。
5.  **关键变更**: 系统从 Redis 读取的完整 `WorkflowContext` 中，**过滤** `stages` 字段，只保留键为 `task_A` 的内容。
6.  系统返回响应，`result` 字段中的 `stages` 仅包含 `task_A`。

### 场景 2: 缓存未命中 (Cache Miss) - *不受影响*
1.  客户端发起 `POST /v1/tasks` 请求，`task_id="job-123"`, `task_name="task_B"`.
2.  Redis 中无 `task_B` 记录。
3.  系统正常调度任务。
4.  响应 `status="pending"`. (行为保持不变)

## 4. 功能需求 (Functional Requirements)

### 4.1 缓存复用响应过滤
- **FR-01**: 当 `POST /v1/tasks` 请求命中缓存时，返回的 `result` 对象（即 `WorkflowContext`）必须经过过滤。
- FR-02: 过滤规则为：`WorkflowContext.stages` 字典中，仅保留与请求参数 `task_name` 完全匹配的键值对。
- FR-03: 此过滤规则必须同时应用于：
    1. 命中缓存复用时的同步 API 响应。
    2. 任务正常执行完成（或复用命中）后发送给客户端的回调（Callback）载荷。
- FR-04: 如果 `WorkflowContext` 中包含其他非 `stages` 的顶层字段（如 `workflow_id`, `created_at`, `shared_storage_path` 等），应予以保留，除非它们包含大量无关数据（目前假设仅需过滤 `stages`）。
- FR-05: 该过滤逻辑**不应**影响 Redis 中存储的实际数据，仅影响本次 API 响应的视图。

## 5. 成功标准 (Success Criteria)

- **SC-01**: 对于已完成的任务 `task_A` (task_id=`job-1`), 再次请求 `task_A` 时，响应的 `result.stages` 仅包含 `task_A`，不包含该 ID 下可能存在的 `task_B` 或 `task_C` 的数据。
- **SC-02**: 响应结构保持有效的 `WorkflowContext` 格式，确保客户端解析兼容性。
- **SC-03**: 现有集成测试（如有）中关于缓存复用的测试用例需要更新或新增用例以验证此过滤行为。

## 6. 假设与约束 (Assumptions & Constraints)

- **假设**: `WorkflowContext` 的核心数据泄露风险主要在于 `stages` 字段。
- **假设**: 客户端仅根据 `task_name` 期望获取对应结果，不依赖“副作用”（即通过请求 A 获取 B 的结果）。
- **约束**: 必须保持 `WorkflowContext` 的数据结构完整性，不能破坏 JSON schema。

## 7. 待澄清问题 (Clarifications)

- [已解决] 是否需要过滤除 `stages` 以外的其他字段？
    - *决定*: 仅过滤 `stages`。保留 `minio_files` 等累积字段原样，以平衡实现复杂度和数据可见性。
- [已解决] 正常执行的回调 (Callback) 是否也需要应用相同的过滤？
    - *决定*: **是**。为了保持 API 返回与回调数据的一致性，正常执行完成后的回调载荷也必须对 `stages` 进行相同的过滤。

## 8. 澄清记录 (Clarifications Session 2025-12-21)

- **Q: 回调数据是否也过滤？** → **A: 是**。正常完成的回调载荷仅包含当前请求的 `task_name` 的数据。
- **Q: 是否深度清洗 minio_files？** → **A: 否**。仅过滤 `stages`。

## 9. 界面/API 变更

无接口签名变更。仅变更响应数据的**内容**（减少了字段）。
