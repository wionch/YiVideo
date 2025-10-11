# ============================================================================
# IndexTTS Service Dockerfile
# 基于 IndexTTS2 模型的文本转语音服务
# ============================================================================

# 使用 PaddlePaddle 官方镜像作为基础镜像
# 基于 Ubuntu 22.04 + CUDA 12.9 + Python 3.10
# 满足 IndexTTS2 的 CUDA 12.8+ 要求
FROM ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddle:3.2.0-gpu-cuda12.9-cudnn9.9

# ========================================
# 1. 环境变量配置
# ========================================
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# IndexTTS 相关环境变量
ENV INDEX_TTS_MODEL_DIR=/models/indextts
ENV TORCH_HOME=/app/.cache/torch
ENV HF_HOME=/app/.cache/huggingface
ENV TRANSFORMERS_CACHE=/app/.cache/transformers

# PyTorch 环境变量
ENV CUDA_VISIBLE_DEVICES=0

# ========================================
# 2. 安装系统依赖
# ========================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    # 音频处理核心依赖
    ffmpeg \
    # 网络工具
    curl \
    wget \
    git \
    # 版本控制
    git-lfs \
    # 系统工具
    unzip \
    build-essential \
    # Python 开发工具
    python3-dev \
    # 清理缓存
    && rm -rf /var/lib/apt/lists/*

# 初始化 git-lfs
RUN git lfs install

# ========================================
# 3. 安装 uv 包管理器 (IndexTTS2 强制要求)
# ========================================
RUN pip install --no-cache-dir uv

# ========================================
# 4. 设置工作目录
# ========================================
WORKDIR /app

# ========================================
# 5. 复制 IndexTTS2 项目代码
# ========================================
# 复制本地的 IndexTTS2 项目
COPY ./services/workers/indextts_service/src/index-tts /tmp/index-tts

# 复制服务代码
COPY ./services/common /app/services/common
COPY ./services/workers/indextts_service /app/services/workers/indextts_service

# ========================================
# 6. 统一安装所有依赖
# ========================================
# 使用 uv 安装 IndexTTS2 和 Celery 相关的所有依赖
WORKDIR /tmp/index-tts

# 复制 Celery 依赖文件到临时目录
COPY ./services/workers/indextts_service/requirements.txt /tmp/requirements.txt

# 安装 IndexTTS2 项目及其依赖
RUN UV_HTTP_TIMEOUT=3000 uv sync --all-extras --default-index "https://mirrors.aliyun.com/pypi/simple"

# 在uv虚拟环境中安装 Celery 相关依赖
RUN uv pip install --no-cache-dir \
    -i http://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    celery>=5.3.0 \
    redis>=5.0.0 \
    pydantic>=2.0.0 \
    PyYAML>=6.0 \
    psutil>=5.9.0 \
    requests>=2.31.0 \
    tqdm>=4.65.0 \
    pathlib2>=2.3.7 \
    ffmpeg-python>=0.2.0 \
    colorlog>=6.0.0

# ========================================
# 7. 创建必要的目录
# ========================================
RUN mkdir -p \
    /app/.cache/indextts \
    /models/indextts \
    /app/services/workers/indextts_service/logs \
    /share/workflows/indextts_output \
    /tmp/index-tts/checkpoints

# 设置目录权限
RUN chmod -R 755 /models /share /app/.cache /tmp/index-tts

# ========================================
# 8. 安装 IndexTTS2 到系统路径
# ==================================
WORKDIR /tmp/index-tts
RUN uv pip install -e .

# ========================================
# 9. 创建 Python 环境脚本
# ========================================
# 创建激活环境的脚本，确保使用uv的虚拟环境
RUN echo '#!/bin/bash\n\
export PYTHONPATH=/app:$PYTHONPATH\n\
export INDEX_TTS_MODEL_DIR=/models/indextts\n\
# 激活uv虚拟环境\n\
source /tmp/index-tts/.venv/bin/activate\n\
exec "$@"' > /app/entrypoint.sh && \
chmod +x /app/entrypoint.sh

# ========================================
# 10. 健康检查
# ========================================
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import sys; import torch; sys.exit(0 if torch.cuda.is_available() else 1)" || exit 1

WORKDIR /app/services/workers/indextts_service

# ========================================
# 11. 启动命令
# ========================================
ENTRYPOINT ["/app/entrypoint.sh"]

# 注意：实际的启动命令在 docker-compose.yml 中配置
CMD ["celery", "-A", "services.workers.indextts_service.app.celery_app", "worker", \
     "--loglevel=info", \
     "--concurrency=1"]