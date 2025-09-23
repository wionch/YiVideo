# services/workers/llm_service/Dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app /app

# The command to run the celery worker will be specified in docker-compose.yml
CMD ["celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=info", "-Q", "llm_queue"]
