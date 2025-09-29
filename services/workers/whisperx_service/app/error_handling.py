#!/usr/bin/env python3
"""
增强的错误处理和重试机制
提供全面的错误分类、处理和重试策略
"""

import time
import logging
import traceback
from enum import Enum
from typing import Dict, Any, Optional, Callable, Type, Union, List
from dataclasses import dataclass, field
from functools import wraps
from contextlib import contextmanager
import threading

from services.common.logger import get_logger

logger = get_logger('error_handling')

class ErrorType(str, Enum):
    """错误类型枚举"""
    # 系统错误
    SYSTEM_ERROR = "system_error"
    MEMORY_ERROR = "memory_error"
    DISK_ERROR = "disk_error"
    NETWORK_ERROR = "network_error"

    # 模型错误
    MODEL_ERROR = "model_error"
    MODEL_LOAD_ERROR = "model_load_error"
    MODEL_INFERENCE_ERROR = "model_inference_error"

    # 配置错误
    CONFIG_ERROR = "config_error"
    CONFIG_VALIDATION_ERROR = "config_validation_error"

    # 任务错误
    TASK_ERROR = "task_error"
    TASK_TIMEOUT_ERROR = "task_timeout_error"
    TASK_CANCELLED_ERROR = "task_cancelled_error"

    # 外部服务错误
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    REDIS_ERROR = "redis_error"
    GPU_ERROR = "gpu_error"

    # 数据错误
    DATA_ERROR = "data_error"
    FILE_NOT_FOUND_ERROR = "file_not_found_error"
    INVALID_FORMAT_ERROR = "invalid_format_error"

