#!/usr/bin/env python3
"""
监控系统安装和配置脚本
自动设置 Prometheus, Grafana, AlertManager 等监控组件
"""

import os
import sys
import subprocess
import shutil
import json
import yaml
from pathlib import Path

def print_step(step: str, description: str):
    """打印步骤信息"""
    print(f"\n=== {step} ===")
    print(description)

def run_command(cmd: str, description: str = None) -> bool:
    """执行命令"""
    if description:
        print(f"执行: {description}")
    print(f"命令: {cmd}")

    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"执行失败: {e}")
        if e.stderr:
            print(f"错误信息: {e.stderr}")
        return False

def create_directories():
    """创建必要的目录"""
    print_step("1", "创建监控目录结构")

    directories = [
        "monitoring",
        "monitoring/prometheus",
        "monitoring/grafana/datasources",
        "monitoring/grafana/dashboards",
        "monitoring/rules",
        "logs/monitoring"
    ]

    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"✓ 创建目录: {directory}")

def generate_prometheus_config():
    """生成 Prometheus 配置"""
    print_step("2", "生成 Prometheus 配置")

    config = {
        'global': {
            'scrape_interval': '15s',
            'evaluation_interval': '15s'
        },
        'scrape_configs': [
            {
                'job_name': 'prometheus',
                'static_configs': [{'targets': ['localhost:9090']}]
            },
            {
                'job_name': 'redis',
                'static_configs': [{'targets': ['redis:6379']}]
            },
            {
                'job_name': 'whisperx_service',
                'static_configs': [{'targets': ['whisperx_service:8080']}],
                'metrics_path': '/metrics',
                'scrape_interval': '30s'
            },
            {
                'job_name': 'api_gateway',
                'static_configs': [{'targets': ['api_gateway:8788']}],
                'metrics_path': '/metrics',
                'scrape_interval': '15s'
            },
            {
                'job_name': 'node_exporter',
                'static_configs': [{'targets': ['node_exporter:9100']}],
                'scrape_interval': '15s'
            }
        ],
        'alerting': {
            'alertmanagers': [
                {
                    'static_configs': [{'targets': ['alertmanager:9093']}]
                }
            ]
        },
        'rule_files': ['rules/*.yml']
    }

    with open('monitoring/prometheus.yml', 'w') as f:
        yaml.dump(config, f, default_flow_style=False)

    print("✓ 生成配置文件: monitoring/prometheus.yml")

def generate_grafana_config():
    """生成 Grafana 配置"""
    print_step("3", "生成 Grafana 配置")

    # 数据源配置
    datasource_config = {
        'apiVersion': 1,
        'datasources': [
            {
                'id': 1,
                'orgId': 1,
                'name': 'Prometheus',
                'type': 'prometheus',
                'access': 'proxy',
                'url': 'http://prometheus:9090',
                'basicAuth': False,
                'isDefault': True
            },
            {
                'id': 2,
                'orgId': 1,
                'name': 'Redis',
                'type': 'redis-datasource',
                'access': 'proxy',
                'url': 'redis:6379',
                'basicAuth': False,
                'isDefault': False
            }
        ]
    }

    with open('monitoring/grafana/datasources/datasources.yml', 'w') as f:
        yaml.dump(datasource_config, f, default_flow_style=False)

    # 仪表板配置
    dashboard_config = {
        'apiVersion': 1,
        'providers': [
            {
                'name': 'default',
                'orgId': 1,
                'folder': '',
                'type': 'file',
                'disableDeletion': False,
                'updateIntervalSeconds': 10,
                'allowUiUpdates': True,
                'options': {
                    'path': '/etc/grafana/provisioning/dashboards'
                }
            }
        ]
    }

    with open('monitoring/grafana/dashboards/dashboards.yml', 'w') as f:
        yaml.dump(dashboard_config, f, default_flow_style=False)

    print("✓ 生成 Grafana 配置文件")

