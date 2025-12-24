# Design: 统一节点响应格式架构设计

## 架构概述

本设计引入了一个分层的响应格式规范体系，通过抽象基类、验证器和命名约定确保所有工作流节点返回一致的响应格式。

## 核心组件

### 1. BaseNodeExecutor 抽象基类

**职责**：为所有节点提供统一的执行框架和响应格式保证。

**设计决策**：
- **为什么使用抽象基类而非接口？**
  - Python 的 ABC 模块提供了强制子类实现特定方法的能力
  - 可以提供默认实现（如通用的输出格式化逻辑）
  - 便于未来扩展（如添加通用的错误处理、日志记录）

**接口定义**：

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from services.common.context import WorkflowContext, StageExecution

class BaseNodeExecutor(ABC):
    """所有节点执行器的抽象基类"""

    def __init__(self, task_name: str, workflow_context: WorkflowContext):
        self.task_name = task_name
        self.context = workflow_context
        self.stage_name = task_name  # 如 "ffmpeg.extract_audio"

    @abstractmethod
    def validate_input(self) -> None:
        """
        验证输入参数。

        抛出 ValueError 如果参数无效。
        子类必须实现此方法以验证特定节点的参数。
        """
        pass

    @abstractmethod
    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行节点的核心业务逻辑。

        返回:
            原始输出字典（未格式化）
        """
        pass

    @abstractmethod
    def get_cache_key_fields(self) -> List[str]:
        """
        返回用于复用判定的字段列表。

        示例: ["audio_path", "model_name"]
        """
        pass

    def execute(self) -> WorkflowContext:
        """
        执行节点的完整流程（模板方法）。

        流程:
        1. 验证输入
        2. 检查缓存复用
        3. 执行核心逻辑
        4. 格式化输出
        5. 更新 WorkflowContext
        """
        import time
        start_time = time.time()

        try:
            # 1. 验证输入
            self.validate_input()

            # 2. 检查缓存复用（由 CacheKeyStrategy 处理）
            # 这里简化，实际由外部 StateManager 处理

            # 3. 执行核心逻辑
            raw_output = self.execute_core_logic()

            # 4. 格式化输出（应用 MinIO URL 命名约定）
            formatted_output = self.format_output(raw_output)

            # 5. 更新 WorkflowContext
            duration = time.time() - start_time
            stage_result = StageExecution(
                status="SUCCESS",
                input_params=self._extract_input_params(),
                output=formatted_output,
                error=None,
                duration=duration
            )

            self.context.stages[self.stage_name] = stage_result

        except Exception as e:
            duration = time.time() - start_time
            stage_result = StageExecution(
                status="FAILED",
                input_params=self._extract_input_params(),
                output={},
                error=str(e),
                duration=duration
            )
            self.context.stages[self.stage_name] = stage_result
            self.context.error = f"{self.stage_name} failed: {str(e)}"

        return self.context

    def format_output(self, raw_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        应用 MinIO URL 命名约定格式化输出。

        默认实现：遍历所有本地路径字段，添加对应的 _minio_url 字段。
        子类可以覆盖此方法以自定义格式化逻辑。
        """
        from services.common.minio_url_convention import apply_minio_url_convention
        return apply_minio_url_convention(raw_output, self.context)

    def _extract_input_params(self) -> Dict[str, Any]:
        """从 WorkflowContext 提取当前节点的输入参数"""
        # 简化实现，实际需要从 context.input_params 和智能回退中提取
        return self.context.input_params.get("input_data", {})
```

**权衡分析**：
- ✅ **优点**：强制统一接口，减少重复代码
- ✅ **优点**：模板方法模式确保执行流程一致
- ❌ **缺点**：增加了继承层级，可能影响可读性
- ❌ **缺点**：现有节点需要重构以继承此基类

**替代方案**：
- **方案 A**：使用装饰器而非基类
  - 优点：侵入性更小
  - 缺点：无法强制实现特定方法
- **方案 B**：使用 Mixin 组合
  - 优点：更灵活
  - 缺点：缺乏清晰的契约

**选择理由**：基类方案提供了最强的契约保证，适合需要严格统一的场景。

---

### 2. MinioUrlNamingConvention 命名规范

**职责**：自动化生成符合规范的 MinIO URL 字段名。

**设计决策**：
- **为什么需要自动化？**
  - 手动命名容易出错（如忘记保留 `_dir` 后缀）
  - 自动化确保 100% 一致性
  - 便于未来修改规范（只需修改一处）

**核心规则**：

```python
# services/common/minio_url_convention.py

