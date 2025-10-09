#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio Separator 服务监控脚本
实时监控音频分离服务的性能、资源使用和任务状态
"""

import os
import sys
import time
import json
import psutil
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import redis
import requests

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AudioSeparatorMonitor:
    """Audio Separator 服务监控器"""

    def __init__(self, redis_host: str = 'redis', redis_port: int = 6379):
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_client = None
        self.start_time = datetime.now()

    def connect_redis(self) -> bool:
        """连接Redis"""
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=True
            )
            self.redis_client.ping()
            logger.info("✅ Redis 连接成功")
            return True
        except Exception as e:
            logger.error(f"❌ Redis 连接失败: {str(e)}")
            return False

    def get_system_info(self) -> Dict[str, Any]:
        """获取系统信息"""
        try:
            # CPU信息
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()

            # 内存信息
            memory = psutil.virtual_memory()
            memory_used_gb = memory.used / (1024**3)
            memory_total_gb = memory.total / (1024**3)
            memory_percent = memory.percent

            # GPU信息（如果可用）
            gpu_info = self.get_gpu_info()

            # 磁盘信息
            disk = psutil.disk_usage('/')
            disk_used_gb = disk.used / (1024**3)
            disk_total_gb = disk.total / (1024**3)
            disk_percent = disk.percent

            return {
                'timestamp': datetime.now().isoformat(),
                'cpu': {
                    'percent': cpu_percent,
                    'count': cpu_count
                },
                'memory': {
                    'used_gb': round(memory_used_gb, 2),
                    'total_gb': round(memory_total_gb, 2),
                    'percent': memory_percent
                },
                'gpu': gpu_info,
                'disk': {
                    'used_gb': round(disk_used_gb, 2),
                    'total_gb': round(disk_total_gb, 2),
                    'percent': disk_percent
                }
            }
        except Exception as e:
            logger.error(f"获取系统信息失败: {str(e)}")
            return {}

    def get_gpu_info(self) -> Dict[str, Any]:
        """获取GPU信息"""
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]  # 使用第一个GPU
                return {
                    'name': gpu.name,
                    'memory_used_mb': gpu.memoryUsed,
                    'memory_total_mb': gpu.memoryTotal,
                    'memory_percent': round(gpu.memoryUtil * 100, 1),
                    'utilization': round(gpu.load * 100, 1),
                    'temperature': gpu.temperature
                }
        except ImportError:
            logger.warning("GPUtil 未安装，无法获取GPU信息")
        except Exception as e:
            logger.warning(f"获取GPU信息失败: {str(e)}")

        return {}

    def get_celery_stats(self) -> Dict[str, Any]:
        """获取Celery统计信息"""
        try:
            # 获取active tasks
            active_tasks = self.redis_client.lrange('celery-task-meta', 0, -1)
            active_count = len(active_tasks)

            # 获取worker信息（通过Celery inspect）
            inspect_stats = self.get_celery_inspect_stats()

            return {
                'active_tasks': active_count,
                'inspect_stats': inspect_stats,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"获取Celery统计信息失败: {str(e)}")
            return {}

    def get_celery_inspect_stats(self) -> Dict[str, Any]:
        """获取Celery inspect统计信息"""
        try:
            from celery import Celery
            from services.workers.audio_separator_service.app.celery_app import celery_app

            inspect = celery_app.control.inspect()

            # 获取active tasks
            active = inspect.active()
            if active:
                active_tasks = list(active.values())[0]
            else:
                active_tasks = []

            # 获取scheduled tasks
            scheduled = inspect.scheduled()
            if scheduled:
                scheduled_tasks = list(scheduled.values())[0]
            else:
                scheduled_tasks = []

            # 获取stats
            stats = inspect.stats()
            if stats:
                worker_stats = list(stats.values())[0]
            else:
                worker_stats = {}

            return {
                'active_tasks': active_tasks,
                'scheduled_tasks': scheduled_tasks,
                'worker_stats': worker_stats
            }
        except Exception as e:
            logger.warning(f"获取Celery inspect统计失败: {str(e)}")
            return {}

    def get_audio_separator_stats(self) -> Dict[str, Any]:
        """获取Audio Separator特定统计信息"""
        try:
            # 检查模型目录
            models_dir = Path("/models/uvr_mdx")
            if models_dir.exists():
                model_files = list(models_dir.glob("*.onnx"))
                models_info = []
                for model_file in model_files:
                    stat = model_file.stat()
                    models_info.append({
                        'name': model_file.name,
                        'size_mb': round(stat.st_size / (1024*1024), 1),
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
            else:
                models_info = []

            # 检查输出目录
            output_dir = Path("/share/workflows/audio_separated")
            recent_outputs = []
            if output_dir.exists():
                # 获取最近24小时的输出文件
                cutoff_time = datetime.now() - timedelta(hours=24)
                for workflow_dir in output_dir.iterdir():
                    if workflow_dir.is_dir():
                        stat = workflow_dir.stat()
                        if datetime.fromtimestamp(stat.st_mtime) > cutoff_time:
                            wav_files = list(workflow_dir.glob("*.wav"))
                            flac_files = list(workflow_dir.glob("*.flac"))
                            recent_outputs.append({
                                'workflow_id': workflow_dir.name,
                                'created': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                                'wav_count': len(wav_files),
                                'flac_count': len(flac_files)
                            })

            return {
                'models': {
                    'count': len(models_info),
                    'files': models_info
                },
                'recent_outputs': {
                    'count_24h': len(recent_outputs),
                    'workflows': recent_outputs[-10:]  # 只保留最近10个
                },
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"获取Audio Separator统计失败: {str(e)}")
            return {}

    def get_redis_info(self) -> Dict[str, Any]:
        """获取Redis信息"""
        try:
            info = self.redis_client.info()
            keyspace = info.get('keyspace', {})

            # 统计各数据库的键数量
            db_stats = {}
            for db_key, db_info in keyspace.items():
                db_stats[db_key] = {
                    'keys': int(db_info.split('keys=')[1].split(',')[0]),
                    'expires': int(db_info.split('expires=')[1].split(',')[0]) if 'expires=' in db_info else 0
                }

            return {
                'used_memory_human': info.get('used_memory_human', 'N/A'),
                'connected_clients': info.get('connected_clients', 0),
                'total_commands_processed': info.get('total_commands_processed', 0),
                'keyspace_stats': db_stats,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"获取Redis信息失败: {str(e)}")
            return {}

    def display_monitoring_dashboard(self):
        """显示监控仪表板"""
        while True:
            try:
                # 清屏
                os.system('clear' if os.name == 'posix' else 'cls')

                # 标题
                print("=" * 80)
                print("🎵 Audio Separator 服务监控仪表板")
                print("=" * 80)
                print(f"⏰ 监控时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"⏱️  运行时长: {datetime.now() - self.start_time}")
                print()

                # 系统信息
                system_info = self.get_system_info()
                if system_info:
                    print("📊 系统资源状态:")
                    print(f"  CPU 使用率: {system_info['cpu']['percent']}% ({system_info['cpu']['count']} 核心)")
                    print(f"  内存使用: {system_info['memory']['used_gb']}GB / {system_info['memory']['total_gb']}GB ({system_info['memory']['percent']}%)")
                    print(f"  磁盘使用: {system_info['disk']['used_gb']}GB / {system_info['disk']['total_gb']}GB ({system_info['disk']['percent']}%)")

                    if system_info.get('gpu'):
                        gpu = system_info['gpu']
                        print(f"  GPU ({gpu['name']}): 显存 {gpu['memory_used_mb']}MB / {gpu['memory_total_mb']}MB ({gpu['memory_percent']}%), 利用率 {gpu['utilization']}%")
                        if gpu.get('temperature'):
                            print(f"    温度: {gpu['temperature']}°C")
                    print()

                # Audio Separator统计
                audio_stats = self.get_audio_separator_stats()
                if audio_stats:
                    print("🎛️  Audio Separator 服务状态:")
                    models = audio_stats['models']
                    print(f"  可用模型: {models['count']} 个")
                    for model in models['files'][:3]:  # 只显示前3个
                        print(f"    - {model['name']} ({model['size_mb']}MB)")

                    outputs = audio_stats['recent_outputs']
                    print(f"  24小时内输出: {outputs['count_24h']} 个工作流")
                    if outputs['workflows']:
                        latest = outputs['workflows'][-1]
                        print(f"    最新工作流: {latest['workflow_id']} ({latest['wav_count']} WAV, {latest['flac_count']} FLAC)")
                    print()

                # Celery统计
                celery_stats = self.get_celery_stats()
                if celery_stats:
                    print("🔄 Celery 任务队列状态:")
                    print(f"  活跃任务: {celery_stats.get('active_tasks', 0)} 个")

                    inspect_stats = celery_stats.get('inspect_stats', {})
                    active_tasks = inspect_stats.get('active_tasks', [])
                    if active_tasks:
                        print("  当前执行的任务:")
                        for task in active_tasks[:3]:  # 只显示前3个
                            task_name = task.get('name', 'Unknown')
                            task_id = task.get('id', 'Unknown')[:8]
                            print(f"    - {task_name} ({task_id}...)")

                    worker_stats = inspect_stats.get('worker_stats', {})
                    if worker_stats:
                        pool = worker_stats.get('pool', {})
                        print(f"  Worker 进程: {pool.get('max-concurrency', 'N/A')} 并发")
                    print()

                # Redis信息
                redis_info = self.get_redis_info()
                if redis_info:
                    print("💾 Redis 缓存状态:")
                    print(f"  内存使用: {redis_info.get('used_memory_human', 'N/A')}")
                    print(f"  连接客户端: {redis_info.get('connected_clients', 0)}")

                    keyspace_stats = redis_info.get('keyspace_stats', {})
                    total_keys = sum(db['keys'] for db in keyspace_stats.values())
                    print(f"  总键数: {total_keys}")
                    print()

                # 等待下一次更新
                print("⏳ 每10秒更新一次 (按 Ctrl+C 退出)")
                time.sleep(10)

            except KeyboardInterrupt:
                print("\n\n👋 监控已停止")
                break
            except Exception as e:
                logger.error(f"监控更新失败: {str(e)}")
                time.sleep(5)

    def export_stats(self, output_file: str) -> bool:
        """导出统计信息到文件"""
        try:
            stats = {
                'timestamp': datetime.now().isoformat(),
                'system_info': self.get_system_info(),
                'audio_separator_stats': self.get_audio_separator_stats(),
                'celery_stats': self.get_celery_stats(),
                'redis_info': self.get_redis_info()
            }

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(stats, f, indent=2, ensure_ascii=False)

            logger.info(f"统计信息已导出到: {output_file}")
            return True
        except Exception as e:
            logger.error(f"导出统计信息失败: {str(e)}")
            return False

    def run_health_check(self) -> bool:
        """运行健康检查"""
        logger.info("🔍 运行 Audio Separator 服务健康检查...")

        health_status = {
            'redis': False,
            'models_dir': False,
            'share_dir': False,
            'celery_worker': False
        }

        # 检查Redis连接
        if self.connect_redis():
            health_status['redis'] = True
            logger.info("✅ Redis 连接正常")

        # 检查模型目录
        models_dir = Path("/models/uvr_mdx")
        if models_dir.exists():
            model_files = list(models_dir.glob("*.onnx"))
            if model_files:
                health_status['models_dir'] = True
                logger.info(f"✅ 模型目录正常，包含 {len(model_files)} 个模型")
            else:
                logger.warning("⚠️ 模型目录存在但为空")
        else:
            logger.error("❌ 模型目录不存在")

        # 检查共享目录
        share_dir = Path("/share")
        if share_dir.exists():
            health_status['share_dir'] = True
            logger.info("✅ 共享目录正常")
        else:
            logger.error("❌ 共享目录不存在")

        # 检查Celery Worker
        try:
            from services.workers.audio_separator_service.app.celery_app import celery_app
            inspect = celery_app.control.inspect()
            stats = inspect.stats()
            if stats:
                health_status['celery_worker'] = True
                logger.info("✅ Celery Worker 运行正常")
            else:
                logger.warning("⚠️ Celery Worker 可能未运行")
        except Exception as e:
            logger.error(f"❌ Celery Worker 检查失败: {str(e)}")

        # 总结
        passed_checks = sum(health_status.values())
        total_checks = len(health_status)

        logger.info(f"\n📋 健康检查结果: {passed_checks}/{total_checks} 项通过")

        if passed_checks == total_checks:
            logger.info("🎉 所有健康检查通过！服务运行正常")
            return True
        else:
            logger.warning("⚠️ 部分健康检查未通过，请检查服务状态")
            return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='Audio Separator 服务监控工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 启动实时监控仪表板
  python scripts/monitor_audio_separator.py --dashboard

  # 运行健康检查
  python scripts/monitor_audio_separator.py --health-check

  # 导出统计信息
  python scripts/monitor_audio_separator.py --export stats.json

  # 显示一次性状态
  python scripts/monitor_audio_separator.py --status
        """
    )

    parser.add_argument('--dashboard', action='store_true',
                       help='启动实时监控仪表板')
    parser.add_argument('--health-check', action='store_true',
                       help='运行健康检查')
    parser.add_argument('--export', metavar='OUTPUT_FILE',
                       help='导出统计信息到文件')
    parser.add_argument('--status', action='store_true',
                       help='显示当前状态')
    parser.add_argument('--redis-host', default='redis',
                       help='Redis主机地址 (默认: redis)')
    parser.add_argument('--redis-port', type=int, default=6379,
                       help='Redis端口 (默认: 6379)')

    args = parser.parse_args()

    # 创建监控器
    monitor = AudioSeparatorMonitor(args.redis_host, args.redis_port)

    # 连接Redis
    if not monitor.connect_redis():
        logger.error("无法连接到Redis，监控功能将受限")

    # 执行命令
    if args.health_check:
        success = monitor.run_health_check()
        sys.exit(0 if success else 1)

    if args.export:
        success = monitor.export_stats(args.export)
        sys.exit(0 if success else 1)

    if args.status:
        print("=== Audio Separator 服务状态 ===")

        system_info = monitor.get_system_info()
        if system_info:
            print("系统资源:")
            print(f"  CPU: {system_info['cpu']['percent']}%")
            print(f"  内存: {system_info['memory']['percent']}%")
            if system_info.get('gpu'):
                gpu = system_info['gpu']
                print(f"  GPU: {gpu['utilization']}% (显存 {gpu['memory_percent']}%)")

        audio_stats = monitor.get_audio_separator_stats()
        if audio_stats:
            models = audio_stats['models']
            print(f"可用模型: {models['count']} 个")
            outputs = audio_stats['recent_outputs']
            print(f"24小时输出: {outputs['count_24h']} 个工作流")

        celery_stats = monitor.get_celery_stats()
        if celery_stats:
            print(f"活跃任务: {celery_stats.get('active_tasks', 0)} 个")

        return

    if args.dashboard:
        monitor.display_monitoring_dashboard()
        return

    # 默认显示帮助
    parser.print_help()


if __name__ == "__main__":
    main()