def generate_alert_rules():
    """生成告警规则"""
    print_step("4", "生成告警规则")

    # WhisperX 告警规则
    whisperx_alerts = {
        'groups': [
            {
                'name': 'whisperx.alerts',
                'rules': [
                    {
                        'alert': 'WhisperxExecutionTimeHigh',
                        'expr': 'whisperx_execution_time_seconds > 300',
                        'for': '5m',
                        'labels': {
                            'severity': 'warning',
                            'service': 'whisperx'
                        },
                        'annotations': {
                            'summary': 'WhisperX 执行时间过长',
                            'description': 'WhisperX 工作流执行时间超过 5 分钟 (当前值: {{ $value }} 秒)'
                        }
                    },
                    {
                        'alert': 'WhisperxGpuMemoryHigh',
                        'expr': 'gpu_memory_used_gb > 8',
                        'for': '5m',
                        'labels': {
                            'severity': 'warning',
                            'service': 'whisperx'
                        },
                        'annotations': {
                            'summary': 'GPU 显存使用过高',
                            'description': 'GPU 显存使用超过 8GB (当前值: {{ $value }} GB)'
                        }
                    }
                ]
            }
        ]
    }

    with open('monitoring/rules/whisperx_alerts.yml', 'w') as f:
        yaml.dump(whisperx_alerts, f, default_flow_style=False)

    # 系统告警规则
    system_alerts = {
        'groups': [
            {
                'name': 'system.alerts',
                'rules': [
                    {
                        'alert': 'HighCpuUsage',
                        'expr': '100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80',
                        'for': '5m',
                        'labels': {
                            'severity': 'warning',
                            'service': 'system'
                        },
                        'annotations': {
                            'summary': 'CPU 使用率过高',
                            'description': 'CPU 使用率超过 80% (当前值: {{ $value }}%)'
                        }
                    },
                    {
                        'alert': 'HighMemoryUsage',
                        'expr': '100 - ((node_memory_MemAvailable_bytes + node_memory_Cached_bytes + node_memory_Buffers_bytes) / node_memory_MemTotal_bytes * 100) > 85',
                        'for': '5m',
                        'labels': {
                            'severity': 'warning',
                            'service': 'system'
                        },
                        'annotations': {
                            'summary': '内存使用率过高',
                            'description': '内存使用率超过 85% (当前值: {{ $value }}%)'
                        }
                    }
                ]
            }
        ]
    }

    with open('monitoring/rules/system_alerts.yml', 'w') as f:
        yaml.dump(system_alerts, f, default_flow_style=False)

    print("✓ 生成告警规则文件")

def update_docker_compose():
    """更新 Docker Compose 配置"""
    print_step("5", "更新 Docker Compose 配置")

    # 检查是否已经包含监控配置
    if os.path.exists('docker-compose.yml'):
        with open('docker-compose.yml', 'r') as f:
            content = f.read()
            if 'prometheus:' in content:
                print("✓ Docker Compose 已包含监控配置")
                return

    # 创建扩展配置文件
    monitoring_compose = """
# 监控服务扩展配置
# 将此配置合并到主 docker-compose.yml 中

services:
  # Prometheus 时序数据库
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - ./monitoring/rules:/etc/prometheus/rules
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
      - '--web.enable-lifecycle'
    restart: unless-stopped
    networks:
      - default

  # Grafana 可视化界面
  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "3000:3000"
    volumes:
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - grafana_data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
      - GF_INSTALL_PLUGINS=redis-datasource
    restart: unless-stopped
    networks:
      - default

  # AlertManager 告警管理
  alertmanager:
    image: prom/alertmanager:latest
    container_name: alertmanager
    ports:
      - "9093:9093"
    volumes:
      - ./monitoring/alertmanager.yml:/etc/alertmanager/alertmanager.yml
      - alertmanager_data:/alertmanager
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
      - '--storage.path=/alertmanager'
    restart: unless-stopped
    networks:
      - default

  # Node Exporter 系统指标收集
  node_exporter:
    image: prom/node-exporter:latest
    container_name: node_exporter
    ports:
      - "9100:9100"
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.rootfs=/rootfs'
      - '--path.sysfs=/host/sys'
      - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'
    restart: unless-stopped
    networks:
      - default

  # Redis Exporter Redis 指标收集
  redis_exporter:
    image: oliver006/redis_exporter:latest
    container_name: redis_exporter
    ports:
      - "9121:9121"
    environment:
      - REDIS_ADDR=redis:6379
    restart: unless-stopped
    networks:
      - default

volumes:
  prometheus_data:
  grafana_data:
  alertmanager_data:
"""

    with open('docker-compose.monitoring.yml', 'w') as f:
        f.write(monitoring_compose)

    print("✓ 创建监控配置文件: docker-compose.monitoring.yml")