from typing import Dict, Any, List
from services.common.context import WorkflowContext

class MinioUrlNamingConvention:
    """MinIO URL 字段命名约定"""

    # 需要生成 MinIO URL 的字段后缀模式
    PATH_SUFFIXES = ["_path", "_file", "_dir", "_audio", "_video"]

    # 数组字段的特殊处理
    ARRAY_FIELDS = ["all_audio_files", "keyframe_files"]

    @staticmethod
    def get_minio_url_field_name(local_field_name: str) -> str:
        """
        根据本地字段名生成 MinIO URL 字段名。

        规则:
        1. 保留完整的本地字段名作为前缀
        2. 添加 _minio_url 后缀
        3. 数组字段添加 _minio_urls（复数）

        示例:
            audio_path → audio_path_minio_url
            keyframe_dir → keyframe_dir_minio_url (保留 _dir)
            multi_frames_path → multi_frames_path_minio_url (保留 _path)
            all_audio_files → all_audio_files_minio_urls (复数)
        """
        if local_field_name in MinioUrlNamingConvention.ARRAY_FIELDS:
            return f"{local_field_name}_minio_urls"
        else:
            return f"{local_field_name}_minio_url"

    @staticmethod
    def is_path_field(field_name: str) -> bool:
        """判断字段是否为路径字段（需要生成 MinIO URL）"""
        return any(field_name.endswith(suffix)
                   for suffix in MinioUrlNamingConvention.PATH_SUFFIXES)

def apply_minio_url_convention(
    output: Dict[str, Any],
    context: WorkflowContext
) -> Dict[str, Any]:
    """
    应用 MinIO URL 命名约定到输出字典。

    参数:
        output: 原始输出字典（包含本地路径）
        context: 工作流上下文（用于获取 MinIO 配置）

    返回:
        增强后的输出字典（包含 MinIO URL 字段）
    """
    from services.common.state_manager import get_minio_url_for_path

    enhanced_output = output.copy()
    convention = MinioUrlNamingConvention()

    # 检查全局上传开关
    auto_upload = context.input_params.get("core", {}).get("auto_upload_to_minio", False)
    if not auto_upload:
        return enhanced_output

    # 遍历所有字段
    for field_name, field_value in output.items():
        if not convention.is_path_field(field_name):
            continue

        minio_field_name = convention.get_minio_url_field_name(field_name)

        # 处理数组字段
        if isinstance(field_value, list):
            minio_urls = [get_minio_url_for_path(path, context) for path in field_value]
            enhanced_output[minio_field_name] = minio_urls

        # 处理单个路径字段
        elif isinstance(field_value, str):
            minio_url = get_minio_url_for_path(field_value, context)
            if minio_url:
                enhanced_output[minio_field_name] = minio_url

    return enhanced_output
```

**验证示例**：

```python
# 测试用例
def test_minio_url_naming_convention():
    convention = MinioUrlNamingConvention()

    # 测试标准字段
    assert convention.get_minio_url_field_name("audio_path") == "audio_path_minio_url"

    # 测试保留后缀
    assert convention.get_minio_url_field_name("keyframe_dir") == "keyframe_dir_minio_url"
    assert convention.get_minio_url_field_name("multi_frames_path") == "multi_frames_path_minio_url"

    # 测试数组字段
    assert convention.get_minio_url_field_name("all_audio_files") == "all_audio_files_minio_urls"
```

---

### 3. NodeResponseValidator 验证器

**职责**：验证节点响应是否符合统一规范。

**设计决策**：
- **为什么需要运行时验证？**
  - 静态类型检查无法覆盖所有规范（如字段命名约定）
  - 开发阶段快速发现不一致问题
  - 生产环境可选择性启用轻量级验证

**验证规则**：

```python
# services/common/validators/node_response_validator.py

from typing import List, Dict, Any
from services.common.context import WorkflowContext
from pydantic import ValidationError

class ValidationError(Exception):
    """验证错误"""
    pass

