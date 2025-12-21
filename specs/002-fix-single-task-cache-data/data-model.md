# 数据模型: 单步任务响应过滤

## 1. 实体

### 1.1 WorkflowContext (API 视图)
在单步任务命中缓存的响应中，`WorkflowContext` 作为一个视图返回，其结构保持不变，但内容受限。

| 字段 | 类型 | 说明 | 过滤行为 |
| :--- | :--- | :--- | :--- |
| `workflow_id` | string | 任务唯一标识符 (task_id) | 保留 |
| `status` | string | 任务状态 | 保留 (通常为 `completed` 或 `pending`) |
| `create_at` | string | 创建时间 | 保留 |
| `updated_at` | string | 更新时间 | 保留 |
| `input_params` | dict | 原始请求参数 | 保留 |
| `shared_storage_path` | string | 共享存储路径 | 保留 |
| `stages` | dict | 执行阶段信息 | **过滤**: 仅保留当前请求的 `task_name` 对应的键 |
| `minio_files` | list | 生成的文件列表 | 保留 (第一阶段暂不进行深度关联过滤) |
| `error` | any | 错误信息 | 保留 |

## 2. 状态转换
此更改不涉及状态转换逻辑的变更。

## 3. 验证规则
- `stages` 字典在响应时必须非空且包含请求的 `task_name`。
- `stages` 字典中不得出现除请求的 `task_name` 以外的任何键。