def setup_grafana_dashboard():
    """设置 Grafana 仪表板"""
    print_step("6", "设置 Grafana 仪表板")

    dashboard = {
        "dashboard": {
            "id": None,
            "title": "WhisperX 性能监控",
            "tags": ["whisperx", "performance"],
            "timezone": "Asia/Shanghai",
            "panels": [
                {
                    "id": 1,
                    "title": "工作流执行时间",
                    "type": "timeseries",
                    "targets": [
                        {
                            "expr": "rate(whisperx_execution_time_seconds_sum[5m]) / rate(whisperx_execution_time_seconds_count[5m])",
                            "legendFormat": "{{backend_type}} - {{status}}"
                        }
                    ],
                    "yAxes": [
                        {"label": "执行时间 (秒)", "min": 0},
                        {"label": "", "min": None}
                    ]
                },
                {
                    "id": 2,
                    "title": "GPU 利用率",
                    "type": "timeseries",
                    "targets": [
                        {
                            "expr": "gpu_utilization_percent",
                            "legendFormat": "GPU 利用率"
                        }
                    ],
                    "yAxes": [
                        {"label": "利用率 (%)", "min": 0, "max": 100},
                        {"label": "", "min": None}
                    ]
                },
                {
                    "id": 3,
                    "title": "成功率",
                    "type": "stat",
                    "targets": [
                        {
                            "expr": "sum(rate(whisperx_workflows_total{status=\"success\"}[5m])) / sum(rate(whisperx_workflows_total[5m])) * 100",
                            "legendFormat": "成功率"
                        }
                    ],
                    "fieldConfig": {
                        "defaults": {
                            "unit": "percent",
                            "min": 0,
                            "max": 100,
                            "thresholds": {
                                "steps": [
                                    {"color": "red", "value": 0},
                                    {"color": "yellow", "value": 80},
                                    {"color": "green", "value": 95}
                                ]
                            }
                        }
                    }
                }
            ],
            "time": {
                "from": "now-1h",
                "to": "now"
            },
            "refresh": "30s"
        }
    }

    with open('monitoring/grafana/dashboards/whisperx_dashboard.json', 'w') as f:
        json.dump(dashboard, f, indent=2)

    print("✓ 创建 Grafana 仪表板")

def create_startup_script():
    """创建启动脚本"""
    print_step("7", "创建启动脚本")

    startup_script = """#!/bin/bash
# 监控系统启动脚本

echo "启动 WhisperX 监控系统..."

# 启动监控服务
docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d prometheus grafana alertmanager node_exporter redis_exporter

echo "等待服务启动..."
sleep 30

# 检查服务状态
echo "检查服务状态..."
docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml ps

echo "监控系统启动完成!"
echo "访问地址:"
echo "- Prometheus: http://localhost:9090"
echo "- Grafana: http://localhost:3000 (admin/admin)"
echo "- AlertManager: http://localhost:9093"
"""

    with open('scripts/start_monitoring.sh', 'w') as f:
        f.write(startup_script)

    # 设置执行权限
    os.chmod('scripts/start_monitoring.sh', 0o755)

    print("✓ 创建启动脚本: scripts/start_monitoring.sh")

def main():
    """主函数"""
    print("=== WhisperX 监控系统安装向导 ===")

    try:
        create_directories()
        generate_prometheus_config()
        generate_grafana_config()
        generate_alert_rules()
        update_docker_compose()
        setup_grafana_dashboard()
        create_startup_script()

        print("\n=== 安装完成 ===")
        print("请执行以下步骤完成安装:")
        print("1. 运行启动脚本: bash scripts/start_monitoring.sh")
        print("2. 访问 Grafana: http://localhost:3000")
        print("3. 访问 Prometheus: http://localhost:9090")
        print("4. 配置告警通知 (修改 monitoring/alertmanager.yml)")

    except Exception as e:
        print(f"\n安装失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()