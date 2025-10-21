# services/workers/pyannote_audio_service/app/__init__.py
# -*- coding: utf-8 -*-

"""
Pyannote Audio Service 应用模块

包含所有与 pyannote.audio 说话人分离相关的功能实现。
"""

__version__ = "1.0.0"
__author__ = "YiVideo Team"

# 任务通过 Celery 直接调用，无需在此处导入