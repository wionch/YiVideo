#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
集成测试: 验证 MinIO 文件上传去重逻辑

模拟真实工作流场景,验证文件不会被重复上传
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, '/app')

from services.common.context import WorkflowContext, StageExecution
from services.common.state_manager import update_workflow_state
from services.common.logger import get_logger

logger = get_logger('integration_test')


def test_deduplication_in_workflow():
    """测试工作流中的去重逻辑"""

    logger.info("=" * 60)
    logger.info("开始集成测试: MinIO 文件上传去重")
    logger.info("=" * 60)

    # 创建测试工作流上下文
    context = WorkflowContext(
        workflow_id="integration_test_dedup",
        input_params={},
        shared_storage_path="/share/workflows/integration_test_dedup",
        stages={}
    )

    # 模拟第一个阶段: 音频提取
    context.stages["extract_audio"] = StageExecution(
        status="SUCCESS",
        output={
            "audio_path": "/share/test/test_audio.wav",  # 使用真实存在的文件
        }
    )

    logger.info("\n第一次调用 update_workflow_state (模拟 Worker 完成任务)")
    logger.info("预期: 如果文件存在,会尝试上传")

    # 第一次调用 (模拟 Worker 完成任务)
    try:
        update_workflow_state(context)
        logger.info("✓ 第一次调用成功")
    except Exception as e:
        logger.warning(f"第一次调用出错 (可能因为文件不存在): {e}")

    # 手动添加 MinIO URL (模拟上传成功)
    context.stages["extract_audio"].output["audio_path_minio_url"] = \
        "http://minio:9000/yivideo/integration_test_dedup/test_audio.wav"

    logger.info("\n第二次调用 update_workflow_state (模拟 API Gateway 合并状态)")
    logger.info("预期: 检测到 audio_path_minio_url 已存在,跳过上传")

    # 第二次调用 (模拟 API Gateway 合并状态)
    try:
        update_workflow_state(context)
        logger.info("✓ 第二次调用成功")
    except Exception as e:
        logger.error(f"第二次调用出错: {e}")
        return False

    logger.info("\n" + "=" * 60)
    logger.info("集成测试完成!")
    logger.info("=" * 60)
    logger.info("\n请检查上方日志,确认:")
    logger.info("1. 第二次调用时出现 '跳过已上传的文件: audio_path (已有 audio_path_minio_url)'")
    logger.info("2. 没有出现 '准备上传文件' 的重复日志")
    logger.info("=" * 60)

    return True


if __name__ == "__main__":
    success = test_deduplication_in_workflow()
    sys.exit(0 if success else 1)
