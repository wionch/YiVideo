# 任务清单: 修复单步任务缓存复用数据返回

## 1. 项目设置 (Setup)

- [x] T001 创建集成测试文件 `tests/integration/test_single_task_cache_filtering.py`

## 2. 基础任务 (Foundation)

- [x] T002 在 `services/api_gateway/app/single_task_executor.py` 中提取私有方法 `_filter_context_for_response`，用于过滤 `WorkflowContext` 字典中的 `stages` 字段，仅保留目标 `task_name` 的数据。

## 3. 用户故事 1: 单任务缓存命中 (Cache Hit)

**目标**: 确保当单步任务请求命中缓存时，同步响应中的 `stages` 仅包含当前请求的任务数据。

- [x] T003 [US1] 修改 `services/api_gateway/app/single_task_executor.py` 的 `_check_reuse` 方法，在返回 `reuse_completed` 状态前调用 `_filter_context_for_response` 处理 `context`。
- [x] T004 [US1] 修改 `services/api_gateway/app/single_task_executor.py` 的 `_check_reuse` 方法，在返回 `reuse_pending` 状态前调用 `_filter_context_for_response` 处理 `context`。
- [x] T005 [US1] 编写测试用例 `test_cache_hit_response_filtering` 在 `tests/integration/test_single_task_cache_filtering.py` 中，验证缓存复用时的同步响应字段。

## 4. 用户故事 2: 回调载荷一致性 (Callback Payload)

**目标**: 确保无论是缓存复用触发的回调，还是正常执行完成触发的回调，其载荷中的 `stages` 均经过过滤。

- [x] T006 [US2] 修改 `services/api_gateway/app/single_task_executor.py` 的 `_send_reuse_callback_async` 方法，在发送回调前调用 `_filter_context_for_response`。
- [x] T007 [US2] 修改 `services/api_gateway/app/single_task_executor.py` 的 `_send_callback_if_needed` 方法，在发送回调前调用 `_filter_context_for_response`（注意此处需要从 `result` 中提取或传入 `task_name`）。
- [x] T008 [US2] 编写测试用例 `test_callback_payload_filtering` 在 `tests/integration/test_single_task_cache_filtering.py` 中，模拟 webhook 接收并验证载荷内容。

## 5. 完善与横切 (Refinement)

- [x] T009 运行完整测试套件 `pytest tests/integration/test_single_task_cache_filtering.py` 确保通过。
- [x] T010 检查 `SingleTaskExecutor` 中是否有其他返回 `WorkflowContext` 的路径需要过滤（如 `get_task_result` 接口通常预期返回完整状态，应保持不变，无需修改）。

## 依赖关系
- T003, T004, T006, T007 依赖 T002 (基础过滤方法)
- T005 依赖 T003, T004
- T008 依赖 T006, T007

## 实施策略
- **MVP**: 先完成 T001-T005，解决同步响应的数据泄露问题。
- **增量**: 再完成 T006-T008，统一回调行为。
