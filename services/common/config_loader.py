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

# 在模块加载时执行一次，以便尽早发现配置问题
CONFIG = get_config()