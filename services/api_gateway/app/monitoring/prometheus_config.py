#!/usr/bin/env python3
"""
Prometheus 监控配置
用于集成 Prometheus + Grafana 监控系统
"""

import os
import yaml
from typing import Dict, Any

class PrometheusConfig:
    """Prometheus 配置生成器"""

    def __init__(self):
        self.config = self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'global': {
                'scrape_interval': '15s',
                'evaluation_interval': '15s'
            },
            'scrape_configs': [
                {
                    'job_name': 'prometheus',
                    'static_configs': [
                        {'targets': ['localhost:9090']}
                    ]
                },
                {
                    'job_name': 'redis',
                    'static_configs': [
                        {'targets': ['redis:6379']}
                    ]
                },
                {
                    'job_name': 'whisperx_service',
                    'static_configs': [
                        {'targets': ['whisperx_service:8080']}
                    ],
                    'metrics_path': '/metrics',
                    'scrape_interval': '30s'
                },
                {
                    'job_name': 'api_gateway',
                    'static_configs': [
                        {'targets': ['api_gateway:8788']}
                    ],
                    'metrics_path': '/metrics',
                    'scrape_interval': '15s'
                },
                {
                    'job_name': 'node_exporter',
                    'static_configs': [
                        {'targets': ['node_exporter:9100']}
                    ],
                    'scrape_interval': '15s'
                }
            ],
            'alerting': {
                'alertmanagers': [
                    {
                        'static_configs': [
                            {'targets': ['alertmanager:9093']}
                        ]
                    }
                ]
            },
            'rule_files': [
                'rules/whisperx_alerts.yml',
                'rules/system_alerts.yml'
            ]
        }

    def generate_config(self, output_path: str = '/etc/prometheus/prometheus.yml'):
        """生成 Prometheus 配置文件"""
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            with open(output_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False)

            print(f"Prometheus 配置已生成: {output_path}")
            return True

        except Exception as e:
            print(f"生成 Prometheus 配置失败: {e}")
            return False

class GrafanaConfig:
    """Grafana 配置生成器"""

    def __init__(self):
        self.datasource_config = self._get_datasource_config()
        self.dashboard_config = self._get_dashboard_config()

    def _get_datasource_config(self) -> Dict[str, Any]:
        """获取数据源配置"""
        return {
            'apiVersion': 1,
            'datasources': [
                {
                    'id': 1,
                    'orgId': 1,
                    'name': 'Prometheus',
                    'type': 'prometheus',
                    'access': 'proxy',
                    'url': 'http://prometheus:9090',
                    'password': '',
                    'user': '',
                    'database': '',
                    'basicAuth': False,
                    'isDefault': True,
                    'jsonData': {
                        'httpMethod': 'POST',
                        'queryTimeout': '60s',
                        'timeInterval': '15s'
                    },
                    'readOnly': False
                },
                {
                    'id': 2,
                    'orgId': 1,
                    'name': 'Redis',
                    'type': 'redis-datasource',
                    'access': 'proxy',
                    'url': 'redis:6379',
                    'password': '',
                    'user': '',
                    'database': '',
                    'basicAuth': False,
                    'isDefault': False,
                    'jsonData': {
                        'poolSize': 5,
                        'timeout': '10s',
                        'pipeline': False
                    },
                    'readOnly': False
                }
            ]
        }

    def _get_dashboard_config(self) -> Dict[str, Any]:
        """获取仪表板配置"""
        return {
            'dashboard': {
                'id': None,
                'title': 'WhisperX 性能监控',
                'tags': ['whisperx', 'performance'],
                'timezone': 'Asia/Shanghai',
                'panels': [
                    {
                        'id': 1,
                        'title': '工作流执行时间',
                        'type': 'graph',
                        'targets': [
                            {
                                'expr': 'rate(whisperx_execution_time_seconds[5m])',
                                'legendFormat': '{{backend_type}} - {{status}}'
                            }
                        ],
                        'yaxes': [
                            {'label': '执行时间 (秒)', 'min': 0},
                            {'label': '', 'min': None}
                        ]
                    },
                    {
                        'id': 2,
                        'title': 'GPU 利用率',
                        'type': 'graph',
                        'targets': [
                            {
                                'expr': 'gpu_utilization_percent',
                                'legendFormat': 'GPU 利用率'
                            }
                        ],
                        'yaxes': [
                            {'label': '利用率 (%)', 'min': 0, 'max': 100},
                            {'label': '', 'min': None}
                        ]
                    },
                    {
                        'id': 3,
                        'title': 'GPU 显存使用',
                        'type': 'graph',
                        'targets': [
                            {
                                'expr': 'gpu_memory_used_gb',
                                'legendFormat': 'GPU 显存使用 (GB)'
                            }
                        ],
                        'yaxes': [
                            {'label': '显存使用 (GB)', 'min': 0},
                            {'label': '', 'min': None}
                        ]
                    },
                    {
                        'id': 4,
                        'title': '处理速度',
                        'type': 'graph',
                        'targets': [
                            {
                                'expr': 'whisperx_processing_speed_x',
                                'legendFormat': '处理速度 (x)'
                            }
                        ],
                        'yaxes': [
                            {'label': '处理速度 (x)', 'min': 0},
                            {'label': '', 'min': None}
                        ]
                    },
                    {
                        'id': 5,
                        'title': '成功率',
                        'type': 'stat',
                        'targets': [
                            {
                                'expr': 'sum(rate(whisperx_workflows_total{status="success"}[5m])) / sum(rate(whisperx_workflows_total[5m])) * 100',
                                'legendFormat': '成功率'
                            }
                        ],
                        'fieldConfig': {
                            'defaults': {
                                'unit': 'percent',
                                'min': 0,
                                'max': 100,
                                'thresholds': {
                                    'steps': [
                                        {'color': 'red', 'value': 0},
                                        {'color': 'yellow', 'value': 80},
                                        {'color': 'green', 'value': 95}
                                    ]
                                }
                            }
                        }
                    }
                ],
                'time': {
                    'from': 'now-1h',
                    'to': 'now'
                },
                'refresh': '30s'
            }
        }

    def generate_datasource_config(self, output_path: str = '/etc/grafana/provisioning/datasources/datasources.yml'):
        """生成数据源配置"""
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            with open(output_path, 'w') as f:
                yaml.dump(self.datasource_config, f, default_flow_style=False)

            print(f"Grafana 数据源配置已生成: {output_path}")
            return True

        except Exception as e:
            print(f"生成 Grafana 数据源配置失败: {e}")
            return False

    def generate_dashboard_config(self, output_path: str = '/etc/grafana/provisioning/dashboards/dashboard.json'):
        """生成仪表板配置"""
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            with open(output_path, 'w') as f:
                import json
                json.dump(self.dashboard_config, f, indent=2)

            print(f"Grafana 仪表板配置已生成: {output_path}")
            return True

        except Exception as e:
            print(f"生成 Grafana 仪表板配置失败: {e}")
            return False

