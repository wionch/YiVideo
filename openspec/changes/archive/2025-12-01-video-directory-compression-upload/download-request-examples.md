# 请求样例分析：压缩包下载功能

## 概述
本文档分析了会下载压缩包的节点，并提供了详细的请求样例。

## 使用下载功能的节点

### 1. paddleocr.detect_subtitle_area

#### 功能描述
从MinIO URL下载关键帧目录，然后进行字幕区域检测。

#### 触发下载的条件
当满足以下条件时会触发下载：
1. `keyframe_dir` 是 MinIO URL 或 HTTP URL
2. `download_from_minio` 参数为 true（或者系统自动检测到URL）

#### 支持的URL格式
- `minio://bucket/path/to/keyframes`
- `http://host:port/bucket/path/to/keyframes`
- `https://host:port/bucket/path/to/keyframes`

#### 请求样例

##### 样例1：工作流模式（从上游获取MinIO URL）
```json
{
    "workflow_id": "wf-12345",
    "input_params": {
        "node_params": {
            "paddleocr.detect_subtitle_area": {
                "download_from_minio": true
            }
        }
    },
    "stages": {
        "ffmpeg.extract_keyframes": {
            "output": {
                "keyframe_minio_url": "minio://yivideo-keyframes/workflow-wf-12345/keyframes",
                "keyframe_local_path": "/share/workflows/wf-12345/keyframes"
            }
        }
    }
}
```

**说明**: 在这个模式下，`detect_subtitle_area` 会从上游 `ffmpeg.extract_keyframes` 的输出中获取 `keyframe_minio_url`，然后下载关键帧。

##### 样例2：参数模式（直接指定MinIO URL）
```json
{
    "workflow_id": "wf-67890",
    "input_params": {
        "node_params": {
            "paddleocr.detect_subtitle_area": {
                "keyframe_dir": "minio://yivideo-keyframes/workflow-wf-67890/keyframes",
                "download_from_minio": true,
                "local_keyframe_dir": "/share/workflows/wf-67890/downloaded_keyframes"
            }
        }
    }
}
```

**说明**: 直接通过 `keyframe_dir` 参数指定MinIO URL，并设置 `local_keyframe_dir` 指定本地下载目录。

##### 样例3：压缩包URL模式（启用压缩上传后的新场景）
```json
{
    "workflow_id": "wf-compressed-123",
    "input_params": {
        "node_params": {
            "paddleocr.detect_subtitle_area": {
                "keyframe_dir": "minio://yivideo-keyframes/workflow-wf-compressed-123/keyframes.zip",
                "download_from_minio": true,
                "auto_decompress": true
            }
        }
    },
    "stages": {
        "ffmpeg.extract_keyframes": {
            "output": {
                "compressed_keyframe_url": "minio://yivideo-keyframes/workflow-wf-compressed-123/keyframes.zip"
            }
        }
    }
}
```

**说明**: 当上游启用了压缩上传时，会生成压缩包URL，需要在下载时自动解压。

---

### 2. paddleocr.create_stitched_images

#### 功能描述
从MinIO URL下载裁剪后的图片目录，然后进行图片拼接。

#### 触发下载的条件
当 `cropped_images_path` 参数是 MinIO URL 时会触发下载。

#### 支持的URL格式
- `minio://bucket/path/to/cropped-images`
- `http://host:port/bucket/path/to/cropped-images`
- `https://host:port/bucket/path/to/cropped-images`

#### 请求样例

##### 样例1：工作流模式（从上游获取MinIO URL）
```json
{
    "workflow_id": "wf-12345",
    "input_params": {
        "node_params": {
            "paddleocr.create_stitched_images": {
                "upload_stitched_images_to_minio": true,
                "delete_local_stitched_images_after_upload": false
            }
        }
    },
    "stages": {
        "ffmpeg.crop_subtitle_images": {
            "output": {
                "cropped_images_minio_url": "minio://yivideo-cropped/workflow-wf-12345/cropped",
                "compressed_archive_url": "minio://yivideo-cropped/workflow-wf-12345/cropped.zip"
            }
        },
        "paddleocr.detect_subtitle_area": {
            "output": {
                "subtitle_area": {
                    "x": 100,
                    "y": 800,
                    "width": 1180,
                    "height": 200
                }
            }
        }
    }
}
```

