#!/usr/bin/env python3
"""
WhisperX 服务监控脚本
"""

import requests
import time
import json
import psutil
from datetime import datetime, timedelta
import subprocess

class WhisperXMonitor:
    def __init__(self):
        self.api_url = "http://localhost:8788"
        self.log_file = "logs/whisperx_monitor.log"

    def check_service_health(self):
        """检查服务健康状态"""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=10)
            return response.status_code == 200
        except:
            return False

    def get_gpu_stats(self):
        """获取 GPU 统计信息"""
        try:
            result = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,utilization.gpu',
                                   '--format=csv,noheader,nounits'],
                                  capture_output=True, text=True)
            if result.returncode == 0:
                memory, utilization = result.stdout.strip().split(', ')
                return {'memory_used': int(memory), 'utilization': int(utilization)}
        except:
            pass
        return {'memory_used': 0, 'utilization': 0}

    def run_test_workflow(self):
        """运行测试工作流"""
        test_workflow = {
            "workflow_config": {
                "workflow_chain": ["ffmpeg.extract_audio", "whisperx.generate_subtitles"]
            },
            "input_params": {
                "video_path": "/app/videos/223.mp4"
            }
        }

        try:
            response = requests.post(f"{self.api_url}/v1/workflows",
                                   json=test_workflow,
                                   timeout=30)
            if response.status_code == 200:
                return response.json().get('workflow_id')
        except:
            pass
        return None

    def monitor_workflow_execution(self, workflow_id):
        """监控工作流执行"""
        start_time = time.time()

        while time.time() - start_time < 600:  # 10分钟超时
            try:
                response = requests.get(f"{self.api_url}/v1/workflows/status/{workflow_id}")
                if response.status_code == 200:
                    status = response.json().get('status')
                    if status == 'SUCCESS':
                        return time.time() - start_time
                    elif status == 'FAILED':
                        return -1
            except:
                pass
            time.sleep(10)

        return -1

    def collect_metrics(self):
        """收集性能指标"""
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'service_healthy': self.check_service_health(),
            'gpu_stats': self.get_gpu_stats(),
            'system_stats': {
                'cpu_percent': psutil.cpu_percent(),
                'memory_percent': psutil.virtual_memory().percent
            }
        }

        # 运行测试工作流
        workflow_id = self.run_test_workflow()
        if workflow_id:
            execution_time = self.monitor_workflow_execution(workflow_id)
            metrics['test_workflow'] = {
                'workflow_id': workflow_id,
                'execution_time': execution_time,
                'success': execution_time > 0
            }

        return metrics

    def save_metrics(self, metrics):
        """保存指标数据"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"logs/whisperx_metrics_{timestamp}.json"

        os.makedirs(os.path.dirname(filename), exist_ok=True)

        with open(filename, 'w') as f:
            json.dump(metrics, f, indent=2)

    def generate_report(self, metrics):
        """生成监控报告"""
        print("\n=== WhisperX 监控报告 ===")
        print(f"时间: {metrics['timestamp']}")
        print(f"服务状态: {'✅ 正常' if metrics['service_healthy'] else '❌ 异常'}")

        gpu_stats = metrics['gpu_stats']
        print(f"GPU 显存使用: {gpu_stats['memory_used']}MB")
        print(f"GPU 利用率: {gpu_stats['utilization']}%")

        system_stats = metrics['system_stats']
        print(f"CPU 使用率: {system_stats['cpu_percent']}%")
        print(f"内存使用率: {system_stats['memory_percent']}%")

        if 'test_workflow' in metrics:
            test_result = metrics['test_workflow']
            if test_result['success']:
                print(f"测试工作流执行时间: {test_result['execution_time']:.2f}s")
            else:
                print("测试工作流执行失败")

    def run_monitoring(self):
        """运行监控"""
        print("开始 WhisperX 服务监控...")

        while True:
            try:
                metrics = self.collect_metrics()
                self.generate_report(metrics)
                self.save_metrics(metrics)

                # 等待 30 分钟
                time.sleep(1800)

            except KeyboardInterrupt:
                print("\n监控已停止")
                break
            except Exception as e:
                print(f"监控错误: {e}")
                time.sleep(60)

if __name__ == "__main__":
    monitor = WhisperXMonitor()
    monitor.run_monitoring()