class ErrorSeverity(str, Enum):
    """错误严重程度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class RetryStrategy(str, Enum):
    """重试策略"""
    FIXED = "fixed"          # 固定间隔
    EXPONENTIAL = "exponential"  # 指数退避
    LINEAR = "linear"        # 线性增加
    FIBONACCI = "fibonacci"  # 斐波那契数列

@dataclass
class ErrorContext:
    """错误上下文信息"""
    error_type: ErrorType
    severity: ErrorSeverity
    message: str
    exception: Optional[Exception] = None
    traceback: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    context: Dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    operation: Optional[str] = None

@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    backoff_factor: float = 2.0
    jitter: bool = True
    retryable_exceptions: List[Type[Exception]] = field(default_factory=lambda: [
        Exception  # 默认重试所有异常
    ])
    non_retryable_exceptions: List[Type[Exception]] = field(default_factory=list)

class ErrorHandler:
    """错误处理器"""

    def __init__(self):
        self._error_history: List[ErrorContext] = []
        self._lock = threading.Lock()
        self._error_callbacks: Dict[ErrorType, List[Callable]] = {}

    def register_error_callback(self, error_type: ErrorType, callback: Callable):
        """注册错误回调函数"""
        if error_type not in self._error_callbacks:
            self._error_callbacks[error_type] = []
        self._error_callbacks[error_type].append(callback)

    def handle_error(self, error_context: ErrorContext) -> Dict[str, Any]:
        """处理错误"""
        with self._lock:
            # 记录错误历史
            self._error_history.append(error_context)

            # 保持最近1000个错误
            if len(self._error_history) > 1000:
                self._error_history = self._error_history[-1000:]

        # 记录错误日志
        self._log_error(error_context)

        # 调用错误回调
        self._call_error_callbacks(error_context)

        # 返回错误处理结果
        return {
            'handled': True,
            'error_type': error_context.error_type.value,
            'severity': error_context.severity.value,
            'message': error_context.message,
            'timestamp': error_context.timestamp
        }

    def _log_error(self, error_context: ErrorContext):
        """记录错误日志"""
        log_method = {
            ErrorSeverity.LOW: logger.info,
            ErrorSeverity.MEDIUM: logger.warning,
            ErrorSeverity.HIGH: logger.error,
            ErrorSeverity.CRITICAL: logger.critical
        }.get(error_context.severity, logger.error)

        log_msg = f"[{error_context.error_type.value}] {error_context.message}"

        if error_context.operation:
            log_msg += f" (operation: {error_context.operation})"

        if error_context.retry_count > 0:
            log_msg += f" (retry: {error_context.retry_count})"

        if error_context.context:
            log_msg += f" (context: {error_context.context})"

        log_method(log_msg)

        if error_context.traceback:
            logger.debug(f"错误详情:\n{error_context.traceback}")

    def _call_error_callbacks(self, error_context: ErrorContext):
        """调用错误回调函数"""
        callbacks = self._error_callbacks.get(error_context.error_type, [])
        for callback in callbacks:
            try:
                callback(error_context)
            except Exception as e:
                logger.error(f"错误回调函数执行失败: {e}")

    def classify_error(self, exception: Exception, operation: str = None) -> ErrorContext:
        """分类错误"""
        error_type = self._determine_error_type(exception)
        severity = self._determine_severity(error_type, exception)

        return ErrorContext(
            error_type=error_type,
            severity=severity,
            message=str(exception),
            exception=exception,
            traceback=traceback.format_exc(),
            operation=operation
        )

    def _determine_error_type(self, exception: Exception) -> ErrorType:
        """确定错误类型"""
        exc_type = type(exception)

        # 内存错误
        if any(name in str(exc_type).lower() for name in ['memory', 'cuda', 'gpu']):
            return ErrorType.MEMORY_ERROR

        # 文件错误
        if any(name in str(exc_type).lower() for name in ['file', 'io', 'os']):
            if 'not found' in str(exception).lower():
                return ErrorType.FILE_NOT_FOUND_ERROR
            return ErrorType.DISK_ERROR

        # 网络错误
        if any(name in str(exc_type).lower() for name in ['connection', 'network', 'timeout']):
            return ErrorType.NETWORK_ERROR

        # 模型错误
        if any(name in str(exc_type).lower() for name in ['model', 'whisper', 'transcribe']):
            if 'load' in str(exception).lower():
                return ErrorType.MODEL_LOAD_ERROR
            return ErrorType.MODEL_INFERENCE_ERROR

        # 配置错误
        if any(name in str(exc_type).lower() for name in ['config', 'validation', 'value']):
            return ErrorType.CONFIG_ERROR

        # 外部服务错误
        if any(name in str(exc_type).lower() for name in ['redis', 'celery']):
            return ErrorType.REDIS_ERROR

        # 默认为系统错误
        return ErrorType.SYSTEM_ERROR

    def _determine_severity(self, error_type: ErrorType, exception: Exception) -> ErrorSeverity:
        """确定错误严重程度"""
        critical_errors = [
            ErrorType.MEMORY_ERROR,
            ErrorType.MODEL_LOAD_ERROR,
            ErrorType.SYSTEM_ERROR
        ]

        high_errors = [
            ErrorType.MODEL_INFERENCE_ERROR,
            ErrorType.DISK_ERROR,
            ErrorType.CONFIG_ERROR
        ]

        if error_type in critical_errors:
            return ErrorSeverity.CRITICAL
        elif error_type in high_errors:
            return ErrorSeverity.HIGH
        elif 'timeout' in str(exception).lower():
            return ErrorSeverity.HIGH
        else:
            return ErrorSeverity.MEDIUM

    def get_error_statistics(self) -> Dict[str, Any]:
        """获取错误统计信息"""
        with self._lock:
            if not self._error_history:
                return {'total_errors': 0}

            error_types = {}
            severity_counts = {}
            recent_errors = []

            for error in self._error_history[-100:]:  # 最近100个错误
                error_types[error.error_type.value] = error_types.get(error.error_type.value, 0) + 1
                severity_counts[error.severity.value] = severity_counts.get(error.severity.value, 0) + 1

                if time.time() - error.timestamp < 3600:  # 1小时内的错误
                    recent_errors.append(error)

            return {
                'total_errors': len(self._error_history),
                'error_types': error_types,
                'severity_counts': severity_counts,
                'recent_errors_1h': len(recent_errors),
                'error_rate_1h': len(recent_errors) / max(1, (time.time() - recent_errors[0].timestamp) / 3600) if recent_errors else 0
            }

class RetryManager:
    """重试管理器"""

    def __init__(self, config: RetryConfig = None):
        self.config = config or RetryConfig()
        self.error_handler = ErrorHandler()

    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """判断是否应该重试"""
        if attempt >= self.config.max_attempts:
            return False

        # 检查是否为不可重试的异常
        for exc_type in self.config.non_retryable_exceptions:
            if isinstance(exception, exc_type):
                return False

        # 检查是否为可重试的异常
        for exc_type in self.config.retryable_exceptions:
            if isinstance(exception, exc_type):
                return True

        # 默认行为
        return True

    def calculate_delay(self, attempt: int) -> float:
        """计算重试延迟"""
        if self.config.strategy == RetryStrategy.FIXED:
            delay = self.config.base_delay
        elif self.config.strategy == RetryStrategy.LINEAR:
            delay = self.config.base_delay * (attempt + 1)
        elif self.config.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.config.base_delay * (self.config.backoff_factor ** attempt)
        elif self.config.strategy == RetryStrategy.FIBONACCI:
            delay = self.config.base_delay * self._fibonacci(attempt + 1)
        else:
            delay = self.config.base_delay

        # 限制最大延迟
        delay = min(delay, self.config.max_delay)

        # 添加抖动
        if self.config.jitter:
            delay *= (0.5 + 0.5 * time.time() % 1)

        return delay

    def _fibonacci(self, n: int) -> int:
        """斐波那契数列"""
        if n <= 1:
            return 1
        a, b = 1, 1
        for _ in range(2, n):
            a, b = b, a + b
        return b

    def retry_with_context(self, func: Callable, *args, **kwargs) -> Any:
        """带上下文的重试执行"""
        last_exception = None
        attempt = 0

        while attempt < self.config.max_attempts:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e

                # 分类错误
                error_context = self.error_handler.classify_error(e, func.__name__)
                error_context.retry_count = attempt

                # 处理错误
                self.error_handler.handle_error(error_context)

                # 判断是否重试
                if not self.should_retry(e, attempt):
                    break

                # 计算延迟
                delay = self.calculate_delay(attempt)
                logger.info(f"重试 {func.__name__} (尝试 {attempt + 1}/{self.config.max_attempts})，延迟 {delay:.2f}s")

                # 等待重试
                time.sleep(delay)
                attempt += 1

        # 所有重试都失败
        if last_exception:
            raise last_exception

    def retry_async_with_context(self, func: Callable, *args, **kwargs) -> Any:
        """异步重试执行"""
        # 这里可以实现异步重试逻辑
        return self.retry_with_context(func, *args, **kwargs)

# 全局实例
error_handler = ErrorHandler()
retry_manager = RetryManager()

def with_retry(
    max_attempts: int = None,
    base_delay: float = None,
    strategy: RetryStrategy = None,
    retryable_exceptions: List[Type[Exception]] = None,
    non_retryable_exceptions: List[Type[Exception]] = None
):
    """重试装饰器"""
    config = RetryConfig()
    if max_attempts is not None:
        config.max_attempts = max_attempts
    if base_delay is not None:
        config.base_delay = base_delay
    if strategy is not None:
        config.strategy = strategy
    if retryable_exceptions is not None:
        config.retryable_exceptions = retryable_exceptions
    if non_retryable_exceptions is not None:
        config.non_retryable_exceptions = non_retryable_exceptions

    manager = RetryManager(config)

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return manager.retry_with_context(func, *args, **kwargs)
        return wrapper
    return decorator

def handle_errors(error_type: ErrorType = None, severity: ErrorSeverity = None):
    """错误处理装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # 分类错误
                error_context = error_handler.classify_error(e, func.__name__)

                # 覆盖错误类型和严重程度
                if error_type:
                    error_context.error_type = error_type
                if severity:
                    error_context.severity = severity

                # 处理错误
                error_handler.handle_error(error_context)
                raise
        return wrapper
    return decorator

