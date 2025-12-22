# 任务: 任务删除 API 节点

**输入**: 来自 `/specs/003-delete-task-data/` 的设计文档  
**先决条件**: plan.md (必需), spec.md (用户故事必需), research.md, data-model.md, contracts/

**测试**: 仅在任务中显式列出时需要编写测试。  
**组织**: 按用户故事分组，确保每个故事可独立实现与测试。

## 阶段 1: 设置 (共享基础设施)

**目的**: 确认文档与契约输入一致，为实现奠定统一接口基线。

- [ ] T001 校对并更新 `specs/003-delete-task-data/contracts/delete-task-api.yaml` 以与 research.md/plan.md 对齐（force/safe 语义、status/results/warnings、错误码示例）；验收：路径 `/v1/tasks/{task_id}/delete`、`force` 默认 false、示例含 success 与 partial_failed、错误码覆盖 400/401/403/404。
- [ ] T002 同步 `specs/003-delete-task-data/quickstart.md` 示例与契约/规范（safe 与 force 请求/响应文案）；验收：示例使用 POST + JSON，字段含 status/results/warnings/timestamp，文案提及强制删除风险。

---

## 阶段 2: 基础 (阻塞性先决条件)

**目的**: 为各用户故事准备通用模型与执行器基础。

- [X] T003 在 `services/api_gateway/app/single_task_models.py` 增加删除相关 Pydantic 模型（TaskDeletionRequest/TaskDeletionResult/ResourceDeletionItem）并保持枚举与 contracts 对齐；验收：模型支持 force 默认 false、status 枚举 success/partial_failed/failed、resource 枚举 local_directory/redis/minio，字段描述与规范一致。
- [X] T004 在 `services/api_gateway/app/single_task_executor.py` 添加内部辅助函数（单文件范围）以解析 task_id 的本地目录、Redis 键前缀、MinIO 对象前缀并执行幂等清理的占位/骨架，尚不处理业务分支；验收：函数返回统一的资源定位结构，可被后续删除流程复用且不影响现有执行路径。

**检查点**: 模型与基础工具可用后方可进入用户故事实现。

---

## 阶段 3: 用户故事 1 - 已完成任务释放空间 (优先级: P1) 🎯 MVP

**目标**: 完成任务的安全删除，清理本地/Redis/MinIO 并返回分资源结果，支持幂等。

**独立测试**: 创建并完成任务后调用删除端点，验证三类资源均删除且重复调用幂等。

### 实施

