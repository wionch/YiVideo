# 快速上手：任务删除 API 节点

## 前置条件
- 已部署网关（默认 `http://localhost:8788`）且具备调用 `/v1/tasks` 的鉴权方式。
- 目标任务已创建；若任务在运行中，需显式传递 `force=true`。

## 请求示例（安全模式，默认拒绝运行态）

```bash
curl -X POST "http://localhost:8788/v1/tasks/task-demo-001/delete" \
  -H "Content-Type: application/json" \
  -d '{"force": false}'
```

预期响应（资源均删除成功）：
```json
{
  "status": "success",
  "results": [
    {"resource": "local_directory", "status": "deleted", "message": "Removed /share/workflows/task-demo-001"},
    {"resource": "redis", "status": "deleted"},
    {"resource": "minio", "status": "deleted"}
  ],
  "warnings": [],
  "timestamp": "2025-12-22T12:00:00Z"
}
```

## 请求示例（强制删除运行中任务）

```bash
curl -X POST "http://localhost:8788/v1/tasks/task-demo-001/delete" \
  -H "Content-Type: application/json" \
  -d '{"force": true}'
```

运行/排队任务将被强制清理，响应需标记风险或部分失败项。

## 错误/部分失败示例
- `status=partial_failed`，`results` 中的某个资源 `status=failed` 且 `retriable=true`，提醒重试。
- 当 `task_id` 不存在时返回 404，不进行任何删除操作。

## 验证点
- 幂等：重复调用同一 task_id 不产生新错误，缺失资源被标记为 skipped。
- 权限：未授权请求返回 401/403。
- 性能：数据量 ≤1GB 时 95% 请求应在 5s 内返回。
