# services/api_gateway/app/incremental_utils.py
# -*- coding: utf-8 -*-

"""
增量工作流执行的辅助函数。
"""

import json
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from redis import Redis

from services.common.context import StageExecution
from services.common.logger import get_logger

logger = get_logger('incremental_utils')

# --- Lua 脚本：安全释放分布式锁 ---
# 该脚本确保只有锁的持有者才能释放锁，防止竞态条件
# 原理：原子性地检查锁的值是否匹配，匹配才删除
LUA_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

# --- Redis 连接 ---
# 注意：这里创建了一个独立的Redis连接。在大型应用中，最好共享一个连接池。
try:
    from services.common.config_loader import get_redis_config
    
    redis_config = get_redis_config()
    REDIS_HOST = redis_config['host']
    REDIS_PORT = redis_config['port']
    # 使用与 state_manager 相同的DB，以确保锁和状态在同一个地方
    REDIS_STATE_DB = int(os.environ.get('REDIS_STATE_DB', 3))
    redis_client = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_STATE_DB, decode_responses=True)
    redis_client.ping()
    logger.info(f"增量工具成功连接到Redis at {REDIS_HOST}:{REDIS_PORT}/{REDIS_STATE_DB}")
except ValueError as e:
    logger.error(f"Redis配置错误: {e}")
    redis_client = None
except Exception as e:
    logger.error(f"增量工具无法连接到Redis. 错误: {e}")
    redis_client = None


@dataclass
class WorkflowDiff:
    """工作流差异计算结果"""
    tasks_to_execute: List[str]  # 需要执行的任务列表
    tasks_to_skip: List[str]      # 跳过的任务列表（已完成）
    is_append_only: bool          # 是否为纯追加模式

def _is_prefix(prefix: List[str], full: List[str]) -> bool:
    """
    检查 prefix 是否为 full 的前缀
    """
    if len(prefix) > len(full):
        return False
    return prefix == full[:len(prefix)]

def compute_workflow_diff(
    old_chain: List[str],
    new_chain: List[str],
    existing_stages: Dict[str, StageExecution],
    mode: str
) -> WorkflowDiff:
    """
    计算工作流任务链的差异
    """
    if mode == "incremental":
        if not _is_prefix(old_chain, new_chain):
            raise ValueError(
                f"增量模式只允许在工作流尾部追加任务。\n"
                f"原任务链: {old_chain}\n"
                f"新任务链: {new_chain}\n"
                f"提示：如果要插入或删除任务，请创建新工作流；"
                f"如果要重试失败任务，请使用 'retry' 模式"
            )

        new_tasks = new_chain[len(old_chain):]

        failed_tasks = []
        for task_name in old_chain:
            stage = existing_stages.get(task_name)
            if not stage or stage.status not in ['SUCCESS', 'COMPLETED']:
                failed_tasks.append(task_name)

        if failed_tasks:
            raise ValueError(
                f"增量模式要求所有现有任务已成功完成。\n"
                f"失败或未完成的任务: {failed_tasks}\n"
                f"提示：请使用 'retry' 模式从失败点重新执行"
            )

        logger.info(f"增量模式验证通过，将追加 {len(new_tasks)} 个新任务")

        return WorkflowDiff(
            tasks_to_execute=new_tasks,
            tasks_to_skip=old_chain,
            is_append_only=True
        )

    elif mode == "retry":
        first_failed_index = None
        for i, task_name in enumerate(new_chain):
            stage = existing_stages.get(task_name)
            if not stage or stage.status not in ['SUCCESS', 'COMPLETED']:
                first_failed_index = i
                logger.info(
                    f"检测到失败/未执行任务: {task_name} "
                    f"(状态: {stage.status if stage else 'NOT_FOUND'})"
                )
                break

        if first_failed_index is None:
            logger.info("所有任务已成功完成，无需重试")
            return WorkflowDiff(
                tasks_to_execute=[],
                tasks_to_skip=new_chain,
                is_append_only=True
            )

        tasks_to_execute = new_chain[first_failed_index:]
        tasks_to_skip = new_chain[:first_failed_index]

        logger.info(
            f"重试模式：从任务 '{tasks_to_execute[0]}' 开始重新执行"
        )

        return WorkflowDiff(
            tasks_to_execute=tasks_to_execute,
            tasks_to_skip=tasks_to_skip,
            is_append_only=False
        )

    else:
        raise ValueError(f"不支持的执行模式: {mode}")


