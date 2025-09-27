# services/common/logger.py
"""
统一日志管理器 - 单例模式
解决重复的logging.basicConfig()调用问题
"""

import logging
import logging.handlers
import os
from typing import Optional


class UnifiedLogger:
    """统一日志管理器 - 单例模式"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not UnifiedLogger._initialized:
            self._setup_logging()
            UnifiedLogger._initialized = True

    def _setup_logging(self):
        """设置日志系统"""
        # 创建格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # 获取根logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        # 清除现有处理器（避免重复）
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        # 文件处理器（可选）
        log_dir = 'logs'
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        file_handler = logging.handlers.RotatingFileHandler(
            f'{log_dir}/yivideo.log',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    def get_logger(self, name: str) -> logging.Logger:
        """获取指定名称的logger"""
        return logging.getLogger(name)

    def set_level(self, level: str):
        """设置日志级别"""
        logging.getLogger().setLevel(getattr(logging, level.upper()))


# 全局实例
_logger_instance = UnifiedLogger()


def get_logger(name: str = __name__) -> logging.Logger:
    """获取logger的便捷函数"""
    return _logger_instance.get_logger(name)


def set_logging_level(level: str):
    """设置日志级别的便捷函数"""
    _logger_instance.set_level(level)