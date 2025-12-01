# MinIO目录上传功能使用指南

## 概述

本系统已实现完整的MinIO目录上传功能，支持：
- 递归上传整个目录到MinIO
- 保留目录结构
- 可选的本地目录清理
- 详细的错误处理和日志记录
- 自动上传机制集成

## 新增功能

### 1. MinIO目录上传模块 (`services/common/minio_directory_upload.py`)

#### 核心类
- **MinioDirectoryUploader**: 主要的上传器类
- **upload_directory_to_minio()**: 便捷函数
- **upload_keyframes_directory()**: 专门用于关键帧的便捷函数

#### 支持的参数
- `local_dir`: 本地目录路径
- `minio_base_path`: MinIO中的基础路径（不包含bucket）
- `bucket_name`: 存储桶名称（可选）
- `file_pattern`: 文件匹配模式（默认"*"，只上传JPEG文件）
- `delete_local`: 上传成功后是否删除本地目录（默认False）
- `preserve_structure`: 是否保留目录结构（默认True）

### 2. 更新的 `ffmpeg.extract_keyframes` 任务

#### 新增参数
- `upload_keyframes_to_minio`: 是否上传关键帧目录到MinIO（默认False）
- `delete_local_keyframes_after_upload`: 上传成功后是否删除本地目录（默认False）

#### 输出字段
基础输出：
```json
{
    "keyframe_dir": "/local/path/to/keyframes"
}
```

启用上传后的输出：
```json
{
    "keyframe_dir": "/local/path/to/keyframes",
    "keyframe_minio_url": "http://minio:9000/bucket/workflow_id/keyframes",
    "keyframe_files_count": 100,
    "keyframe_uploaded_files": ["frame_0001.jpg", "frame_0002.jpg", ...]
}
```

上传失败时的输出：
```json
{
    "keyframe_dir": "/local/path/to/keyframes",
    "keyframe_upload_error": "错误信息",
    "keyframe_files_count": 100,
    "keyframe_uploaded_files": ["成功上传的文件列表"]
}
```

### 3. 更新的状态管理器自动上传

状态管理器现在会自动检测和处理 `keyframe_dir` 字段：
- 检测目录路径
- 递归上传所有JPEG文件
- 保留目录结构
- 更新输出为MinIO URL

## 使用方法

### 方法1: 通过参数启用上传（推荐）

在调用 `ffmpeg.extract_keyframes` 时传入参数：

```python
# 在工作流配置中
{
    "node_params": {
        "ffmpeg.extract_keyframes": {
            "upload_keyframes_to_minio": True,
            "delete_local_keyframes_after_upload": False
        }
    }
}
```

### 方法2: 依赖自动上传机制

如果设置了 `upload_keyframes_to_minio=False`，状态管理器会自动检测并上传 `keyframe_dir` 目录。

### 方法3: 直接使用模块

```python
from services.common.minio_directory_upload import upload_keyframes_directory

result = upload_keyframes_directory(
    local_dir="/path/to/keyframes",
    workflow_id="workflow_123",
    delete_local=False
)

print(f"上传结果: {result}")
```

## MinIO路径结构

上传后的文件在MinIO中的路径结构：
```
bucket/
└── {workflow_id}/
    └── keyframes/
        ├── frame_0001.jpg
        ├── frame_0002.jpg
        ├── frame_0003.jpg
        └── ...
```

## 注意事项

1. **上传路径**: 所有文件上传到 `{workflow_id}/keyframes/` 路径下
2. **文件类型**: 默认只上传JPEG文件（*.jpg）
3. **目录保留**: 保持原始目录结构
4. **错误处理**: 上传失败不会影响主要业务流程
5. **性能**: 大目录上传可能需要较长时间
6. **存储清理**: 默认不删除本地文件，可通过参数控制

## 错误处理

- 目录不存在 → 抛出 FileNotFoundError
- 参数无效 → 抛出 ValueError
- 上传失败 → 记录日志但不影响主流程
- 部分文件失败 → 返回成功和失败文件列表

## 日志记录

系统会记录详细的日志信息：
- 上传开始/完成
- 成功/失败的文件列表
- 错误信息和堆栈跟踪
- 性能统计信息

## 配置建议

1. **生产环境**: 建议启用 `upload_keyframes_to_minio=True`
2. **本地测试**: 可以使用自动上传机制
3. **存储清理**: 生产环境建议 `delete_local_keyframes_after_upload=True`
4. **文件过滤**: 可以调整 `file_pattern` 来控制上传的文件类型

## 向后兼容性

- ✅ 现有代码无需修改
- ✅ 默认行为保持不变
- ✅ 新功能通过参数控制
- ✅ 自动上传机制可选

## 性能优化

1. **并发上传**: 支持多文件并发上传
2. **错误恢复**: 单个文件失败不影响其他文件
3. **资源管理**: 及时释放上传后的文件句柄
4. **进度跟踪**: 详细的进度和统计信息