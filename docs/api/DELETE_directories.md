# DELETE /v1/files/directories - 删除本地目录

## 概述

此端点用于删除本地文件系统中的指定目录及其所有内容。

## 端点信息

-   **方法**: `DELETE`
-   **路径**: `/v1/files/directories`
-   **认证**: 需要（继承现有 API 网关认证）
-   **速率限制**: 继承现有 API 网关限制

## 请求参数

| 名称           | 类型   | 必需 | 描述                 |
| -------------- | ------ | ---- | -------------------- |
| directory_path | string | 是   | 要删除的本地目录路径 |

### 参数说明

-   `directory_path`: 要删除的目录路径
    -   必须是相对路径
    -   不能包含 `..` （防止路径遍历攻击）
    -   不能是绝对路径
    -   路径不存在时操作仍然成功（幂等性）

## 请求示例

```bash
curl -X DELETE "http://localhost:8000/v1/files/directories?directory_path=/share/workflows/task123" \
  -H "Content-Type: application/json"
```

## 响应模型

```json
{
    "success": true,
    "message": "目录删除成功: /share/workflows/task123",
    "file_path": "/share/workflows/task123"
}
```

### 响应字段

-   **success** (boolean): 操作是否成功
-   **message** (string): 操作结果消息
-   **file_path** (string): 被删除的目录路径

## 成功响应示例

### 场景 1: 删除存在的目录

```json
{
    "success": true,
    "message": "目录删除成功: /share/workflows/task123",
    "file_path": "/share/workflows/task123"
}
```

### 场景 2: 删除不存在的目录（幂等性）

```json
{
    "success": true,
    "message": "目录不存在，删除操作已幂等完成: /share/workflows/task456",
    "file_path": "/share/workflows/task456"
}
```

## 错误响应示例

### 400 Bad Request - 无效参数

```json
{
    "detail": "directory_path不能为空"
}
```

### 400 Bad Request - 不安全的路径

```json
{
    "detail": "无效的目录路径"
}
```

### 400 Bad Request - 路径不是目录

```json
{
    "detail": "路径不是目录: /share/workflows/task123"
}
```

### 403 Forbidden - 权限不足

```json
{
    "detail": "权限不足，无法删除目录: /root/protected_directory"
}
```

### 500 Internal Server Error - 服务器错误

```json
{
    "detail": "删除目录失败: [错误详情]"
}
```

## 错误代码说明

| HTTP 状态码 | 场景         | 描述                             |
| ----------- | ------------ | -------------------------------- |
| 400         | 参数错误     | 缺少 `directory_path` 或路径无效 |
| 400         | 安全检查失败 | 包含 `..` 或绝对路径             |
| 400         | 路径类型错误 | 路径存在但不是目录               |
| 403         | 权限不足     | 无权限访问或删除指定目录         |
| 500         | 服务器错误   | 删除目录时发生内部错误           |

## 使用场景

### 清理工作流临时文件

```bash
# 删除已完成的工作流目录
curl -X DELETE "http://localhost:8000/v1/files/directories?directory_path=/share/workflows/workflow_abc123"
```

### 批量清理（遍历）

```bash
#!/bin/bash
# 删除所有超过7天的工作流目录

workflow_dirs=(
    "/share/workflows/task001"
    "/share/workflows/task002"
    "/share/workflows/task003"
)

for dir in "${workflow_dirs[@]}"; do
    curl -X DELETE "http://localhost:8000/v1/files/directories?directory_path=$dir"
done
```

## 安全注意事项

1. **路径验证**: 系统会自动验证路径，防止路径遍历攻击
2. **权限检查**: 删除操作会检查文件系统权限
3. **幂等性**: 删除不存在的目录被认为是安全的
4. **不可恢复**: 目录删除后无法恢复，请谨慎操作

## 性能说明

-   删除小目录（< 100 个文件）: < 100ms
-   删除大目录可能需要更长时间，建议异步处理
-   系统会记录详细的操作日志

## 最佳实践

1. **确认目录不再需要**: 删除前确认不再需要目录中的文件
2. **检查权限**: 确保有足够的权限删除目录
3. **考虑备份**: 重要数据删除前考虑备份
4. **使用相对路径**: 避免使用绝对路径
5. **监控日志**: 关注删除操作的日志记录

## 相关端点

-   `GET /v1/files/list` - 列出文件
-   `GET /v1/files/download/{file_path}` - 下载文件
-   `DELETE /v1/files/{file_path}` - 删除 MinIO 文件

## 更新日志

| 版本  | 日期       | 变更                           |
| ----- | ---------- | ------------------------------ |
| 1.0.0 | 2025-12-05 | 初始版本，增加删除本地目录功能 |
