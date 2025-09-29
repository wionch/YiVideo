#!/usr/bin/env python3
"""
WhisperX 健康检查和自动化测试脚本
提供全面的系统健康检查和自动化测试功能
"""

import sys
import os
import time
import json
import logging
import requests
import subprocess
from datetime import datetime
from typing import Dict, List, Any, Tuple
import argparse

# 添加项目路径
sys.path.append('/app/services')

class WhisperXHealthChecker:
    def __init__(self):
        self.api_url = "http://localhost:8788"
        self.test_video = "/app/videos/223.mp4"
        self.log_file = "logs/whisperx_health.log"
        self.report_file = "logs/whisperx_health_report.json"

        # 健康检查阈值
        self.thresholds = {
            "max_gpu_memory_usage": 85,  # GPU内存使用率阈值 (%)
            "max_gpu_temperature": 85,   # GPU温度阈值 (°C)
            "max_system_memory": 90,     # 系统内存使用率阈值 (%)
            "max_disk_usage": 90,        # 磁盘使用率阈值 (%)
            "max_response_time": 30,     # API响应时间阈值 (秒)
            "max_workflow_time": 600     # 工作流执行时间阈值 (秒)
        }

        self.setup_logging()

    def setup_logging(self):
        """设置日志"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def check_api_health(self) -> Dict[str, Any]:
        """检查 API 健康状态"""
        result = {
            "component": "API Gateway",
            "status": "healthy",
            "response_time": 0,
            "endpoints": {},
            "issues": []
        }

        endpoints_to_check = [
            ("/docs", "Swagger UI"),
            ("/api/v1/monitoring/gpu-lock/health", "GPU Lock Health"),
            ("/api/v1/monitoring/statistics", "System Statistics"),
        ]

        try:
            for endpoint, name in endpoints_to_check:
                start_time = time.time()
                try:
                    response = requests.get(f"{self.api_url}{endpoint}", timeout=10)
                    response_time = time.time() - start_time

                    result["endpoints"][name] = {
                        "status_code": response.status_code,
                        "response_time": response_time,
                        "healthy": response.status_code == 200
                    }

                    if response_time > self.thresholds["max_response_time"]:
                        result["issues"].append(f"{name} 响应时间过长: {response_time:.2f}s")

                except requests.exceptions.Timeout:
                    result["endpoints"][name] = {
                        "status_code": 0,
                        "response_time": self.thresholds["max_response_time"],
                        "healthy": False,
                        "error": "请求超时"
                    }
                    result["issues"].append(f"{name} 请求超时")
                except Exception as e:
                    result["endpoints"][name] = {
                        "status_code": 0,
                        "response_time": 0,
                        "healthy": False,
                        "error": str(e)
                    }
                    result["issues"].append(f"{name} 连接失败: {e}")

            # 确定整体状态
            unhealthy_endpoints = [ep for ep in result["endpoints"].values() if not ep.get("healthy", False)]
            if unhealthy_endpoints:
                result["status"] = "unhealthy"
                result["issues"].insert(0, f"{len(unhealthy_endpoints)} 个端点异常")

        except Exception as e:
            result["status"] = "critical"
            result["issues"].append(f"API 检查失败: {e}")

        return result

    def check_service_health(self) -> Dict[str, Any]:
        """检查 WhisperX 服务健康状态"""
        result = {
            "component": "WhisperX Service",
            "status": "healthy",
            "container_status": "",
            "celery_status": {},
            "issues": []
        }

        try:
            # 检查容器状态
            container_result = subprocess.run(
                ['docker-compose', 'ps', 'whisperx_service'],
                capture_output=True, text=True
            )

            if "Up" in container_result.stdout:
                result["container_status"] = "running"
            else:
                result["status"] = "unhealthy"
                result["issues"].append("容器未运行")

            # 检查 Celery 状态
            try:
                celery_result = subprocess.run(
                    ['docker', 'exec', 'whisperx_service', 'celery', '-A', 'app.tasks', 'inspect', 'stats'],
                    capture_output=True, text=True, timeout=10
                )

                if celery_result.returncode == 0:
                    result["celery_status"] = {
                        "status": "healthy",
                        "message": "Celery worker 正常运行"
                    }
                else:
                    result["celery_status"] = {
                        "status": "unhealthy",
                        "message": "Celery worker 异常"
                    }
                    result["issues"].append("Celery worker 状态异常")

            except subprocess.TimeoutExpired:
                result["celery_status"] = {
                    "status": "timeout",
                    "message": "Celery 检查超时"
                }
                result["issues"].append("Celery 检查超时")
            except Exception as e:
                result["celery_status"] = {
                    "status": "error",
                    "message": str(e)
                }
                result["issues"].append(f"Celery 检查失败: {e}")

            # 检查配置加载
            try:
                config_check = subprocess.run(
                    ['docker', 'exec', 'whisperx_service', 'python', '-c',
                     'from services.common.config_loader import CONFIG; '
                     'print("CONFIG_OK"); '
                     'print("FasterWhisper:", CONFIG.get("whisperx_service", {}).get("use_faster_whisper", "N/A"))'],
                    capture_output=True, text=True, timeout=10
                )

                if config_check.returncode == 0 and "CONFIG_OK" in config_check.stdout:
                    result["config_status"] = "healthy"
                else:
                    result["issues"].append("配置加载异常")
                    result["status"] = "unhealthy"

            except Exception as e:
                result["issues"].append(f"配置检查失败: {e}")

            if result["issues"]:
                result["status"] = "unhealthy"

        except Exception as e:
            result["status"] = "critical"
            result["issues"].append(f"服务检查失败: {e}")

        return result

    def check_gpu_health(self) -> Dict[str, Any]:
        """检查 GPU 健康状态"""
        result = {
            "component": "GPU",
            "status": "healthy",
            "memory_used": 0,
            "memory_total": 0,
            "memory_usage_percent": 0,
            "utilization": 0,
            "temperature": 0,
            "issues": []
        }

        try:
            # 获取 GPU 信息
            gpu_info = subprocess.run(
                ['nvidia-smi', '--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu',
                 '--format=csv,noheader,nounits'],
                capture_output=True, text=True
            )

            if gpu_info.returncode == 0:
                values = gpu_info.stdout.strip().split(', ')
                if len(values) >= 4:
                    result["memory_used"] = int(values[0])
                    result["memory_total"] = int(values[1])
                    result["utilization"] = int(values[2])
                    result["temperature"] = int(values[3])
                    result["memory_usage_percent"] = (result["memory_used"] / result["memory_total"]) * 100

                    # 检查阈值
                    if result["memory_usage_percent"] > self.thresholds["max_gpu_memory_usage"]:
                        result["issues"].append(f"GPU 内存使用率过高: {result['memory_usage_percent']:.1f}%")

                    if result["temperature"] > self.thresholds["max_gpu_temperature"]:
                        result["issues"].append(f"GPU 温度过高: {result['temperature']}°C")

                    if result["utilization"] > 95:
                        result["issues"].append(f"GPU 利用率过高: {result['utilization']}%")

            else:
                result["status"] = "unhealthy"
                result["issues"].append("无法获取 GPU 信息")

        except FileNotFoundError:
            result["status"] = "warning"
            result["issues"].append("nvidia-smi 命令未找到，可能无 GPU")
        except Exception as e:
            result["status"] = "unhealthy"
            result["issues"].append(f"GPU 检查失败: {e}")

        if result["issues"]:
            result["status"] = "unhealthy"

        return result

    def check_system_health(self) -> Dict[str, Any]:
        """检查系统资源健康状态"""
        result = {
            "component": "System Resources",
            "status": "healthy",
            "cpu_percent": 0,
            "memory_percent": 0,
            "disk_percent": 0,
            "issues": []
        }

        try:
            import psutil
            result["cpu_percent"] = psutil.cpu_percent()
            result["memory_percent"] = psutil.virtual_memory().percent
            result["disk_percent"] = psutil.disk_usage('/').percent

            # 检查阈值
            if result["memory_percent"] > self.thresholds["max_system_memory"]:
                result["issues"].append(f"系统内存使用率过高: {result['memory_percent']:.1f}%")

            if result["disk_percent"] > self.thresholds["max_disk_usage"]:
                result["issues"].append(f"磁盘使用率过高: {result['disk_percent']:.1f}%")

            if result["cpu_percent"] > 90:
                result["issues"].append(f"CPU 使用率过高: {result['cpu_percent']:.1f}%")

        except ImportError:
            result["status"] = "warning"
            result["issues"].append("psutil 模块未安装")
        except Exception as e:
            result["status"] = "unhealthy"
            result["issues"].append(f"系统检查失败: {e}")

        if result["issues"]:
            result["status"] = "unhealthy"

        return result

    def run_workflow_test(self) -> Dict[str, Any]:
        """运行工作流测试"""
        result = {
            "component": "Workflow Test",
            "status": "healthy",
            "workflow_id": None,
            "execution_time": 0,
            "stages_completed": 0,
            "issues": []
        }

        try:
            # 检查测试文件
            if not os.path.exists(self.test_video):
                result["status"] = "unhealthy"
                result["issues"].append(f"测试文件不存在: {self.test_video}")
                return result

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
                result["status"] = "unhealthy"
                result["issues"].append(f"工作流提交失败: {response.status_code}")
                return result

            workflow_id = response.json().get('workflow_id')
            result["workflow_id"] = workflow_id

            # 监控执行
            start_time = time.time()
            while time.time() - start_time < self.thresholds["max_workflow_time"]:
                try:
                    status_response = requests.get(f"{self.api_url}/v1/workflows/status/{workflow_id}")
                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        current_status = status_data.get('status')

                        if current_status == 'SUCCESS':
                            result["execution_time"] = time.time() - start_time
                            result["stages_completed"] = len(status_data.get('stages', {}))
                            break
                        elif current_status == 'FAILED':
                            result["status"] = "unhealthy"
                            result["issues"].append("工作流执行失败")
                            break

                except Exception as e:
                    result["issues"].append(f"状态检查失败: {e}")
                    break

                time.sleep(5)

            if time.time() - start_time >= self.thresholds["max_workflow_time"]:
                result["status"] = "unhealthy"
                result["issues"].append("工作流执行超时")

        except Exception as e:
            result["status"] = "critical"
            result["issues"].append(f"工作流测试失败: {e}")

        return result

    def run_comprehensive_health_check(self) -> Dict[str, Any]:
        """运行全面的健康检查"""
        print("开始 WhisperX 全面健康检查...")
        print(f"检查时间: {datetime.now()}")
        print("=" * 60)

        health_report = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "healthy",
            "checks": [],
            "summary": {
                "total_checks": 0,
                "healthy_checks": 0,
                "unhealthy_checks": 0,
                "critical_issues": 0
            }
        }

        # 运行各项检查
        checks = [
            ("API Health", self.check_api_health),
            ("Service Health", self.check_service_health),
            ("GPU Health", self.check_gpu_health),
            ("System Health", self.check_system_health),
            ("Workflow Test", self.run_workflow_test)
        ]

        for check_name, check_func in checks:
            print(f"\n检查 {check_name}...")
            try:
                check_result = check_func()
                check_result["check_name"] = check_name
                health_report["checks"].append(check_result)

                # 更新摘要
                health_report["summary"]["total_checks"] += 1
                if check_result["status"] == "healthy":
                    health_report["summary"]["healthy_checks"] += 1
                    print(f"  ✅ {check_name}: 健康")
                elif check_result["status"] == "unhealthy":
                    health_report["summary"]["unhealthy_checks"] += 1
                    print(f"  ⚠️ {check_name}: 不健康")
                    for issue in check_result.get("issues", []):
                        print(f"     - {issue}")
                elif check_result["status"] == "critical":
                    health_report["summary"]["critical_issues"] += 1
                    print(f"  ❌ {check_name}: 严重问题")
                elif check_result["status"] == "warning":
                    print(f"  ⚠️ {check_name}: 警告")

            except Exception as e:
                error_result = {
                    "check_name": check_name,
                    "component": check_name,
                    "status": "critical",
                    "issues": [f"检查失败: {e}"]
                }
                health_report["checks"].append(error_result)
                health_report["summary"]["total_checks"] += 1
                health_report["summary"]["critical_issues"] += 1
                print(f"  ❌ {check_name}: 检查异常 - {e}")

        # 确定整体状态
        if health_report["summary"]["critical_issues"] > 0:
            health_report["overall_status"] = "critical"
        elif health_report["summary"]["unhealthy_checks"] > 0:
            health_report["overall_status"] = "unhealthy"
        elif health_report["summary"]["healthy_checks"] == health_report["summary"]["total_checks"]:
            health_report["overall_status"] = "healthy"
        else:
            health_report["overall_status"] = "warning"

        # 保存报告
        self.save_health_report(health_report)

        # 输出摘要
        self.print_health_summary(health_report)

        return health_report

    def save_health_report(self, report: Dict[str, Any]):
        """保存健康检查报告"""
        os.makedirs(os.path.dirname(self.report_file), exist_ok=True)

        with open(self.report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"\n健康检查报告已保存到: {self.report_file}")

    def print_health_summary(self, report: Dict[str, Any]):
        """打印健康检查摘要"""
        print("\n" + "=" * 60)
        print("健康检查摘要")
        print("=" * 60)

        summary = report["summary"]
        print(f"总体状态: {report['overall_status'].upper()}")
        print(f"检查项目: {summary['total_checks']}")
        print(f"健康项目: {summary['healthy_checks']}")
        print(f"问题项目: {summary['unhealthy_checks']}")
        print(f"严重问题: {summary['critical_issues']}")

        # 输出建议
        print("\n建议操作:")
        if report["overall_status"] == "critical":
            print("🚨 立即检查系统状态，可能需要重启服务")
        elif report["overall_status"] == "unhealthy":
            print("⚠️ 检查问题项目并修复")
        elif report["overall_status"] == "warning":
            print("ℹ️ 监控警告项目，预防问题发生")
        else:
            print("✅ 系统运行正常，继续保持监控")

    def run_monitoring_mode(self, interval: int = 300):
        """运行监控模式"""
        print(f"开始监控模式，检查间隔: {interval} 秒")

        try:
            while True:
                print(f"\n{'='*60}")
                print(f"监控检查 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print('='*60)

                report = self.run_comprehensive_health_check()

                # 如果有严重问题，发送警报
                if report["overall_status"] == "critical":
                    print("\n🚨 检测到严重问题！需要立即处理！")

                print(f"\n等待 {interval} 秒后进行下一次检查...")
                time.sleep(interval)

        except KeyboardInterrupt:
            print("\n监控已停止")
        except Exception as e:
            print(f"\n监控模式出错: {e}")

def main():
    parser = argparse.ArgumentParser(description="WhisperX 健康检查工具")
    parser.add_argument("--mode", choices=["check", "monitor"], default="check",
                       help="运行模式: check (单次检查) 或 monitor (持续监控)")
    parser.add_argument("--interval", type=int, default=300,
                       help="监控模式下的检查间隔（秒）")

    args = parser.parse_args()

    checker = WhisperXHealthChecker()

    if args.mode == "monitor":
        checker.run_monitoring_mode(args.interval)
    else:
        report = checker.run_comprehensive_health_check()
        # 返回适当的退出码
        if report["overall_status"] == "critical":
            exit(2)
        elif report["overall_status"] == "unhealthy":
            exit(1)
        else:
            exit(0)

if __name__ == "__main__":
    main()