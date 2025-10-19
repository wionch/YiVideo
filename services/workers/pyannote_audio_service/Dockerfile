# ===== 精简版：直接使用官方 pip + venv =====
FROM nvidia/cuda:12.9.1-cudnn-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 1. 系统依赖 + ffmpeg + python3-venv
RUN apt-get update && apt-get install -y \
    python3 python3-venv python3-dev python3-pip \
    ffmpeg \
    libavcodec-dev libavformat-dev libavutil-dev libswscale-dev libswresample-dev \
    && ffmpeg -version \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.12 /usr/bin/python

# 2. 创建并激活虚拟环境（一次性）
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 3. 升级 pip & 安装依赖
COPY services/workers/pyannote_audio_service/requirements.txt /app/requirements.txt
RUN pip install -U pip && \
    pip install -r /app/requirements.txt

# 4. 复制代码
WORKDIR /app/services/workers/pyannote_audio_service
# COPY services/common                /app/services/common
# COPY services/workers/pyannote_audio_service /app/services/workers/pyannote_audio_service
# COPY config.yml                     /app/config.yml

# 5. 默认命令（调试/待机）
# CMD ["tail", "-f", "/dev/null"]
CMD ["celery", "-A", "app.tasks.celery_app", "worker", "-l", "info", "-Q", "pyannote_audio_queue"]
