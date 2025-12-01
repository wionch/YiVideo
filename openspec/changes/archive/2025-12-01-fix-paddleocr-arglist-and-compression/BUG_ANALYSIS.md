# Bug分析报告：`paddleocr.create_stitched_images`压缩包未解压问题

## 问题描述

在执行`paddleocr.create_stitched_images`任务时，虽然成功下载了压缩包，但没有进行解压，导致后续图片拼接失败。

## 日志分析

### 输入数据
```json
{
    "task_name": "paddleocr.create_stitched_images",
    "task_id": "task_id",
    "input_data": {
        "cropped_images_path": "http://host.docker.internal:9000/yivideo/task_id/cropped_images/frames_compressed.zip",
        "subtitle_area": [0, 607, 1280, 679],
        "upload_stitched_images_to_minio": true,
        "auto_decompress": true
    }
}
```

### 关键日志信息
```
[2025-12-01 08:01:55,556: INFO/ForkPoolWorker-29] [paddleocr.create_stitched_images] 检测到输入路径为URL，尝试从远程下载目录: http://host.docker.internal:9000/yivideo/task_id/cropped_images/frames_compressed.zip

[2025-12-01 08:01:55,556: INFO/ForkPoolWorker-29] [paddleocr.create_stitched_images] 规范化URL为MinIO格式: minio://yivideo/task_id/cropped_images

[2025-12-01 08:01:55,556: INFO/ForkPoolWorker-29] 开始下载MinIO目录: minio://yivideo/task_id/cropped_images

[2025-12-01 08:01:55,580: INFO/ForkPoolWorker-29] 找到 1 个文件需要下载

[2025-12-01 08:02:04,785: INFO/ForkPoolWorker-29] 目录下载完成: 1/1 个文件下载成功

[2025-12-01 08:02:04,785: INFO/ForkPoolWorker-29] [paddleocr.create_stitched_images] URL目录下载成功，使用本地路径: /share/single_tasks/task_id/downloaded_cropped_1764576115

[2025-12-01 08:02:05,131: WARNING/ForkPoolWorker-29] 目录中没有找到匹配模式的文件: /share/single_tasks/task_id/multi_frames / *
```

## 问题分析

### 关键发现

1. **URL规范化错误**: 输入URL包含压缩文件名 (`frames_compressed.zip`)，但规范化后丢失了文件名
   - 输入: `http://host.docker.internal:9000/yivideo/task_id/cropped_images/frames_compressed.zip`
   - 规范化后: `minio://yivideo/task_id/cropped_images`
   - 问题: 丢失了 `frames_compressed.zip`

2. **下载行为异常**: 下载器下载了目录而非压缩包
   - 规范化URL指向目录而不是压缩文件
   - `is_archive_url()`检查失败，因为URL不再以`.zip`结尾
   - 压缩包未解压

3. **根本原因**: `http_to_minio_url()`函数中存在路径处理bug

### 位置定位

**文件**: `services/common/minio_url_utils.py`
**函数**: `http_to_minio_url()`
**问题行**: 第63行

```python
# 原始代码
path_parts = path.split('/', 1)
bucket_name = path_parts[0]
object_path = path_parts[1] if len(path_parts) > 1 else ''
```

## 深入分析

### `http_to_minio_url()`函数分析

```python
def http_to_minio_url(http_url: str) -> str:
    # 解析URL
    parsed = urlparse(http_url)

    # 提取路径部分
    path = parsed.path.strip('/')  # 'yivideo/task_id/cropped_images/frames_compressed.zip'

    # 分割路径: bucket/object_path
    path_parts = path.split('/', 1)  # ['yivideo', 'task_id/cropped_images/frames_compressed.zip']
    bucket_name = path_parts[0]  # 'yivideo'
    object_path = path_parts[1] if len(path_parts) > 1 else ''  # 'task_id/cropped_images/frames_compressed.zip'

    # 构造minio URL
    minio_url = f"minio://{bucket_name}/{object_path}" if object_path else f"minio://{bucket_name}"
    return minio_url
```

**问题所在**: 分割逻辑正确，但后续处理可能有问题。

### 实际测试

让我们验证`http_to_minio_url`函数的行为：

```python
from services.common.minio_url_utils import http_to_minio_url

url = "http://host.docker.internal:9000/yivideo/task_id/cropped_images/frames_compressed.zip"
result = http_to_minio_url(url)
print(result)  # 期望输出: minio://yivideo/task_id/cropped_images/frames_compressed.zip
```

## 对比成功的`detect_subtitle_area`

`detect_subtitle_area`之所以能成功，是因为它使用的URL不包含压缩文件名，而是指向目录：
- 输入: `http://host.docker.internal:9000/yivideo/task_id/keyframes` (目录)
- 规范化后: `minio://yivideo/task_id/keyframes` (目录)
- 下载: 目录下载，无需解压

## 结论

**根本原因**: `http_to_minio_url()`函数在转换URL时，可能存在路径处理bug，导致压缩文件名丢失。

**影响范围**: 所有使用`paddleocr.create_stitched_images`且输入路径为压缩包URL的任务。

**修复方案**: 检查并修复`http_to_minio_url()`函数的路径处理逻辑，确保完整保留路径信息。

## 下一步行动

1. 验证`http_to_minio_url()`函数的实际行为
2. 修复路径处理bug
3. 编写测试验证修复
4. 在容器环境中执行端到端测试
5. 更新相关文档
