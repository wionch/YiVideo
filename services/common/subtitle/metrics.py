"""
Prometheus指标配置

为AI字幕优化功能提供可观测性指标。

作者: Claude Code
日期: 2025-11-06
版本: v1.0.0
"""

from prometheus_client import Counter, Histogram, Gauge, start_http_server
import logging

logger = logging.getLogger(__name__)

# 计数器指标
ai_subtitle_optimization_requests_total = Counter(
    'ai_subtitle_optimization_requests_total',
    'Total number of AI subtitle optimization requests',
    ['provider', 'status']
)

ai_subtitle_optimization_commands_total = Counter(
    'ai_subtitle_optimization_commands_total',
    'Total number of AI optimization commands applied',
    ['command_type']
)

# 直方图指标
ai_subtitle_optimization_duration_seconds = Histogram(
    'ai_subtitle_optimization_duration_seconds',
    'Duration of AI subtitle optimization process',
    ['provider', 'batch_mode']
)

ai_subtitle_optimization_api_call_duration_seconds = Histogram(
    'ai_subtitle_optimization_api_call_duration_seconds',
    'Duration of AI API calls',
    ['provider']
)

ai_subtitle_optimization_subtitle_count = Histogram(
    'ai_subtitle_optimization_subtitle_count',
    'Number of subtitles in optimization process',
    ['batch_mode']
)

# 仪表盘指标
ai_subtitle_optimization_active_tasks = Gauge(
    'ai_subtitle_optimization_active_tasks',
    'Number of currently active optimization tasks'
)

ai_subtitle_optimization_batch_size = Gauge(
    'ai_subtitle_optimization_batch_size',
    'Current batch size for optimization',
    ['provider']
)

ai_subtitle_optimization_processing_time = Gauge(
    'ai_subtitle_optimization_processing_time',
    'Processing time of last optimization',
    ['provider']
)


class MetricsCollector:
    """指标收集器

    统一管理AI字幕优化功能的指标收集。
    """

    def __init__(self):
        """初始化指标收集器"""
        pass

    def record_request(self, provider: str, status: str, duration: float):
        """记录请求指标

        Args:
            provider: AI提供商
            status: 状态 (success/failure)
            duration: 持续时间
        """
        ai_subtitle_optimization_requests_total.labels(
            provider=provider, status=status
        ).inc()

        ai_subtitle_optimization_duration_seconds.labels(
            provider=provider,
            batch_mode='unknown'
        ).observe(duration)

    def record_api_call(self, provider: str, duration: float):
        """记录API调用指标

        Args:
            provider: AI提供商
            duration: 调用持续时间
        """
        ai_subtitle_optimization_api_call_duration_seconds.labels(
            provider=provider
        ).observe(duration)

    def record_commands(self, command_types: dict):
        """记录指令统计

        Args:
            command_types: 指令类型统计字典
        """
        for cmd_type, count in command_types.items():
            if count > 0:
                ai_subtitle_optimization_commands_total.labels(
                    command_type=cmd_type
                ).inc(count)

    def record_subtitle_count(self, count: int, batch_mode: bool):
        """记录字幕数量

        Args:
            count: 字幕数量
            batch_mode: 是否为批处理模式
        """
        ai_subtitle_optimization_subtitle_count.labels(
            batch_mode='batch' if batch_mode else 'single'
        ).observe(count)

    def set_active_tasks(self, count: int):
        """设置活跃任务数

        Args:
            count: 活跃任务数量
        """
        ai_subtitle_optimization_active_tasks.set(count)

    def set_batch_size(self, provider: str, size: int):
        """设置批处理大小

        Args:
            provider: AI提供商
            size: 批处理大小
        """
        ai_subtitle_optimization_batch_size.labels(
            provider=provider
        ).set(size)

    def set_processing_time(self, provider: str, time: float):
        """设置处理时间

        Args:
            provider: AI提供商
            time: 处理时间
        """
        ai_subtitle_optimization_processing_time.labels(
            provider=provider
        ).set(time)

    def start_metrics_server(self, port: int = 8000):
        """启动指标服务器

        Args:
            port: 端口号
        """
        try:
            start_http_server(port)
            logger.info(f"Prometheus指标服务器已启动 - 端口: {port}")
        except Exception as e:
            logger.error(f"启动指标服务器失败: {e}")


# 全局指标收集器实例
metrics_collector = MetricsCollector()