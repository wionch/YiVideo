# 修复：ffmpeg.crop_subtitle_images 压缩上传报错问题

## Why

在完成 `video-directory-compression-upload` 功能实施后，`ffmpeg.crop_subtitle_images` 任务在尝试使用压缩上传功能时出现多个严重错误，导致任务虽然返回成功状态，但实际文件上传失败。这些错误包括：
1. 变量未定义错误 (NameError)
2. 目录路径错误，导致压缩失败
3. 错误处理机制不完善，压缩失败时无法自动回退
4. 文件模式匹配错误，导致无法找到要压缩的文件

这些问题的存在导致 `ffmpeg.crop_subtitle_images` 的压缩上传功能完全不可用，影响了系统的整体性能和用户体验。

## What Changes

本次修复包含以下变更：
- 修复 `minio_directory_upload.py` 中未定义变量 `format_enum` 和 `level_enum` 的错误
- 修复对枚举类型调用字符串方法 `.lower()` 的错误
- 添加智能路径解析逻辑，支持带/不带 frames 子目录的两种模式
- 修复文件模式匹配逻辑，正确处理逗号分隔的文件模式字符串
- 完善错误处理机制，添加三层回退机制确保压缩失败时自动回退到非压缩上传模式
- 保持向后兼容性，不影响现有非压缩上传功能

## 问题背景

在完成 `video-directory-compression-upload` 功能实施后，`ffmpeg.crop_subtitle_images` 任务在尝试使用压缩上传功能时出现多个严重错误，导致任务虽然返回成功状态，但实际文件上传失败。

### 报错现象

当调用以下参数时：
```json
{
    "task_name": "ffmpeg.crop_subtitle_images",
    "input_data": {
        "video_path": "http://host.docker.internal:9000/yivideo/task_id/223.mp4",
        "subtitle_area": [0, 607, 1280, 679],
        "upload_cropped_images_to_minio": true,
        "compress_directory_before_upload": true,
        "compression_format": "zip",
        "compression_level": "default"
    }
}
```

## 问题分析

### 1. 目录路径错误
- **错误路径**: `/share/single_tasks/task_id/cropped_images/frames`
- **实际路径**: `/share/single_tasks/task_id/cropped_images/frames`（frames子目录不存在）
- **根因**: 代码假设图片存储在 `frames` 子目录中，但实际直接存储在 `cropped_images` 目录

### 2. 变量名错误 (NameError)
- **错误信息**: `NameError: name 'compression_format' is not defined`
- **根因**: 压缩级别映射时使用 `compression_format` 变量，但实际应该使用参数中的 `compression_format` 值
- **位置**: `services/common/minio_directory_upload.py:514`

### 3. 压缩包文件不存在
- **错误**: 压缩失败后仍尝试上传不存在的压缩包文件
- **根因**: 错误处理不当，压缩失败时没有正确回退
- **表现**: `FileNotFoundError: 本地文件不存在: /tmp/frames_compressed_*.zip`

## 解决方案

### 1. 修复目录路径问题
- 调整 `ffmpeg.crop_subtitle_images` 任务，正确识别图片存储路径
- 支持两种路径模式：带 `frames` 子目录和不带子目录
- 添加路径验证逻辑

### 2. 修复变量引用错误
- 将 `compression_format` 变量改为使用实际的参数值
- 确保压缩级别映射正确使用 `compression_format` 参数

### 3. 完善错误处理机制
- 压缩失败时正确回退到非压缩上传模式
- 添加详细的错误日志和状态记录
- 确保任务状态与实际执行结果一致

### 4. 添加单元测试
- 测试压缩和非压缩两种模式
- 测试不同目录结构情况
- 测试错误回退机制

## 预期成果

1. **ffmpeg.crop_subtitle_images** 在使用压缩上传时能够正常工作
2. 错误处理机制完善，压缩失败时自动回退
3. 日志信息更加清晰，便于问题排查
4. 所有相关路径和变量引用正确

## 影响范围

### 直接影响
- `services/workers/ffmpeg_service/app/tasks.py` - ffmpeg.crop_subtitle_images 实现
- `services/common/minio_directory_upload.py` - 压缩上传逻辑
- `services/common/file_service.py` - 文件上传服务

### 测试覆盖
- `tests/unit/services/workers/ffmpeg_service/test_crop_subtitle_images.py`
- `tests/unit/services/common/test_minio_directory_upload.py`

### 相关功能
- `ffmpeg.extract_keyframes` (已正常工作)
- `paddleocr.detect_subtitle_area` (应不受影响)

## 风险评估

- **低风险**: 这是明确的bug修复，不改变现有API
- **向后兼容**: 保持所有现有参数和接口不变
- **回退方案**: 如修复失败，可回退到非压缩上传模式
- **测试覆盖**: 修复后进行全面测试验证

## 验证标准

1. ✅ `ffmpeg.crop_subtitle_images` 使用压缩上传参数时正常执行
2. ✅ 压缩失败时自动回退到非压缩模式
3. ✅ 日志记录清晰，无误导性错误信息
4. ✅ 单元测试和集成测试通过
5. ✅ 不影响现有非压缩上传功能

---

## 完成状态
✅ **所有问题已修复并通过测试验收**

**变更ID**: fix-crop-subtitle-images-compression
**提案版本**: v1.0
**创建时间**: 2025-11-30
**完成时间**: 2025-11-30 19:20
**提案状态**: 已完成
