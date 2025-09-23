# services/common/config_loader.py
# -*- coding: utf-8 -*-

"""
通用的配置文件加载器。

提供一个单例模式的函数，用于加载项目根目录下的 `config.yml` 文件，
并缓存结果，以便所有服务都能高效、一致地访问配置。
"""

import os
import yaml
import logging
from typing import Dict, Any

# --- 全局缓存 ---
_config_cache: Dict[str, Any] = None

# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
            logging.info(f"通用配置加载器: {config_path} 加载成功。")
            return _config_cache
        else:
            logging.error(f"通用配置加载器: {config_path} 文件为空或格式错误。")
            _config_cache = {}
            return _config_cache

    except FileNotFoundError:
        logging.error(f"通用配置加载器: 无法在路径 '{config_path}' 找到 config.yml 文件。")
        _config_cache = {}
        return _config_cache
    except Exception as e:
        logging.error(f"通用配置加载器: 加载 config.yml 时发生未知错误: {e}")
        _config_cache = {}
        return _config_cache

# 在模块加载时执行一次，以便尽早发现配置问题
CONFIG = get_config()