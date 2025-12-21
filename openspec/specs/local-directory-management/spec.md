# local-directory-management Specification

## Purpose
TBD - created by archiving change add-directory-delete-api. Update Purpose after archive.
## Requirements
### Requirement: Delete Local Directory

系统 MUST 提供删除本地文件系统目录的HTTP接口，支持安全验证和错误处理。

#### Scenario: 删除存在的目录

- **WHEN** 用户请求删除一个存在的本地目录
- **THEN** 返回成功响应，目录及其内容被删除

#### Scenario: 删除不存在的目录

- **WHEN** 用户请求删除一个不存在的目录
- **THEN** 返回成功响应（idempotent操作）

#### Scenario: 路径遍历攻击防护

- **WHEN** 用户请求包含 ".." 或绝对路径的目录删除
- **THEN** 返回400错误，提示无效的目录路径

#### Scenario: 权限不足

- **WHEN** 用户请求删除无权限访问的目录
- **THEN** 返回403错误，提示权限不足

### Requirement: Directory Delete API Endpoint

API网关 MUST 实现 `DELETE /v1/directories` 端点，支持查询参数指定目录路径。

#### Scenario: 成功删除

- **WHEN** 发送DELETE请求到 `/v1/directories?directory_path=/share/workflows/task123`
- **THEN** 返回JSON响应，包含 success=true 和适当的成功消息

#### Scenario: 参数验证

- **WHEN** 发送DELETE请求到 `/v1/directories` 不带 directory_path 参数
- **THEN** 返回400错误，提示 directory_path 为必需参数

#### Scenario: 安全的目录路径验证

- **WHEN** 发送DELETE请求到 `/v1/directories?directory_path=../../../etc`
- **THEN** 返回400错误，提示无效的目录路径

