# PaddleOCR压缩包URL处理问题分析

## 问题描述

在执行 `paddleocr.create_stitched_images` 任务时，虽然压缩文件下载成功，但没有进行解压和图片拼接工作。从日志可以看出：

```
原始URL: http://host.docker.internal:9000/yivideo/task_id/cropped_images/frames_compressed.zip
规范化后: minio://yivideo/task_id/cropped_images
```

**关键问题：文件名 `frames_compressed.zip` 在URL规范化过程中丢失了！**

## 问题根因分析

### 1. URL规范化逻辑缺陷

在 `create_stitched_images` 任务中（第490-496行）：

```python
# 统一处理URL格式
try:
    minio_url = normalize_minio_url(input_dir_str)
    logger.info(f"[{stage_name}] 规范化URL为MinIO格式: {minio_url}")
except ValueError as e:
    # 如果规范化失败，保持原始URL
    minio_url = input_dir_str
    logger.info(f"[{stage_name}] 保持原始URL格式: {minio_url}")
```

问题在于 `normalize_minio_url` 函数在处理HTTP URL时没有正确保留完整的文件路径。

### 2. `http_to_minio_url` 函数分析

查看 `services/common/minio_url_utils.py` 第30-72行的 `http_to_minio_url` 函数：

```python
def http_to_minio_url(http_url: str) -> str:
    # 解析URL
    parsed = urlparse(http_url)
    
    # 提取路径部分
    path = parsed.path.strip('/')
    if not path:
        raise ValueError(f"HTTP URL中缺少路径部分: {http_url}")
    
    # 分割路径: bucket/object_path
    path_parts = path.split('/', 1)
    if len(path_parts) < 1:
        raise ValueError(f"无法从HTTP URL中提取bucket: {http_url}")
    
    bucket_name = path_parts[0]
    object_path = path_parts[1] if len(path_parts) > 1 else ''
    
    # 构造minio URL
    minio_url = f"minio://{bucket_name}/{object_path}" if object_path else f"minio://{bucket_name}"
    return minio_url
```

**这里有潜在问题！** 当 `object_path` 为空字符串时，会构造出 `minio://bucket_name` 格式的URL，丢失了路径信息。

### 3. 压缩包检测逻辑

`download_directory_from_minio` 函数（第344-349行）：

```python
# 检查是否为压缩包URL且启用自动解压
if auto_decompress and is_archive_url(minio_url):
    return downloader.download_and_extract_archive(
        minio_url=minio_url,
        local_dir=local_dir
    )
```

`is_archive_url` 函数（第25-36行）：

```python
def is_archive_url(url: str) -> bool:
    lower_url = url.lower()
    return lower_url.endswith(('.zip', '.tar.gz', '.tar'))
```

由于URL规范化后丢失了文件名，压缩包检测失败，因此没有调用解压逻辑。

## 对比分析

### `detect_subtitle_area` 为什么能正常工作？

`detect_subtitle_area` 使用的是 `download_keyframes_directory` 函数，该函数：

1. 专门用于下载关键帧（只关注.jpg文件）
2. 使用不同的文件模式过滤逻辑
3. 可能没有完全依赖压缩包检测机制

### 关键差异

| 功能 | `detect_subtitle_area` | `create_stitched_images` |
|------|------------------------|---------------------------|
| 下载函数 | `download_keyframes_directory` | `download_directory_from_minio` |
| 文件模式 | `*.jpg` (硬编码) | `*` (默认) |
| URL处理 | 使用相同的规范化逻辑 | 使用相同的规范化逻辑 |
| 压缩包支持 | 是 | 是（但检测失败） |

## 解决方案

### 方案1: 修复URL规范化逻辑
确保 `normalize_minio_url` 函数正确保留完整的文件路径。

### 方案2: 在调用下载函数前先检查压缩包
在调用 `download_directory_from_minio` 之前，先用原始URL检查是否为压缩包。

### 方案3: 改进下载函数的压缩包检测
让 `download_directory_from_minio` 函数同时检查原始URL和规范化后的URL。

## 推荐修复方案

**方案2 + 方案3结合**：

1. 在 `create_stitched_images` 中，先用原始URL检查是否为压缩包
2. 如果是压缩包，传递原始URL给下载函数
3. 改进下载函数的压缩包检测逻辑，同时支持原始URL和规范化URL的检测

## 预期结果

修复后，以下流程应该能够正常工作：

1. 原始URL: `http://host.docker.internal:9000/yivideo/task_id/cropped_images/frames_compressed.zip`
2. 检测为压缩包: ✅
3. 下载并解压压缩包: ✅
4. 执行图片拼接: ✅
5. 上传拼接结果: ✅

## 测试验证

需要创建测试用例验证：
1. 压缩包URL的正确识别
2. URL规范化过程中文件名的保留
3. 完整的压缩→下载→解压→处理流程