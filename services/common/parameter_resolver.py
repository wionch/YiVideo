# services/common/parameter_resolver.py
# -*- coding: utf-8 -*-

"""
参数解析器模块。

负责解析工作流中节点参数的占位符，实现动态数据流。
提供统一的参数获取接口，支持多层级回退机制。
"""

import re
from typing import Any, Dict, List, Optional, Union
from services.common.context import WorkflowContext

# 正则表达式，用于匹配 ${{ stages.<stage_name>.output.<field_name> }} 格式
# 支持的 stage_name 和 field_name 字符集包括字母、数字、下划线、点和连字符
PARAM_REGEX = re.compile(r"\$\{\{\s*stages\.([\w\.-]+)\.output\.([\w\.-]+)\s*\}\}")

def _resolve_string(value: str, context: Dict[str, Any]) -> Any:
    """
    解析单个字符串。

    如果字符串完全匹配占位符格式，则替换为其在上下文中的实际值。
    否则，按原样返回字符串。
    """
    match = PARAM_REGEX.fullmatch(value.strip())
    if not match:
        return value  # 不是一个完整的占位符，直接返回

    stage_name, field_name = match.groups()

    # 从 context 中安全地获取值
    stage_output = context.get("stages", {}).get(stage_name, {}).get("output", {})

    if field_name in stage_output:
        return stage_output[field_name]
    else:
        raise ValueError(
            f"参数解析失败: 在阶段 '{stage_name}' 的输出中未找到字段 '{field_name}'。 "
            f"可用字段: {list(stage_output.keys())}"
        )

def _resolve_list_item(item: Any, context: Dict[str, Any]) -> Any:
    """辅助函数，用于递归解析列表中的项。"""
    if isinstance(item, str):
        return _resolve_string(item, context)
    if isinstance(item, dict):
        return resolve_parameters(item, context)
    if isinstance(item, list):
        return [_resolve_list_item(sub_item, context) for sub_item in item]
    return item

def resolve_parameters(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    递归地解析一个字典中所有的参数占位符。

    Args:
        params: 包含可能占位符的节点参数字典。
        context: 完整的工作流上下文，用于查找替换值。

    Returns:
        一个新的字典，其中所有占位符都被替换为实际值。
    """
    resolved_params = {}
    for key, value in params.items():
        if isinstance(value, str):
            resolved_params[key] = _resolve_string(value, context)
        elif isinstance(value, dict):
            resolved_params[key] = resolve_parameters(value, context)
        elif isinstance(value, list):
            resolved_params[key] = [_resolve_list_item(item, context) for item in value]
        else:
            resolved_params[key] = value
    return resolved_params

def get_param_with_fallback(
    param_name: str,
    resolved_params: Dict[str, Any],
    workflow_context: Union[WorkflowContext, Dict[str, Any]],
    default: Any = None,
    fallback_from_input_data: bool = True,
    fallback_from_stage: Optional[str] = None,
    fallback_field: Optional[str] = None,
    allow_dynamic_resolution: bool = True
) -> Any:
    """
    智能参数获取工具，统一支持三种参数来源的获取

    参数获取优先级（从高到低）：
    1. node_params（已通过 resolve_parameters 解析的参数）
    2. input_data（支持动态引用 ${{}} 解析）
    3. 指定的前置阶段输出（上游节点输出）
    4. 默认值

    支持场景：
    ✅ 工作流模式 - node_params + 动态引用
    ✅ 单任务模式 - input_data（静态值）
    ✅ 单任务模式 - input_data（动态引用）
    ✅ 上游节点自动获取

    Args:
        param_name: 参数名称
        resolved_params: 已解析的节点参数字典（来自 node_params，已经过 resolve_parameters 处理）
        workflow_context: 工作流上下文对象或字典
        default: 默认值
        fallback_from_input_data: 是否从 input_data 回退（默认 True）
        fallback_from_stage: 可选的前置阶段名称（如 "paddleocr.detect_subtitle_area"）
        fallback_field: 前置阶段输出中的字段名（默认与 param_name 相同）
        allow_dynamic_resolution: 是否对 input_data 中的值进行动态引用解析（默认 True）

    Returns:
        参数值或默认值

    Examples:
        # 基本用法
        >>> video_path = get_param_with_fallback("video_path", resolved_params, context)

        # 从前置节点回退
        >>> subtitle_area = get_param_with_fallback(
        ...     "subtitle_area",
        ...     resolved_params,
        ...     context,
        ...     fallback_from_stage="paddleocr.detect_subtitle_area"
        ... )

        # 带默认值
        >>> batch_size = get_param_with_fallback(
        ...     "batch_size",
        ...     resolved_params,
        ...     context,
        ...     default=10
        ... )
    """
    # 转换 WorkflowContext 对象为字典（兼容性处理）
    if isinstance(workflow_context, WorkflowContext):
        context_dict = workflow_context.model_dump()
    else:
        context_dict = workflow_context

    # 1. 优先从 resolved_params 获取（node_params，已解析）
    value = resolved_params.get(param_name)
    if value is not None:
        return value

    # 2. 从 input_data 回退（支持动态引用）
    if fallback_from_input_data:
        input_data = context_dict.get("input_params", {}).get("input_data", {})
        value = input_data.get(param_name)

        if value is not None:
            # 🔑 关键：如果值是字符串且包含动态引用，则解析它
            if allow_dynamic_resolution and isinstance(value, str):
                try:
                    resolved_value = _resolve_string(value, context_dict)
                    return resolved_value
                except ValueError:
                    # 如果解析失败（不是有效的动态引用），返回原值
                    return value
            return value

    # 3. 从前置阶段回退（上游节点输出）
    if fallback_from_stage:
        field = fallback_field or param_name
        stages = context_dict.get("stages", {})
        stage = stages.get(fallback_from_stage, {})

        if stage:
            output = stage.get("output", {})
            value = output.get(field)
            if value is not None:
                return value

    # 4. 返回默认值
    return default
