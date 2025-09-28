# services/common/config_loader.py
# -*- coding: utf-8 -*-

"""
通用的配置文件加载器。

提供一个单例模式的函数，用于加载项目根目录下的 `config.yml` 文件，
并缓存结果，以便所有服务都能高效、一致地访问配置。
"""

import os

from services.common.logger import get_logger

logger = get_logger('config_loader')
import logging
from typing import Any
from typing import Dict

import yaml

# --- 全局缓存 ---
_config_cache: Dict[str, Any] = None

# --- 日志配置 ---
# 日志已统一管理，使用 services.common.logger

def get_config() -> Dict[str, Any]:
    """
    加载并返回全局配置字典。

    第一次调用时，它会查找并解析 config.yml 文件，然后将结果缓存起来。
    后续调用将直接返回缓存的配置，避免重复的文件I/O。

    Returns:
        Dict[str, Any]: 包含所有配置的字典。
    """
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    config_path = ""
    try:
        # 配置文件位于项目根目录，此文件位于 services/common/ 下
        # 因此需要向上回溯两级目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, '..', '..', 'config.yml')
        
        with open(config_path, 'r', encoding='utf-8') as f:
            _config_cache = yaml.safe_load(f)
        
        if _config_cache:
            logger.info(f"通用配置加载器: {config_path} 加载成功。")
            return _config_cache
        else:
            logger.error(f"通用配置加载器: {config_path} 文件为空或格式错误。")
            _config_cache = {}
            return _config_cache

    except FileNotFoundError:
        logger.error(f"通用配置加载器: 无法在路径 '{config_path}' 找到 config.yml 文件。")
        _config_cache = {}
        return _config_cache
    except Exception as e:
        logger.error(f"通用配置加载器: 加载 config.yml 时发生未知错误: {e}")
        _config_cache = {}
        return _config_cache

def get_cleanup_temp_files_config() -> bool:
    """
    获取临时文件清理配置。

    注意：为了支持实时配置变更，此函数每次都会重新读取配置文件，
    不使用全局缓存机制。

    Returns:
        bool: True表示需要清理临时文件，False表示保留临时文件。默认为True。
    """
    try:
        # 每次都重新读取配置文件，确保获取最新配置
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, '..', '..', 'config.yml')

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        if not config:
            logger.warning("配置文件为空，使用默认值 cleanup_temp_files=True")
            return True

        core_config = config.get('core', {})
        cleanup_config = core_config.get('cleanup_temp_files', True)  # 默认为True

        logger.info(f"实时读取配置 cleanup_temp_files: {cleanup_config}")

        # 确保返回的是boolean类型
        if isinstance(cleanup_config, bool):
            return cleanup_config
        elif isinstance(cleanup_config, str):
            return cleanup_config.lower() in ('true', '1', 'yes', 'on')
        else:
            logger.warning(f"cleanup_temp_files 配置值 '{cleanup_config}' 格式不正确，使用默认值 True")
            return True

    except FileNotFoundError:
        logger.error("配置文件未找到，使用默认值 cleanup_temp_files=True")
        return True
    except Exception as e:
        logger.error(f"读取配置文件时出错: {e}，使用默认值 cleanup_temp_files=True")
        return True


def get_gpu_lock_config() -> Dict[str, Any]:
    """
    获取GPU锁配置参数。

    注意：为了支持实时配置变更，此函数每次都会重新读取配置文件，
    不使用全局缓存机制。这样可以支持运行时动态调整GPU锁参数。

    Returns:
        Dict[str, Any]: 包含GPU锁配置的字典，包含以下键：
            - poll_interval: 轮询间隔（秒）
            - max_wait_time: 最大等待时间（秒）
            - lock_timeout: 锁超时时间（秒）
            - exponential_backoff: 是否启用指数退避
            - max_poll_interval: 最大轮询间隔（秒）
            - use_event_driven: 是否启用事件驱动机制（Redis Pub/Sub）
            - fallback_timeout: 事件驱动回退超时时间（秒）
    """
    try:
        # 每次都重新读取配置文件，确保获取最新配置
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, '..', '..', 'config.yml')

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        if not config:
            logger.warning("配置文件为空，使用默认GPU锁配置")
            return _get_default_gpu_lock_config()

        gpu_lock_config = config.get('gpu_lock', {})

        # 使用默认值填充缺失的配置项
        default_config = _get_default_gpu_lock_config()
        final_config = default_config.copy()
        final_config.update(gpu_lock_config)

        logger.info(f"实时读取GPU锁配置: {final_config}")

        # 验证配置值的合法性
        return _validate_gpu_lock_config(final_config)

    except FileNotFoundError:
        logger.error("配置文件未找到，使用默认GPU锁配置")
        return _get_default_gpu_lock_config()
    except Exception as e:
        logger.error(f"读取GPU锁配置时出错: {e}，使用默认配置")
        return _get_default_gpu_lock_config()


