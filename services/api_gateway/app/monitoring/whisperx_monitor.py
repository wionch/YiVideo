#!/usr/bin/env python3
"""
WhisperX 服务监控系统
提供全面的性能监控、告警和可视化功能
"""

import time
import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import redis
import requests
import psutil
import torch
from services.common.config_loader import CONFIG
from services.common.logger import get_logger

logger = get_logger('whisperx_monitor')

@dataclass
class WhisperxMetrics:
    """WhisperX 性能指标数据类"""
    timestamp: str
    workflow_id: str
    execution_time: float
    gpu_memory_used_gb: float
    gpu_utilization_percent: float
    cpu_percent: float
    memory_percent: float
    audio_duration: float
    processing_speed_x: float
    backend_type: str
    thread_count: int
    status: str

class WhisperxMonitor:
    """WhisperX 服务监控器"""

    def __init__(self):
        self.redis_client = redis.Redis(
            host=CONFIG.get('redis', {}).get('host', 'redis'),
            port=CONFIG.get('redis', {}).get('port', 6379),
            db=CONFIG.get('redis', {}).get('db_state_store', 3),
            decode_responses=True
        )

        self.metrics_key = "whisperx:metrics"
        self.alerts_key = "whisperx:alerts"
        self.config_key = "whisperx:monitor_config"

        # 默认监控配置
        self.default_config = {
            "collection_interval": 30,  # 秒
            "retention_hours": 168,     # 7天
            "alert_thresholds": {
                "execution_time": 300,      # 5分钟
                "gpu_memory": 8,           # 8GB
                "gpu_utilization": 95,     # 95%
                "cpu_percent": 80,         # 80%
                "memory_percent": 85,      # 85%
                "processing_speed": 0.5    # 0.5x
            },
            "alert_cooldown": 300  # 5分钟冷却时间
        }

        self.load_config()

    def load_config(self):
        """加载监控配置"""
        try:
            saved_config = self.redis_client.hgetall(self.config_key)
            if saved_config:
                self.config = json.loads(saved_config.get('config', '{}'))
            else:
                self.config = self.default_config
                self.save_config()
        except Exception as e:
            logger.error(f"加载监控配置失败: {e}")
            self.config = self.default_config

    def save_config(self):
        """保存监控配置"""
        try:
            self.redis_client.hset(
                self.config_key,
                mapping={'config': json.dumps(self.config), 'updated_at': datetime.now().isoformat()}
            )
        except Exception as e:
            logger.error(f"保存监控配置失败: {e}")

    def collect_system_metrics(self) -> Dict[str, Any]:
        """收集系统性能指标"""
        metrics = {}

        # GPU 指标
        if torch.cuda.is_available():
            gpu_memory_allocated = torch.cuda.memory_allocated() / 1024**3  # GB
            gpu_memory_reserved = torch.cuda.memory_reserved() / 1024**3  # GB
            gpu_utilization = self._get_gpu_utilization()

            metrics.update({
                "gpu_memory_allocated_gb": gpu_memory_allocated,
                "gpu_memory_reserved_gb": gpu_memory_reserved,
                "gpu_utilization_percent": gpu_utilization
            })

        # CPU 和内存指标
        metrics.update({
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "memory_available_gb": psutil.virtual_memory().available / 1024**3,
            "disk_usage_percent": psutil.disk_usage('/').percent
        })

        return metrics

    def _get_gpu_utilization(self) -> float:
        """获取 GPU 利用率"""
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
                capture_output=True, text=True
            )
            return float(result.stdout.strip())
        except:
            return 0.0

    def collect_workflow_metrics(self, workflow_id: str, execution_data: Dict[str, Any]) -> WhisperxMetrics:
        """收集工作流性能指标"""
        system_metrics = self.collect_system_metrics()

        # 从执行数据中提取信息
        execution_time = execution_data.get('execution_time', 0)
        audio_duration = execution_data.get('audio_duration', 0)
        backend_type = execution_data.get('backend_type', 'unknown')
        thread_count = execution_data.get('thread_count', 0)
        status = execution_data.get('status', 'unknown')

        # 计算处理速度
        processing_speed = execution_time / audio_duration if audio_duration > 0 else 0

        metrics = WhisperxMetrics(
            timestamp=datetime.now().isoformat(),
            workflow_id=workflow_id,
            execution_time=execution_time,
            gpu_memory_used_gb=system_metrics.get('gpu_memory_allocated_gb', 0),
            gpu_utilization_percent=system_metrics.get('gpu_utilization_percent', 0),
            cpu_percent=system_metrics.get('cpu_percent', 0),
            memory_percent=system_metrics.get('memory_percent', 0),
            audio_duration=audio_duration,
            processing_speed_x=processing_speed,
            backend_type=backend_type,
            thread_count=thread_count,
            status=status
        )

        return metrics

    def store_metrics(self, metrics: WhisperxMetrics):
        """存储性能指标"""
        try:
            # 使用 Redis Stream 存储时间序列数据
            metrics_data = asdict(metrics)
            self.redis_client.xadd(
                self.metrics_key,
                metrics_data,
                maxlen=10000  # 保留最近10000条记录
            )

            # 清理过期数据
            retention_cutoff = datetime.now() - timedelta(hours=self.config['retention_hours'])
            self.redis_client.xtrim(self.metrics_key, minid=f'{int(retention_cutoff.timestamp())}-0')

        except Exception as e:
            logger.error(f"存储性能指标失败: {e}")

    def check_alerts(self, metrics: WhisperxMetrics) -> List[Dict[str, Any]]:
        """检查告警条件"""
        alerts = []
        thresholds = self.config['alert_thresholds']

        # 检查各项指标
        if metrics.execution_time > thresholds['execution_time']:
            alerts.append({
                'type': 'execution_time',
                'level': 'warning',
                'message': f'执行时间过长: {metrics.execution_time:.2f}s',
                'value': metrics.execution_time,
                'threshold': thresholds['execution_time']
            })

        if metrics.gpu_memory_used_gb > thresholds['gpu_memory']:
            alerts.append({
                'type': 'gpu_memory',
                'level': 'warning',
                'message': f'GPU显存使用过高: {metrics.gpu_memory_used_gb:.2f}GB',
                'value': metrics.gpu_memory_used_gb,
                'threshold': thresholds['gpu_memory']
            })

        if metrics.gpu_utilization_percent > thresholds['gpu_utilization']:
            alerts.append({
                'type': 'gpu_utilization',
                'level': 'warning',
                'message': f'GPU利用率过高: {metrics.gpu_utilization_percent:.1f}%',
                'value': metrics.gpu_utilization_percent,
                'threshold': thresholds['gpu_utilization']
            })

        if metrics.cpu_percent > thresholds['cpu_percent']:
            alerts.append({
                'type': 'cpu_percent',
                'level': 'warning',
                'message': f'CPU使用率过高: {metrics.cpu_percent:.1f}%',
                'value': metrics.cpu_percent,
                'threshold': thresholds['cpu_percent']
            })

        if metrics.memory_percent > thresholds['memory_percent']:
            alerts.append({
                'type': 'memory_percent',
                'level': 'warning',
                'message': f'内存使用率过高: {metrics.memory_percent:.1f}%',
                'value': metrics.memory_percent,
                'threshold': thresholds['memory_percent']
            })

        if metrics.processing_speed_x < thresholds['processing_speed']:
            alerts.append({
                'type': 'processing_speed',
                'level': 'warning',
                'message': f'处理速度过慢: {metrics.processing_speed_x:.2f}x',
                'value': metrics.processing_speed_x,
                'threshold': thresholds['processing_speed']
            })

        return alerts

    def send_alert(self, alert: Dict[str, Any]):
        """发送告警"""
        try:
            # 检查冷却时间
            cooldown_key = f"alert_cooldown:{alert['type']}"
            last_alert = self.redis_client.get(cooldown_key)

            if last_alert:
                last_time = datetime.fromisoformat(last_alert)
                if datetime.now() - last_time < timedelta(seconds=self.config['alert_cooldown']):
                    return  # 在冷却时间内，不重复发送

            # 存储告警
            alert_data = {
                **alert,
                'timestamp': datetime.now().isoformat(),
                'workflow_id': getattr(self, 'current_workflow_id', 'unknown')
            }

            self.redis_client.lpush(self.alerts_key, json.dumps(alert_data))
            self.redis_client.set(cooldown_key, datetime.now().isoformat(), ex=self.config['alert_cooldown'])

            # 记录日志
            logger.warning(f"告警触发: {alert['message']}")

        except Exception as e:
            logger.error(f"发送告警失败: {e}")

    def get_metrics_summary(self, hours: int = 24) -> Dict[str, Any]:
        """获取性能指标摘要"""
        try:
            since = datetime.now() - timedelta(hours=hours)

            # 从 Redis Stream 读取指标
            metrics_stream = self.redis_client.xrange(
                self.metrics_key,
                min=f'{int(since.timestamp())}-0',
                max='+'
            )

            if not metrics_stream:
                return {'error': '没有找到指标数据'}

            # 解析指标
            metrics_list = []
            for _, data in metrics_stream:
                metrics_list.append(WhisperxMetrics(**data))

            # 计算统计信息
            if metrics_list:
                execution_times = [m.execution_time for m in metrics_list]
                gpu_usages = [m.gpu_utilization_percent for m in metrics_list]
                processing_speeds = [m.processing_speed_x for m in metrics_list]

                summary = {
                    'period_hours': hours,
                    'total_workflows': len(metrics_list),
                    'success_rate': len([m for m in metrics_list if m.status == 'SUCCESS']) / len(metrics_list) * 100,
                    'avg_execution_time': sum(execution_times) / len(execution_times),
                    'max_execution_time': max(execution_times),
                    'min_execution_time': min(execution_times),
                    'avg_gpu_utilization': sum(gpu_usages) / len(gpu_usages),
                    'avg_processing_speed': sum(processing_speeds) / len(processing_speeds),
                    'backend_distribution': self._get_backend_distribution(metrics_list)
                }

                return summary
            else:
                return {'error': '没有找到有效的指标数据'}

        except Exception as e:
            logger.error(f"获取指标摘要失败: {e}")
            return {'error': str(e)}

    def _get_backend_distribution(self, metrics_list: List[WhisperxMetrics]) -> Dict[str, int]:
        """获取后端类型分布"""
        distribution = {}
        for metrics in metrics_list:
            backend = metrics.backend_type
            distribution[backend] = distribution.get(backend, 0) + 1
        return distribution

    def get_recent_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近的告警"""
        try:
            alerts_data = self.redis_client.lrange(self.alerts_key, 0, limit - 1)
            alerts = []

            for alert_json in alerts_data:
                alerts.append(json.loads(alert_json))

            return alerts

        except Exception as e:
            logger.error(f"获取告警历史失败: {e}")
            return []

    def cleanup_old_data(self):
        """清理过期数据"""
        try:
            # 清理过期指标
            retention_cutoff = datetime.now() - timedelta(hours=self.config['retention_hours'])
            self.redis_client.xtrim(self.metrics_key, minid=f'{int(retention_cutoff.timestamp())}-0')

            # 清理过期告警（保留最近1000条）
            self.redis_client.ltrim(self.alerts_key, 0, 999)

            logger.info("数据清理完成")

        except Exception as e:
            logger.error(f"数据清理失败: {e}")

class WhisperxMonitoringService:
    """WhisperX 监控服务"""

    def __init__(self):
        self.monitor = WhisperxMonitor()
        self.running = False
        self.collection_thread = None
        self.cleanup_thread = None

    def start(self):
        """启动监控服务"""
        if self.running:
            logger.warning("监控服务已经在运行")
            return

        self.running = True
        logger.info("启动 WhisperX 监控服务")

        # 启动指标收集线程
        self.collection_thread = threading.Thread(target=self._collection_loop, daemon=True)
        self.collection_thread.start()

        # 启动数据清理线程
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()

        logger.info("WhisperX 监控服务已启动")

    def stop(self):
        """停止监控服务"""
        self.running = False
        logger.info("停止 WhisperX 监控服务")

        if self.collection_thread:
            self.collection_thread.join(timeout=5)

        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=5)

    def _collection_loop(self):
        """指标收集循环"""
        while self.running:
            try:
                # 收集系统指标
                system_metrics = self.monitor.collect_system_metrics()

                # 这里可以添加更多的监控逻辑
                # 例如：检查工作流状态、处理告警等

                time.sleep(self.monitor.config['collection_interval'])

            except Exception as e:
                logger.error(f"指标收集错误: {e}")
                time.sleep(60)  # 错误时等待较长时间

    def _cleanup_loop(self):
        """数据清理循环"""
        while self.running:
            try:
                # 每小时清理一次过期数据
                self.monitor.cleanup_old_data()
                time.sleep(3600)

            except Exception as e:
                logger.error(f"数据清理错误: {e}")
                time.sleep(3600)

def main():
    """主函数 - 用于测试"""
    monitor = WhisperxMonitor()

    # 测试配置加载
    print("=== 监控配置 ===")
    print(json.dumps(monitor.config, indent=2, ensure_ascii=False))

    # 测试系统指标收集
    print("\n=== 系统指标 ===")
    system_metrics = monitor.collect_system_metrics()
    print(json.dumps(system_metrics, indent=2, ensure_ascii=False))

    # 测试指标摘要
    print("\n=== 指标摘要 ===")
    summary = monitor.get_metrics_summary(hours=1)
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    # 测试告警历史
    print("\n=== 告警历史 ===")
    alerts = monitor.get_recent_alerts(limit=10)
    print(json.dumps(alerts, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()