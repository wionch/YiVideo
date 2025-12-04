# 修复残留 /tmp 使用 - 简化技术设计

## 背景和约束

### 当前问题

在 `refactor-directory-usage` 提案完成后，容器日志显示压缩上传功能仍在使用 `/tmp` 目录：

```
[2025-12-04 08:43:28,748: INFO/ForkPoolWorker-31] 开始压缩目录: /share/workflows/task_id/cropped_images/frames -> /tmp/frames_compressed_1764837808_c0febec5.zip
```

### 设计约束

-   最小化变更，直接替换问题代码
-   遵循 KISS 原则，保持简单
-   不引入新的依赖或复杂的抽象
-   确保现有功能不受影响

## 简化方案

### 原则

-   **KISS**: 直接替换，不创建复杂的工具类
-   **DRY**: 提取公共的路径生成函数
-   **YAGNI**: 只解决当前问题，不为未来可能的需求设计

### 实现策略

#### 1. 创建简单的路径生成函数

在 `services/common/` 目录创建一个简单的工具函数：

```python
# services/common/temp_path_utils.py
import os
import time
import uuid

def get_temp_path(workflow_id: str, suffix: str = "") -> str:
    """生成基于工作流ID的临时文件路径"""
    temp_dir = f"/share/workflows/{workflow_id}/tmp"
    os.makedirs(temp_dir, exist_ok=True)

    timestamp = int(time.time() * 1000)
    unique_id = str(uuid.uuid4())[:8]
    filename = f"temp_{timestamp}_{unique_id}{suffix}"

    return os.path.join(temp_dir, filename)
```

#### 2. 直接替换每个文件中的临时文件使用

**services/common/minio_directory_upload.py**

```python
# 第137行替换前:
temp_archive_path = os.path.join(
    tempfile.gettempdir(),
    f"{source_name}_compressed_{timestamp}_{unique_id}"
)

# 替换后:
temp_archive_path = get_temp_path(
    workflow_id,
    f".zip" if compression_format == CompressionFormat.ZIP else ".tar.gz"
)
```

**services/common/minio_directory_download.py**

```python
# 第90行替换前:
with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
    temp_archive_path = tmp_file.name

# 替换后:
temp_archive_path = get_temp_path(workflow_id, suffix)
```

**services/workers/paddleocr_service/app/tasks.py**

```python
# 第305行替换前:
with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.json') as tmp_file:
    json.dump(keyframe_paths, tmp_file)
    paths_file_path = tmp_file.name

# 替换后:
paths_file_path = get_temp_path(workflow_context.workflow_id, '.json')
with open(paths_file_path, 'w', encoding='utf-8') as f:
    json.dump(keyframe_paths, f)
```

**services/workers/audio_separator_service/app/model_manager.py**

```python
# 第59行替换前:
with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json', encoding='utf-8') as tmp:
    output_file = tmp.name

# 替换后:
output_file = get_temp_path(getattr(self, 'workflow_id', ''), '.json')
```

**services/api_gateway/app/minio_service.py**

```python
# 第66行和第183行替换前:
temp_file = tempfile.NamedTemporaryFile(delete=False)
temp_file.write(file_data)
temp_file.close()

# 替换后:
temp_file_path = get_temp_path(workflow_id or "")
with open(temp_file_path, 'wb') as f:
    f.write(file_data)
```

#### 3. 统一清理策略

在每个服务的 finally 块中添加清理逻辑：

```python
finally:
    # 清理临时文件
    if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
        try:
            os.remove(temp_file_path)
        except Exception:
            pass  # 忽略清理错误
```

## 风险和权衡

### 主要风险

1. **路径错误**: 确保 workflow_id 正确传递
2. **权限问题**: 验证目录创建权限
3. **清理遗漏**: 确保所有临时文件被清理

### 缓解措施

-   添加必要的错误处理
-   验证目录创建成功
-   在开发和测试环境中充分验证

## 测试策略

### 简单验证

1. **代码审查**: 确保所有 `/tmp` 使用被替换
2. **静态检查**: 使用搜索工具确认无残留
3. **功能测试**: 验证核心功能正常工作
4. **日志检查**: 确认容器日志中无 `/tmp` 路径

### 验证标准

-   容器日志中不再出现 `/tmp` 路径
-   所有服务工作流正常运行
-   临时文件正确清理

## 实施计划

### 阶段 1: 创建工具函数 (5 分钟)

-   创建简单的 `get_temp_path()` 函数
-   添加必要的导入

### 阶段 2: 逐个文件替换 (30 分钟)

-   按优先级逐个替换每个文件中的临时文件使用
-   添加必要的错误处理

### 阶段 3: 验证 (15 分钟)

-   运行搜索确认无残留 `/tmp` 使用
-   进行基本功能测试
-   检查容器日志

## 开放问题

1. 是否需要在所有服务完成后统一清理旧目录？
2. 是否需要添加监控来跟踪临时文件使用情况？

## 预期效果

-   ✅ 最小的代码变更
-   ✅ 消除所有 `/tmp` 使用
-   ✅ 提高安全性
-   ✅ 易于理解和维护
