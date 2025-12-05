# YiVideo API 文档总览

YiVideo AI视频处理平台提供完整的RESTful API，支持动态工作流编排、单个任务执行、文件管理和系统监控。本文档是所有API的入口指南。

## 📚 API 文档目录

### 🚀 核心功能 API
- **[工作流API](WORKFLOW_API.md)** - 动态编排和管理AI处理工作流
  - 创建和执行多阶段视频处理流程
  - 支持增量执行和失败重试
  - 实时工作流状态监控

- **[单任务API](SINGLE_TASK_API.md)** - 独立的单个任务执行
  - 直接调用AI处理服务（ASR、OCR、TTS等）
  - 任务状态实时查询
  - 支持callback回调机制

### 📁 文件管理 API
- **[文件操作API](FILE_OPERATIONS_API.md)** - MinIO存储和本地文件管理
  - 文件上传/下载/删除
  - 目录管理
  - 流式传输优化

### 📊 系统管理 API
- **[监控API](MONITORING_API.md)** - GPU锁监控和系统健康检查
  - GPU资源锁管理
  - 任务心跳监控
  - 系统健康状态
  - 性能统计

### ⚡ 快速入门
- **[快速开始指南](QUICK_START.md)** - 5分钟快速上手
  - 基础使用示例
  - 常见场景演示
  - 最佳实践建议

---

## 🌐 API 基础信息

### 服务地址
```bash
http://localhost:8000
```
*默认端口可在配置文件中修改*

### 版本信息
- **当前版本**: v1
- **版本策略**: URL路径版本控制（`/v1/`）
- **兼容性**: 新版本会保持向后兼容

### 内容类型
- **请求格式**: `application/json`
- **响应格式**: `application/json`
- **文件上传**: `multipart/form-data`

---

## 🔐 认证和授权

### 当前状态
当前版本API**暂时未实现认证机制**，所有端点可直接访问。

> **⚠️ 重要提醒**: 在生产环境中部署时，必须启用适当的认证机制（如API Key、JWT Token等）。

### 未来认证方案（待实现）
```bash
# API Key 认证（建议）
Authorization: Bearer YOUR_API_KEY

# 或
X-API-Key: YOUR_API_KEY
```

---

## 📝 请求和响应规范

### 通用请求头
```http
Content-Type: application/json
Accept: application/json
```

### 通用响应格式
```json
{
    "success": true,
    "data": { ... },
    "message": "操作成功",
    "timestamp": "2025-12-05T02:56:00Z"
}
```

### 分页响应格式（适用列表接口）
```json
{
    "items": [ ... ],
    "total": 100,
    "page": 1,
    "size": 20,
    "pages": 5
}
```

---

## ⚠️ 错误处理

### HTTP 状态码
| 状态码 | 说明 | 场景 |
|--------|------|------|
| 200 | 成功 | 请求成功处理 |
| 202 | 已接受 | 异步任务已创建 |
| 400 | 请求错误 | 参数验证失败 |
| 403 | 禁止访问 | 权限不足 |
| 404 | 资源未找到 | 工作流/任务不存在 |
| 409 | 冲突 | 资源已被占用 |
| 410 | 资源不可用 | 存储目录不存在 |
| 429 | 请求过多 | 触发速率限制 |
| 500 | 服务器错误 | 内部错误 |

### 错误响应格式
```json
{
    "detail": "错误详细信息",
    "error": {
        "code": "ERROR_CODE",
        "message": "用户友好的错误信息",
        "timestamp": "2025-12-05T02:56:00Z",
        "details": { ... }
    }
}
```

### 常见错误码
| 错误码 | 说明 | 解决方案 |
|--------|------|----------|
| INVALID_PARAMS | 请求参数无效 | 检查参数格式和必填项 |
| WORKFLOW_NOT_FOUND | 工作流不存在 | 检查workflow_id |
| TASK_NOT_FOUND | 任务不存在 | 检查task_id |
| GPU_LOCKED | GPU资源被占用 | 等待或手动释放锁 |
| FILE_NOT_FOUND | 文件不存在 | 检查文件路径 |
| PERMISSION_DENIED | 权限不足 | 检查访问权限 |
| INTERNAL_ERROR | 内部错误 | 查看服务器日志 |

---

## 🚦 速率限制

### 当前策略
- **默认限制**: 每分钟1000次请求（可配置）
- **限流算法**: 滑动窗口
- **超限处理**: 返回429状态码

### 速率限制响应头
```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1701764160
```

---

## 🔄 幂等性

### 支持幂等的操作
- **工作流创建**: 相同参数重复请求会创建不同工作流（每次生成新workflow_id）
- **文件删除**: 删除不存在的文件返回成功（幂等）
- **任务取消**: 重复取消同一任务返回相同结果（幂等）

### 幂等性头部（建议）
```http
Idempotency-Key: <uuid>
```
*未来版本将支持此头部以确保请求幂等性*

---

## 📊 API 统计信息

### 服务健康检查
```bash
GET /
```

### API 服务状态
```bash
GET /api/v1/monitoring/health
```

### 实时统计
```bash
GET /api/v1/monitoring/statistics
```

---

## 💡 使用建议

### 最佳实践
1. **超时设置**: 建议设置合理的请求超时（建议30秒以上）
2. **重试机制**: 对于网络错误，使用指数退避重试
3. **错误处理**: 始终检查HTTP状态码和响应内容
4. **并发控制**: 避免同时创建过多工作流
5. **资源管理**: 及时清理已完成的工作流文件

### 性能优化
1. **文件上传**: 使用流式上传支持大文件
2. **批量操作**: 使用单任务API执行独立操作
3. **状态查询**: 避免过于频繁的状态查询
4. **工作流设计**: 合理拆分任务，避免单任务过长

### 监控建议
1. 定期检查 `/api/v1/monitoring/health`
2. 监控GPU锁状态和任务心跳
3. 关注错误日志和告警信息
4. 使用 `/api/v1/monitoring/statistics` 了解系统负载

---

## 🆘 获取帮助

### 自助诊断
1. **查看服务状态**: `GET /api/v1/monitoring/health`
2. **检查API文档**: 本文档及子文档
3. **查看示例代码**: `docs/api/QUICK_START.md`

### 联系支持
- **项目仓库**: https://github.com/your-org/yivideo
- **问题反馈**: GitHub Issues
- **技术文档**: 查看 `docs/technical/` 目录

---

## 📅 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2025-12-05 | 初始API文档发布 |

---

*最后更新: 2025-12-05 | 文档版本: 1.0.0*
