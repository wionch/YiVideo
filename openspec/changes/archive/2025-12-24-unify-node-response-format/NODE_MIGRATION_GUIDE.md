# 节点迁移指南

**版本**: 1.0
**日期**: 2025-12-23
**适用范围**: 所有需要迁移到统一响应格式的工作流节点

---

## 📋 迁移概述

### 目标

将现有节点从旧的响应格式迁移到基于 `BaseNodeExecutor` 的统一响应格式。

### 迁移收益

1. **统一的响应格式**: 所有节点遵循 WorkflowContext 结构
2. **自动化 MinIO URL 生成**: 无需手动处理 MinIO URL 字段
3. **透明的缓存逻辑**: 显式声明缓存键字段
4. **自动化验证**: 开发时即可发现格式问题
5. **更好的错误处理**: 统一的异常捕获和记录

---

## 🔄 迁移步骤

### 步骤 1: 分析现有节点

**检查清单**:
- [ ] 找到节点的 Celery 任务定义
- [ ] 理解节点的输入参数
- [ ] 理解节点的输出字段
- [ ] 识别路径字段(需要 MinIO URL)
- [ ] 识别缓存依赖字段

**示例**:
```python
# 现有节点: services/workers/ffmpeg_service/app/tasks.py
@celery_app.task(name="ffmpeg.extract_audio")
def extract_audio_task(task_id: str, video_path: str):
    # 输入: video_path
    # 输出: audio_path
    # 路径字段: audio_path
    # 缓存依赖: video_path
    ...
```

---

### 步骤 2: 创建节点执行器类

**模板**:
```python
from typing import Dict, Any, List
from services.common.base_node_executor import BaseNodeExecutor


class YourNodeExecutor(BaseNodeExecutor):
    """
    [节点名称] 执行器。

    功能：[简要描述]

    输入参数：
        - param1: 参数1说明
        - param2: 参数2说明

    输出字段：
        - output1: 输出1说明
        - output1_minio_url: MinIO URL（如果上传启用）
    """

    def validate_input(self) -> None:
        """验证输入参数"""
        input_data = self.get_input_data()

        # 检查必需参数
        if "param1" not in input_data:
            raise ValueError("Missing required parameter: param1")

        # 检查参数有效性
        if not input_data["param1"]:
            raise ValueError("Parameter 'param1' cannot be empty")

    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行核心业务逻辑。

        Note:
            这里调用实际的处理函数。
        """
        input_data = self.get_input_data()

        # 调用实际处理函数
        result = your_processing_function(
            param1=input_data["param1"],
            param2=input_data.get("param2", "default_value")
        )

        # 返回原始输出（不包含 MinIO URL）
        return {
            "output1": result["path"],
            "output2": result["metadata"]
        }

    def get_cache_key_fields(self) -> List[str]:
        """
        返回缓存键字段。

        规则：
        - 包含所有影响输出的输入参数
        - 不包含不影响结果的参数（如 task_id）
        """
        return ["param1", "param2"]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段（用于缓存验证）。

        规则：
        - 包含所有核心输出字段
        - 如果字段缺失，缓存无效
        """
        return ["output1"]

    def get_custom_path_fields(self) -> List[str]:
        """
        返回自定义路径字段（可选）。

        规则：
        - 只有不符合标准后缀的路径字段才需要声明
        - 标准后缀: _path, _file, _dir, _audio, _video, _image
        """
        return []  # 如果没有自定义路径字段，返回空列表
```

---

### 步骤 3: 更新 Celery 任务

**迁移前**:
```python
@celery_app.task(name="ffmpeg.extract_audio")
def extract_audio_task(task_id: str, video_path: str):
    try:
        # 处理逻辑
        audio_path = extract_audio(video_path)

        # 更新状态
        state_manager.update_stage(
            task_id,
            "ffmpeg.extract_audio",
            status="SUCCESS",
            output={"audio_path": audio_path}
        )
    except Exception as e:
        state_manager.update_stage(
            task_id,
            "ffmpeg.extract_audio",
            status="FAILED",
            error=str(e)
        )
```

