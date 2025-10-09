# ============================================================================
# Audio Separator Service Dockerfile
# 基于 UVR-MDX 模型的人声/背景音分离服务
# ============================================================================

# 使用 PaddlePaddle 官方镜像作为基础镜像
# 基于 Ubuntu 22.04 + CUDA 11.8 + Python 3.10
# 与 paddleocr_service 和 whisperx_service 共享同一基础镜像，节省磁盘空间
FROM ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddle:3.1.1-gpu-cuda11.8-cudnn8.9

# ========================================
# 1. 环境变量配置
# ========================================
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Audio Separator 相关环境变量
ENV AUDIO_SEPARATOR_MODEL_DIR=/app/.cache/audio_separator
ENV TORCH_HOME=/app/.cache/torch
ENV HF_HOME=/app/.cache/huggingface

# ========================================
# 2. 安装系统依赖
# ========================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    # FFmpeg - 音频处理核心依赖
    ffmpeg \
    # 音频库依赖
    libsndfile1-dev \
    libsox-dev \
    # 网络工具
    curl \
    wget \
    git \
    # 清理缓存
    && rm -rf /var/lib/apt/lists/*

# ========================================
# 3. 设置工作目录
# ========================================
WORKDIR /app

# ========================================
# 4. 安装 Python 依赖（优化缓存）
# ========================================
# 先复制 requirements.txt
COPY ./services/workers/audio_separator_service/requirements.txt /tmp/requirements.txt

# 安装依赖（使用阿里云镜像源，与其他服务保持一致）
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    -i http://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    -r /tmp/requirements.txt

# ========================================
# 5. 复制项目代码
# ========================================
# 复制共享库
COPY ./services/common /app/services/common

# 复制 audio_separator_service 代码
COPY ./services/workers/audio_separator_service /app/services/workers/audio_separator_service

# ========================================
# 6. 创建必要的目录（在复制代码之后，确保目录存在）
# ========================================
RUN mkdir -p \
    /app/.cache/audio_separator \
    /models/uvr_mdx \
    /app/services/workers/audio_separator_service/logs \
    /share/workflows/audio_separated

# 设置目录权限
RUN chmod -R 755 /models /share /app/.cache


# ========================================
# 7. 预下载 UVR-MDX 模型（可选）
# ========================================
# 注意：模型较大（约 300MB），构建时会增加镜像大小
# 如果需要加快首次启动速度，可以在这里预下载模型
# RUN python -c "from audio_separator.separator import Separator; \
#     s = Separator(model_file_dir='/models/uvr_mdx'); \
#     s.load_model('UVR-MDX-NET-Inst_HQ_4.onnx')"

# ========================================
# 8. 健康检查
# ========================================
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import sys; from audio_separator.separator import Separator; sys.exit(0)" || exit 1


WORKDIR /app/services/workers/audio_separator_service
# ========================================
# 9. 启动 Celery Worker
# ========================================
# 注意：实际的启动命令在 docker-compose.yml 中配置
# 这里保留默认 CMD 仅用于独立运行容器时使用
CMD ["celery", "-A", "services.workers.audio_separator_service.app.celery_app", "worker", \
     "--loglevel=info", \
     "--concurrency=1"]
