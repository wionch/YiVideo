# Base image with FFmpeg 8 and NVIDIA support
FROM jrottenberg/ffmpeg:8-nvidia

# Set environment variables for non-interactive installation and unbuffered Python output
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install Python, pip, and other system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    mediainfo \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip

# Set the working directory
WORKDIR /app

# Copy and install Python dependencies first to leverage Docker cache
COPY ./services/workers/ffmpeg_service/requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

# Create a non-root user for better security
# The -m flag creates a home directory at /home/appuser
RUN useradd -ms /bin/bash -d /home/appuser appuser

# Change ownership of the app directory to the new user.
# This is the key step to solve the permission issue for mounted volumes.
RUN chown -R appuser:appuser /app

# Create the tmp directory and ensure proper permissions for mounted volumes
RUN mkdir -p /app/tmp && chown -R appuser:appuser /app/tmp

# Switch to the non-root user
USER appuser

# Set the final working directory for the command
WORKDIR /app/services/workers/ffmpeg_service

# The application code is provided via the volume mount in docker-compose.yml
# The command to run the celery worker is specified in docker-compose.yml
