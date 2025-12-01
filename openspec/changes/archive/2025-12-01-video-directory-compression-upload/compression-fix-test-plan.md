# 压缩上传功能修复测试计划

## 修复总结

### 🔧 主要修复内容

1. **修复临时文件名生成问题**
   - 问题：`shutil._hash_compress` 属性不存在导致AttributeError
   - 解决：实现时间戳 + UUID的临时文件名生成机制

2. **修复ffmpeg任务逻辑错误** 
   - 问题：`upload_cropped_images_compressed` 函数返回键名错误
   - 解决：统一返回 `result['archive_url']` 替代 `result['uploaded_files']`

3. **修复参数类型处理问题**
   - 问题：`AttributeError: 'CompressionLevel' object has no attribute 'lower'`
   - 解决：实现灵活参数处理，支持字符串和枚举类型输入

### 📁 修复的核心文件

#### 1. services/common/directory_compression.py
```python
# 修复了临时文件生成
temp_dir = tempfile.gettempdir()
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
unique_id = str(uuid.uuid4())[:8]
compress_filename = f"{timestamp}_{unique_id}_compressed"

if format_enum == CompressionFormat.ZIP:
    archive_path = os.path.join(temp_dir, f"{compress_filename}.zip")
```

#### 2. services/workers/ffmpeg_service/app/tasks.py
```python
# 修复了返回键名
result['archive_url'] = compression_result['archive_url']
# 移除错误的 result['uploaded_files'] 处理
```

#### 3. services/common/minio_directory_upload.py
```python
# 修复了参数类型处理
def upload_directory_compressed(..., 
                               compression_format: Union[str, CompressionFormat] = "zip",
                               compression_level: Union[str, CompressionLevel] = "default", ...):
    
    # 参数类型转换
    format_str = compression_format.value if isinstance(compression_format, CompressionFormat) else compression_format
    level_str = compression_level.value if isinstance(compression_level, CompressionLevel) else compression_level
    format_enum = CompressionFormat(format_str)
    level_enum = CompressionLevel(level_str)
```

## 🧪 测试计划

### 测试场景 1: 基础压缩功能
```python
# 创建测试目录
test_dir = create_test_images(num_images=10)

# 测试ZIP压缩
result = compress_directory(
    directory_path=str(test_dir),
    compression_format=CompressionFormat.ZIP,
    compression_level=CompressionLevel.DEFAULT,
    delete_original=False
)

# 验证结果
assert os.path.exists(result['archive_path'])
assert result['file_count'] == 10
assert 'compression_ratio' in result
```

### 测试场景 2: 参数类型兼容性
```python
# 测试字符串参数
upload_directory_compressed(
    local_dir="test_path",
    minio_base_path="test/upload",
    compression_format="zip",  # 字符串
    compression_level="default"  # 字符串
)

# 测试枚举参数  
upload_directory_compressed(
    local_dir="test_path", 
    minio_base_path="test/upload",
    compression_format=CompressionFormat.ZIP,  # 枚举
    compression_level=CompressionLevel.DEFAULT  # 枚举
)
```

### 测试场景 3: 完整工作流
```json
{
    "task_name": "ffmpeg.crop_subtitle_images",
    "input_data": {
        "upload_cropped_images_to_minio": true,
        "compress_directory_before_upload": true,
        "compression_format": "zip", 
        "compression_level": "default"
    }
}
```

### 测试场景 4: 关键帧压缩上传
```json
{
    "task_name": "ffmpeg.extract_keyframes",
    "input_data": {
        "upload_keyframes_to_minio": true,
        "compress_keyframes_before_upload": true,
        "keyframe_compression_format": "zip",
        "keyframe_compression_level": "default" 
    }
}
```

## ✅ 验证要点

1. **压缩功能正常**
   - 临时文件生成无错误
   - 压缩过程无异常
   - 文件完整性验证通过

2. **上传功能正常**
   - 参数类型处理正确
   - 返回格式统一
   - 错误处理机制完善

3. **工作流集成正常**
   - ffmpeg任务集成正确
   - 状态管理配合正常
   - 向后兼容性保持

## 🚀 性能优势

### 修复前 vs 修复后
- **修复前**: 1,000张图片 → 1,000次单独上传请求
- **修复后**: 1,000张图片 → 1次压缩包上传请求

### 网络请求减少
- 减少 99.9% 的网络请求数量
- 显著提升大批量图片上传性能
- 降低网络超时和失败风险

## 📊 预期测试结果

1. **压缩测试**: ✅ 所有压缩格式正常工作
2. **参数测试**: ✅ 字符串和枚举参数都能正确处理  
3. **集成测试**: ✅ ffmpeg任务集成无错误
4. **性能测试**: ✅ 大文件集合压缩上传性能显著提升

---

**修复完成时间**: 2025-11-30 18:46:21
**状态**: ✅ 修复完成，准备测试验证