class NodeResponseValidator:
    """节点响应验证器"""

    def __init__(self, strict_mode: bool = False):
        """
        参数:
            strict_mode: 严格模式（开发环境建议启用）
        """
        self.strict_mode = strict_mode
        self.errors: List[str] = []

    def validate(self, context: WorkflowContext, stage_name: str) -> bool:
        """
        验证指定阶段的响应格式。

        返回:
            True 如果验证通过，False 否则
        """
        self.errors = []

        if stage_name not in context.stages:
            self.errors.append(f"Stage '{stage_name}' not found in context")
            return False

        stage = context.stages[stage_name]

        # 规则 1: 检查必需字段
        self._validate_required_fields(stage, stage_name)

        # 规则 2: 检查状态字段格式
        self._validate_status_field(stage, stage_name)

        # 规则 3: 检查 MinIO URL 字段命名
        self._validate_minio_url_naming(stage, stage_name)

        # 规则 4: 检查时长字段
        self._validate_duration_field(stage, stage_name)

        # 规则 5: 检查数据溯源字段
        self._validate_provenance_field(stage, stage_name)

        if self.errors and self.strict_mode:
            raise ValidationError(f"Validation failed: {'; '.join(self.errors)}")

        return len(self.errors) == 0

    def _validate_required_fields(self, stage, stage_name: str):
        """验证必需字段存在"""
        required_fields = ["status", "input_params", "output", "error", "duration"]
        for field in required_fields:
            if not hasattr(stage, field):
                self.errors.append(f"{stage_name}: Missing required field '{field}'")

    def _validate_status_field(self, stage, stage_name: str):
        """验证状态字段格式（必须大写）"""
        if stage.status not in ["SUCCESS", "FAILED", "PENDING", "RUNNING"]:
            self.errors.append(
                f"{stage_name}: Invalid status '{stage.status}'. "
                f"Must be one of: SUCCESS, FAILED, PENDING, RUNNING"
            )

    def _validate_minio_url_naming(self, stage, stage_name: str):
        """验证 MinIO URL 字段命名约定"""
        from services.common.minio_url_convention import MinioUrlNamingConvention

        convention = MinioUrlNamingConvention()
        output = stage.output

        for field_name in output.keys():
            # 检查是否为 MinIO URL 字段
            if "_minio_url" in field_name:
                # 提取本地字段名
                local_field_name = field_name.replace("_minio_urls", "").replace("_minio_url", "")

                # 验证命名是否符合约定
                expected_name = convention.get_minio_url_field_name(local_field_name)
                if field_name != expected_name:
                    self.errors.append(
                        f"{stage_name}: MinIO URL field '{field_name}' does not follow naming convention. "
                        f"Expected: '{expected_name}'"
                    )

                # 验证对应的本地字段是否存在
                if local_field_name not in output:
                    self.errors.append(
                        f"{stage_name}: MinIO URL field '{field_name}' exists but "
                        f"corresponding local field '{local_field_name}' is missing"
                    )

    def _validate_duration_field(self, stage, stage_name: str):
        """验证时长字段（禁止使用 processing_time 等别名）"""
        output = stage.output

        # 检查是否使用了非标准时长字段
        non_standard_duration_fields = ["processing_time", "transcribe_duration", "execution_time"]
        for field in non_standard_duration_fields:
            if field in output:
                self.errors.append(
                    f"{stage_name}: Non-standard duration field '{field}' found. "
                    f"Use 'duration' at stage level instead"
                )

    def _validate_provenance_field(self, stage, stage_name: str):
        """验证数据溯源字段（可选但推荐）"""
        output = stage.output

        # 如果节点使用了智能回退，应该包含 provenance 信息
        if "provenance" in output:
            provenance = output["provenance"]
            required_provenance_fields = ["source_stage", "source_field"]

            for field in required_provenance_fields:
                if field not in provenance:
                    self.errors.append(
                        f"{stage_name}: Provenance field missing '{field}'"
                    )

    def get_validation_report(self) -> str:
        """获取验证报告"""
        if not self.errors:
            return "✅ All validations passed"

        report = f"❌ Found {len(self.errors)} validation errors:\n"
        for i, error in enumerate(self.errors, 1):
            report += f"  {i}. {error}\n"

        return report