@contextmanager
def error_context(operation: str = None, context: Dict[str, Any] = None):
    """错误上下文管理器"""
    error_ctx = None
    try:
        yield
    except Exception as e:
        error_ctx = error_handler.classify_error(e, operation)
        if context:
            error_ctx.context.update(context)
        error_handler.handle_error(error_ctx)
        raise

def get_error_statistics() -> Dict[str, Any]:
    """获取错误统计信息"""
    return error_handler.get_error_statistics()

def register_error_callback(error_type: ErrorType, callback: Callable):
    """注册错误回调函数"""
    error_handler.register_error_callback(error_type, callback)

# 示例错误回调函数
def log_error_to_database(error_context: ErrorContext):
    """将错误记录到数据库"""
    logger.info(f"记录错误到数据库: {error_context.error_type} - {error_context.message}")

def send_error_notification(error_context: ErrorContext):
    """发送错误通知"""
    if error_context.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
        logger.error(f"发送严重错误通知: {error_context.message}")

# 注册默认回调
register_error_callback(ErrorType.CRITICAL, send_error_notification)

if __name__ == "__main__":
    # 测试错误处理
    @with_retry(max_attempts=3, base_delay=1.0)
    def test_function():
        import random
        if random.random() < 0.7:
            raise Exception("随机错误")
        return "成功"

    try:
        result = test_function()
        print(f"结果: {result}")
    except Exception as e:
        print(f"最终失败: {e}")

    # 查看错误统计
    stats = get_error_statistics()
    print(f"错误统计: {stats}")