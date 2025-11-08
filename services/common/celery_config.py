# services/common/celery_config.py
# -*- coding: utf-8 -*-

"""
Centralized Celery configuration module.

This module reads Redis connection details from environment variables
and constructs the broker and result backend URLs for Celery.
All services should import their configuration from this single source of truth.
"""

import os
import sys
from services.common.logger import get_logger

logger = get_logger('celery_config')

# --- Redis Configuration ---
REDIS_HOST = os.environ.get('REDIS_HOST')
REDIS_PORT = os.environ.get('REDIS_PORT')

if not REDIS_HOST or not REDIS_PORT:
    logger.error("Environment variables REDIS_HOST and REDIS_PORT must be set.")
    sys.exit("Error: Redis configuration environment variables are missing, services cannot start.")

# --- Celery URL Construction ---
BROKER_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
BACKEND_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/1"

logger.info(f"Celery configuration loaded: BROKER_URL='{BROKER_URL}', BACKEND_URL='{BACKEND_URL}'")