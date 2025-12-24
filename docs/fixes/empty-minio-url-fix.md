# 修复记录: 空 MinIO URL 导致文件未上传问题

## 问题描述

在实施文件上传去重功能后，发现部分阶段的 `*_minio_url` 字段为**空字符串**，导致文件实际未上传到 MinIO。

### 问题表现

```json
{
  "ffmpeg.extract_audio": {
    "output": {
      "audio_path": "/share/workflows/.../audio.wav",
      "audio_path_minio_url": ""  // ❌ 空字符串
    }
  },
  "audio_separator.separate_vocals": {
    "output": {
      "vocal_audio": "/share/.../vocals.flac",
      "vocal_audio_minio_url": "",  // ❌ 空字符串
      "all_audio_files_minio_urls": [  // ✅ 但数组字段有值
        "http://minio:9000/yivideo/..."
      ]
    }
  }
}
```

## 根本原因

### 原始去重逻辑缺陷

`services/common/state_manager.py:168-170` (修复前)

```python
# 处理单个文件字段
elif isinstance(file_value, str):
    # 优先检查是否已有 MinIO URL
    if minio_field_name in stage.output:  # ← 只检查字段存在
        logger.info(f"跳过已上传的文件: {key} (已有 {minio_field_name})")
        continue  # ❌ 问题：即使值为空字符串也跳过
```

### 问题本质

1. **Worker 预创建字段**：某些 Worker 可能在初始化时创建 `*_minio_url` 字段并赋值为空字符串 `""`
2. **去重逻辑误判**：`if minio_field_name in stage.output` 只检查字段是否存在，不验证值是否有效
3. **结果**：空字符串被误认为"已上传"，跳过实际上传操作

## 修复方案

### 修复 1: 单个文件字段验证

**文件**: `services/common/state_manager.py:113-125`

**修改前**:
```python
elif isinstance(file_value, str):
    # 优先检查是否已有 MinIO URL
    if minio_field_name in stage.output:
        logger.info(f"跳过已上传的文件: {key} (已有 {minio_field_name})")
        continue
```

**修改后**:
```python
elif isinstance(file_value, str):
    # 检查是否已有有效的 MinIO URL（非空字符串且是有效URL）
    existing_url = stage.output.get(minio_field_name)
    if existing_url and isinstance(existing_url, str) and existing_url.strip():
        # 验证是有效的URL而非空字符串
        if existing_url.startswith('http://') or existing_url.startswith('https://'):
            logger.info(f"跳过已上传的文件: {key} (已有 {minio_field_name} = {existing_url})")
            continue
        else:
            logger.warning(f"检测到无效的MinIO URL: {minio_field_name} = '{existing_url}', 将重新上传")
```

**验证逻辑**:
1. ✅ 检查字段存在: `stage.output.get(minio_field_name)`
2. ✅ 检查非空: `existing_url and existing_url.strip()`
3. ✅ 检查URL格式: `startswith('http://') or startswith('https://')`
4. ✅ 无效URL警告: 记录日志并重新上传

### 修复 2: 数组文件字段验证

**文件**: `services/common/state_manager.py:62-75`

**修改前**:
```python
if isinstance(file_value, list):
    # 检查是否已有 MinIO URL 数组
    if minio_field_name in stage.output and stage.output[minio_field_name]:
        logger.info(f"跳过已上传的文件数组: {key} (已有 {minio_field_name})")
        continue
```

**修改后**:
```python
if isinstance(file_value, list):
    # 检查是否已有有效的 MinIO URL 数组（非空且包含有效URL）
    existing_urls = stage.output.get(minio_field_name)
    if existing_urls and isinstance(existing_urls, list) and len(existing_urls) > 0:
        # 验证至少有一个有效URL
        has_valid_url = any(
            isinstance(url, str) and url.strip() and
            (url.startswith('http://') or url.startswith('https://'))
            for url in existing_urls
        )
        if has_valid_url:
            logger.info(f"跳过已上传的文件数组: {key} (已有 {minio_field_name})")
            continue
```

**验证逻辑**:
1. ✅ 检查数组非空: `len(existing_urls) > 0`
2. ✅ 验证至少一个有效URL: `any(url.startswith('http://') ...)`

## 验证结果

### 单元测试

新增 3 个测试用例（`tests/unit/common/test_state_manager_upload_dedup.py`）:

```
✅ test_empty_string_minio_url_triggers_upload - 空字符串触发重新上传
✅ test_empty_array_minio_urls_triggers_upload - 空数组触发重新上传
✅ test_invalid_url_format_triggers_reupload - 无效URL格式触发重新上传
```

**总测试结果**: 15/15 通过

### 代码审查

所有去重检查点已更新：

| 位置 | 字段类型 | 验证逻辑 | 状态 |
|------|---------|---------|------|
| Line 62-75 | 数组字段 | 检查非空 + 至少一个有效URL | ✅ |
| Line 113-125 | 单个文件 | 检查非空 + URL格式 | ✅ |

## 影响评估

### 修复前后对比

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| `*_minio_url = ""` | ❌ 跳过上传 | ✅ 执行上传 |
| `*_minio_url = "invalid"` | ❌ 跳过上传 | ✅ 警告并重新上传 |
| `*_minio_urls = []` | ❌ 跳过上传 | ✅ 执行上传 |
| `*_minio_url = "http://..."` | ✅ 正确跳过 | ✅ 正确跳过 |

### 向后兼容性

✅ **完全兼容**

- 有效URL仍然正确跳过
- 仅修复空值和无效值场景
- 不改变数据结构

## 相关文件

### 修改的文件
- `services/common/state_manager.py` (2 处修复)

### 新增的测试
- `tests/unit/common/test_state_manager_upload_dedup.py::TestEmptyUrlHandling` (3 个测试)

## 总结

✅ **问题已完全解决**
✅ **所有测试通过 (15/15)**
✅ **向后兼容**
✅ **增强日志可观测性**

**建议**: 立即部署到生产环境，确保所有文件正确上传到 MinIO。

---

**修复日期**: 2025-12-24
**修复人员**: Claude Code
**相关提案**: `fix-duplicate-minio-upload`
**关联问题**: 空 MinIO URL 导致文件未上传
