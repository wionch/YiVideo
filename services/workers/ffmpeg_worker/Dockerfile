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

# Create a non-root user for better security
RUN useradd -ms /bin/bash appuser
USER appuser

# Set the working directory
WORKDIR /app

# Copy and install Python dependencies
COPY ./services/workers/ffmpeg_worker/requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Copy the application code into the container
COPY ./services/workers/ffmpeg_worker/app /app/app

# The command to run the celery worker will be specified in docker-compose.yml
