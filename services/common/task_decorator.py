# services/common/task_decorator.py
# -*- coding: utf-8 -*-

"""
工作流任务装饰器。

提供一个装饰器 `@workflow_task`，用于在 Celery 任务执行前自动处理参数化输入。
"""

from functools import wraps
from .parameter_resolver import resolve_parameters
from .logger import get_logger

logger = get_logger(__name__)

def workflow_task(task_function):
    """
    一个装饰器，用于自动解析和注入工作流节点的参数。

    它会查找为当前任务节点定义的参数，使用 `parameter_resolver` 解析占位符，
    然后将解析后的值更新回工作流上下文中，以便任务函数直接使用。
    """
    @wraps(task_function)
    def wrapper(self, context: dict, *args, **kwargs):
        # 'self' 是 Celery 的 Task 实例
        stage_name = self.name

        # 1. 从 context 中获取为本节点定义的原始参数
        # 结构: context['input_params']['node_params'][stage_name]
        node_params = context.get("input_params", {}).get("node_params", {}).get(stage_name, {})

        if node_params:
            logger.info(f"[{stage_name}] 检测到节点参数，开始解析...")
            try:
                # 2. 调用解析器，将占位符替换为实际值
                resolved_params = resolve_parameters(node_params, context)
                logger.info(f"[{stage_name}] 参数解析完成。")

                # 3. 将解析后的参数更新回 input_params 的顶层，供任务直接使用
                # 使用 .update() 可以覆盖任何同名的顶层参数
                context.get("input_params", {}).update(resolved_params)

            except ValueError as e:
                logger.error(f"[{stage_name}] 参数解析失败: {e}")
                # 抛出异常以使任务失败并报告错误
                raise e
        else:
            logger.info(f"[{stage_name}] 未提供节点参数，跳过解析。")

        # 4. 调用被装饰的原始任务函数
        return task_function(self, context, *args, **kwargs)

    return wrapper