class AlertRules:
    """告警规则配置"""

    def __init__(self):
        self.whisperx_alerts = self._get_whisperx_alerts()
        self.system_alerts = self._get_system_alerts()

    def _get_whisperx_alerts(self) -> Dict[str, Any]:
        """获取 WhisperX 告警规则"""
        return {
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
                        },
                        {
                            'alert': 'WhisperxGpuUtilizationHigh',
                            'expr': 'gpu_utilization_percent > 95',
                            'for': '5m',
                            'labels': {
                                'severity': 'warning',
                                'service': 'whisperx'
                            },
                            'annotations': {
                                'summary': 'GPU 利用率过高',
                                'description': 'GPU 利用率超过 95% (当前值: {{ $value }}%)'
                            }
                        },
                        {
                            'alert': 'WhisperxProcessingSpeedLow',
                            'expr': 'whisperx_processing_speed_x < 0.5',
                            'for': '10m',
                            'labels': {
                                'severity': 'warning',
                                'service': 'whisperx'
                            },
                            'annotations': {
                                'summary': 'WhisperX 处理速度过慢',
                                'description': 'WhisperX 处理速度低于 0.5x (当前值: {{ $value }}x)'
                            }
                        },
                        {
                            'alert': 'WhisperxSuccessRateLow',
                            'expr': 'sum(rate(whisperx_workflows_total{status="success"}[5m])) / sum(rate(whisperx_workflows_total[5m])) * 100 < 90',
                            'for': '10m',
                            'labels': {
                                'severity': 'critical',
                                'service': 'whisperx'
                            },
                            'annotations': {
                                'summary': 'WhisperX 成功率过低',
                                'description': 'WhisperX 工作流成功率低于 90% (当前值: {{ $value }}%)'
                            }
                        }
                    ]
                }
            ]
        }

    def _get_system_alerts(self) -> Dict[str, Any]:
        """获取系统告警规则"""
        return {
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
                        },
                        {
                            'alert': 'HighDiskUsage',
                            'expr': '100 - (node_filesystem_avail_bytes / node_filesystem_size_bytes * 100) > 85',
                            'for': '5m',
                            'labels': {
                                'severity': 'warning',
                                'service': 'system'
                            },
                            'annotations': {
                                'summary': '磁盘使用率过高',
                                'description': '磁盘使用率超过 85% (当前值: {{ $value }}%)'
                            }
                        },
                        {
                            'alert': 'RedisDown',
                            'expr': 'up{job="redis"} == 0',
                            'for': '1m',
                            'labels': {
                                'severity': 'critical',
                                'service': 'redis'
                            },
                            'annotations': {
                                'summary': 'Redis 服务不可用',
                                'description': 'Redis 服务不可用超过 1 分钟'
                            }
                        }
                    ]
                }
            ]
        }

    def generate_alert_rules(self, output_dir: str = '/etc/prometheus/rules'):
        """生成告警规则文件"""
        try:
            os.makedirs(output_dir, exist_ok=True)

            # 生成 WhisperX 告警规则
            with open(f'{output_dir}/whisperx_alerts.yml', 'w') as f:
                yaml.dump(self.whisperx_alerts, f, default_flow_style=False)

            # 生成系统告警规则
            with open(f'{output_dir}/system_alerts.yml', 'w') as f:
                yaml.dump(self.system_alerts, f, default_flow_style=False)

            print(f"告警规则已生成: {output_dir}")
            return True

        except Exception as e:
            print(f"生成告警规则失败: {e}")
            return False

def main():
    """主函数 - 生成所有监控配置"""
    print("=== 生成监控配置 ===")

    # 生成 Prometheus 配置
    prometheus_config = PrometheusConfig()
    prometheus_config.generate_config()

    # 生成 Grafana 配置
    grafana_config = GrafanaConfig()
    grafana_config.generate_datasource_config()
    grafana_config.generate_dashboard_config()

    # 生成告警规则
    alert_rules = AlertRules()
    alert_rules.generate_alert_rules()

    print("=== 监控配置生成完成 ===")

if __name__ == "__main__":
    main()