# services/workers/wservice/app/celery_app.py
# -*- coding: utf-8 -*-

"""
wservice - Celery Application
"""

from celery import Celery
from services.common.config_loader import CONFIG

# 从配置中获取服务名称、broker和backend
service_name = 'wservice'
celery_config = CONFIG.get_celery_config(service_name)

if not celery_config:
    raise ValueError(f"无法在 config.yml 中找到 {service_name} 的 Celery 配置")

app = Celery(
    service_name,
    broker=celery_config['broker'],
    backend=celery_config['backend'],
    include=[
        'services.workers.wservice.app.tasks'
    ]
)

# 使用通用配置更新Celery实例
app.conf.update(
    task_track_started=True,
    result_expires=3600,
)

# 设置为默认应用
app.set_default()