```

---

### 4. CacheKeyStrategy 缓存策略

**职责**：统一复用判定逻辑。

**设计决策**：
- **为什么需要显式声明缓存键？**
  - 当前的隐式判定逻辑（检查某个输出字段是否非空）不透明
  - 不同节点的判定逻辑不一致
  - 显式声明便于理解和维护

**接口定义**：

```python
# services/common/cache_key_strategy.py

from typing import List, Dict, Any
from abc import ABC, abstractmethod

class CacheKeyStrategy(ABC):
    """缓存键生成策略接口"""

    @abstractmethod
    def get_cache_key_fields(self) -> List[str]:
        """
        返回用于生成缓存键的字段列表。

        示例:
            ["audio_path", "model_name"] 表示缓存键由这两个字段组合生成
        """
        pass

    def generate_cache_key(self, task_name: str, input_params: Dict[str, Any]) -> str:
        """
        生成缓存键。

        参数:
            task_name: 任务名称（如 "ffmpeg.extract_audio"）
            input_params: 输入参数字典

        返回:
            缓存键字符串
        """
        import hashlib
        import json

        key_fields = self.get_cache_key_fields()
        key_values = {}

        for field in key_fields:
            if field in input_params:
                key_values[field] = input_params[field]

        # 生成稳定的哈希
        key_str = json.dumps(key_values, sort_keys=True)
        hash_value = hashlib.md5(key_str.encode()).hexdigest()

        return f"{task_name}:{hash_value}"
```

**使用示例**：

```python
class FFmpegExtractAudioExecutor(BaseNodeExecutor, CacheKeyStrategy):
    """FFmpeg 音频提取节点"""

    def get_cache_key_fields(self) -> List[str]:
        """
        音频提取的缓存键仅依赖输入视频路径。
        不同的视频路径会生成不同的音频文件。
        """
        return ["video_path"]

    def execute_core_logic(self) -> Dict[str, Any]:
        # 实现音频提取逻辑
        pass
```

---

## 数据流图

```
┌─────────────────┐
│  API Request    │
│  (input_data)   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  BaseNodeExecutor.execute()         │
│  ┌─────────────────────────────┐   │
│  │ 1. validate_input()         │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │ 2. check cache (外部)       │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │ 3. execute_core_logic()     │   │
│  │    (子类实现)               │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │ 4. format_output()          │   │
│  │    ↓                        │   │
│  │  apply_minio_url_convention │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │ 5. update WorkflowContext   │   │
│  └─────────────────────────────┘   │
└─────────────────┬───────────────────┘
                  │
                  ▼
         ┌────────────────────┐
         │ NodeResponseValidator│
         │ (开发环境)          │
         └────────┬────────────┘
                  │
                  ▼
         ┌────────────────────┐
         │  WorkflowContext   │
         │  (统一格式)        │
         └────────────────────┘
```

---

## 迁移策略

### 阶段 1：共存期（第 1-6 周）
- 新节点继承 `BaseNodeExecutor`
- 旧节点保持原样
- 验证器仅在开发环境启用

### 阶段 2：迁移期（第 7-8 周）
- 逐步迁移旧节点
- 提供兼容性层（`legacy_format` 参数）
- 更新文档

### 阶段 3：废弃期（6 个月后）
- 移除兼容性层
- 所有节点强制使用新格式

---

## 性能考虑

### 验证器性能优化

```python
# 生产环境：轻量级验证
validator = NodeResponseValidator(strict_mode=False)

# 开发环境：严格验证
validator = NodeResponseValidator(strict_mode=True)
```

### MinIO URL 生成优化

- 使用缓存避免重复计算
- 批量上传减少网络开销

---

## 安全考虑

### 路径遍历防护

```python
def validate_local_path(path: str) -> bool:
    """验证路径不包含路径遍历攻击"""
    if ".." in path or path.startswith("/"):
        raise ValueError(f"Invalid path: {path}")
    return True
```

### MinIO URL 签名

- 使用预签名 URL 限制访问时间
- 避免在日志中泄露完整 URL

---

## 开放问题

1. **是否需要版本化响应格式？**
   - 在响应中添加 `response_format_version` 字段？
   - 支持客户端请求特定版本？

2. **如何处理超大输出？**
   - 是否需要分页机制？
   - 是否需要压缩响应？

3. **是否需要 JSON Schema 支持？**
   - 提供 OpenAPI 规范？
   - 支持客户端自动生成类型定义？