**迁移后**:
```python
@celery_app.task(name="ffmpeg.extract_audio")
def extract_audio_task(task_id: str):
    # 1. 获取工作流上下文
    context = state_manager.get_workflow_context(task_id)

    # 2. 创建执行器
    executor = FFmpegExtractAudioExecutor("ffmpeg.extract_audio", context)

    # 3. 执行（自动处理验证、执行、格式化、错误处理）
    result_context = executor.execute()

    # 4. 保存结果
    state_manager.save_workflow_context(task_id, result_context)

    # 5. 返回状态
    return result_context.stages["ffmpeg.extract_audio"].status
```

**关键变化**:
- ✅ 不再需要手动参数传递（从 context 读取）
- ✅ 不再需要手动错误处理（executor 自动处理）
- ✅ 不再需要手动状态更新（executor 自动更新）
- ✅ 不再需要手动 MinIO URL 生成（自动处理）

---

### 步骤 4: 添加单元测试

**测试模板**:
```python
# tests/unit/workers/ffmpeg_service/test_extract_audio_executor.py

import pytest
from services.common.context import WorkflowContext
from services.workers.ffmpeg_service.executors import FFmpegExtractAudioExecutor


class TestFFmpegExtractAudioExecutor:
    """FFmpegExtractAudioExecutor 测试"""

    def test_successful_execution(self):
        """测试成功执行"""
        context = WorkflowContext(
            workflow_id="task-001",
            shared_storage_path="/share/workflows/task-001",
            input_params={
                "input_data": {"video_path": "/share/video.mp4"},
                "core": {"auto_upload_to_minio": False}
            }
        )

        executor = FFmpegExtractAudioExecutor("ffmpeg.extract_audio", context)
        result_context = executor.execute()

        assert "ffmpeg.extract_audio" in result_context.stages
        stage = result_context.stages["ffmpeg.extract_audio"]
        assert stage.status == "SUCCESS"
        assert "audio_path" in stage.output

    def test_missing_video_path(self):
        """测试缺少 video_path 参数"""
        context = WorkflowContext(
            workflow_id="task-002",
            shared_storage_path="/share/workflows/task-002",
            input_params={"input_data": {}}
        )

        executor = FFmpegExtractAudioExecutor("ffmpeg.extract_audio", context)
        result_context = executor.execute()

        stage = result_context.stages["ffmpeg.extract_audio"]
        assert stage.status == "FAILED"
        assert "Missing required parameter" in stage.error

    def test_minio_url_generation(self):
        """测试 MinIO URL 生成"""
        context = WorkflowContext(
            workflow_id="task-003",
            shared_storage_path="/share/workflows/task-003",
            input_params={
                "input_data": {"video_path": "/share/video.mp4"},
                "core": {"auto_upload_to_minio": True}
            }
        )

        executor = FFmpegExtractAudioExecutor("ffmpeg.extract_audio", context)
        result_context = executor.execute()

        stage = result_context.stages["ffmpeg.extract_audio"]
        assert "audio_path" in stage.output
        assert "audio_path_minio_url" in stage.output
```

---

### 步骤 5: 验证响应格式

**使用 NodeResponseValidator**:
```python
from services.common.validators import NodeResponseValidator

# 在测试或开发环境中验证
validator = NodeResponseValidator(strict_mode=True)
is_valid = validator.validate(result_context, "ffmpeg.extract_audio")

if not is_valid:
    print(validator.get_validation_report())
```

---

## 📝 迁移检查清单

### 代码迁移
- [ ] 创建节点执行器类（继承 BaseNodeExecutor）
- [ ] 实现 `validate_input()` 方法
- [ ] 实现 `execute_core_logic()` 方法
- [ ] 实现 `get_cache_key_fields()` 方法
- [ ] 实现 `get_required_output_fields()` 方法
- [ ] （可选）实现 `get_custom_path_fields()` 方法
- [ ] 更新 Celery 任务函数
- [ ] 移除旧的手动状态更新代码

### 测试
- [ ] 添加成功执行测试
- [ ] 添加参数验证测试
- [ ] 添加错误处理测试
- [ ] 添加 MinIO URL 生成测试
- [ ] 使用 NodeResponseValidator 验证响应格式

