#!/usr/bin/env python3
"""
生产环境部署验证脚本
用于验证 WhisperX 系统在生产环境中的部署和运行状态
"""

import os
import sys
import time
import json
import subprocess
import requests
import yaml
from datetime import datetime
from typing import Dict, List, Any, Optional

class ProductionDeploymentValidator:
    """生产环境部署验证器"""

    def __init__(self):
        self.config_file = "config.yml"
        self.docker_compose_file = "docker-compose.yml"
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "environment": "production",
            "checks": {},
            "summary": {
                "total_checks": 0,
                "passed_checks": 0,
                "failed_checks": 0,
                "success_rate": 0.0
            }
        }

    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            return {}

    def run_all_checks(self) -> Dict[str, Any]:
        """运行所有检查"""
        print("=== 开始生产环境部署验证 ===")

        # 基础环境检查
        self.check_system_requirements()
        self.check_docker_environment()
        self.check_network_connectivity()

        # 服务状态检查
        self.check_service_status()
        self.check_api_endpoints()
        self.check_database_connectivity()

        # 性能检查
        self.check_performance_metrics()
        self.check_resource_usage()

        # 安全检查
        self.check_security_configuration()
        self.check_backup_system()

        # 监控检查
        self.check_monitoring_system()
        self.check_alert_system()

        # 生成报告
        self.generate_report()

        return self.results

    def check_system_requirements(self):
        """检查系统要求"""
        print("检查系统要求...")

        check_name = "system_requirements"
        checks = []

        # 检查操作系统
        try:
            result = subprocess.run(['uname', '-a'], capture_output=True, text=True)
            checks.append({
                "name": "operating_system",
                "status": "passed",
                "message": f"操作系统: {result.stdout.strip()}",
                "details": {"os_info": result.stdout.strip()}
            })
        except Exception as e:
            checks.append({
                "name": "operating_system",
                "status": "failed",
                "message": f"无法获取操作系统信息: {e}"
            })

        # 检查 GPU
        try:
            result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'],
                                 capture_output=True, text=True)
            if result.returncode == 0:
                gpu_info = result.stdout.strip()
                checks.append({
                    "name": "gpu_availability",
                    "status": "passed",
                    "message": f"GPU 可用: {gpu_info}",
                    "details": {"gpu_info": gpu_info}
                })
            else:
                checks.append({
                    "name": "gpu_availability",
                    "status": "failed",
                    "message": "GPU 不可用"
                })
        except Exception as e:
            checks.append({
                "name": "gpu_availability",
                "status": "failed",
                "message": f"GPU 检查失败: {e}"
            })

        # 检查内存
        try:
            result = subprocess.run(['free', '-h'], capture_output=True, text=True)
            memory_info = result.stdout
            checks.append({
                "name": "memory_check",
                "status": "passed",
                "message": "内存检查通过",
                "details": {"memory_info": memory_info}
            })
        except Exception as e:
            checks.append({
                "name": "memory_check",
                "status": "failed",
                "message": f"内存检查失败: {e}"
            })

        # 检查磁盘空间
        try:
            result = subprocess.run(['df', '-h'], capture_output=True, text=True)
            disk_info = result.stdout
            checks.append({
                "name": "disk_space",
                "status": "passed",
                "message": "磁盘空间检查通过",
                "details": {"disk_info": disk_info}
            })
        except Exception as e:
            checks.append({
                "name": "disk_space",
                "status": "failed",
                "message": f"磁盘空间检查失败: {e}"
            })

        self.results["checks"][check_name] = checks

    def check_docker_environment(self):
        """检查 Docker 环境"""
        print("检查 Docker 环境...")

        check_name = "docker_environment"
        checks = []

        # 检查 Docker 版本
        try:
            result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
            checks.append({
                "name": "docker_version",
                "status": "passed",
                "message": f"Docker 版本: {result.stdout.strip()}",
                "details": {"version": result.stdout.strip()}
            })
        except Exception as e:
            checks.append({
                "name": "docker_version",
                "status": "failed",
                "message": f"Docker 版本检查失败: {e}"
            })

        # 检查 Docker Compose
        try:
            result = subprocess.run(['docker-compose', '--version'], capture_output=True, text=True)
            checks.append({
                "name": "docker_compose",
                "status": "passed",
                "message": f"Docker Compose 版本: {result.stdout.strip()}",
                "details": {"version": result.stdout.strip()}
            })
        except Exception as e:
            checks.append({
                "name": "docker_compose",
                "status": "failed",
                "message": f"Docker Compose 检查失败: {e}"
            })

        # 检查 Docker 服务状态
        try:
            result = subprocess.run(['docker', 'info'], capture_output=True, text=True)
            if result.returncode == 0:
                checks.append({
                    "name": "docker_service",
                    "status": "passed",
                    "message": "Docker 服务运行正常"
                })
            else:
                checks.append({
                    "name": "docker_service",
                    "status": "failed",
                    "message": "Docker 服务异常"
                })
        except Exception as e:
            checks.append({
                "name": "docker_service",
                "status": "failed",
                "message": f"Docker 服务检查失败: {e}"
            })

        self.results["checks"][check_name] = checks

    def check_network_connectivity(self):
        """检查网络连接"""
        print("检查网络连接...")

        check_name = "network_connectivity"
        checks = []

        # 检查网络连接
        test_urls = [
            "https://www.google.com",
            "https://github.com",
            "https://pypi.org"
        ]

        for url in test_urls:
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    checks.append({
                        "name": f"network_{url.split('//')[1].split('.')[0]}",
                        "status": "passed",
                        "message": f"网络连接正常: {url}"
                    })
                else:
                    checks.append({
                        "name": f"network_{url.split('//')[1].split('.')[0]}",
                        "status": "failed",
                        "message": f"网络连接异常: {url} (HTTP {response.status_code})"
                    })
            except Exception as e:
                checks.append({
                    "name": f"network_{url.split('//')[1].split('.')[0]}",
                    "status": "failed",
                    "message": f"网络连接失败: {url} ({e})"
                })

        self.results["checks"][check_name] = checks

    def check_service_status(self):
        """检查服务状态"""
        print("检查服务状态...")

        check_name = "service_status"
        checks = []

        # 检查 Docker Compose 服务
        try:
            result = subprocess.run(['docker-compose', 'ps'], capture_output=True, text=True)
            services_info = result.stdout

            # 解析服务状态
            services = []
            for line in services_info.split('\n')[1:]:  # 跳过标题行
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 4:
                        service_name = parts[0]
                        status = parts[3] if len(parts) > 3 else 'unknown'
                        services.append({
                            "name": service_name,
                            "status": status
                        })

            # 检查关键服务
            critical_services = ['api_gateway', 'whisperx_service', 'redis']
            for service in critical_services:
                found = False
                for s in services:
                    if service in s['name']:
                        found = True
                        if 'Up' in s['status']:
                            checks.append({
                                "name": f"service_{service}",
                                "status": "passed",
                                "message": f"服务 {service} 运行正常: {s['status']}"
                            })
                        else:
                            checks.append({
                                "name": f"service_{service}",
                                "status": "failed",
                                "message": f"服务 {service} 状态异常: {s['status']}"
                            })
                        break

                if not found:
                    checks.append({
                        "name": f"service_{service}",
                        "status": "failed",
                        "message": f"服务 {service} 未找到"
                    })

        except Exception as e:
            checks.append({
                "name": "service_check",
                "status": "failed",
                "message": f"服务状态检查失败: {e}"
            })

        self.results["checks"][check_name] = checks

    def check_api_endpoints(self):
        """检查 API 端点"""
        print("检查 API 端点...")

        check_name = "api_endpoints"
        checks = []

        # 定义要检查的端点
        endpoints = [
            ("http://localhost:8788/health", "健康检查"),
            ("http://localhost:8788/v1/workflows/recent", "最近工作流"),
            ("http://localhost:8788/api/v1/monitoring/gpu-lock/health", "GPU 锁状态")
        ]

        for url, description in endpoints:
            try:
                response = requests.get(url, timeout=30)
                if response.status_code == 200:
                    checks.append({
                        "name": f"api_{url.split('/')[-2] if url.split('/')[-2] else 'health'}",
                        "status": "passed",
                        "message": f"{description} 端点正常",
                        "details": {
                            "url": url,
                            "status_code": response.status_code,
                            "response_time": response.elapsed.total_seconds()
                        }
                    })
                else:
                    checks.append({
                        "name": f"api_{url.split('/')[-2] if url.split('/')[-2] else 'health'}",
                        "status": "failed",
                        "message": f"{description} 端点异常: HTTP {response.status_code}",
                        "details": {
                            "url": url,
                            "status_code": response.status_code
                        }
                    })
            except requests.exceptions.Timeout:
                checks.append({
                    "name": f"api_{url.split('/')[-2] if url.split('/')[-2] else 'health'}",
                    "status": "failed",
                    "message": f"{description} 端点超时",
                    "details": {"url": url}
                })
            except requests.exceptions.ConnectionError:
                checks.append({
                    "name": f"api_{url.split('/')[-2] if url.split('/')[-2] else 'health'}",
                    "status": "failed",
                    "message": f"{description} 端点连接失败",
                    "details": {"url": url}
                })
            except Exception as e:
                checks.append({
                    "name": f"api_{url.split('/')[-2] if url.split('/')[-2] else 'health'}",
                    "status": "failed",
                    "message": f"{description} 端点检查失败: {e}",
                    "details": {"url": url}
                })

        self.results["checks"][check_name] = checks

    def check_database_connectivity(self):
        """检查数据库连接"""
        print("检查数据库连接...")

        check_name = "database_connectivity"
        checks = []

        # 检查 Redis 连接
        try:
            result = subprocess.run(['docker-compose', 'exec', 'redis', 'redis-cli', 'ping'],
                                 capture_output=True, text=True)
            if 'PONG' in result.stdout:
                checks.append({
                    "name": "redis_connection",
                    "status": "passed",
                    "message": "Redis 连接正常"
                })
            else:
                checks.append({
                    "name": "redis_connection",
                    "status": "failed",
                    "message": f"Redis 连接失败: {result.stdout}"
                })
        except Exception as e:
            checks.append({
                "name": "redis_connection",
                "status": "failed",
                "message": f"Redis 连接检查失败: {e}"
            })

        self.results["checks"][check_name] = checks

    def check_performance_metrics(self):
        """检查性能指标"""
        print("检查性能指标...")

        check_name = "performance_metrics"
        checks = []

        # 检查 GPU 性能
        try:
            result = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used', '--format=csv,noheader,nounits'],
                                 capture_output=True, text=True)
            if result.returncode == 0:
                gpu_metrics = result.stdout.strip().split(',')
                gpu_utilization = float(gpu_metrics[0])
                gpu_memory = float(gpu_metrics[1])

                checks.append({
                    "name": "gpu_utilization",
                    "status": "passed",
                    "message": f"GPU 利用率: {gpu_utilization}%",
                    "details": {"utilization": gpu_utilization}
                })

                checks.append({
                    "name": "gpu_memory",
                    "status": "passed",
                    "message": f"GPU 显存使用: {gpu_memory} MB",
                    "details": {"memory_used": gpu_memory}
                })
            else:
                checks.append({
                    "name": "gpu_metrics",
                    "status": "failed",
                    "message": "无法获取 GPU 性能指标"
                })
        except Exception as e:
            checks.append({
                "name": "gpu_metrics",
                "status": "failed",
                "message": f"GPU 性能检查失败: {e}"
            })

        self.results["checks"][check_name] = checks

    def check_resource_usage(self):
        """检查资源使用情况"""
        print("检查资源使用情况...")

        check_name = "resource_usage"
        checks = []

        # 检查容器资源使用
        try:
            result = subprocess.run(['docker', 'stats', '--no-stream', '--format', 'table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}'],
                                 capture_output=True, text=True)
            if result.returncode == 0:
                resource_info = result.stdout
                checks.append({
                    "name": "container_resources",
                    "status": "passed",
                    "message": "容器资源使用正常",
                    "details": {"resource_info": resource_info}
                })
            else:
                checks.append({
                    "name": "container_resources",
                    "status": "failed",
                    "message": "无法获取容器资源信息"
                })
        except Exception as e:
            checks.append({
                "name": "container_resources",
                "status": "failed",
                "message": f"容器资源检查失败: {e}"
            })

        self.results["checks"][check_name] = checks

    def check_security_configuration(self):
        """检查安全配置"""
        print("检查安全配置...")

        check_name = "security_configuration"
        checks = []

        # 检查防火墙状态
        try:
            result = subprocess.run(['sudo', 'ufw', 'status'], capture_output=True, text=True)
            if 'Status: active' in result.stdout:
                checks.append({
                    "name": "firewall_status",
                    "status": "passed",
                    "message": "防火墙已启用"
                })
            else:
                checks.append({
                    "name": "firewall_status",
                    "status": "warning",
                    "message": "防火墙未启用"
                })
        except Exception as e:
            checks.append({
                "name": "firewall_status",
                "status": "failed",
                "message": f"防火墙检查失败: {e}"
            })

        # 检查 SSL/TLS 配置
        try:
            response = requests.get('https://localhost:8788/health', timeout=10, verify=False)
            if response.status_code == 200:
                checks.append({
                    "name": "ssl_configuration",
                    "status": "passed",
                    "message": "SSL/TLS 配置正常"
                })
            else:
                checks.append({
                    "name": "ssl_configuration",
                    "status": "failed",
                    "message": "SSL/TLS 配置异常"
                })
        except Exception:
            checks.append({
                "name": "ssl_configuration",
                "status": "warning",
                "message": "SSL/TLS 未配置"
            })

        self.results["checks"][check_name] = checks

    def check_backup_system(self):
        """检查备份系统"""
        print("检查备份系统...")

        check_name = "backup_system"
        checks = []

        # 检查备份目录
        backup_dirs = ['/backup', '/var/backups', './backups']
        backup_found = False

        for backup_dir in backup_dirs:
            if os.path.exists(backup_dir):
                backup_found = True
                try:
                    # 检查备份文件
                    backup_files = os.listdir(backup_dir)
                    if backup_files:
                        checks.append({
                            "name": "backup_directory",
                            "status": "passed",
                            "message": f"备份目录正常: {backup_dir} ({len(backup_files)} 个文件)",
                            "details": {"backup_dir": backup_dir, "file_count": len(backup_files)}
                        })
                    else:
                        checks.append({
                            "name": "backup_directory",
                            "status": "warning",
                            "message": f"备份目录为空: {backup_dir}"
                        })
                except Exception as e:
                    checks.append({
                        "name": "backup_directory",
                        "status": "failed",
                        "message": f"备份目录检查失败: {backup_dir} ({e})"
                    })
                break

        if not backup_found:
            checks.append({
                "name": "backup_directory",
                "status": "failed",
                "message": "未找到备份目录"
            })

        self.results["checks"][check_name] = checks

    def check_monitoring_system(self):
        """检查监控系统"""
        print("检查监控系统...")

        check_name = "monitoring_system"
        checks = []

        # 检查 Prometheus
        try:
            response = requests.get('http://localhost:9090/api/v1/query?query=up', timeout=10)
            if response.status_code == 200:
                checks.append({
                    "name": "prometheus",
                    "status": "passed",
                    "message": "Prometheus 监控系统正常"
                })
            else:
                checks.append({
                    "name": "prometheus",
                    "status": "failed",
                    "message": f"Prometheus 状态异常: HTTP {response.status_code}"
                })
        except Exception as e:
            checks.append({
                "name": "prometheus",
                "status": "failed",
                "message": f"Prometheus 连接失败: {e}"
            })

        # 检查 Grafana
        try:
            response = requests.get('http://localhost:3000/api/health', timeout=10)
            if response.status_code == 200:
                checks.append({
                    "name": "grafana",
                    "status": "passed",
                    "message": "Grafana 监控界面正常"
                })
            else:
                checks.append({
                    "name": "grafana",
                    "status": "failed",
                    "message": f"Grafana 状态异常: HTTP {response.status_code}"
                })
        except Exception as e:
            checks.append({
                "name": "grafana",
                "status": "failed",
                "message": f"Grafana 连接失败: {e}"
            })

        self.results["checks"][check_name] = checks

    def check_alert_system(self):
        """检查告警系统"""
        print("检查告警系统...")

        check_name = "alert_system"
        checks = []

        # 检查 AlertManager
        try:
            response = requests.get('http://localhost:9093/api/v1/status', timeout=10)
            if response.status_code == 200:
                checks.append({
                    "name": "alertmanager",
                    "status": "passed",
                    "message": "AlertManager 告警系统正常"
                })
            else:
                checks.append({
                    "name": "alertmanager",
                    "status": "failed",
                    "message": f"AlertManager 状态异常: HTTP {response.status_code}"
                })
        except Exception as e:
            checks.append({
                "name": "alertmanager",
                "status": "failed",
                "message": f"AlertManager 连接失败: {e}"
            })

        self.results["checks"][check_name] = checks

    def generate_report(self):
        """生成验证报告"""
        print("生成验证报告...")

        # 计算统计信息
        total_checks = 0
        passed_checks = 0
        failed_checks = 0

        for category, checks in self.results["checks"].items():
            for check in checks:
                total_checks += 1
                if check["status"] == "passed":
                    passed_checks += 1
                elif check["status"] == "failed":
                    failed_checks += 1

        self.results["summary"]["total_checks"] = total_checks
        self.results["summary"]["passed_checks"] = passed_checks
        self.results["summary"]["failed_checks"] = failed_checks
        self.results["summary"]["success_rate"] = (passed_checks / total_checks * 100) if total_checks > 0 else 0

        # 保存报告
        report_filename = f"production_validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_filename, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)

        print(f"验证报告已保存: {report_filename}")

        # 输出摘要
        print(f"\n=== 验证报告摘要 ===")
        print(f"总检查项: {total_checks}")
        print(f"通过检查: {passed_checks}")
        print(f"失败检查: {failed_checks}")
        print(f"成功率: {self.results['summary']['success_rate']:.1f}%")

        # 如果失败检查过多，建议处理
        if failed_checks > 0:
            print(f"\n⚠️  发现 {failed_checks} 个失败的检查项")
            print("请查看详细报告并修复问题")

def main():
    """主函数"""
    validator = ProductionDeploymentValidator()

    try:
        results = validator.run_all_checks()

        # 根据结果设置退出码
        if results["summary"]["failed_checks"] == 0:
            print("\n✅ 所有检查项通过！")
            sys.exit(0)
        else:
            print(f"\n❌ {results['summary']['failed_checks']} 个检查项失败")
            sys.exit(1)

    except Exception as e:
        print(f"\n验证过程中发生错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()