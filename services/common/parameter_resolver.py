# services/common/parameter_resolver.py
# -*- coding: utf-8 -*-

"""
参数解析器模块。

负责解析工作流中节点参数的占位符，实现动态数据流。
"""

import re
from typing import Any, Dict, List

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