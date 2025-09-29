#!/usr/bin/env python3
"""
完善的性能监控和指标收集系统
提供全面的性能指标收集、分析和报告功能
"""

import time
import threading
import psutil
import gc
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque
import json
import logging

from services.common.logger import get_logger

logger = get_logger('performance_monitoring')

@dataclass
class PerformanceMetrics:
    """性能指标数据类"""
    timestamp: float
    operation: str
    duration: float
    memory_usage_mb: float
    cpu_usage_percent: float
    gpu_memory_usage_mb: Optional[float] = None
    gpu_utilization_percent: Optional[float] = None
    batch_size: Optional[int] = None
    audio_duration: Optional[float] = None
    success: bool = True
    error_message: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PerformanceSummary:
    """性能摘要数据类"""
    operation: str
    total_operations: int
    successful_operations: int
    failed_operations: int
    average_duration: float
    min_duration: float
    max_duration: float
    p95_duration: float
    p99_duration: float
    average_memory_usage: float
    peak_memory_usage: float
    average_cpu_usage: float
    success_rate: float
    throughput_per_minute: float
    last_updated: float

class PerformanceMonitor:
    """性能监控器"""

    def __init__(self, max_history_size: int = 10000):
        self.max_history_size = max_history_size
        self.metrics_history: deque = deque(maxlen=max_history_size)
        self.operation_summaries: Dict[str, PerformanceSummary] = {}
        self.current_operations: Dict[str, List[PerformanceMetrics]] = defaultdict(list)
        self.lock = threading.RLock()
        self._gpu_available = self._check_gpu_availability()
        self._monitoring_enabled = True

    def _check_gpu_availability(self) -> bool:
        """检查GPU是否可用"""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def _get_gpu_metrics(self) -> Dict[str, float]:
        """获取GPU指标"""
        if not self._gpu_available:
            return {}

        try:
            import torch
            if torch.cuda.is_available():
                current_device = torch.cuda.current_device()
                gpu_memory_allocated = torch.cuda.memory_allocated(current_device) / 1024 / 1024  # MB
                gpu_memory_cached = torch.cuda.memory_reserved(current_device) / 1024 / 1024  # MB

                return {
                    'gpu_memory_usage_mb': gpu_memory_allocated,
                    'gpu_memory_cached_mb': gpu_memory_cached
                }
        except Exception as e:
            logger.debug(f"获取GPU指标失败: {e}")

        return {}

    def _get_system_metrics(self) -> Dict[str, float]:
        """获取系统指标"""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            cpu_percent = process.cpu_percent(interval=0.1)

            return {
                'memory_usage_mb': memory_info.rss / 1024 / 1024,
                'cpu_usage_percent': cpu_percent
            }
        except Exception as e:
            logger.debug(f"获取系统指标失败: {e}")
            return {
                'memory_usage_mb': 0,
                'cpu_usage_percent': 0
            }

    def start_operation(self, operation: str, context: Dict[str, Any] = None) -> str:
        """开始监控操作"""
        if not self._monitoring_enabled:
            return None

        operation_id = f"{operation}_{int(time.time() * 1000000)}"
        start_time = time.time()

        with self.lock:
            self.current_operations[operation_id] = {
                'operation': operation,
                'start_time': start_time,
                'context': context or {}
            }

        return operation_id

    def end_operation(self, operation_id: str, success: bool = True,
                    error_message: str = None, **kwargs) -> Optional[PerformanceMetrics]:
        """结束监控操作"""
        if not self._monitoring_enabled or operation_id not in self.current_operations:
            return None

        end_time = time.time()
        operation_info = self.current_operations.pop(operation_id)

        # 获取性能指标
        system_metrics = self._get_system_metrics()
        gpu_metrics = self._get_gpu_metrics()

        # 创建性能指标
        metrics = PerformanceMetrics(
            timestamp=end_time,
            operation=operation_info['operation'],
            duration=end_time - operation_info['start_time'],
            memory_usage_mb=system_metrics.get('memory_usage_mb', 0),
            cpu_usage_percent=system_metrics.get('cpu_usage_percent', 0),
            gpu_memory_usage_mb=gpu_metrics.get('gpu_memory_usage_mb'),
            batch_size=kwargs.get('batch_size'),
            audio_duration=kwargs.get('audio_duration'),
            success=success,
            error_message=error_message,
            context=operation_info['context']
        )

        # 记录指标
        with self.lock:
            self.metrics_history.append(metrics)
            self._update_operation_summary(metrics)

        return metrics

    def _update_operation_summary(self, metrics: PerformanceMetrics):
        """更新操作摘要"""
        operation = metrics.operation

        if operation not in self.operation_summaries:
            self.operation_summaries[operation] = PerformanceSummary(
                operation=operation,
                total_operations=0,
                successful_operations=0,
                failed_operations=0,
                average_duration=0,
                min_duration=float('inf'),
                max_duration=0,
                p95_duration=0,
                p99_duration=0,
                average_memory_usage=0,
                peak_memory_usage=0,
                average_cpu_usage=0,
                success_rate=0,
                throughput_per_minute=0,
                last_updated=time.time()
            )

        summary = self.operation_summaries[operation]

        # 更新基本统计
        summary.total_operations += 1
        if metrics.success:
            summary.successful_operations += 1
        else:
            summary.failed_operations += 1

        # 更新持续时间统计
        durations = [m.duration for m in self.metrics_history if m.operation == operation]
        if durations:
            summary.average_duration = sum(durations) / len(durations)
            summary.min_duration = min(durations)
            summary.max_duration = max(durations)

            # 计算百分位数
            sorted_durations = sorted(durations)
            if len(sorted_durations) >= 20:
                summary.p95_duration = sorted_durations[int(len(sorted_durations) * 0.95)]
                summary.p99_duration = sorted_durations[int(len(sorted_durations) * 0.99)]

        # 更新内存统计
        memory_usages = [m.memory_usage_mb for m in self.metrics_history if m.operation == operation]
        if memory_usages:
            summary.average_memory_usage = sum(memory_usages) / len(memory_usages)
            summary.peak_memory_usage = max(memory_usages)

        # 更新CPU统计
        cpu_usages = [m.cpu_usage_percent for m in self.metrics_history if m.operation == operation]
        if cpu_usages:
            summary.average_cpu_usage = sum(cpu_usages) / len(cpu_usages)

        # 更新成功率
        summary.success_rate = (summary.successful_operations / summary.total_operations) * 100

        # 计算吞吐量
        recent_operations = [m for m in self.metrics_history if m.operation == operation and
                            m.timestamp > time.time() - 60]  # 最近1分钟
        summary.throughput_per_minute = len(recent_operations)

        summary.last_updated = time.time()

    def get_operation_summary(self, operation: str) -> Optional[PerformanceSummary]:
        """获取操作摘要"""
        with self.lock:
            return self.operation_summaries.get(operation)

    def get_all_summaries(self) -> Dict[str, PerformanceSummary]:
        """获取所有操作摘要"""
        with self.lock:
            return self.operation_summaries.copy()

    def get_recent_metrics(self, operation: str = None,
                          minutes: int = 60) -> List[PerformanceMetrics]:
        """获取最近的性能指标"""
        cutoff_time = time.time() - (minutes * 60)

        with self.lock:
            if operation:
                return [m for m in self.metrics_history
                       if m.operation == operation and m.timestamp > cutoff_time]
            else:
                return [m for m in self.metrics_history if m.timestamp > cutoff_time]

    def get_performance_insights(self, operation: str = None) -> Dict[str, Any]:
        """获取性能洞察"""
        insights = {
            'overall_health': 'good',
            'recommendations': [],
            'warnings': [],
            'critical_issues': []
        }

        summaries = self.get_all_summaries()
        if operation:
            summaries = {k: v for k, v in summaries.items() if k == operation}

        for op_name, summary in summaries.items():
            # 检查成功率
            if summary.success_rate < 90:
                insights['warnings'].append(f"{op_name}: 成功率较低 ({summary.success_rate:.1f}%)")
            if summary.success_rate < 70:
                insights['critical_issues'].append(f"{op_name}: 成功率严重过低 ({summary.success_rate:.1f}%)")
                insights['overall_health'] = 'poor'

            # 检查性能
            if summary.average_duration > 300:  # 5分钟
                insights['warnings'].append(f"{op_name}: 平均处理时间过长 ({summary.average_duration:.1f}s)")
            if summary.p99_duration > 600:  # 10分钟
                insights['critical_issues'].append(f"{op_name}: P99处理时间过长 ({summary.p99_duration:.1f}s)")
                insights['overall_health'] = 'poor'

            # 检查内存使用
            if summary.peak_memory_usage > 8000:  # 8GB
                insights['warnings'].append(f"{op_name}: 内存使用过高 ({summary.peak_memory_usage:.1f}MB)")
            if summary.peak_memory_usage > 16000:  # 16GB
                insights['critical_issues'].append(f"{op_name}: 内存使用严重过高 ({summary.peak_memory_usage:.1f}MB)")
                insights['overall_health'] = 'poor'

            # 检查吞吐量
            if summary.throughput_per_minute < 1 and summary.total_operations > 10:
                insights['recommendations'].append(f"{op_name}: 吞吐量较低，考虑优化处理流程")

        # 生成优化建议
        if insights['overall_health'] == 'good':
            insights['recommendations'].append("系统性能良好，继续保持")
        elif insights['overall_health'] == 'poor':
            insights['recommendations'].append("系统存在严重性能问题，建议立即优化")

        return insights

    def export_metrics(self, filepath: str, format: str = 'json'):
        """导出性能指标"""
        with self.lock:
            data = {
                'export_timestamp': time.time(),
                'metrics_history': [self._metrics_to_dict(m) for m in self.metrics_history],
                'operation_summaries': {
                    op: self._summary_to_dict(summary)
                    for op, summary in self.operation_summaries.items()
                },
                'performance_insights': self.get_performance_insights()
            }

        if format.lower() == 'json':
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        else:
            raise ValueError(f"不支持的导出格式: {format}")

        logger.info(f"性能指标已导出到: {filepath}")

    def _metrics_to_dict(self, metrics: PerformanceMetrics) -> Dict[str, Any]:
        """将性能指标转换为字典"""
        return {
            'timestamp': metrics.timestamp,
            'operation': metrics.operation,
            'duration': metrics.duration,
            'memory_usage_mb': metrics.memory_usage_mb,
            'cpu_usage_percent': metrics.cpu_usage_percent,
            'gpu_memory_usage_mb': metrics.gpu_memory_usage_mb,
            'batch_size': metrics.batch_size,
            'audio_duration': metrics.audio_duration,
            'success': metrics.success,
            'error_message': metrics.error_message,
            'context': metrics.context
        }

    def _summary_to_dict(self, summary: PerformanceSummary) -> Dict[str, Any]:
        """将性能摘要转换为字典"""
        return {
            'operation': summary.operation,
            'total_operations': summary.total_operations,
            'successful_operations': summary.successful_operations,
            'failed_operations': summary.failed_operations,
            'average_duration': summary.average_duration,
            'min_duration': summary.min_duration,
            'max_duration': summary.max_duration,
            'p95_duration': summary.p95_duration,
            'p99_duration': summary.p99_duration,
            'average_memory_usage': summary.average_memory_usage,
            'peak_memory_usage': summary.peak_memory_usage,
            'average_cpu_usage': summary.average_cpu_usage,
            'success_rate': summary.success_rate,
            'throughput_per_minute': summary.throughput_per_minute,
            'last_updated': summary.last_updated
        }

    def clear_history(self):
        """清空历史记录"""
        with self.lock:
            self.metrics_history.clear()
            self.operation_summaries.clear()
            self.current_operations.clear()

    def get_system_health(self) -> Dict[str, Any]:
        """获取系统健康状态"""
        try:
            # 获取系统级指标
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            cpu_percent = psutil.cpu_percent(interval=1)

            system_health = {
                'timestamp': time.time(),
                'memory': {
                    'total_gb': memory.total / 1024 / 1024 / 1024,
                    'available_gb': memory.available / 1024 / 1024 / 1024,
                    'used_percent': memory.percent
                },
                'disk': {
                    'total_gb': disk.total / 1024 / 1024 / 1024,
                    'free_gb': disk.free / 1024 / 1024 / 1024,
                    'used_percent': disk.percent
                },
                'cpu': {
                    'usage_percent': cpu_percent,
                    'core_count': psutil.cpu_count()
                },
                'process_count': len(psutil.pids())
            }

            # GPU信息
            if self._gpu_available:
                try:
                    import torch
                    gpu_info = []
                    for i in range(torch.cuda.device_count()):
                        gpu_memory = torch.cuda.memory_allocated(i) / 1024 / 1024 / 1024  # GB
                        gpu_name = torch.cuda.get_device_name(i)
                        gpu_info.append({
                            'device_id': i,
                            'name': gpu_name,
                            'memory_used_gb': gpu_memory
                        })
                    system_health['gpu'] = gpu_info
                except Exception as e:
                    logger.debug(f"获取GPU信息失败: {e}")

            return system_health

        except Exception as e:
            logger.error(f"获取系统健康状态失败: {e}")
            return {'error': str(e)}

    def enable_monitoring(self):
        """启用监控"""
        self._monitoring_enabled = True
        logger.info("性能监控已启用")

    def disable_monitoring(self):
        """禁用监控"""
        self._monitoring_enabled = False
        logger.info("性能监控已禁用")