- [X] T005 [US1] 在 `services/api_gateway/app/single_task_executor.py` 实现删除主流程：默认 safe 模式拒绝运行/排队，成功/完成态执行本地目录、Redis、MinIO 分资源清理并生成 per-resource 结果与整体状态；验收：返回结构符合 TaskDeletionResult，缺失资源记为 skipped，支持 timestamp 输出。
- [X] T006 [US1] 在 `services/api_gateway/app/single_task_executor.py` 与 `services/api_gateway/app/single_task_api.py` 补充删除路由的鉴权/权限复用（与现有单任务接口一致），校验未授权/无权限时返回 401/403；验收：路由挂载与现有鉴权依赖一致，未授权用例通过。
- [X] T007 [US1] 在 `services/api_gateway/app/single_task_api.py` 增加 `POST /v1/tasks/{task_id}/delete` 路由，校验 task_id/force，调用执行器并映射 HTTP 状态（200 成功/部分失败，404 未找到，400 非终态 safe 拒绝）；验收：响应字段与模型一致，记录日志，鉴权已生效。
- [ ] T008 [US1] 更新 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md` 增加删除节点说明：路径、请求/响应示例、safe 默认行为与 force 风险提示、幂等说明；验收：文档新增小节与契约字段一致，包含成功与部分失败示例。
- [ ] T009 [US1] 更新 `specs/003-delete-task-data/quickstart.md` 以匹配实际路由与字段命名（含 force=true 示例与风险提示）；验收：示例请求可直接执行，字段名与实现一致。
- [X] T017 [P] [US1] 在 `tests/api_gateway/test_task_delete_api.py` 添加幂等用例：对同一 task_id 连续调用删除 3 次，断言 status/结果一致、缺失资源标记为 skipped，无新增错误或副作用。

---

## 阶段 4: 用户故事 2 - 失败/脏数据清理 (优先级: P2)

**目标**: 对失败任务或残留输出进行清理，部分失败需明确可重试项。

**独立测试**: 人为制造失败任务，调用删除端点，验证 Redis/MinIO 清理与部分失败标记。

### 实施

- [ ] T010 [US2] 在 `services/api_gateway/app/single_task_executor.py` 扩展删除流程对失败态/残留输出的处理：容忍缺失对象，遇到依赖故障返回 partial_failed 并标记 retriable；验收：失败态允许删除，结果中包含失败资源的 message/retriable。
- [ ] T011 [P] [US2] 在 `tests/api_gateway/test_task_delete_api.py` 添加失败任务清理场景测试（可使用假定上下文/模拟依赖）；验收：测试覆盖 partial_failed 与 retriable 标志，运行通过。
- [X] T018 [P] [US2] 在 `tests/api_gateway/test_task_delete_api.py` 模拟 MinIO/Redis 不可用：删除响应应为 partial_failed，失败资源标记 retriable=true，其余可用资源成功清理；记录错误信息。

---

## 阶段 5: 用户故事 3 - 无效任务请求保护 (优先级: P3)

**目标**: 对不存在的 task_id 提示未找到，不做副作用，幂等。

**独立测试**: 对不存在 task_id 反复调用删除端点，返回 404/未找到信息且无副作用。

### 实施

- [ ] T012 [US3] 在 `tests/api_gateway/test_task_delete_api.py` 添加不存在 task_id 的契约/集成用例，验证返回 404/未找到文案且不触发资源清理；验收：重复调用保持相同输出，无副作用。

---

## 阶段 6: 完善与横切关注点

**目的**: 收尾、对齐文档与性能/安全检查。

- [ ] T013 [P] 在 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md` 与 `specs/003-delete-task-data/quickstart.md` 交叉复核最终实现，补充风险/性能备注（5s 目标、幂等说明）；验收：文档描述与实现一致且引用最新字段。
- [ ] T014 在 `services/api_gateway/app/single_task_executor.py` 补充日志/错误处理和审计信息（记录 force 删除、部分失败明细），确保不泄露敏感路径；验收：日志含 task_id/force 标记，错误路径统一。
- [ ] T015 运行功能自检：`tests/api_gateway/test_task_delete_api.py`（如存在）及现有测试套件；验收：相关测试通过，无新增警告。
- [ ] T016 在 `tests/api_gateway/test_task_delete_api.py` 或独立脚本中添加性能基线检查：对 ≤1GB 删除路径测量响应 P95（目标 5s）或记录现状并在文档中标注限制；验收：测试/脚本可运行并输出时间，若未达标则在文档注明。

---

## 依赖关系与执行顺序

- 设置阶段先于基础；基础完成后方可进入用户故事阶段。  
- US1 依赖 T003-T004；US2 依赖 US1 完成的执行器/路由基础；US3 仅依赖基础与路由存在。  
- 最终完善阶段依赖所有目标用户故事完成。

### 并行机会
- 标记为 [P] 的任务可并行：T002、T011、T013（文档/测试不同文件）。  
- 用户故事阶段在基础完成后可并行推进不同文件的任务，例如 T005（执行器）与 T006（路由）可由不同人并行，但需在 T008/T009 文档对齐前完成。

### 实施策略 (MVP 优先)
- 优先完成 US1（T005-T009）以交付可用删除能力（MVP）。  
- US2/US3 提升鲁棒性与错误处理，可在 MVP 后增量交付。  
- 每个故事的独立测试标准见各故事说明；US2/US3 的测试集中在 `tests/api_gateway/test_task_delete_api.py`。  
