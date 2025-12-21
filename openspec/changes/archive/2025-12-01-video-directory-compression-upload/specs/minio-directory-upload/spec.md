# MinIO目录上传功能 - 规格Delta

## ADDED Requirements

### MU-001: 压缩包上传接口
#### Scenario: 压缩目录上传
**Given** 本地目录和MinIO目标路径  
**When** 调用 `upload_directory_compressed` 方法  
**Then** 应该：
- 先压缩目录为ZIP或TAR.GZ格式
- 然后上传压缩包到MinIO
- 返回包含压缩信息和上传URL的结果字典

#### Scenario: 压缩参数配置
**Given** 压缩上传功能  
**When** 指定压缩格式和级别  
**Then** 应该：
- 支持 "zip" 和 "tar.gz" 格式
- 支持 "store", "fast", "default", "maximum" 级别
- 正确传递参数到底层压缩模块

#### Scenario: 进度回调支持
**Given** 压缩上传操作  
**When** 注册进度回调  
**Then** 应该提供压缩和上传的实时进度

### MU-002: 下载解压功能
#### Scenario: 压缩包下载并解压
**Given** MinIO中的压缩包URL  
**When** 调用 `download_and_extract` 方法  
**Then** 应该：
- 下载压缩包到本地
- 自动检测压缩包格式
- 解压到指定目录
- 返回解压结果信息

#### Scenario: 压缩包格式检测
**Given** 各种格式的压缩包  
**When** 下载后自动检测  
**Then** 应该根据文件扩展名正确识别格式：
- .zip → ZIP解压
- .tar.gz → TAR.GZ解压

### MU-003: 错误处理和回退
#### Scenario: 压缩失败回退
**Given** 压缩操作失败  
**When** 执行 `upload_directory_compressed`  
**Then** 应该：
- 自动回退到非压缩上传模式
- 记录回退原因和错误信息
- 确保任务继续执行而非失败

#### Scenario: 网络中断恢复
**Given** 上传过程中网络中断  
**When** 网络恢复  
**Then** 应该：
- 支持断点续传（如果可能）
- 或者重新开始上传
- 提供有意义的错误信息

## MODIFIED Requirements

### MU-004: 现有接口兼容性
#### Scenario: 现有API调用保持不变
**Given** 现有的 `upload_directory_to_minio` 调用  
**When** 不启用压缩参数  
**Then** 应该保持原有的行为和性能特征

#### Scenario: 向后兼容参数
**Given** 旧版本的API调用  
**When** 不提供新参数  
**Then** 应该使用默认值：
- `compress_before_upload = false`
- `compression_format = "zip"`
- `compression_level = "default"`

### MU-005: 输出格式增强
#### Scenario: 新增输出字段
**Given** 成功完成压缩上传  
**When** 返回结果  
**Then** 应该包含额外字段：
- `archive_url`: 压缩包的MinIO URL
- `compression_info`: 压缩统计信息字典
- `compressed`: 是否使用压缩模式的标志

## REMOVED Requirements

无

## 验证标准

- 压缩上传必须支持所有现有参数
- 错误处理必须完善，包含自动回退
- 性能必须优于非压缩模式（大量文件场景）
- 内存使用必须受控，支持大目录
- 向后兼容性必须100%

**变更ID**: video-directory-compression-upload  
**能力**: minio-directory-upload  
**状态**: 待实施  
**版本**: v1.0