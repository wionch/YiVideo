# Dockerfile

# ============================================================================
# 第一阶段：构建器 (Builder)
# 此阶段用于安装所有构建工具和编译Python依赖。
# ============================================================================
FROM nvidia/cuda:12.9.1-cudnn-runtime-ubuntu24.04 AS builder

# 1. 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

# 2. 安装构建时所必需的系统依赖
# cmake 和 ccache 是 vLLM/Triton 编译 CUDA 内核所需
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    cmake \
    ccache \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/bin/python

# 3. 创建并激活虚拟环境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 4. 复制并安装Python依赖
WORKDIR /app
COPY services/workers/qwen3_asr_service/requirements.txt requirements.txt

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# ============================================================================
# 第二阶段：最终镜像 (Final Image)
# ============================================================================
FROM nvidia/cuda:12.9.1-cudnn-runtime-ubuntu24.04

# 1. 再次设置环境变量
# MAX_JOBS: 限制 Triton/vLLM 编译 CUDA 内核时的并行度，避免内存不足
# HF_ENDPOINT: 使用 Hugging Face 镜像站，解决国内访问问题
# CCACHE_DIR: ccache 缓存目录
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    MAX_JOBS=4 \
    NVCC_THREADS=2 \
    HF_ENDPOINT=https://hf-mirror.com \
    CCACHE_DIR=/app/.cache/ccache

# 2. 安装运行时依赖
# build-essential 和 python3-dev 是必需的：vLLM + Triton 需要 C 编译器和 Python 头文件来动态编译 CUDA 内核
# cmake 和 ccache 用于加速 CUDA 内核的编译
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-dev \
    ffmpeg \
    libsndfile1 \
    build-essential \
    cmake \
    ccache \
    && rm -rf /var/lib/apt/lists/*

# 3. 创建非 root 用户和 ccache 缓存目录
RUN groupadd --gid 1001 appuser && \
    useradd --uid 1001 --gid 1001 --shell /bin/bash --create-home appuser && \
    mkdir -p /app && \
    mkdir -p /app/.cache/ccache && \
    chown -R appuser:appuser /app

# 4. 切换用户
USER appuser

# 5. 设置工作目录
WORKDIR /app

# 6. 拷贝虚拟环境
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
RUN ln -sf /usr/bin/python3 /opt/venv/bin/python && \
    ln -sf /usr/bin/pip3 /opt/venv/bin/pip

# 7. 复制应用程序源代码
COPY --chown=appuser:appuser services/common /app/services/common
COPY --chown=appuser:appuser services/workers/qwen3_asr_service /app/services/workers/qwen3_asr_service
COPY --chown=appuser:appuser config.yml /app/config.yml

# 8. 切换工作目录
WORKDIR /app/services/workers/qwen3_asr_service

# 9. 默认启动命令
CMD ["celery", "-A", "app.celery_app", "worker", "-l", "info", "-Q", "qwen3_asr_queue", "--concurrency=1", "-n", "qwen3_asr_worker@%h"]
