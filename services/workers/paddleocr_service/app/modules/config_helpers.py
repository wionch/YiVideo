# -*- coding: utf-8 -*-
"""
PaddleOCR 专用配置辅助函数
用于解析和获取OCR相关的配置参数
"""
import logging
from typing import Any, Dict

from services.common.config_loader import CONFIG
from services.common.logger import get_logger

logger = get_logger('ocr_config')

def get_ocr_models_config() -> Dict[str, Any]:
    """
    获取OCR模型配置
    
    Returns:
        Dict[str, Any]: 包含检测和识别模型配置的字典
    """
    default_models_config = {
        'detection_model': 'PP-OCRv5_server_det',
        'recognition_models': {
            'zh': 'PP-OCRv5_server_rec',
            'chinese_cht': 'PP-OCRv5_server_rec',
            'en': 'en_PP-OCRv5_mobile_rec',
            'ja': 'PP-OCRv5_server_rec',
            'korean': 'korean_PP-OCRv5_mobile_rec',
            'fr': 'latin_PP-OCRv5_mobile_rec',
            'de': 'latin_PP-OCRv5_mobile_rec',
            'es': 'latin_PP-OCRv5_mobile_rec',
            'it': 'latin_PP-OCRv5_mobile_rec',
            'pt': 'latin_PP-OCRv5_mobile_rec',
            'ru': 'eslav_PP-OCRv5_mobile_rec',
            'th': 'th_PP-OCRv5_mobile_rec',
            'ar': 'ar_PP-OCRv5_mobile_rec',
            'default': 'PP-OCRv5_server_rec'
        },
        'subtitle_optimized': True,
        'use_angle_cls': False,
        'use_space_char': True
    }
    
    try:
        ocr_config = CONFIG.get('ocr', {})
        models_config = ocr_config.get('models', {})
        
        # 合并默认配置和用户配置
        final_config = default_models_config.copy()
        
        # 更新检测模型
        if 'detection_model' in models_config:
            final_config['detection_model'] = models_config['detection_model']
        
        # 更新识别模型
        if 'recognition_models' in models_config:
            final_config['recognition_models'].update(models_config['recognition_models'])
            
        # 更新优化设置
        for key in ['subtitle_optimized', 'use_angle_cls', 'use_space_char']:
            if key in models_config:
                final_config[key] = models_config[key]
        
        return final_config
        
    except Exception as e:
        logger.warning(f"加载OCR模型配置失败，使用默认配置: {e}")
        return default_models_config


def get_recognition_model_for_lang(lang: str) -> str:
    """
    根据语言获取最佳的识别模型
    
    Args:
        lang: 语言代码 (如 'zh', 'en')
        
    Returns:
        str: 对应的识别模型名称
    """
    models_config = get_ocr_models_config()
    recognition_models = models_config.get('recognition_models', {})
    
    # 语言代码标准化映射
    lang_mapping = {
        'ch': 'zh',           # PaddleOCR的ch映射到标准的zh
        'chinese': 'zh',
        'china': 'zh',
        'english': 'en',
        'japan': 'ja',
        'japanese': 'ja',
        'france': 'fr',
        'french': 'fr',
        'germany': 'de',
        'german': 'de',
        'spain': 'es',
        'spanish': 'es',
        'italy': 'it',
        'italian': 'it',
        'portugal': 'pt',
        'portuguese': 'pt',
        'russia': 'ru',
        'russian': 'ru',
        'thailand': 'th',
        'thai': 'th',
        'arabic': 'ar',
    }
    
    # 标准化语言代码
    normalized_lang = lang_mapping.get(lang.lower(), lang.lower())
    
    # 获取对应的模型，如果没找到则使用默认模型
    model_name = recognition_models.get(normalized_lang)
    if not model_name:
        model_name = recognition_models.get('default', 'PP-OCRv5_server_rec')
    
    return model_name


def get_detection_model() -> str:
    """
    获取文本检测模型
    
    Returns:
        str: 检测模型名称
    """
    models_config = get_ocr_models_config()
    return models_config.get('detection_model', 'PP-OCRv5_server_det')
