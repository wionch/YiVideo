# Capability: MinIO URL 命名约定 (MinIO URL Naming Convention)

## ADDED Requirements

### Requirement: 所有 MinIO URL 字段必须遵循统一命名约定

**优先级**: P0
**理由**: 消除字段命名不一致问题，便于客户端解析

#### Scenario: 生成标准 MinIO URL 字段名

**Given** 节点输出包含本地路径字段 `audio_path`
**When** 应用 MinIO URL 命名约定
**Then** 生成的 MinIO URL 字段名必须为 `audio_path_minio_url`
**And** 字段名必须保留完整的本地字段名作为前缀

**示例**:
| 本地字段名 | MinIO URL 字段名 | 说明 |
|-----------|-----------------|------|
| `audio_path` | `audio_path_minio_url` | ✅ 标准格式 |
| `keyframe_dir` | `keyframe_dir_minio_url` | ✅ 保留 `_dir` 后缀 |
| `multi_frames_path` | `multi_frames_path_minio_url` | ✅ 保留 `_path` 后缀 |
| `segments_file` | `segments_file_minio_url` | ✅ 保留 `_file` 后缀 |

**反例**（不符合规范）:
| 本地字段名 | 错误的 MinIO URL 字段名 | 问题 |
|-----------|----------------------|------|
| `keyframe_dir` | `keyframe_minio_url` | ❌ 丢失了 `_dir` 后缀 |
| `multi_frames_path` | `multi_frames_minio_url` | ❌ 丢失了 `_path` 后缀 |

#### Scenario: 处理数组类型的路径字段

**Given** 节点输出包含数组类型的路径字段 `all_audio_files`
**When** 应用 MinIO URL 命名约定
**Then** 生成的 MinIO URL 字段名必须为 `all_audio_files_minio_urls`（复数形式）
**And** 字段值必须为 URL 数组

**示例**:
```python
# 输入
{
    "all_audio_files": [
        "/share/workflows/task-001/audio1.wav",
        "/share/workflows/task-001/audio2.wav"
    ]
}

# 输出
{
    "all_audio_files": [
        "/share/workflows/task-001/audio1.wav",
        "/share/workflows/task-001/audio2.wav"
    ],
    "all_audio_files_minio_urls": [
        "http://localhost:9000/yivideo/task-001/audio1.wav",
        "http://localhost:9000/yivideo/task-001/audio2.wav"
    ]
}
```

---

### Requirement: 自动识别需要生成 MinIO URL 的字段

**优先级**: P0
**理由**: 避免手动指定每个字段，减少遗漏

#### Scenario: 根据字段后缀自动识别路径字段

**Given** 节点输出包含以下字段:
```python
{
    "audio_path": "/share/audio.wav",
    "segments_file": "/share/segments.json",
    "keyframe_dir": "/share/keyframes",
    "model_name": "base",  # 非路径字段
    "duration": 10.5       # 非路径字段
}
```
**When** 应用 MinIO URL 命名约定
**Then** 仅为以下字段生成 MinIO URL:
- `audio_path` → `audio_path_minio_url`
- `segments_file` → `segments_file_minio_url`
- `keyframe_dir` → `keyframe_dir_minio_url`

**And** 非路径字段（`model_name`, `duration`）不生成 MinIO URL

**识别规则**:
字段名以以下后缀结尾时被视为路径字段:
- `_path`
- `_file`
- `_dir`
- `_audio`
- `_video`
- `_image`

#### Scenario: 支持自定义路径字段列表

**Given** 某个节点有特殊的路径字段名（如 `vocal_audio`）
**And** 该字段名不符合标准后缀规则
**When** 节点在 `CUSTOM_PATH_FIELDS` 列表中声明该字段
**Then** 该字段也必须生成 MinIO URL

**示例**:
```python
class AudioSeparatorExecutor(BaseNodeExecutor):
    CUSTOM_PATH_FIELDS = ["vocal_audio", "instrumental_audio"]

    def execute_core_logic(self) -> Dict[str, Any]:
        return {
            "vocal_audio": "/share/vocal.wav",
            "instrumental_audio": "/share/instrumental.wav"
        }
```

**输出**:
```python
{
    "vocal_audio": "/share/vocal.wav",
    "vocal_audio_minio_url": "http://...",
    "instrumental_audio": "/share/instrumental.wav",
    "instrumental_audio_minio_url": "http://..."
}
```

---

### Requirement: 仅在全局上传开关启用时生成 MinIO URL

**优先级**: P0
**理由**: 避免不必要的上传和 URL 生成

#### Scenario: 全局上传开关关闭时不生成 MinIO URL

**Given** 全局配置 `core.auto_upload_to_minio = false`
**And** 节点输出包含本地路径字段
**When** 应用 MinIO URL 命名约定
**Then** 不生成任何 MinIO URL 字段
**And** 仅返回本地路径字段

#### Scenario: 全局上传开关启用时生成 MinIO URL

**Given** 全局配置 `core.auto_upload_to_minio = true`
**And** 节点输出包含本地路径字段
**When** 应用 MinIO URL 命名约定
**Then** 为所有路径字段生成对应的 MinIO URL 字段
**And** 本地路径字段保持不变

---

### Requirement: 原始本地路径字段不得被覆盖或删除

**优先级**: P0
**理由**: 保持向后兼容性，某些客户端可能依赖本地路径

#### Scenario: MinIO URL 字段作为增强字段添加

