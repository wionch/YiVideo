# Redis 任务数据存储拆分设计

日期: 2026-01-29

## 背景
当前所有节点阶段数据集中存放在单一 Redis 键 `workflow_state:{task_id}`，导致键体积膨胀、读写耦合。需求要求按节点拆分存储，并将 TTL 统一为 1 天。

## 目标
- 每个节点执行数据独立存储，键格式为 `{任务id}:node:{func_name}`（`task_name` 中 `.` 替换为 `:`）。
- TTL 固定 1 天（86400 秒）。
- 对外 API 请求/响应格式保持不变（仍为 `WorkflowContext` 视图）。

## 约束
- 不保留旧键 `workflow_state:{task_id}`。
- 不新增索引键，读取聚合依赖 `SCAN`（方案 A）。
- 所有日志与文档保持中文。

## 方案概述
在 `state_manager` 中引入“节点键”读写与聚合逻辑：
- 写入：`create_workflow_state` / `update_workflow_state` 只写当前节点视图到 `{task_id}:node:{func_name}`，并用 `setex` 刷新 TTL。
- 读取：`get_workflow_state` 通过 `SCAN {task_id}:node:*` 拉取所有节点键，合并 `stages` 形成聚合 `WorkflowContext`。
- 删除：删除任务时扫描并删除该 `task_id` 下全部节点键。

## 数据模型
- 单节点键存储：顶层字段保留（`workflow_id/create_at/input_params/shared_storage_path/status/updated_at/...`），`stages` 仅包含本节点一项。
- 聚合输出：合并所有节点 `stages`，顶层字段取 `updated_at` 最新的节点视图作为来源。

## 组件与改动点
- `services/common/state_manager.py`
  - 新增节点键生成函数（`task_name` 规范化）。
  - 修改 create/update/get 的读写逻辑与 TTL。
  - 新增扫描聚合与批量删除能力。
- `services/api_gateway/app/single_task_executor.py`
  - 删除计划中的 Redis 键改为按前缀扫描删除。

## 数据流
1. API 创建任务上下文，调用 `create_workflow_state` → 写入单节点键。
2. Worker 完成节点执行，调用 `update_workflow_state` → 覆盖该节点键并刷新 TTL。
3. `/v1/tasks/{id}/status` 调用 `get_workflow_state` → 扫描聚合后返回统一结构。
4. 删除任务 → 扫描并删除 `{task_id}:node:*`。

## 错误处理
- Redis 不可用时保持现有错误返回与日志。
- 聚合时单节点解析失败则记录错误并跳过，避免影响整体查询。

## 兼容性
- 对外 API 请求/响应结构保持不变。
- 复用逻辑仍基于聚合后的 `stages[task_name]` 判断。
- TTL 由原默认 7 天调整为 1 天，会影响复用窗口。

## 测试与验证（容器内）
- 创建单任务后确认 Redis 中仅出现 `{task_id}:node:*` 键，TTL=86400。
- 多节点任务后查询 `/v1/tasks/{id}/status`，`stages` 包含全部节点且结构不变。
- 复用命中验证（成功节点返回 completed + reuse_info）。
- 删除任务后该 `task_id` 的所有节点键被清理。
