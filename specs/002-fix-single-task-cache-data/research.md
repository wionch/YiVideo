# 研究报告: 单步任务缓存复用数据过滤

## 1. 现状分析
在 `services/api_gateway/app/single_task_executor.py` 的 `_check_reuse` 方法中，当命中缓存时，系统通过 `deepcopy(existing_state)` 复制了整个工作流上下文。虽然代码中尝试设置 `state_copy["stages"][task_name] = stage_data`，但由于 `deepcopy` 已经包含了所有的 `stages`，导致返回给客户端的结果中包含了该 `task_id` 下所有曾执行过的阶段数据。

## 2. 核心发现
- **代码位置**: `services/api_gateway/app/single_task_executor.py` -> `SingleTaskExecutor._check_reuse` (约 L190-L240)
- **问题根源**: `state_copy = deepcopy(existing_state)` 保留了所有阶段信息。
- **影响范围**: 仅影响单步任务请求命中缓存时的响应内容，不影响实际执行逻辑，也不影响 Redis 中的持久化数据（因为使用了 `skip_side_effects=true` 的更新或仅作为视图返回）。

## 3. 技术方案
### 3.1 过滤 `stages`
在 `_check_reuse` 中，对于 `mode == "reuse_completed"` 的情况，将 `state_copy["stages"]` 重新赋值为仅包含当前 `task_name` 的字典。

```python
state_copy["stages"] = {task_name: stage_data}
```

### 3.2 过滤 `minio_files` (可选但推荐)
`minio_files` 是一个列表。如果需要彻底隔离，应当仅保留与该 `stage` 输出相关的文件。
由于 `stage_data["output"]` 中通常包含本地路径或 MinIO URL，可以通过检查 `minio_files` 中的 `url` 是否被包含在 `stage_data["output"]` 的值中来进行启发式过滤。

### 3.3 对 `reuse_pending` 的处理
当状态为 `pending/running` 时，目前的实现返回了整个 `existing_state`：
```python
            if status in ["pending", "running"]:
                reuse_info["state"] = status
                return {
                    "reuse_hit": True,
                    "state": status,
                    "reuse_info": reuse_info,
                    "context": existing_state
                }
```
这也需要过滤。

## 4. 结论与决定
- **决定 1**: 必须过滤 `stages` 字段，确保仅返回当前请求的 `task_name`。
- **决定 2**: 同时在 `reuse_completed` 和 `reuse_pending` 两种命中缓存的情况下进行过滤。
- **决定 3**: 对于 `minio_files`，由于其为扁平列表且缺乏明确的 Stage 归属标签，第一阶段先不过滤，或仅进行简单的启发式过滤。考虑到用户诉求主要是“不返回所有任务数据”，过滤掉 `stages` 已经解决了 90% 的冗余。

## 5. 替代方案考虑
- **方案 A**: 在 `api_gateway/app/single_task_api.py` 中进行过滤。
  - *优点*: 逻辑更靠近 API 层。
  - *缺点*: `executor` 已经返回了处理过的 `context`，在 `executor` 内部处理更符合单一职责。
- **方案 B**: 修改 `WorkflowContext` 的序列化逻辑。
  - *缺点*: 影响太大，可能破坏其他服务（如 Worker）的预期。

最终选择在 `SingleTaskExecutor._check_reuse` 中进行局部过滤。