### 文档
- [ ] 更新节点文档说明
- [ ] 添加使用示例
- [ ] 更新 API 文档（如果需要）

---

## ⚠️  常见问题

### Q1: 如何处理不符合标准后缀的路径字段？

**A**: 使用 `get_custom_path_fields()` 方法声明。

```python
def get_custom_path_fields(self) -> List[str]:
    # 例如: vocal_audio, instrumental_audio 不符合标准后缀
    return ["vocal_audio", "instrumental_audio"]
```

### Q2: 如何处理数组类型的路径字段？

**A**: 在 `MinioUrlNamingConvention.ARRAY_FIELDS` 中声明，或者让字段名包含 `_files` 后缀。

```python
# 方式1: 添加到 ARRAY_FIELDS
ARRAY_FIELDS = ["all_audio_files", "keyframe_files", "your_array_field"]

# 方式2: 使用 _files 后缀
output = {
    "segment_files": ["/share/seg1.mp4", "/share/seg2.mp4"]
}
# 自动生成: segment_files_minio_urls
```

### Q3: 如何处理可选参数？

**A**: 在 `execute_core_logic()` 中使用 `.get()` 提供默认值。

```python
def execute_core_logic(self) -> Dict[str, Any]:
    input_data = self.get_input_data()

    # 必需参数
    video_path = input_data["video_path"]

    # 可选参数
    format = input_data.get("format", "wav")  # 默认 wav
    bitrate = input_data.get("bitrate", 128)  # 默认 128

    return process(video_path, format, bitrate)
```

### Q4: 如何处理敏感参数（如 API 密钥）？

**A**: BaseNodeExecutor 自动脱敏常见敏感字段。如需自定义，覆盖 `_extract_input_params()` 方法。

```python
def _extract_input_params(self) -> Dict[str, Any]:
    input_params = super()._extract_input_params()

    # 自定义脱敏
    if "custom_secret" in input_params:
        input_params["custom_secret"] = "***"

    return input_params
```

### Q5: 如何处理复杂的缓存逻辑？

**A**: 在 `get_cache_key_fields()` 中声明所有影响输出的字段。

```python
def get_cache_key_fields(self) -> List[str]:
    # 包含所有影响结果的参数
    return [
        "audio_path",      # 输入文件
        "model_name",      # 模型选择
        "language",        # 语言设置
        "beam_size"        # 算法参数
    ]
    # 不包含: task_id, callback_url 等不影响结果的参数
```

---

## 📊 迁移优先级

### P0 - 高优先级 (Phase 2)
1. ffmpeg.extract_audio
2. ffmpeg.merge_audio
3. ffmpeg.extract_keyframes
4. faster_whisper.transcribe
5. audio_separator.separate

### P1 - 中优先级 (Phase 3)
6. pyannote_audio.get_speaker_segments
7. pyannote_audio.validate_diarization
8. paddleocr.detect_subtitle_area
9. paddleocr.recognize_text
10. indextts.generate_speech
11. gptsovits.generate_speech
12. inpainting.remove_subtitles
13. ffmpeg.merge_video
14. ffmpeg.extract_audio_segments

### P2 - WService 节点 (Phase 4)
15. wservice.transcribe_audio
16. wservice.correct_subtitles
17. wservice.merge_subtitles
18. wservice.translate_subtitles

---

## 🎯 成功标准

迁移完成后，节点应该满足：

1. ✅ 继承 `BaseNodeExecutor`
2. ✅ 实现所有抽象方法
3. ✅ 通过 `NodeResponseValidator` 验证
4. ✅ 单元测试覆盖率 > 80%
5. ✅ 所有测试用例通过
6. ✅ 文档完整（docstring + 使用示例）

---

## 📚 参考资源

- **示例实现**: `services/common/examples/ffmpeg_extract_audio_executor.py`
- **基类文档**: `services/common/base_node_executor.py`
- **验证器文档**: `services/common/validators/node_response_validator.py`
- **测试示例**: `tests/unit/common/test_base_node_executor.py`

---

**版本历史**:
- v1.0 (2025-12-23): 初始版本
