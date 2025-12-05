# 变更：添加删除本地目录的HTTP接口

## 为什么

当前系统提供了MinIO文件操作API（`/v1/files`），但缺乏删除本地文件系统目录的功能。工作流执行后，生成的临时文件和目录（如 `/share/workflows/{task_id}`）需要手动清理，这影响了存储空间管理和系统维护。

## 变更内容

- 在API网关中添加新的HTTP端点 `DELETE /v1/directories`
- 支持删除本地文件系统中的指定目录
- 提供安全的路径验证和错误处理
- 返回统一的响应格式，与现有文件操作API保持一致

## 影响

- **影响的代码文件**：
  - `services/api_gateway/app/file_operations.py` - 新增删除目录功能
  - `services/api_gateway/app/single_task_models.py` - 可能需要新的响应模型

- **影响的规范**：
  - 新的API capability: `local-directory-management`

- **向后兼容性**：此变更不破坏现有功能，是新增的独立端点