def merge_node_params(
    old_params: Dict[str, Any],
    new_params: Dict[str, Any],
    strategy: str
) -> Dict[str, Any]:
    """
    合并节点参数，处理冲突
    """
    if strategy == "override":
        logger.info(f"使用 override 策略，完全使用新参数")
        return new_params.copy()

    elif strategy == "strict":
        conflicts = {}
        for key in new_params:
            if key in old_params and old_params[key] != new_params[key]:
                conflicts[key] = {
                    "old_value": old_params[key],
                    "new_value": new_params[key]
                }

        if conflicts:
            conflicts_json = json.dumps(conflicts, indent=2, ensure_ascii=False)
            raise ValueError(
                f"检测到参数冲突（strict 模式不允许覆盖）：\n{conflicts_json}"
            )

        merged = {**old_params, **new_params}
        logger.info(f"strict 模式：参数验证通过，无冲突")
        return merged

    else:  # strategy == "merge"
        merged = old_params.copy()
        overridden_keys = []
        new_keys = []

        for key, value in new_params.items():
            if key in old_params:
                if old_params[key] != value:
                    overridden_keys.append(key)
                    logger.warning(
                        f"参数 '{key}' 被覆盖: "
                        f"{old_params[key]} -> {value}"
                    )
            else:
                new_keys.append(key)

            merged[key] = value

        logger.info(
            f"merge 模式：覆盖 {len(overridden_keys)} 个参数, "
            f"新增 {len(new_keys)} 个参数"
        )

        return merged

def acquire_workflow_lock(workflow_id: str, timeout: int = 30) -> Optional[str]:
    """
    获取工作流的分布式锁。

    使用 UUID 作为锁的唯一标识，确保只有锁的持有者才能释放它。
    这是并发安全的关键：避免一个进程误释放另一个进程的锁。

    Args:
        workflow_id: 工作流的唯一标识
        timeout: 锁的自动过期时间（秒），防止死锁

    Returns:
        Optional[str]: 成功时返回唯一的 lock_value（UUID），失败时返回 None
    """
    if not redis_client:
        logger.error("Redis未连接，无法获取锁")
        return None

    lock_key = f"workflow_lock:{workflow_id}"
    lock_value = str(uuid.uuid4())  # 使用 UUID 作为唯一标识

    # 使用 SET NX EX 实现原子性的锁获取
    # NX: 只在键不存在时设置
    # EX: 设置过期时间，防止死锁
    acquired = redis_client.set(
        lock_key,
        lock_value,
        ex=timeout,
        nx=True
    )

    if acquired:
        logger.info(f"成功获取工作流锁: {workflow_id} (lock_value: {lock_value[:8]}...)")
        return lock_value
    else:
        logger.warning(f"无法获取工作流锁（可能正在被修改）: {workflow_id}")
        return None

def release_workflow_lock(workflow_id: str, lock_value: str):
    """
    安全地释放工作流的分布式锁。

    使用 Lua 脚本确保"检查并删除"的原子性，只有锁的持有者才能释放锁。
    这是并发安全的关键：防止进程 A 释放进程 B 持有的锁。

    工作原理：
    1. 原子性地读取锁的当前值
    2. 比较是否与提供的 lock_value 匹配
    3. 仅在匹配时删除锁

    Args:
        workflow_id: 工作流的唯一标识
        lock_value: 获取锁时得到的唯一值（UUID）
    """
    if not redis_client:
        logger.error("Redis未连接，无法释放锁")
        return

    lock_key = f"workflow_lock:{workflow_id}"

    try:
        # 使用 Lua 脚本保证"检查并删除"的原子性
        # 返回值：1 表示删除成功，0 表示锁不存在或值不匹配
        released = redis_client.eval(LUA_RELEASE_SCRIPT, 1, lock_key, lock_value)

        if released:
            logger.info(f"已安全释放工作流锁: {workflow_id} (lock_value: {lock_value[:8]}...)")
        else:
            # 可能的原因：
            # 1. 锁已超时自动过期（正常情况）
            # 2. 锁被其他进程持有（异常情况，需关注）
            logger.warning(
                f"尝试释放锁失败（锁不存在或值不匹配）: {workflow_id}。"
                f"这可能意味着锁已超时或被其他进程持有。"
            )
    except Exception as e:
        logger.error(f"释放锁时发生异常: {e}", exc_info=True)
