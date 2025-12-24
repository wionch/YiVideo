# services/common/base_node_executor.py
# -*- coding: utf-8 -*-

"""
节点执行器抽象基类。

本模块提供统一的节点执行框架，确保所有工作流节点遵循一致的执行流程和响应格式。

核心设计：
- 模板方法模式：execute() 定义统一流程
- 抽象方法：子类实现特定业务逻辑
- 自动格式化：应用 MinIO URL 命名约定
- 异常处理：统一的错误捕获和记录
"""

import time
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

from services.common.context import WorkflowContext, StageExecution
from services.common.minio_url_convention import apply_minio_url_convention


class BaseNodeExecutor(ABC):
    """
    所有节点执行器的抽象基类。

    子类必须实现以下抽象方法：
    - validate_input(): 验证输入参数
    - execute_core_logic(): 执行核心业务逻辑
    - get_cache_key_fields(): 返回缓存键字段列表

    使用示例：
        class FFmpegExtractAudioExecutor(BaseNodeExecutor):
            def validate_input(self) -> None:
                if "video_path" not in self.get_input_data():
                    raise ValueError("Missing required parameter: video_path")

            def execute_core_logic(self) -> Dict[str, Any]:
                video_path = self.get_input_data()["video_path"]
                audio_path = self._extract_audio(video_path)
                return {"audio_path": audio_path}

            def get_cache_key_fields(self) -> List[str]:
                return ["video_path"]
    """

    def __init__(self, task_name: str, workflow_context: WorkflowContext):
        """
        初始化节点执行器。

        Args:
            task_name: 任务名称（如 "ffmpeg.extract_audio"）
            workflow_context: 工作流上下文
        """
        self.task_name = task_name
        self.context = workflow_context
        self.stage_name = task_name  # 阶段名称与任务名称相同

    @abstractmethod
    def validate_input(self) -> None:
        """
        验证输入参数。

        子类必须实现此方法以验证特定节点的参数。
        如果参数无效，应抛出 ValueError 异常。

        Raises:
            ValueError: 如果输入参数无效
        """
        pass

    @abstractmethod
    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行节点的核心业务逻辑。

        子类必须实现此方法以执行特定的业务逻辑。

        Returns:
            原始输出字典（未格式化，不包含 MinIO URL）

        Raises:
            Exception: 如果执行失败
        """
        pass

    @abstractmethod
    def get_cache_key_fields(self) -> List[str]:
        """
        返回用于复用判定的字段列表。

        子类必须实现此方法以声明缓存键字段。

        Returns:
            字段名称列表

        Examples:
            >>> return ["audio_path", "model_name"]
        """
        pass

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段列表（用于复用判定）。

        子类可以覆盖此方法以声明必需的输出字段。
        默认返回空列表（不验证输出字段）。

        Returns:
            必需输出字段名称列表
        """
        return []

    def get_custom_path_fields(self) -> List[str]:
        """
        返回自定义路径字段列表（不符合标准后缀规则的路径字段）。

        子类可以覆盖此方法以声明自定义路径字段。
        默认返回空列表。

        Returns:
            自定义路径字段名称列表

        Examples:
            >>> return ["vocal_audio", "instrumental_audio"]
        """
        return []

    def execute(self) -> WorkflowContext:
        """
        执行节点的完整流程（模板方法）。

        流程:
        1. 验证输入
        2. 执行核心逻辑
        3. 格式化输出（应用 MinIO URL 命名约定）
        4. 更新 WorkflowContext
        5. 返回更新后的 WorkflowContext

        Returns:
            更新后的 WorkflowContext

        Note:
            此方法不应被子类覆盖。
        """
        start_time = time.time()

        try:
            # 1. 验证输入
            self.validate_input()

            # 2. 执行核心逻辑
            raw_output = self.execute_core_logic()

            # 3. 格式化输出（应用 MinIO URL 命名约定）
            formatted_output = self.format_output(raw_output)

            # 4. 更新 WorkflowContext
            duration = time.time() - start_time
            stage_result = StageExecution(
                status="SUCCESS",
                input_params=self._extract_input_params(),
                output=formatted_output,
                error=None,
                duration=round(duration, 2)
            )

            self.context.stages[self.stage_name] = stage_result

        except Exception as e:
            # 异常处理：记录错误信息
            duration = time.time() - start_time
            stage_result = StageExecution(
                status="FAILED",
                input_params=self._extract_input_params(),
                output={},
                error=str(e),
                duration=round(duration, 2)
            )

            self.context.stages[self.stage_name] = stage_result
            self.context.error = f"{self.stage_name} failed: {str(e)}"

        return self.context

    def format_output(self, raw_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        应用 MinIO URL 命名约定格式化输出。

        默认实现：遍历所有本地路径字段，添加对应的 _minio_url 字段占位符。
        子类可以覆盖此方法以自定义格式化逻辑。

        Args:
            raw_output: 原始输出字典

        Returns:
            格式化后的输出字典

        Note:
            实际的 MinIO URL 生成由 StateManager 处理。
        """
        # 检查全局上传开关（从 config.yml 读取）
        from services.common.config_loader import get_config

        try:
            config = get_config() or {}
            auto_upload = config.get("core", {}).get("auto_upload_to_minio", True)
        except Exception:
            # 如果配置读取失败，默认启用上传
            auto_upload = True

        return apply_minio_url_convention(
            output=raw_output,
            auto_upload_enabled=auto_upload,
            custom_path_fields=self.get_custom_path_fields()
        )

    def get_input_data(self) -> Dict[str, Any]:
        """
        获取输入数据字典。

        Returns:
            输入数据字典
        """
        return self.context.input_params.get("input_data", {})

    def _extract_input_params(self) -> Dict[str, Any]:
        """
        从 WorkflowContext 提取当前节点的输入参数快照。

        Returns:
            输入参数字典

        Note:
            敏感信息（如 API 密钥）应被脱敏。
        """
        input_params = self.get_input_data().copy()

        # 脱敏敏感字段
        sensitive_fields = ["api_key", "token", "password", "secret"]
        for field in sensitive_fields:
            if field in input_params:
                input_params[field] = "***"

        return input_params