**Given** 节点输出包含 `audio_path = "/share/audio.wav"`
**When** 应用 MinIO URL 命名约定
**Then** 输出必须同时包含:
- `audio_path`: "/share/audio.wav"（原始字段）
- `audio_path_minio_url`: "http://..."（新增字段）

**And** `audio_path` 的值不得被修改为 MinIO URL

---

## MODIFIED Requirements

### Requirement: 现有节点的 MinIO URL 字段必须重命名

**优先级**: P0
**理由**: 消除现有的命名不一致问题

#### Scenario: 修复 ffmpeg.extract_keyframes 的字段命名

**Given** 现有节点输出:
```python
{
    "keyframe_dir": "/share/keyframes",
    "keyframe_minio_url": "http://..."  # ❌ 错误：丢失了 _dir
}
```
**When** 迁移到新命名约定
**Then** 输出必须修改为:
```python
{
    "keyframe_dir": "/share/keyframes",
    "keyframe_dir_minio_url": "http://..."  # ✅ 正确：保留 _dir
}
```

#### Scenario: 修复 paddleocr.create_stitched_images 的字段命名

**Given** 现有节点输出:
```python
{
    "multi_frames_path": "/share/multi_frames",
    "multi_frames_minio_url": "http://..."  # ❌ 错误：丢失了 _path
}
```
**When** 迁移到新命名约定
**Then** 输出必须修改为:
```python
{
    "multi_frames_path": "/share/multi_frames",
    "multi_frames_path_minio_url": "http://..."  # ✅ 正确：保留 _path
}
```

#### Scenario: 修复 audio_separator.separate_vocals 的数组字段命名

**Given** 现有节点输出:
```python
{
    "all_audio_files": ["/share/vocal.wav", "/share/instrumental.wav"],
    "all_audio_minio_urls": ["http://...", "http://..."]  # ❌ 错误：不完整
}
```
**When** 迁移到新命名约定
**Then** 输出必须修改为:
```python
{
    "all_audio_files": ["/share/vocal.wav", "/share/instrumental.wav"],
    "all_audio_files_minio_urls": ["http://...", "http://..."]  # ✅ 正确：完整字段名
}
```

---

## REMOVED Requirements

无（这是新增能力）

---

## 依赖关系

- **依赖**: `services/common/state_manager.py` 中的 MinIO 上传逻辑
- **被依赖**: `BaseNodeExecutor.format_output()` 方法
- **被依赖**: `NodeResponseValidator` 验证器

---

## 测试要求

### 单元测试

1. **测试标准字段命名**:
   ```python
   def test_standard_field_naming():
       assert get_minio_url_field_name("audio_path") == "audio_path_minio_url"
       assert get_minio_url_field_name("keyframe_dir") == "keyframe_dir_minio_url"
       assert get_minio_url_field_name("segments_file") == "segments_file_minio_url"
   ```

2. **测试数组字段命名**:
   ```python
   def test_array_field_naming():
       assert get_minio_url_field_name("all_audio_files") == "all_audio_files_minio_urls"
   ```

3. **测试路径字段识别**:
   ```python
   def test_path_field_detection():
       assert is_path_field("audio_path") == True
       assert is_path_field("model_name") == False
       assert is_path_field("duration") == False
   ```

4. **测试全局开关控制**:
   ```python
   def test_global_upload_switch():
       # auto_upload_to_minio = False
       output = apply_minio_url_convention({"audio_path": "/share/audio.wav"}, context)
       assert "audio_path_minio_url" not in output

       # auto_upload_to_minio = True
       context.input_params["core"] = {"auto_upload_to_minio": True}
       output = apply_minio_url_convention({"audio_path": "/share/audio.wav"}, context)
       assert "audio_path_minio_url" in output
   ```

5. **测试原始字段保留**:
   ```python
   def test_original_field_preservation():
       output = apply_minio_url_convention({"audio_path": "/share/audio.wav"}, context)
       assert output["audio_path"] == "/share/audio.wav"  # 原始值不变
       assert "audio_path_minio_url" in output
   ```

### 集成测试

1. **测试真实 MinIO 上传**:
   - 验证生成的 MinIO URL 可访问
   - 验证 URL 指向正确的文件

2. **测试所有节点的字段命名**:
   - 遍历所有 18 个节点
   - 验证所有 MinIO URL 字段符合命名约定

---

## 性能要求

- 字段命名生成的时间复杂度必须为 O(n)，其中 n 为输出字段数量
- 不得使用正则表达式进行字段识别（性能考虑）

---

## 向后兼容性

### 迁移策略

**阶段 1（第 1-4 周）**:
- 新字段与旧字段并存
- 同时返回 `keyframe_minio_url` 和 `keyframe_dir_minio_url`
- 在响应中添加废弃警告

**阶段 2（第 5-8 周）**:
- 文档更新，标记旧字段为废弃
- 客户端迁移指南发布

**阶段 3（6 个月后）**:
- 移除旧字段
- 仅返回符合新约定的字段

### 废弃警告示例

```python
{
    "keyframe_dir": "/share/keyframes",
    "keyframe_minio_url": "http://...",  # 废弃，将在 v2.0 移除
    "keyframe_dir_minio_url": "http://...",  # 推荐使用
    "_warnings": [
        "Field 'keyframe_minio_url' is deprecated. Use 'keyframe_dir_minio_url' instead."
    ]
}
```
