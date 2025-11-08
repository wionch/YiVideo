# Dockerfile for wservice

# 1. Base Image
FROM python:3.10-slim-buster

# 2. Environment Variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. Working Directory
WORKDIR /app

# 4. Install Dependencies
# Copy requirements first to leverage Docker cache
COPY ./services/workers/wservice/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 5. Copy Application Code
# Copy the entire services directory to make all common modules available
COPY ./services /app/services

# 6. Command to Run
# Run the celery worker for wservice.
# Using solo pool as it's a simple, non-GPU task worker.
CMD ["celery", "-A", "services.workers.wservice.app.celery_app", "worker", "--loglevel=info", "-P", "solo"]
