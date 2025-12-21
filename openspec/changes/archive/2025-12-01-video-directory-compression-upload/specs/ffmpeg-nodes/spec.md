# FFmpeg工作流节点 - 规格Delta

## ADDED Requirements

### FF-001: crop_subtitle_images 节点压缩上传
#### Scenario: 启用压缩上传
**Given** crop_subtitle_images 任务  
**When** 设置 `compress_directory_before_upload = true`  
**Then** 应该：
- 在上传裁剪图片时启用压缩模式
- 使用默认 "zip" 格式和 "default" 级别
- 返回压缩包URL和压缩统计信息

#### Scenario: 压缩参数配置
**Given** crop_subtitle_images 任务  
**When** 提供压缩相关参数  
**Then** 应该支持：
- `compression_format`: "zip" 或 "tar.gz"
- `compression_level`: "store", "fast", "default", "maximum"
- 自动验证参数格式和范围

#### Scenario: 压缩失败回退
**Given** 压缩上传失败  
**When** 执行任务  
**Then** 应该：
- 自动回退到非压缩上传模式
- 设置 `fallback_from_compression = true`
- 记录 `original_error` 详细信息
- 任务状态保持成功

### FF-002: extract_keyframes 节点压缩上传
#### Scenario: 关键帧压缩上传
**Given** extract_keyframes 任务  
**When** 设置 `compress_keyframes_before_upload = true`  
**Then** 应该：
- 压缩上传提取的关键帧图片
- 只压缩 .jpg 格式文件
- 返回与 crop_subtitle_images 一致的输出格式

#### Scenario: 关键帧压缩配置
**Given** extract_keyframes 任务压缩模式  
**When** 提供配置参数  
**Then** 应该与 crop_subtitle_images 保持一致：
- 相同的参数名称和默认值
- 相同的错误处理逻辑
- 相同的输出格式结构

## MODIFIED Requirements

### FF-003: 输出格式增强
#### Scenario: 新增压缩包URL字段
**Given** 成功完成压缩上传  
**When** 返回输出数据  
**Then** 应该包含：
- `compressed_archive_url`: 压缩包的MinIO URL
- `compression_info`: 压缩统计信息字典
- `fallback_from_compression`: 是否从压缩模式回退的标志

#### Scenario: 压缩统计信息
**Given** 压缩上传完成  
**When** 返回压缩信息  
**Then** 应该包含：
- `original_size`: 原始目录大小（字节）
- `compressed_size`: 压缩包大小（字节）
- `compression_ratio`: 压缩比例（0-1）
- `files_count`: 处理的文件数量
- `compression_time`: 压缩耗时（秒）
- `checksum`: 压缩包校验和
- `format`: 使用的压缩格式

### FF-004: 参数系统集成
#### Scenario: 参数解析增强
**Given** 工作流参数系统  
**When** 解析压缩相关参数  
**Then** 应该：
- 支持 `${{node_params.ffmpeg.crop_subtitle_images.compress_directory_before_upload}}` 格式
- 提供默认值确保向后兼容
- 验证参数类型和取值范围

#### Scenario: 工作流上下文集成
**Given** 工作流执行上下文  
**When** 使用压缩上传  
**Then** 应该：
- 正确传递压缩参数到上传函数
- 在工作流上下文中记录压缩状态
- 支持压缩相关的监控和日志

## REMOVED Requirements

无

## 验证标准

- 所有现有API调用必须保持不变
- 新参数必须默认为禁用状态
- 压缩失败时必须自动回退
- 输出格式必须向后兼容
- 性能提升必须达到预期目标

**变更ID**: video-directory-compression-upload  
**能力**: ffmpeg-nodes  
**状态**: 待实施  
**版本**: v1.0