# services/common/validators/node_response_validator.py
# -*- coding: utf-8 -*-

"""
节点响应验证器。

本模块提供自动化的节点响应格式验证，确保所有节点遵循统一的响应规范。

验证规则：
1. 必需字段验证：status, input_params, output, error, duration
2. 状态字段格式：必须为大写（SUCCESS/FAILED/PENDING/RUNNING）
3. MinIO URL 命名约定：{field_name}_minio_url
4. 禁止非标准时长字段：processing_time, transcribe_duration 等
5. 数据溯源字段格式（可选）：provenance 包含 source_stage, source_field
"""

import os
from typing import List, Dict, Any

from services.common.context import WorkflowContext, StageExecution
from services.common.minio_url_convention import validate_minio_url_naming


class ValidationError(Exception):
    """验证错误异常"""
    pass


class NodeResponseValidator:
    """节点响应验证器"""

    # 允许的状态值
    VALID_STATUSES = ["SUCCESS", "FAILED", "PENDING", "RUNNING"]

    # 非标准时长字段（应该被禁止）
    NON_STANDARD_DURATION_FIELDS = [
        "processing_time",
        "transcribe_duration",
        "execution_time",
        "elapsed_time"
    ]

    def __init__(self, strict_mode: bool = None):
        """
        初始化验证器。

        Args:
            strict_mode: 严格模式（True=抛出异常，False=仅记录错误）
                        如果为 None，从环境变量读取
        """
        if strict_mode is None:
            strict_mode = os.getenv("NODE_RESPONSE_VALIDATOR_STRICT_MODE", "false").lower() == "true"

        self.strict_mode = strict_mode
        self.errors: List[str] = []

    def validate(self, context: WorkflowContext, stage_name: str) -> bool:
        """
        验证指定阶段的响应格式。

        Args:
            context: 工作流上下文
            stage_name: 阶段名称

        Returns:
            True 如果验证通过，False 否则

        Raises:
            ValidationError: 如果 strict_mode=True 且验证失败
        """
        self.errors = []

        if stage_name not in context.stages:
            self.errors.append(f"Stage '{stage_name}' not found in context")
            if self.strict_mode:
                raise ValidationError(f"Validation failed: {'; '.join(self.errors)}")
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

        # 规则 5: 检查数据溯源字段（可选）
        self._validate_provenance_field(stage, stage_name)

        if self.errors and self.strict_mode:
            raise ValidationError(f"Validation failed: {'; '.join(self.errors)}")

        return len(self.errors) == 0

    def _validate_required_fields(self, stage: StageExecution, stage_name: str):
        """验证必需字段存在"""
        required_fields = ["status", "input_params", "output", "error", "duration"]
        for field in required_fields:
            if not hasattr(stage, field):
                self.errors.append(f"{stage_name}: Missing required field '{field}'")

    def _validate_status_field(self, stage: StageExecution, stage_name: str):
        """验证状态字段格式（必须大写）"""
        if stage.status not in self.VALID_STATUSES:
            self.errors.append(
                f"{stage_name}: Invalid status '{stage.status}'. "
                f"Must be one of: {', '.join(self.VALID_STATUSES)}"
            )

    def _validate_minio_url_naming(self, stage: StageExecution, stage_name: str):
        """验证 MinIO URL 字段命名约定"""
        naming_errors = validate_minio_url_naming(stage.output)
        for error in naming_errors:
            self.errors.append(f"{stage_name}: {error}")

    def _validate_duration_field(self, stage: StageExecution, stage_name: str):
        """验证时长字段（禁止使用非标准字段）"""
        output = stage.output

        # 检查是否使用了非标准时长字段
        for field in self.NON_STANDARD_DURATION_FIELDS:
            if field in output:
                self.errors.append(
                    f"{stage_name}: Non-standard duration field '{field}' found. "
                    f"Use 'duration' at stage level instead"
                )

    def _validate_provenance_field(self, stage: StageExecution, stage_name: str):
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
        """
        获取验证报告。

        Returns:
            格式化的验证报告字符串
        """
        if not self.errors:
            return "✅ All validations passed"

        report = f"❌ Found {len(self.errors)} validation error(s):\n"
        for i, error in enumerate(self.errors, 1):
            report += f"  {i}. {error}\n"

        return report
