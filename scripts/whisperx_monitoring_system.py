#!/usr/bin/env python3
"""
WhisperX 完整监控系统
提供实时监控、性能测试、健康检查和报告生成功能
"""

import requests
import time
import json
import psutil
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
import subprocess
import os

class WhisperXMonitoringSystem:
    def __init__(self):
        self.api_url = "http://localhost:8788"
        self.log_file = "logs/whisperx_monitoring.log"
        self.metrics_file = "logs/whisperx_metrics.json"
        self.report_file = "logs/whisperx_report.html"

        # 监控配置
        self.monitor_interval = 30  # 秒
        self.test_video = "/app/videos/223.mp4"
        self.max_test_duration = 600  # 10分钟

        # 初始化日志
        self._setup_logging()

        # 性能基准
        self.performance_baseline = {
            "native_backend": {"load_time": 0, "inference_time": 0, "total_time": 0},
            "faster_whisper": {"load_time": 0, "inference_time": 0, "total_time": 0}
        }

    def _setup_logging(self):
        """设置日志系统"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def check_service_health(self) -> Dict[str, Any]:
        """检查服务健康状态"""
        health_status = {
            "api_gateway": False,
            "whisperx_service": False,
            "redis": False,
            "gpu_lock": False,
            "timestamp": datetime.now().isoformat()
        }

        try:
            # 检查 API 网关
            response = requests.get(f"{self.api_url}/docs", timeout=5)
            health_status["api_gateway"] = response.status_code == 200
        except:
            pass

        try:
            # 检查 GPU 锁系统
            response = requests.get(f"{self.api_url}/api/v1/monitoring/gpu-lock/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                health_status["gpu_lock"] = data.get("overall_status") != "critical"
                health_status["redis"] = True
        except:
            pass

        # 检查 WhisperX 服务状态
        try:
            result = subprocess.run(['docker-compose', 'ps', 'whisperx_service'],
                                  capture_output=True, text=True)
            health_status["whisperx_service"] = "Up" in result.stdout
        except:
            pass

        return health_status

    def get_gpu_stats(self) -> Dict[str, Any]:
        """获取 GPU 统计信息"""
        gpu_stats = {
            "memory_used": 0,
            "memory_total": 0,
            "utilization": 0,
            "temperature": 0,
            "timestamp": datetime.now().isoformat()
        }

        try:
            result = subprocess.run([
                'nvidia-smi',
                '--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu',
                '--format=csv,noheader,nounits'
            ], capture_output=True, text=True)

            if result.returncode == 0:
                values = result.stdout.strip().split(', ')
                if len(values) >= 4:
                    gpu_stats.update({
                        "memory_used": int(values[0]),
                        "memory_total": int(values[1]),
                        "utilization": int(values[2]),
                        "temperature": int(values[3])
                    })
        except:
            pass

        return gpu_stats

    def get_system_stats(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        return {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage('/').percent,
            "timestamp": datetime.now().isoformat()
        }

    def run_workflow_test(self) -> Dict[str, Any]:
        """运行工作流测试"""
        test_result = {
            "workflow_id": None,
            "success": False,
            "execution_time": 0,
            "error": None,
            "stages": {},
            "timestamp": datetime.now().isoformat()
        }

        try:
            # 提交工作流
            workflow_data = {
                "video_path": self.test_video,
                "workflow_config": {
                    "workflow_chain": ["ffmpeg.extract_audio", "whisperx.generate_subtitles"]
                }
            }

            response = requests.post(f"{self.api_url}/v1/workflows",
                                   json=workflow_data, timeout=30)

            if response.status_code != 200:
                test_result["error"] = f"工作流提交失败: {response.status_code}"
                return test_result

            workflow_id = response.json().get('workflow_id')
            test_result["workflow_id"] = workflow_id

            # 监控执行
            start_time = time.time()
            last_status_check = start_time

            while time.time() - start_time < self.max_test_duration:
                try:
                    status_response = requests.get(f"{self.api_url}/v1/workflows/status/{workflow_id}")

                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        current_status = status_data.get('status')

                        # 记录阶段状态
                        if status_data.get('stages'):
                            test_result["stages"] = status_data['stages']

                        if current_status == 'SUCCESS':
                            test_result["success"] = True
                            test_result["execution_time"] = time.time() - start_time
                            break
                        elif current_status == 'FAILED':
                            test_result["error"] = "工作流执行失败"
                            break

                    last_status_check = time.time()
                    time.sleep(10)

                except Exception as e:
                    test_result["error"] = f"状态检查失败: {e}"
                    break

            if time.time() - start_time >= self.max_test_duration:
                test_result["error"] = "工作流执行超时"

        except Exception as e:
            test_result["error"] = f"测试执行失败: {e}"

        return test_result

    def collect_metrics(self) -> Dict[str, Any]:
        """收集完整的性能指标"""
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "health": self.check_service_health(),
            "gpu_stats": self.get_gpu_stats(),
            "system_stats": self.get_system_stats(),
            "workflow_test": self.run_workflow_test()
        }

        return metrics

    def save_metrics(self, metrics: Dict[str, Any]):
        """保存指标数据"""
        os.makedirs(os.path.dirname(self.metrics_file), exist_ok=True)

        try:
            # 读取现有数据
            if os.path.exists(self.metrics_file):
                with open(self.metrics_file, 'r') as f:
                    data = json.load(f)
            else:
                data = {"metrics": []}

            # 添加新数据
            data["metrics"].append(metrics)

            # 保持最近100条记录
            if len(data["metrics"]) > 100:
                data["metrics"] = data["metrics"][-100:]

            with open(self.metrics_file, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            self.logger.error(f"保存指标失败: {e}")

    def generate_report(self, metrics: Dict[str, Any]):
        """生成监控报告"""
        report_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>WhisperX 监控报告</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #2c3e50; color: white; padding: 20px; }}
        .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; }}
        .success {{ background: #d4edda; color: #155724; }}
        .warning {{ background: #fff3cd; color: #856404; }}
        .error {{ background: #f8d7da; color: #721c24; }}
        .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px; }}
        .metric-card {{ padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f2f2f2; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 WhisperX 监控报告</h1>
        <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>

    <div class="section">
        <h2>📊 系统健康状态</h2>
        <div class="metrics-grid">
            <div class="metric-card">
                <h3>API 网关</h3>
                <p class="{'success' if metrics['health']['api_gateway'] else 'error'}">
                    {'✅ 正常' if metrics['health']['api_gateway'] else '❌ 异常'}
                </p>
            </div>
            <div class="metric-card">
                <h3>WhisperX 服务</h3>
                <p class="{'success' if metrics['health']['whisperx_service'] else 'error'}">
                    {'✅ 正常' if metrics['health']['whisperx_service'] else '❌ 异常'}
                </p>
            </div>
            <div class="metric-card">
                <h3>GPU 锁系统</h3>
                <p class="{'success' if metrics['health']['gpu_lock'] else 'error'}">
                    {'✅ 正常' if metrics['health']['gpu_lock'] else '❌ 异常'}
                </p>
            </div>
            <div class="metric-card">
                <h3>Redis</h3>
                <p class="{'success' if metrics['health']['redis'] else 'error'}">
                    {'✅ 正常' if metrics['health']['redis'] else '❌ 异常'}
                </p>
            </div>
        </div>
    </div>

    <div class="section">
        <h2>🎮 GPU 状态</h2>
        <table>
            <tr><th>项目</th><th>数值</th></tr>
            <tr><td>显存使用</td><td>{metrics['gpu_stats']['memory_used']} MB / {metrics['gpu_stats']['memory_total']} MB</td></tr>
            <tr><td>显存使用率</td><td>{metrics['gpu_stats']['memory_used']/metrics['gpu_stats']['memory_total']*100:.1f}%</td></tr>
            <tr><td>GPU 利用率</td><td>{metrics['gpu_stats']['utilization']}%</td></tr>
            <tr><td>GPU 温度</td><td>{metrics['gpu_stats']['temperature']}°C</td></tr>
        </table>
    </div>

    <div class="section">
        <h2>💻 系统资源</h2>
        <table>
            <tr><th>项目</th><th>数值</th></tr>
            <tr><td>CPU 使用率</td><td>{metrics['system_stats']['cpu_percent']}%</td></tr>
            <tr><td>内存使用率</td><td>{metrics['system_stats']['memory_percent']}%</td></tr>
            <tr><td>磁盘使用率</td><td>{metrics['system_stats']['disk_usage']}%</td></tr>
        </table>
    </div>

    <div class="section">
        <h2>🔄 工作流测试</h2>
        <div class="{'success' if metrics['workflow_test']['success'] else 'error'}">
            <h3>测试结果: {'✅ 成功' if metrics['workflow_test']['success'] else '❌ 失败'}</h3>
            {'<p>执行时间: {:.2f}s</p>'.format(metrics['workflow_test']['execution_time']) if metrics['workflow_test']['success'] else ''}
            {'<p>错误信息: {}</p>'.format(metrics['workflow_test']['error']) if metrics['workflow_test']['error'] else ''}
        </div>
    </div>
</body>
</html>
        """

        os.makedirs(os.path.dirname(self.report_file), exist_ok=True)
        with open(self.report_file, 'w', encoding='utf-8') as f:
            f.write(report_content)

    def run_monitoring_cycle(self):
        """运行一个监控周期"""
        self.logger.info("开始监控周期...")

        try:
            # 收集指标
            metrics = self.collect_metrics()

            # 保存指标
            self.save_metrics(metrics)

            # 生成报告
            self.generate_report(metrics)

            # 输出摘要
            self._print_summary(metrics)

        except Exception as e:
            self.logger.error(f"监控周期执行失败: {e}")

    def _print_summary(self, metrics: Dict[str, Any]):
        """打印监控摘要"""
        print(f"\n=== WhisperX 监控摘要 ===")
        print(f"时间: {metrics['timestamp']}")

        # 健康状态
        health = metrics['health']
        healthy_count = sum(1 for v in health.values() if v and v is not False)
        total_count = len([v for v in health.values() if v is not None])
        print(f"系统健康: {healthy_count}/{total_count} 项正常")

        # GPU 状态
        gpu = metrics['gpu_stats']
        print(f"GPU 显存: {gpu['memory_used']}MB / {gpu['memory_total']}MB ({gpu['memory_used']/gpu['memory_total']*100:.1f}%)")
        print(f"GPU 利用率: {gpu['utilization']}%")

        # 工作流测试
        workflow = metrics['workflow_test']
        if workflow['success']:
            print(f"工作流测试: ✅ 成功 ({workflow['execution_time']:.2f}s)")
        else:
            print(f"工作流测试: ❌ 失败 ({workflow.get('error', '未知错误')})")

    def run_continuous_monitoring(self):
        """运行连续监控"""
        self.logger.info("开始连续监控...")

        try:
            while True:
                self.run_monitoring_cycle()
                print(f"\n等待 {self.monitor_interval} 秒后进行下一次监控...")
                time.sleep(self.monitor_interval)

        except KeyboardInterrupt:
            self.logger.info("监控已停止")
        except Exception as e:
            self.logger.error(f"连续监控失败: {e}")

if __name__ == "__main__":
    monitor = WhisperXMonitoringSystem()

    # 单次运行
    monitor.run_monitoring_cycle()

    # 如果要运行连续监控，取消下面的注释
    # monitor.run_continuous_monitoring()