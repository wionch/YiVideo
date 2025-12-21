# 实施计划: 修复单步任务缓存复用数据返回

## 1. 技术上下文

### 1.1 依赖项
- `services/api_gateway/app/single_task_executor.py`: 核心逻辑所在地。
- `services/common/state_manager.py`: 用于获取任务状态。
- `WorkflowContext`: 数据结构定义。

### 1.2 未知数 & 风险 (NEEDS CLARIFICATION)
- **无**: 逻辑清晰，已在 `research.md` 中确认。

## 2. 宪法检查

### 原则遵循
- **KISS**: 实现方式为简单的字典过滤，无复杂抽象。
- **DRY**: 过滤逻辑仅在 `_check_reuse` 中实现，避免重复。
- **测试优先**: 将编写集成测试来验证过滤行为。

## 3. 门槛评估
- **变更类型**: 行为修正。
- **风险等级**: 低。
- **兼容性**: 保持 `WorkflowContext` 结构，兼容现有客户端。

## 4. 实施阶段

### 阶段 0: 研究与验证
- 已完成 `research.md`。

### 阶段 1: 设计与合约
- 已生成 `data-model.md`。
- 已生成 `contracts/response-filtering.yaml`。
- 已生成 `quickstart.md`。

### 阶段 2: 开发 (即将开始)
1. 修改 `services/api_gateway/app/single_task_executor.py`。
2. 在 `_check_reuse` 方法中，对 `reuse_completed` 和 `reuse_pending` 模式下的 `context` 进行 `stages` 过滤。
3. **新增**: 在 `_send_reuse_callback_async` 和正常执行的 `_send_callback_if_needed` 逻辑中，也应用同样的过滤逻辑。这可能需要提取一个公共的 `_filter_context_for_response(context, task_name)` 方法。
4. 确保 `deepcopy` 后立即执行过滤，不影响原始 Redis 数据。

### 阶段 3: 验证
1. 运行现有测试 `tests/test_single_task_callback_reuse.py`。
2. 编写新的集成测试 `tests/integration/test_single_task_cache_filtering.py`。
3. 手动验证 (curl)。

## 5. 任务分解
- [ ] 任务 1: 提取公共过滤方法 `_filter_context_for_response`。
- [ ] 任务 2: 在 `_check_reuse` (缓存复用) 中应用过滤。
- [ ] 任务 3: 在 `_send_reuse_callback_async` (缓存回调) 中应用过滤。
- [ ] 任务 4: 在 `_send_callback_if_needed` (正常回调) 中应用过滤。
- [ ] 任务 5: 编写并运行测试用例，验证 API 响应和回调载荷的一致性。