# 全局性能监控器实例
performance_monitor = PerformanceMonitor()

# 性能监控装饰器
def monitor_performance(operation_name: str = None):
    """性能监控装饰器"""
    def decorator(func):
        name = operation_name or f"{func.__module__}.{func.__name__}"

        def wrapper(*args, **kwargs):
            operation_id = performance_monitor.start_operation(name)
            try:
                result = func(*args, **kwargs)
                performance_monitor.end_operation(operation_id, success=True)
                return result
            except Exception as e:
                performance_monitor.end_operation(operation_id, success=False, error_message=str(e))
                raise
        return wrapper
    return decorator

# 性能监控上下文管理器
class PerformanceContext:
    """性能监控上下文管理器"""

    def __init__(self, operation: str, context: Dict[str, Any] = None):
        self.operation = operation
        self.context = context or {}
        self.operation_id = None

    def __enter__(self):
        self.operation_id = performance_monitor.start_operation(self.operation, self.context)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.operation_id:
            success = exc_type is None
            error_message = str(exc_val) if exc_val else None
            performance_monitor.end_operation(self.operation_id, success, error_message)

def get_performance_summary(operation: str = None) -> Dict[str, Any]:
    """获取性能摘要的便利函数"""
    if operation:
        summary = performance_monitor.get_operation_summary(operation)
        return performance_monitor._summary_to_dict(summary) if summary else {}
    else:
        return {
            op: performance_monitor._summary_to_dict(summary)
            for op, summary in performance_monitor.get_all_summaries().items()
        }

def get_performance_insights(operation: str = None) -> Dict[str, Any]:
    """获取性能洞察的便利函数"""
    return performance_monitor.get_performance_insights(operation)

def export_performance_metrics(filepath: str, format: str = 'json'):
    """导出性能指标的便利函数"""
    performance_monitor.export_metrics(filepath, format)

if __name__ == "__main__":
    # 测试性能监控
    @monitor_performance("test_operation")
    def test_function():
        time.sleep(0.1)
        return "test_result"

    # 运行测试
    for i in range(5):
        test_function()

    # 获取性能摘要
    summary = get_performance_summary("test_operation")
    print(f"性能摘要: {summary}")

    # 获取性能洞察
    insights = get_performance_insights()
    print(f"性能洞察: {insights}")