# 视频图片目录压缩上传优化提案

## Why

YiVideo平台中的`ffmpeg.crop_subtitle_images`和`ffmpeg.extract_keyframes`功能在处理大量图片时存在严重的性能问题。当前实现采用逐个文件上传的方式，对于几千至上万张图片的工作负载，会产生大量的网络传输请求，导致执行效率低下。

### 现状问题
- **ffmpeg.crop_subtitle_images**: 处理视频的所有字幕帧图片，数量可达几千至上万张
- **ffmpeg.extract_keyframes**: 随机抽取关键帧，通常几十到几百张图片
- **上传方式**: 逐个文件上传，建立大量HTTP连接
- **性能影响**: 网络延迟累积，服务器连接池压力，处理时间过长

## What Changes

通过引入目录压缩机制，将大量图片文件打包成单一压缩包后上传，显著减少网络请求次数，提高传输效率。

### 核心改进点

#### 1. 目录压缩功能
- 实现`directory_compression.py`模块，提供ZIP压缩能力
- 支持大文件压缩和进度回调
- 包含完整性校验机制

#### 2. 上传流程优化
- 扩展`minio_directory_upload.py`，添加压缩包上传选项
- 上传前自动压缩目录
- 支持压缩包URL作为输出

#### 3. 功能节点扩展
- **ffmpeg.crop_subtitle_images**: 添加`compress_directory_before_upload`参数
- **ffmpeg.extract_keyframes**: 扩展现有上传逻辑，支持压缩选项
- **paddleocr.detect_subtitle_area**: 支持从压缩包下载和解压

#### 4. 向后兼容性
- 保持现有参数和接口不变
- 新参数为可选，默认为False（保持原有行为）
- 支持渐进式迁移

YiVideo平台中的`ffmpeg.crop_subtitle_images`和`ffmpeg.extract_keyframes`功能在处理大量图片时存在性能问题。当前实现采用逐个文件上传的方式，对于几千至上万张图片的工作负载，会产生大量的网络传输请求，导致执行效率低下。

### 现状问题
- **ffmpeg.crop_subtitle_images**: 处理视频的所有字幕帧图片，数量可达几千至上万张
- **ffmpeg.extract_keyframes**: 随机抽取关键帧，通常几十到几百张图片
- **上传方式**: 逐个文件上传，建立大量HTTP连接
- **性能影响**: 网络延迟累积，服务器连接池压力，处理时间过长

## 解决方案

通过引入目录压缩机制，将大量图片文件打包成单一压缩包后上传，显著减少网络请求次数，提高传输效率。

### 核心改进点

#### 1. 目录压缩功能
- 实现`directory_compression.py`模块，提供ZIP压缩能力
- 支持大文件压缩和进度回调
- 包含完整性校验机制

#### 2. 上传流程优化
- 扩展`minio_directory_upload.py`，添加压缩包上传选项
- 上传前自动压缩目录
- 支持压缩包URL作为输出

#### 3. 功能节点扩展
- **ffmpeg.crop_subtitle_images**: 添加`compress_directory_before_upload`参数
- **ffmpeg.extract_keyframes**: 扩展现有上传逻辑，支持压缩选项
- **paddleocr.detect_subtitle_area**: 支持从压缩包下载和解压

#### 4. 向后兼容性
- 保持现有参数和接口不变
- 新参数为可选，默认为False（保持原有行为）
- 支持渐进式迁移

## 影响分析

### 受影响的功能
- **ffmpeg.crop_subtitle_images**: 核心功能修改
- **ffmpeg.extract_keyframes**: 扩展上传选项
- **paddleocr.detect_subtitle_area**: 新增压缩包支持
- **minio_directory_upload/upload**: 扩展上传能力

### 性能提升预期
- **上传效率**: 提升80%+（网络请求从N次减少到1次）
- **网络带宽**: 节省60%+（压缩比通常30-50%）
- **处理时间**: 减少50-70%（特别是大量文件场景）
- **服务器资源**: 减少连接池压力

### 风险评估
- **低风险**: 新参数为可选，不影响现有功能
- **内存占用**: 压缩过程临时增加内存使用
- **磁盘空间**: 压缩过程需要额外临时空间
- **失败回退**: 压缩失败时自动回退到原有上传方式

## 实施计划

### Phase 1: 核心模块开发 (预计2-3天)
1. 创建`directory_compression.py`压缩模块
2. 扩展`minio_directory_upload.py`支持压缩包
3. 实现下载解压功能

### Phase 2: 功能节点更新 (预计1-2天)
1. 更新`ffmpeg.crop_subtitle_images`支持压缩
2. 更新`ffmpeg.extract_keyframes`扩展上传选项
3. 更新`paddleocr.detect_subtitle_area`支持压缩包

### Phase 3: 测试验证 (预计1天)
1. 单元测试覆盖
2. 集成测试验证
3. 性能基准测试

### Phase 4: 文档和部署 (预计0.5天)
1. 更新文档和配置示例
2. 监控指标添加
3. 生产环境部署

## 成功标准

### 技术指标
- 压缩功能稳定性>99%
- 向后兼容性100%
- 性能提升>50%（实测）
- 内存使用增长<20%

### 功能指标
- 保持现有API兼容性
- 新参数默认行为与原功能一致
- 错误处理完善（失败回退机制）
- 监控和日志完整

## 后续优化方向

1. **压缩算法优化**: 支持更多压缩格式（tar.gz, 7z等）
2. **增量上传**: 对大文件支持分块压缩和断点续传
3. **智能压缩**: 根据文件类型选择最佳压缩策略
4. **缓存机制**: 压缩结果缓存，避免重复压缩

---

**变更ID**: video-directory-compression-upload  
**提案版本**: v1.0  
**创建时间**: 2025-11-30  
**提案状态**: 待评审