# services/api_gateway/app/workflow_factory.py
# -*- coding: utf-8 -*-

"""
工作流构建工厂 V3 - 完全解耦

根据传入的工作流配置，动态地创建并连接Celery任务，形成一个可执行的任务链。
此版本不再直接导入worker任务，而是通过任务名称字符串来构建签名，实现完全解耦。
"""

import logging

from services.common.logger import get_logger

logger = get_logger('workflow_factory')
from typing import Any
from typing import Dict
from typing import List

from celery import chain
from celery import signature

# 日志已统一管理，使用 services.common.logger

def build_workflow_chain(workflow_config: Dict[str, Any], initial_context: Dict[str, Any]) -> chain:
    """
    根据配置动态构建Celery任务链。

    Args:
        workflow_config (Dict[str, Any]): 从API请求中解析出的工作流配置。
                                           必须包含一个 `workflow_chain` 列表，其中包含任务的名称字符串。
        initial_context (Dict[str, Any]): 初始的工作流上下文，将作为第一个任务的输入。

    Returns:
        celery.chain: 一个准备好被执行的Celery任务链。
        
    Raises:
        ValueError: 如果配置格式不正确。
    """
    
    task_names = workflow_config.get("workflow_chain")
    if not task_names or not isinstance(task_names, list):
        raise ValueError("工作流配置中缺少或无效的 'workflow_chain' 列表。")

    logger.info(f"正在为工作流构建任务链: {' -> '.join(task_names)}")

    task_signatures = []
    for i, task_name in enumerate(task_names):
        # 从任务名中动态推断队列名，例如 'ffmpeg.extract_keyframes' -> 'ffmpeg_queue'
        try:
            queue_name = f"{task_name.split('.')[0]}_queue"
        except IndexError:
            raise ValueError(f"任务名 '{task_name}' 格式不正确，无法推断队列名。")

        # 为任务签名设置正确的队列
        task_options = {'queue': queue_name}

        # 直接使用任务名称字符串创建任务签名
        # 这是Celery实现服务解耦的标准方式
        if i == 0:
            # 第一个任务，需要传入初始上下文。
            task_sig = signature(task_name, kwargs={'context': initial_context}, options=task_options, immutable=True)
        else:
            # 后续任务，它们将自动接收前一个任务的返回值作为输入。
            task_sig = signature(task_name, options=task_options)
        
        task_signatures.append(task_sig)

    if not task_signatures:
        raise ValueError("无法为工作流构建任何任务，请检查配置。")

    # 将所有任务签名连接成一个链
    workflow_chain = chain(task_signatures)
    logger.info("成功构建动态、解耦的工作流任务链。")
    
    return workflow_chain