def _get_default_gpu_lock_config() -> Dict[str, Any]:
    """
    获取默认的GPU锁配置。

    优化后的配置参数，更适合生产环境使用：
    - 减少等待时间，提高响应性
    - 保持合理的锁超时时间
    - 启用智能退避机制
    - 支持事件驱动机制，显著提高响应速度

    Returns:
        Dict[str, Any]: 默认GPU锁配置
    """
    return {
        'poll_interval': 0.5,          # 轮询间隔（秒）- 快速响应
        'max_wait_time': 300,          # 最大等待时间（秒）- 5分钟
        'lock_timeout': 600,           # 锁超时时间（秒）- 10分钟
        'exponential_backoff': True,   # 启用指数退避
        'max_poll_interval': 5,        # 最大轮询间隔（秒）- 避免过长等待
        'use_event_driven': True,      # 启用事件驱动机制（Redis Pub/Sub）
        'fallback_timeout': 30         # 事件驱动回退超时时间（秒）
    }


def get_gpu_lock_monitor_config() -> Dict[str, Any]:
    """
    获取GPU锁监控配置参数。

    Returns:
        Dict[str, Any]: 包含GPU锁监控配置的字典
    """
    try:
        # 每次都重新读取配置文件，确保获取最新配置
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, '..', '..', 'config.yml')

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        if not config:
            logger.warning("配置文件为空，使用默认GPU锁监控配置")
            return _get_default_gpu_lock_monitor_config()

        monitor_config = config.get('gpu_lock_monitor', {})

        # 使用默认值填充缺失的配置项
        default_config = _get_default_gpu_lock_monitor_config()
        for key, value in default_config.items():
            if key not in monitor_config:
                monitor_config[key] = value

        # 验证配置的合法性
        validated_config = _validate_gpu_lock_monitor_config(monitor_config)
        return validated_config

    except Exception as e:
        logger.error(f"读取GPU锁监控配置失败: {e}，使用默认配置")
        return _get_default_gpu_lock_monitor_config()


def _get_default_gpu_lock_monitor_config() -> Dict[str, Any]:
    """
    获取默认的GPU锁监控配置。

    Returns:
        Dict[str, Any]: 默认GPU锁监控配置
    """
    return {
        'monitor_interval': 30,
        'timeout_levels': {
            'warning': 1800,
            'soft_timeout': 3600,
            'hard_timeout': 7200
        },
        'heartbeat': {
            'interval': 60,
            'timeout': 300
        },
        'cleanup': {
            'max_retry': 3,
            'retry_delay': 60
        },
        'enabled': True,
        'auto_recovery': True,
        'health_thresholds': {
            'min_success_rate': 0.8,
            'max_timeout_rate': 0.2,
            'max_lock_age': 3600,
            'recent_window_size': 20
        }
    }


