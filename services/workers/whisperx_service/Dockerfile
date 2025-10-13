# 使用 PaddlePaddle 官方镜像作为基础镜像
# 基于 Ubuntu 22.04 + CUDA 11.8 + Python 3.10
# FROM ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddle:3.1.1-gpu-cuda11.8-cudnn8.9
# FROM ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddle:3.2.0-gpu-cuda12.9-cudnn9.9
FROM nvidia/cuda:12.9.1-cudnn-devel-ubuntu24.04

# 1. 设置环境变量，避免交互式提示
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# 2. 优化构建：安装 WhisperX 必需的系统依赖和 FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Python 3.12 和 pip
    python3.12 \
    python3-pip \
    python3.12-dev \
    python3.12-venv \
    # FFmpeg - WhisperX 音频处理的硬依赖
    ffmpeg \
    # 音频处理依赖
    libsox-dev \
    libsndfile1-dev \
    # 网络工具（用于调试）
    curl \
    wget \
    git \
    # 清理缓存
    && rm -rf /var/lib/apt/lists/* \
    # 创建 Python 和 pip 的符号链接
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip

# 3. 设置工作目录
WORKDIR /app

# 4. 优化 Docker 缓存：分阶段安装依赖
# 复制核心依赖文件
COPY ./services/workers/whisperx_service/requirements.txt /tmp/requirements.txt

# 5. 安装核心 Python 依赖（使用国内镜像源）
RUN pip install --no-cache-dir --break-system-packages -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
    -r /tmp/requirements.txt

# 6. 优化：仅复制 WhisperX 服务相关的代码
COPY ./services/common /app/services/common
COPY ./services/workers/whisperx_service /app/services/workers/whisperx_service

# 7. 设置 WhisperX 相关环境变量
ENV WHISPERX_MODEL_CACHE_DIR=/app/.cache/whisperx
ENV HF_HOME=/app/.cache/huggingface
ENV TRANSFORMERS_CACHE=/app/.cache/transformers

# 8. 创建缓存目录并设置权限
RUN mkdir -p /app/.cache/whisperx /app/.cache/huggingface /app/.cache/transformers && \
    chmod -R 755 /app/.cache

# 9. 【新增】修复WhisperX中的use_auth_token问题
# 9.1 替换asr.py中的硬编码token
RUN sed -i 's/use_auth_token=None/use_auth_token=os.getenv("HF_TOKEN")/g' \
    /usr/local/lib/python3.12/dist-packages/whisperx/asr.py

# 9.2 添加os模块导入到asr.py（如果还没有）
RUN grep -q "import os" /usr/local/lib/python3.12/dist-packages/whisperx/asr.py || \
    sed -i '/^import sys/a import os' \
    /usr/local/lib/python3.12/dist-packages/whisperx/asr.py

# 9.3 修复pyannote.py中的use_auth_token问题
# 首先移除包含use_auth_token的参数
RUN sed -i 's/use_auth_token: Union\[Text, None\] = None,//' \
    /usr/local/lib/python3.12/dist-packages/whisperx/vads/pyannote.py
# 然后替换super()调用，移除use_auth_token参数
RUN sed -i 's/super().__init__(segmentation=segmentation, fscore=fscore, use_auth_token=use_auth_token, \*\*inference_kwargs)/super().__init__(segmentation=segmentation, fscore=fscore, **inference_kwargs)/' \
    /usr/local/lib/python3.12/dist-packages/whisperx/vads/pyannote.py

# 10. 为 CMD 设置正确的工作目录
WORKDIR /app/services/workers/whisperx_service

# 10. 优化启动命令（添加性能调优参数）
CMD ["celery", "-A", "app.tasks.celery_app", "worker", \
     "-l", "info", \
     "-Q", "whisperx_queue", \
     "--max-tasks-per-child=10", \
     "--max-memory-per-child=300000", \
     "-P", "eventlet"]