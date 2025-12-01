# 技术设计文档：修复 ffmpeg.crop_subtitle_images 压缩上传

## 背景

本设计文档针对 `video-directory-compression-upload` 功能实施后导致的 `ffmpeg.crop_subtitle_images` 任务压缩上传失败问题。

## 问题详情

### 错误1: 目录路径错误
```python
# 错误：尝试访问不存在的路径
compress_dir = "/share/single_tasks/task_id/cropped_images/frames"

# 实际：图片存储在
actual_dir = "/share/single_tasks/task_id/cropped_images/"
```

### 错误2: 变量未定义
```python
# minio_directory_upload.py:514
"fast": CompressionLevel.FAST,
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
# 上一行：
bucket_name: Optional[str] = None,
# ...
else:
    # 错误：compression_format 变量未定义
    if compression_format == "zip":
```

### 错误3: 压缩包不存在
- 压缩过程失败，生成的压缩包文件不存在
- 但后续代码仍尝试访问该文件
- 缺少错误处理和回退机制

## 技术方案

### 方案1: 修复路径硬编码（推荐）

**决策**: 修复路径逻辑，使其能正确识别实际存储位置

**实现**:
```python
# ffmpeg_service/app/tasks.py
def crop_subtitle_images(self, context):
    # ...
    # 原代码:
    # frames_dir = os.path.join(output_dir, "frames")
    
    # 修改为：
    frames_dir = output_dir  # 直接使用 output_dir，不添加 frames 子目录
    
    # 添加路径验证
    if not os.path.exists(frames_dir):
        # 尝试带 frames 子目录的路径
        frames_dir_with_subdir = os.path.join(output_dir, "frames")
        if os.path.exists(frames_dir_with_subdir):
            frames_dir = frames_dir_with_subdir
        else:
            # 记录警告，但继续使用原始路径
            self.log.warning(f"目录不存在: {frames_dir}")
```

**优点**:
- 简单直接，修复最根本的问题
- 不改变现有架构
- 风险低

**缺点**:
- 可能还有其他隐藏的路径问题

### 方案2: 抽象路径管理（备选）

**决策**: 创建统一的路径管理逻辑

**实现**:
```python
# 创建 PathResolver 类
class ImagePathResolver:
    @staticmethod
    def resolve_cropped_images_dir(task_id):
        """解析裁剪图片目录，支持多种结构"""
        base_path = f"/share/single_tasks/{task_id}/cropped_images"
        
        # 方案A: 直接存储
        if os.path.exists(base_path):
            return base_path
        
        # 方案B: frames 子目录
        frames_path = os.path.join(base_path, "frames")
        if os.path.exists(frames_path):
            return frames_path
        
        # 默认返回
        return base_path
```

**优点**:
- 更好的可维护性
- 支持多种路径结构
- 便于未来扩展

**缺点**:
- 需要更多重构代码
- 增加复杂性

**结论**: 鉴于这是紧急 bug 修复，采用方案1，快速解决问题。

### 方案3: 完善错误处理

**决策**: 添加压缩失败回退机制

**实现**:
```python
# minio_directory_upload.py
def upload_directory_compressed(..., compression_format=None):
    try:
        # 尝试压缩上传
        compression_result = compress_directory(...)
        
        # 上传压缩包
        upload_result = upload_to_minio(
            local_file_path=compression_result.compressed_file_path,
            ...
        )
        
        return {
            "success": True,
            "compressed": True,
            **upload_result
        }
        
    except Exception as e:
        # 压缩或上传失败，记录日志
        logger.warning(f"压缩上传失败，回退到非压缩模式: {e}")
        
        # 回退到非压缩上传
        return upload_directory_uncompressed(...)
```

**优点**:
- 提高系统鲁棒性
- 用户体验更好
- 避免完全失败

**缺点**:
- 可能掩盖实际问题
- 需要记录回退次数

## 变量引用错误修复

### 问题位置
```python
# minio_directory_upload.py:350 附近
else:
    # 错误：compression_format 变量未定义
    if compression_format == "zip":
```

### 修复方案
```python
# 修复：使用参数中的 compression_format
def upload_directory_to_minio(
    ...,
    compression_format: str = None,
    compression_level: str = None
):
    ...
    # 在函数内部使用参数
    if compression_format == "zip":
        ...
```

**关键点**: 确保函数签名中的参数能正确传递到使用位置。

## 测试策略

### 单元测试
1. **路径解析测试**
   ```python
   def test_cropped_images_path_resolution():
       # 测试无 frames 子目录的情况
       # 测试有 frames 子目录的情况
       # 测试目录不存在的情况
   ```

2. **压缩上传测试**
   ```python
   def test_compression_fallback():
       # 测试压缩成功的情况
       # 测试压缩失败回退的情况
       # 测试压缩包上传失败回退的情况
   ```

### 集成测试
1. 使用提供的测试参数执行完整流程
2. 验证文件成功上传到 MinIO
3. 验证日志无错误信息

## 风险评估

### 高风险
- **无**: 这是明确的bug修复，不会引入新功能

### 中风险
- **回归风险**: 可能影响现有功能
- **缓解**: 充分的单元测试和集成测试

### 低风险
- **路径变化**: 可能还有其他代码依赖特定路径
- **缓解**: 代码审查，确保所有引用都已修复

## 迁移计划

### 回滚方案
1. 如果修复失败，可以快速回滚到非压缩上传模式
2. 保持所有现有API不变
3. 回滚步骤：
   ```bash
   git revert <commit-hash>
   docker-compose restart ffmpeg_service
   ```

### 部署步骤
1. 修复代码并提交
2. 构建镜像：`docker-compose build ffmpeg_service`
3. 部署到测试环境
4. 运行测试验证
5. 部署到生产环境
6. 监控系统日志24小时

## 开放问题

1. **Q**: 为什么最初的设计假设图片存储在 `frames` 子目录中？
   **A**: 需要追溯代码历史，了解原始设计意图。可能是为了与 `extract_keyframes` 保持一致。

2. **Q**: 是否需要为其他任务也添加类似的回退机制？
   **A**: 建议在完成此修复后，审查所有压缩相关功能，确保一致性。

3. **Q**: 如何确保修复后不会影响 `extract_keyframes` 功能？
   **A**: 通过集成测试验证 `extract_keyframes` 仍然正常工作。

## 总结

本修复采用最小化更改原则：
1. 修复路径问题
2. 修复变量引用错误
3. 添加回退机制

目标是快速解决问题，降低风险，确保系统稳定运行。
