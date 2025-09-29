# services/workers/whisperx_service/Dockerfile - 优化版本 V2
# 基于 WHISPERX_OPTIMIZATION_PLAN.md 的优化建议

# 1. 使用 PaddlePaddle 官方镜像作为基础镜像
# 基于 Ubuntu 22.04 + CUDA 11.8 + Python 3.10
FROM ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddle:3.1.1-gpu-cuda11.8-cudnn8.9

# 2. 设置环境变量，避免交互式提示
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# 3. 优化构建：安装 WhisperX 必需的系统依赖和 FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
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
    && rm -rf /var/lib/apt/lists/*

# 4. 设置工作目录
WORKDIR /app

# 5. 优化 Docker 缓存：分阶段安装依赖
# 先复制核心依赖文件
COPY ./services/workers/whisperx_service/requirements.txt /tmp/requirements.txt

# 6. 安装核心 Python 依赖（使用国内镜像源）
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
    # 核心框架依赖
    celery redis pydantic PyYAML \
    # 音频处理
    ffmpeg-python \
    # Faster-Whisper 优化依赖
    faster-whisper \
    ctranslate2 \
    # 模型量化支持
    # 其他 WhisperX 依赖
    pyannote.audio

# 7. 安装 WhisperX（从 GitHub 克隆最新版本）
RUN pip install --no-cache-dir -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
    git+https://github.com/m-bain/whisperx.git

# 8. 优化：仅复制 WhisperX 服务相关的代码
COPY ./services/common /app/services/common
COPY ./services/workers/whisperx_service /app/services/workers/whisperx_service

# 9. 设置 WhisperX 相关环境变量
ENV WHISPERX_MODEL_CACHE_DIR=/app/.cache/whisperx
ENV HF_HOME=/app/.cache/huggingface
ENV TRANSFORMERS_CACHE=/app/.cache/transformers

# 10. 创建缓存目录并设置权限
RUN mkdir -p /app/.cache/whisperx /app/.cache/huggingface /app/.cache/transformers && \
    chmod -R 755 /app/.cache

# 11. 为 CMD 设置正确的工作目录
WORKDIR /app/services/workers/whisperx_service

# 12. 优化启动命令（添加性能调优参数）
CMD ["celery", "-A", "app.tasks.celery_app", "worker", \
     "-l", "info", \
     "-Q", "whisperx_queue", \
     "--max-tasks-per-child=10", \
     "--max-memory-per-child=300000", \
     "-P", "eventlet"]