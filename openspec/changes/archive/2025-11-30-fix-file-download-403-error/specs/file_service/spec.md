## MODIFIED Requirements
### Requirement: 文件下载服务
The file download service SHALL correctly handle MinIO access and provide reliable download functionality, including proper authentication, retry mechanisms, and error handling.

#### Scenario: MinIO文件下载成功
- **WHEN** 用户请求下载MinIO中的视频文件
- **THEN** 系统使用正确的认证信息访问MinIO并成功下载文件

#### Scenario: HTTP文件下载重试
- **WHEN** HTTP下载遇到临时网络错误
- **THEN** 系统自动重试下载，使用指数退避策略，最多重试3次

#### Scenario: 下载失败错误处理
- **WHEN** 文件下载最终失败（包括403认证错误）
- **THEN** 系统提供详细的错误信息，包括具体的失败原因和网络诊断信息

## ADDED Requirements
### Requirement: MinIO连接健康检查
The system SHALL verify MinIO connection status and authentication information validity.

#### Scenario: 连接状态验证
- **WHEN** 文件服务初始化时
- **THEN** 系统验证MinIO连接并记录连接状态信息

### Requirement: 增强的URL解析
The system SHALL correctly parse different URL formats and select appropriate download strategies.

#### Scenario: URL格式标准化
- **WHEN** 接收到HTTP格式的MinIO URL时
- **THEN** 系统自动转换为适当的MinIO客户端调用方式

### Requirement: 网络诊断信息
The system SHALL provide detailed network connection diagnostic information to help troubleshoot issues.

#### Scenario: 详细错误日志
- **WHEN** 文件下载失败时
- **THEN** 系统记录详细的错误信息，包括URL、认证状态、网络状态等