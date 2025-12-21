# PaddleOCR工作流节点 - 规格Delta

## ADDED Requirements

### PO-001: detect_subtitle_area 压缩包下载
#### Scenario: 自动解压关键帧
**Given** detect_subtitle_area 任务  
**When** 提供压缩包URL并设置 `auto_decompress = true`  
**Then** 应该：
- 下载压缩包到本地临时目录
- 自动检测压缩包格式并解压
- 将解压后的关键帧用于区域检测

#### Scenario: 压缩包URL检测
**Given** 输入的URL  
**When** URL指向压缩包  
**Then** 应该：
- 基于文件扩展名识别压缩格式（.zip, .tar.gz）
- 保留原始文件名避免信息丢失
- 使用MinIO API验证URL有效性

### PO-002: create_stitched_images 压缩包支持
#### Scenario: 压缩包图片输入
**Given** create_stitched_images 任务  
**When** `cropped_images_path` 是压缩包URL  
**Then** 应该：
- 支持压缩包下载和自动解压
- 将解压后的图片用于图像拼接
- 保持现有的批量处理逻辑不变

#### Scenario: 多帧压缩包处理
**Given** create_stitched_images 多帧模式  
**When** `multi_frames_path` 是压缩包URL  
**Then** 应该：
- 解压多帧图片包
- 验证解压后的目录结构
- 继续正常的拼接处理流程

### PO-003: perform_ocr 压缩包OCR
#### Scenario: 多帧压缩包OCR
**Given** perform_ocr 任务多帧模式  
**When** `multi_frames_path` 是压缩包URL  
**Then** 应该：
- 下载并解压多帧图片
- 保持与manifest文件处理逻辑的兼容性
- 执行正常的OCR识别流程

## MODIFIED Requirements

### PO-004: 下载参数增强
#### Scenario: 自动解压参数
**Given** 所有使用下载功能的PaddleOCR任务  
**When** 解析参数  
**Then** 应该支持：
- `auto_decompress`: boolean, 默认true, 是否自动解压
- `decompress_dir`: string, 可选, 指定解压目录
- `delete_compressed_after_decompress`: boolean, 默认false, 解压后删除压缩包

#### Scenario: 参数格式支持
**Given** 工作流参数系统  
**When** 解析解压参数  
**Then** 应该支持：
- `${{node_params.paddleocr.detect_subtitle_area.auto_decompress}}` 格式
- 正确的默认值和类型验证
- 与现有参数系统的无缝集成

### PO-005: 智能URL处理
#### Scenario: URL类型检测
**Given** 各种格式的输入路径  
**When** 处理下载请求  
**Then** 应该：
- 区分普通目录URL和压缩包URL
- 对压缩包URL保持原始文件名
- 对普通URL进行MinIO格式规范化

#### Scenario: 压缩包文件名校验
**Given** 压缩包URL包含文件名信息  
**When** 下载和解压  
**Then** 应该：
- 验证文件名符合预期格式
- 避免文件名冲突和覆盖
- 提供详细的下载和解压日志

## REMOVED Requirements

无

## 验证标准

- 所有现有API调用必须保持不变
- 自动解压必须默认为启用状态
- 压缩包下载必须支持所有主流格式
- 解压失败时必须有适当的错误处理
- 性能必须优于逐个文件下载模式

**变更ID**: video-directory-compression-upload  
**能力**: paddleocr-nodes  
**状态**: 待实施  
**版本**: v1.0