def _validate_gpu_lock_monitor_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    验证GPU锁监控配置的合法性。

    Args:
        config: 原始配置

    Returns:
        Dict[str, Any]: 验证后的配置
    """
    validated_config = config.copy()

    # 验证监控间隔
    if 'monitor_interval' in validated_config:
        validated_config['monitor_interval'] = max(10, min(300, validated_config['monitor_interval']))

    # 验证超时级别
    if 'timeout_levels' in validated_config:
        levels = validated_config['timeout_levels']
        if 'warning' in levels:
            levels['warning'] = max(60, min(7200, levels['warning']))
        if 'soft_timeout' in levels:
            levels['soft_timeout'] = max(levels.get('warning', 1800), min(7200, levels['soft_timeout']))
        if 'hard_timeout' in levels:
            levels['hard_timeout'] = max(levels.get('soft_timeout', 3600), min(14400, levels['hard_timeout']))

    # 验证心跳配置
    if 'heartbeat' in validated_config:
        heartbeat = validated_config['heartbeat']
        if 'interval' in heartbeat:
            heartbeat['interval'] = max(10, min(300, heartbeat['interval']))
        if 'timeout' in heartbeat:
            heartbeat['timeout'] = max(heartbeat.get('interval', 60), min(600, heartbeat['timeout']))

    # 验证健康阈值
    if 'health_thresholds' in validated_config:
        thresholds = validated_config['health_thresholds']
        if 'min_success_rate' in thresholds:
            thresholds['min_success_rate'] = max(0.0, min(1.0, thresholds['min_success_rate']))
        if 'max_timeout_rate' in thresholds:
            thresholds['max_timeout_rate'] = max(0.0, min(1.0, thresholds['max_timeout_rate']))

    return validated_config


def _validate_gpu_lock_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    验证GPU锁配置的合法性。

    Args:
        config: 待验证的配置字典

    Returns:
        Dict[str, Any]: 验证后的配置字典
    """
    validated_config = config.copy()

    # 验证轮询间隔
    if 'poll_interval' in validated_config:
        poll_interval = validated_config['poll_interval']
        if not isinstance(poll_interval, (int, float)) or poll_interval <= 0:
            logger.warning(f"poll_interval 值 '{poll_interval}' 不合法，使用默认值 1")
            validated_config['poll_interval'] = 1

    # 验证最大等待时间
    if 'max_wait_time' in validated_config:
        max_wait_time = validated_config['max_wait_time']
        if not isinstance(max_wait_time, (int, float)) or max_wait_time <= 0:
            logger.warning(f"max_wait_time 值 '{max_wait_time}' 不合法，使用默认值 6000")
            validated_config['max_wait_time'] = 6000

    # 验证锁超时时间
    if 'lock_timeout' in validated_config:
        lock_timeout = validated_config['lock_timeout']
        if not isinstance(lock_timeout, (int, float)) or lock_timeout <= 0:
            logger.warning(f"lock_timeout 值 '{lock_timeout}' 不合法，使用默认值 9000")
            validated_config['lock_timeout'] = 9000

    # 验证指数退避
    if 'exponential_backoff' in validated_config:
        exponential_backoff = validated_config['exponential_backoff']
        if not isinstance(exponential_backoff, bool):
            logger.warning(f"exponential_backoff 值 '{exponential_backoff}' 不合法，使用默认值 True")
            validated_config['exponential_backoff'] = True

    # 验证最大轮询间隔
    if 'max_poll_interval' in validated_config:
        max_poll_interval = validated_config['max_poll_interval']
        if not isinstance(max_poll_interval, (int, float)) or max_poll_interval <= 0:
            logger.warning(f"max_poll_interval 值 '{max_poll_interval}' 不合法，使用默认值 10")
            validated_config['max_poll_interval'] = 10

    # 验证事件驱动机制
    if 'use_event_driven' in validated_config:
        use_event_driven = validated_config['use_event_driven']
        if not isinstance(use_event_driven, bool):
            logger.warning(f"use_event_driven 值 '{use_event_driven}' 不合法，使用默认值 True")
            validated_config['use_event_driven'] = True

    # 验证回退超时时间
    if 'fallback_timeout' in validated_config:
        fallback_timeout = validated_config['fallback_timeout']
        if not isinstance(fallback_timeout, (int, float)) or fallback_timeout <= 0:
            logger.warning(f"fallback_timeout 值 '{fallback_timeout}' 不合法，使用默认值 30")
            validated_config['fallback_timeout'] = 30

    return validated_config

# 在模块加载时执行一次，以便尽早发现配置问题
CONFIG = get_config()