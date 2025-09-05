# -*- coding: utf-8 -*-
# utils/config_loader.py
"""
通用配置加载模块
提供统一的配置文件读取功能，避免重复的路径查找逻辑
"""

import os
import yaml
from typing import Dict, Any, Optional


def load_global_config() -> Dict[str, Any]:
    """
    加载全局config.yml配置文件
    
    Returns:
        Dict[str, Any]: 配置字典，如果加载失败返回空字典
    """
    # 定义可能的配置文件路径（按优先级排序）
    possible_paths = [
        # 1. 当前工作目录 (最高优先级)
        "config.yml",
        
        # 2. /app目录 (Docker容器中的标准位置)
        "/app/config.yml",
        
        # 3. 项目根目录的相对路径（从services/workers/paddleocr_service/app向上查找）
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "config.yml"),
        
        # 4. 从当前文件向上查找到项目根目录
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "config.yml"))
    ]
    
    for config_path in possible_paths:
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    # print(f"成功加载配置文件: {config_path}")
                    return config if config else {}
        except Exception as e:
            print(f"尝试加载配置文件 {config_path} 失败: {e}")
            continue
    
    print("警告：未能找到或加载任何配置文件，返回空配置")
    return {}


def get_ocr_lang(default_lang: str = 'ch') -> str:
    """
    获取OCR语言配置
    
    Args:
        default_lang: 默认语言，如果配置中没有则使用此值
        
    Returns:
        str: 语言代码 (如 'ch', 'en')
    """
    try:
        config = load_global_config()
        lang = config.get('ocr', {}).get('lang', default_lang)
        return lang if isinstance(lang, str) else default_lang
    except Exception:
        return default_lang


def get_num_workers(section: str = 'area_detector', default_workers: int = 2) -> int:
    """
    获取工作进程数配置
    
    Args:
        section: 配置段名称 ('area_detector', 'ocr' 等)
        default_workers: 默认进程数
        
    Returns:
        int: 进程数
    """
    try:
        config = load_global_config()
        num_workers = config.get(section, {}).get('num_workers', default_workers)
        return num_workers if isinstance(num_workers, int) and num_workers > 0 else default_workers
    except Exception:
        return default_workers


def get_config_section(section_name: str, default_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    获取指定配置段
    
    Args:
        section_name: 配置段名称
        default_config: 默认配置，如果段不存在则返回此值
        
    Returns:
        Dict[str, Any]: 配置段字典
    """
    try:
        config = load_global_config()
        section_config = config.get(section_name, default_config or {})
        return section_config if isinstance(section_config, dict) else (default_config or {})
    except Exception:
        return default_config or {}