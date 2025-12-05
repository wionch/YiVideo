# 文件操作 API 文档

文件操作API提供对MinIO对象存储和本地文件系统的管理功能，支持文件上传、下载、删除和目录管理。

## 📋 目录

- [概述](#概述)
- [存储系统](#存储系统)
- [端点列表](#端点列表)
- [上传文件](#上传文件)
- [下载文件](#下载文件)
- [删除文件](#删除文件)
- [删除目录](#删除目录)
- [安全说明](#安全说明)
- [示例和最佳实践](#示例和最佳实践)

---

## 概述

### 文件操作类型

**MinIO存储**：
- 对象存储服务
- 适合大文件存储
- 支持文件下载链接
- 分布式存储

**本地文件系统**：
- 临时工作目录
- 任务执行中间结果
- 工作流共享存储
- `/share` 目录

### 核心特性
- **流式上传**: 支持大文件高效上传
- **路径安全**: 防止路径遍历攻击
- **幂等操作**: 删除操作支持幂等性
- **文件类型**: 自动识别MIME类型

---

## 存储系统

### MinIO 配置

**默认存储桶**: `yivideo`
**访问地址**: `http://localhost:9000`
**访问方式**: 通过API Gateway代理

**存储特点**：
- 高可用性
- 版本控制
- 数据冗余
- 生命周期管理

### 本地文件系统

**共享目录**: `/share`
**工作流目录**: `/share/workflows/{workflow_id}`
**临时文件**: `/share/tmp`

**目录结构**：
```
/share/
├── workflows/
│   ├── workflow_id_1/
│   │   ├── stage_0/
│   │   ├── stage_1/
│   │   └── output/
│   └── workflow_id_2/
│       └── ...
└── tmp/
```

---

## 端点列表

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/v1/files/upload` | 上传文件到MinIO |
| GET | `/v1/files/download/{file_path}` | 从MinIO下载文件 |
| DELETE | `/v1/files/{file_path}` | 删除MinIO中的文件 |
| DELETE | `/v1/files/directories` | 删除本地目录 |

---

## 上传文件

### POST /v1/files/upload

将文件上传到MinIO存储桶（流式上传优化版本）。

#### 端点信息
- **方法**: `POST`
- **路径**: `/v1/files/upload`
- **认证**: 当前无需认证
- **内容类型**: `multipart/form-data`
- **速率限制**: 20次/分钟

#### 请求参数

| 名称 | 类型 | 必需 | 描述 |
|------|------|------|------|
| file | file | 是 | 要上传的文件 |
| file_path | string | 是 | 文件在MinIO中的路径 |
| bucket | string | 否 | 文件桶名称（默认：yivideo） |

#### 请求示例

**使用cURL上传**：
```bash
curl -X POST "http://localhost:8000/v1/files/upload" \
  -F "file=@/path/to/video.mp4" \
  -F "file_path=videos/lecture.mp4" \
  -F "bucket=yivideo"
```

**使用Python requests**：
```python
import requests

with open('/path/to/video.mp4', 'rb') as f:
    files = {'file': f}
    data = {
        'file_path': 'videos/lecture.mp4',
        'bucket': 'yivideo'
    }
    response = requests.post(
        'http://localhost:8000/v1/files/upload',
        files=files,
        data=data
    )
    print(response.json())
```

**上传JSON文件**：
```bash
curl -X POST "http://localhost:8000/v1/files/upload" \
  -F "file=@config.json" \
  -F "file_path=configs/project.json" \
  -F "bucket=yivideo"
```

#### 响应模型

**成功响应**：
```json
{
    "file_path": "videos/lecture.mp4",
    "bucket": "yivideo",
    "download_url": "http://localhost:9000/yivideo/videos/lecture.mp4",
    "size": 104857600,
    "uploaded_at": "2025-12-05T02:56:00Z",
    "content_type": "video/mp4"
}
```

#### 响应字段说明

- `file_path` (string): 文件路径
- `bucket` (string): 存储桶名称
- `download_url` (string): 文件下载链接
- `size` (int): 文件大小（字节）
- `uploaded_at` (string): 上传时间
- `content_type` (string): 文件MIME类型

#### 错误响应

**400 Bad Request - 缺少参数**：
```json
{
    "detail": "file_path不能为空"
}
```

**400 Bad Request - 文件路径不安全**：
```json
{
    "detail": "无效的文件路径"
}
```

**400 Bad Request - 文件大小为0**：
```json
{
    "detail": "文件大小为0"
}
```

**500 Internal Server Error - 上传失败**：
```json
{
    "detail": "文件上传失败: [错误详情]"
}
```

---

## 下载文件

### GET /v1/files/download/{file_path}

从MinIO下载文件。

#### 端点信息
- **方法**: `GET`
- **路径**: `/v1/files/download/{file_path}`
- **认证**: 当前无需认证
- **速率限制**: 100次/分钟

#### 路径参数

| 名称 | 类型 | 必需 | 描述 |
|------|------|------|------|
| file_path | string | 是 | 文件在MinIO中的路径 |

#### 查询参数

| 名称 | 类型 | 必需 | 描述 |
|------|------|------|------|
| bucket | string | 否 | 文件桶名称（默认：yivideo） |

#### 请求示例

```bash
curl -X GET "http://localhost:8000/v1/files/download/videos/lecture.mp4?bucket=yivideo" \
  -o "output.mp4"
```

#### 响应模型

**成功响应**：
- **内容类型**: 根据文件类型自动识别
- **Content-Disposition**: 附件下载
- **文件数据**: 二进制文件内容

**响应头**：
```http
Content-Type: video/mp4
Content-Disposition: attachment; filename="lecture.mp4"
Content-Length: 104857600
```

#### 错误响应

**400 Bad Request - 无效路径**：
```json
{
    "detail": "无效的文件路径"
}
```

**500 Internal Server Error - 下载失败**：
```json
{
    "detail": "文件下载失败: [错误详情]"
}
```

---

## 删除文件

### DELETE /v1/files/{file_path}

删除MinIO中的文件。

#### 端点信息
- **方法**: `DELETE`
- **路径**: `/v1/files/{file_path:path}`
- **认证**: 当前无需认证
- **速率限制**: 50次/分钟

#### 路径参数

| 名称 | 类型 | 必需 | 描述 |
|------|------|------|------|
| file_path | string | 是 | 文件在MinIO中的路径 |

#### 查询参数

| 名称 | 类型 | 必需 | 描述 |
|------|------|------|------|
| bucket | string | 否 | 文件桶名称（默认：yivideo） |

#### 请求示例

```bash
curl -X DELETE "http://localhost:8000/v1/files/videos/lecture.mp4?bucket=yivideo"
```

#### 响应模型

**成功响应**：
```json
{
    "success": true,
    "message": "文件删除成功: videos/lecture.mp4",
    "file_path": "videos/lecture.mp4"
}
```

**删除不存在的文件（幂等）**：
```json
{
    "success": true,
    "message": "文件删除成功: videos/nonexistent.mp4",
    "file_path": "videos/nonexistent.mp4"
}
```

**删除失败**：
```json
{
    "success": false,
    "message": "文件删除失败: videos/lecture.mp4",
    "file_path": "videos/lecture.mp4"
}
```

---

## 删除目录

### DELETE /v1/files/directories

删除本地文件系统中的目录及其所有内容。

> **详细文档**: 此端点的完整文档请参考 [DELETE_directories.md](DELETE_directories.md)

#### 端点信息
- **方法**: `DELETE`
- **路径**: `/v1/files/directories`
- **认证**: 当前无需认证
- **速率限制**: 20次/分钟

#### 查询参数

| 名称 | 类型 | 必需 | 描述 |
|------|------|------|------|
| directory_path | string | 是 | 要删除的本地目录路径 |

#### 请求示例

```bash
curl -X DELETE "http://localhost:8000/v1/files/directories?directory_path=/share/workflows/workflow_123"
```

#### 响应示例

```json
{
    "success": true,
    "message": "目录删除成功: /share/workflows/workflow_123",
    "file_path": "/share/workflows/workflow_123"
}
```

#### 安全特性

1. **路径验证**: 防止路径遍历攻击（禁止 `..`）
2. **权限检查**: 验证文件系统权限
3. **目录限制**: 只能删除 `/share/` 目录下的路径
4. **幂等操作**: 删除不存在的目录返回成功

---

## 安全说明

### 路径安全

**允许的路径格式**：
```
✅ videos/input.mp4
✅ configs/project.json
✅ workflow_123/output.txt
```

**禁止的路径格式**：
```
❌ ../secret.txt
❌ /etc/passwd
❌ ~/private/file.txt
```

### 访问控制

**MinIO存储**：
- 默认访问控制策略
- 可配置存储桶权限
- 支持预签名URL

**本地文件系统**：
- 限制在 `/share/` 目录
- 自动权限检查
- 防止越权访问

### 最佳安全实践

1. **验证路径**: 始终检查文件路径安全性
2. **权限最小化**: 只授予必要的权限
3. **敏感文件**: 不要在公共存储中存放敏感文件
4. **访问日志**: 监控文件访问日志

---

## 示例和最佳实践

### 示例1：文件上传下载完整流程

```bash
# 1. 上传文件
response=$(curl -s -X POST "http://localhost:8000/v1/files/upload" \
  -F "file=@/path/to/video.mp4" \
  -F "file_path=videos/lecture.mp4")

file_path=$(echo "$response" | jq -r '.file_path')
download_url=$(echo "$response" | jq -r '.download_url')

echo "文件已上传: $file_path"
echo "下载链接: $download_url"

# 2. 下载文件
curl -X GET "http://localhost:8000/v1/files/download/videos/lecture.mp4" \
  -o "downloaded_video.mp4"

echo "文件已下载"

# 3. 删除文件
curl -X DELETE "http://localhost:8000/v1/files/videos/lecture.mp4"
echo "文件已删除"
```

### 示例2：批量上传

```bash
#!/bin/bash

files=(
    "video1.mp4:videos/video1.mp4"
    "video2.mp4:videos/video2.mp4"
    "config.json:configs/config.json"
)

for item in "${files[@]}"; do
    IFS=':' read -r local_file remote_path <<< "$item"
    echo "上传文件: $local_file -> $remote_path"

    curl -X POST "http://localhost:8000/v1/files/upload" \
      -F "file=@$local_file" \
      -F "file_path=$remote_path" \
      -F "bucket=yivideo"
done

echo "批量上传完成"
```

### 示例3：工作流文件管理

```bash
# 工作流开始，创建目录结构
workflow_id="workflow-123"
mkdir -p "/share/workflows/$workflow_id/stage_0"
mkdir -p "/share/workflows/$workflow_id/stage_1"

# 上传输入文件
curl -X POST "http://localhost:8000/v1/files/upload" \
  -F "file=@input.mp4" \
  -F "file_path=workflows/$workflow_id/input.mp4"

# ... 执行工作流任务 ...

# 清理工作流目录
curl -X DELETE "http://localhost:8000/v1/files/directories?directory_path=/share/workflows/$workflow_id"

echo "工作流文件清理完成"
```

### 示例4：Python客户端

```python
import requests
import os

class YiVideoFileClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url

    def upload_file(self, local_path, remote_path, bucket="yivideo"):
        """上传文件到MinIO"""
        with open(local_path, 'rb') as f:
            files = {'file': f}
            data = {
                'file_path': remote_path,
                'bucket': bucket
            }
            response = requests.post(
                f"{self.base_url}/v1/files/upload",
                files=files,
                data=data
            )
            return response.json()

    def download_file(self, remote_path, local_path, bucket="yivideo"):
        """下载文件从MinIO"""
        response = requests.get(
            f"{self.base_url}/v1/files/download/{remote_path}",
            params={'bucket': bucket}
        )

        if response.status_code == 200:
            with open(local_path, 'wb') as f:
                f.write(response.content)
            return True
        return False

    def delete_file(self, remote_path, bucket="yivideo"):
        """删除MinIO文件"""
        response = requests.delete(
            f"{self.base_url}/v1/files/{remote_path}",
            params={'bucket': bucket}
        )
        return response.json()

    def delete_directory(self, directory_path):
        """删除本地目录"""
        response = requests.delete(
            f"{self.base_url}/v1/files/directories",
            params={'directory_path': directory_path}
        )
        return response.json()

# 使用示例
client = YiVideoFileClient()

# 上传文件
result = client.upload_file("local.mp4", "videos/remote.mp4")
print(f"上传结果: {result}")

# 下载文件
success = client.download_file("videos/remote.mp4", "downloaded.mp4")
print(f"下载{'成功' if success else '失败'}")

# 删除文件
result = client.delete_file("videos/remote.mp4")
print(f"删除结果: {result}")
```

### 最佳实践

#### 1. 文件组织
- **命名规范**: 使用清晰的路径和文件名
- **分类存储**: 按类型和项目组织文件结构
- **版本控制**: 为重要文件添加版本号

#### 2. 性能优化
- **流式上传**: 使用流式上传处理大文件
- **并发限制**: 控制并发上传数量
- **文件压缩**: 大文件考虑压缩后再上传

#### 3. 错误处理
- **网络错误**: 实现重试机制
- **文件不存在**: 妥善处理404错误
- **权限错误**: 检查存储桶权限

#### 4. 资源管理
- **及时清理**: 删除不再需要的文件
- **定期归档**: 将历史文件归档到冷存储
- **监控存储**: 定期检查存储使用情况

#### 5. 调试技巧
- **使用test端点**: 测试连接和权限
- **查看响应头**: 检查Content-Type等元数据
- **分步测试**: 先测试小文件，再处理大文件

---

## 性能说明

### 上传性能
- **小文件** (< 10MB): < 1秒
- **中等文件** (10-100MB): 1-10秒
- **大文件** (> 100MB): 取决于网络带宽
- **并发上传**: 建议不超过5个并发

### 下载性能
- **下载速度**: 取决于MinIO服务器性能
- **支持断点续传**: 是
- **缓存策略**: MinIO自动缓存

### 删除性能
- **文件删除**: < 100ms
- **目录删除**: 取决于目录大小和文件数量
- **批量删除**: 建议分批删除大量文件

---

## 文件大小限制

| 操作 | 最大文件大小 | 建议大小 |
|------|--------------|----------|
| 上传 | 5GB | < 500MB |
| 下载 | 无限制 | - |
| 临时存储 | 取决于磁盘空间 | < 10GB |

---

## 相关文档

- [工作流API](WORKFLOW_API.md)
- [单任务API](SINGLE_TASK_API.md)
- [监控API](MONITORING_API.md)
- [MinIO目录上传指南](../technical/reference/MINIO_DIRECTORY_UPLOAD_GUIDE.md)
- [DELETE_directories.md](DELETE_directories.md)

## 更新日志

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2025-12-05 | 初始文件操作API文档 |

---

*最后更新: 2025-12-05 | 文档版本: 1.0.0*