**说明**: 从上游 `ffmpeg.crop_subtitle_images` 获取裁剪图片的MinIO URL（可以是压缩包），然后下载并处理。

##### 样例2：参数模式（直接指定MinIO URL）
```json
{
    "workflow_id": "wf-67890",
    "input_params": {
        "node_params": {
            "paddleocr.create_stitched_images": {
                "cropped_images_path": "minio://yivideo-cropped/workflow-wf-67890/cropped",
                "subtitle_area": {
                    "x": 100,
                    "y": 800,
                    "width": 1180,
                    "height": 200
                },
                "upload_stitched_images_to_minio": true
            }
        }
    }
}
```

**说明**: 直接指定裁剪图片的MinIO URL和字幕区域参数。

##### 样例3：压缩包URL模式（新场景）
```json
{
    "workflow_id": "wf-compressed-456",
    "input_params": {
        "node_params": {
            "paddleocr.create_stitched_images": {
                "cropped_images_path": "minio://yivideo-cropped/workflow-wf-compressed-456/cropped.zip",
                "subtitle_area": {
                    "x": 100,
                    "y": 800,
                    "width": 1180,
                    "height": 200
                },
                "auto_decompress": true,
                "upload_stitched_images_to_minio": true
            }
        }
    }
}
```

**说明**: 当上游启用了压缩上传时，裁剪图片可能是压缩包格式，需要在下载时自动解压。

---

## 压缩包下载新需求

### 需要新增的参数
为了支持压缩包下载解压，需要在下载函数中添加以下参数：

#### 对 paddleocr.detect_subtitle_area 的增强
```json
{
    "node_params": {
        "paddleocr.detect_subtitle_area": {
            "keyframe_dir": "minio://bucket/path/to/keyframes.zip",
            "download_from_minio": true,
            "auto_decompress": true,
            "decompress_dir": "/share/workflows/wf-123/downloaded",
            "delete_compressed_after_decompress": true
        }
    }
}
```

#### 对 paddleocr.create_stitched_images 的增强
```json
{
    "node_params": {
        "paddleocr.create_stitched_images": {
            "cropped_images_path": "minio://bucket/path/to/cropped.zip",
            "auto_decompress": true,
            "decompress_dir": "/share/workflows/wf-123/downloaded",
            "delete_compressed_after_decompress": true,
            "subtitle_area": {...}
        }
    }
}
```

### 增强参数说明

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `auto_decompress` | boolean | false | 是否自动解压下载的压缩包 |
| `decompress_dir` | string | 自动生成 | 解压目录路径 |
| `delete_compressed_after_decompress` | boolean | false | 解压后是否删除压缩包 |
| `compression_format` | string | "zip" | 压缩包格式（zip, tar.gz） |

---

## 下载实现流程

### 当前流程
1. 检测URL是否为MinIO URL
2. 规范化URL格式
3. 调用 `download_directory_from_minio` 下载目录
4. 验证下载结果
5. 使用本地路径继续处理

### 增强后的流程
1. 检测URL是否为MinIO URL
2. 检测URL是否为压缩包（.zip, .tar.gz等）
3. 如果是压缩包且 `auto_decompress=true`:
   a. 下载压缩包到临时目录
   b. 解压缩到指定目录
   c. 可选：删除压缩包
4. 使用解压后的目录路径继续处理

---

## 需要修改的文件

1. **`services/common/minio_directory_download.py`**
   - 添加压缩包检测逻辑
   - 添加自动解压参数
   - 实现解压功能

2. **`services/workers/paddleocr_service/app/tasks.py`**
   - 在 `detect_subtitle_area` 中添加 `auto_decompress` 参数支持
   - 在 `create_stitched_images` 中添加 `auto_decompress` 参数支持

---

## 测试策略

### 单元测试
1. 测试压缩包下载功能
2. 测试自动解压功能
3. 测试错误处理（压缩包损坏等）

### 集成测试
1. 测试完整工作流（压缩上传 → 下载解压 → 处理）
2. 测试向后兼容性（现有非压缩工作流不受影响）

### 性能测试
1. 测试大文件压缩包下载性能
2. 测试解压性能
3. 测试内存使用情况
