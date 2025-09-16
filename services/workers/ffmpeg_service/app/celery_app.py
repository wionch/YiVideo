from celery import Celery

# Create a Celery instance
# The first argument is the name of the current module, which is used for task name generation.
# The broker argument specifies the URL of the message broker (Redis).
# The backend argument specifies the URL of the result backend (also Redis).
celery_app = Celery(
    'ffmpeg_service',
    broker='redis://redis:6379/0',
    backend='redis://redis:6379/0',
    include=['app.tasks']  # List of modules to import when the worker starts.
)

# Optional Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],  # Ignore other content
    result_serializer='json',
    timezone='Asia/Shanghai',
    enable_utc=True,
)