# Dockerfile

# ============================================================================
# 第一阶段：构建器 (Builder)
# 此阶段用于安装所有开发工具和编译Python依赖。
# ============================================================================
FROM nvidia/cuda:12.9.1-cudnn-runtime-ubuntu24.04 AS builder

# 1. 环境变量配置
ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# 2. 安装构建时所必需的系统依赖
# 包括 Python 开发头文件、音频库的开发头文件和编译工具链
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3-pip \
    python3.12-venv \
    python3.12-dev \
    build-essential \
    libsndfile1-dev \
    libsox-dev \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.12 /usr/bin/python

# 3. 创建并激活虚拟环境
# 将所有依赖安装在 /opt/venv 中，使其与系统Python隔离且便于移植
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 4. 复制并安装Python依赖
# 仅复制 requirements.txt 以最大化利用Docker层缓存
WORKDIR /app
COPY ./services/workers/audio_separator_service/requirements.txt requirements.txt

# 在虚拟环境中安装依赖，不再需要 --break-system-packages
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --timeout=1200 -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt


# ============================================================================
# 第二阶段：最终镜像 (Final Image)
# 此阶段只包含运行应用所必需的文件，非常轻量和安全。
# ============================================================================
FROM nvidia/cuda:12.9.1-cudnn-runtime-ubuntu24.04

# 1. 再次设置环境变量
ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    # 将虚拟环境的 bin 目录加入 PATH，这样可以直接执行 python, celery 等命令
    PATH="/opt/venv/bin:$PATH" \
    # 设置 PYTHONPATH，让 Python 解释器找到我们的模块
    PYTHONPATH=/app \
    # Audio Separator 相关环境变量
    AUDIO_SEPARATOR_MODEL_DIR=/app/.cache/audio_separator \
    TORCH_HOME=/app/.cache/torch \
    HF_HOME=/app/.cache/huggingface

# 2. 安装运行时所必需的最小系统依赖
# 注意：这里不再需要 *-dev 包，只需安装它们的运行时库
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    ffmpeg \
    libsndfile1 \
    libsox-fmt-all \
    && rm -rf /var/lib/apt/lists/*

# 3. 创建一个非 root 用户和必要的目录
RUN groupadd --gid 1001 appuser && \
    useradd --uid 1001 --gid 1001 --shell /bin/bash --create-home appuser && \
    # 创建应用和数据目录，并赋予所有权
    mkdir -p /app /models /share && \
    chown -R appuser:appuser /app /models /share

# 4. 切换到非 root 用户
USER appuser

# 5. 设置工作目录
WORKDIR /app

# 6. 从构建器阶段复制已安装好所有依赖的Python虚拟环境
# 这是多阶段构建的核心优势：只引入纯净的依赖，不引入任何编译工具
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
# 修复虚拟环境中的符号链接，使其指向 final 阶段的正确解释器
RUN ln -sf /usr/bin/python3 /opt/venv/bin/python && \
    ln -sf /usr/bin/pip3 /opt/venv/bin/pip

# 7. 复制应用程序源代码
COPY --chown=appuser:appuser ./services/common /app/services/common
COPY --chown=appuser:appuser ./services/workers/audio_separator_service /app/services/workers/audio_separator_service

# 8. 确保必要的缓存目录存在并具有正确权限
RUN mkdir -p /app/.cache/audio_separator && \
    chown -R appuser:appuser /app/.cache

# 9. 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import sys; from audio_separator.separator import Separator; sys.exit(0)" || exit 1

# 10. 设置工作目录并定义启动命令
WORKDIR /app/services/workers/audio_separator_service
CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=info", "--concurrency=1"]