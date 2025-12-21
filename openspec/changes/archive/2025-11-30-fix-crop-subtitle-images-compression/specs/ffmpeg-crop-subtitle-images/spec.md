## ADDED Requirements
### Requirement: ffmpeg.crop_subtitle_images 支持压缩上传
ffmpeg.crop_subtitle_images 任务 SHALL 支持通过 compress_directory_before_upload 参数启用目录压缩上传功能。

#### Scenario: 启用压缩上传成功
- **GIVEN** 任务参数包含 compress_directory_before_upload=true, compression_format="zip"
- **AND** 图片文件存在于正确的目录路径
- **WHEN** 执行 ffmpeg.crop_subtitle_images 任务
- **THEN** 系统 SHALL 压缩图片目录并上传压缩包到 MinIO
- **AND** 返回压缩包的 MinIO URL
- **AND** 任务状态为成功
- **AND** 日志记录压缩上传成功信息

#### Scenario: 压缩失败时自动回退
- **GIVEN** 任务参数包含 compress_directory_before_upload=true
- **AND** 压缩过程失败（例如：目录不存在、磁盘空间不足）
- **WHEN** 执行 ffmpeg.crop_subtitle_images 任务
- **THEN** 系统 SHALL 记录压缩失败的警告日志
- **AND** 自动回退到非压缩上传模式
- **AND** 成功上传文件到 MinIO
- **AND** 返回上传文件的 MinIO URL
- **AND** 任务状态为成功

#### Scenario: 压缩上传路径处理
- **GIVEN** 任务执行完成后生成图片文件
- **AND** 启用了压缩上传功能
- **WHEN** 系统尝试压缩目录
- **THEN** 系统 SHALL 正确识别图片实际存储路径（无 frames 子目录）
- **AND** 压缩该路径下的所有图片文件
- **AND** 不出现 "No such file or directory" 错误
- **AND** 成功生成压缩包文件

#### Scenario: 变量引用正确性
- **GIVEN** 启用了压缩上传功能
- **AND** compression_format 参数为 "zip"
- **WHEN** 执行压缩上传逻辑
- **THEN** 所有 compression_format 变量引用 SHALL 正确解析
- **AND** 不出现 "NameError: name 'compression_format' is not defined" 错误
- **AND** 压缩级别映射正确应用

#### Scenario: 不影响非压缩模式
- **GIVEN** 任务参数不包含 compress_directory_before_upload 或设为 false
- **WHEN** 执行 ffmpeg.crop_subtitle_images 任务
- **THEN** 系统 SHALL 使用原有非压缩上传逻辑
- **AND** 行为与修复前完全一致
- **AND** 不出现任何新的错误或警告
- **AND** 保持所有现有API参数不变

### Requirement: ffmpeg.crop_subtitle_images 错误处理机制
系统 SHALL 为 ffmpeg.crop_subtitle_images 提供完善的错误处理机制。

#### Scenario: 压缩包文件不存在错误处理
- **GIVEN** 压缩过程生成压缩包失败
- **WHEN** 系统尝试上传压缩包
- **THEN** 系统 SHALL 检测到压缩包文件不存在
- **AND** 记录详细的错误日志（包含文件路径信息）
- **AND** 触发回退机制，尝试非压缩上传
- **AND** 最终任务状态为成功（如果回退成功）
- **AND** 不抛出未捕获的异常

#### Scenario: 路径验证和警告
- **GIVEN** 图片目录路径与预期不符
- **WHEN** 系统尝试压缩目录
- **THEN** 系统 SHALL 验证路径是否存在
- **AND** 如果路径不存在，SHALL 记录警告日志
- **AND** 尝试其他可能的路径（带 frames 子目录）
- **AND** 如果所有路径都不存在，记录错误并终止压缩
- **AND** 触发回退机制
