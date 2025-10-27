# Dockerfile

# =========================================================================
# 第一阶段：构建器 (Builder)
# 此阶段用于安装所有构建时依赖，编译Python包。
# =========================================================================
FROM nvidia/cuda:12.9.1-cudnn-runtime-ubuntu24.04 AS builder

# 设置环境变量，使用国内镜像源加速构建
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 安装构建时所必需的系统依赖
# 包括 Python 开发头文件、ffmpeg 开发库和编译工具链
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    python3-dev \
    python3-pip \
    build-essential \
    ffmpeg \
    libavcodec-dev libavformat-dev libavutil-dev libswscale-dev libswresample-dev \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/bin/python

# 创建虚拟环境
RUN python -m venv /opt/venv

# 激活虚拟环境，后续所有命令都将使用此环境中的python和pip
ENV PATH="/opt/venv/bin:$PATH"

# 仅复制 requirements.txt 文件，以最大化利用Docker层缓存
WORKDIR /app
COPY services/workers/pyannote_audio_service/requirements.txt requirements.txt

# 在虚拟环境中安装所有Python依赖
# --no-cache-dir 在此阶段已由环境变量设置，可省略
RUN pip install --upgrade pip && \
    pip install -r requirements.txt


# =========================================================================
# 第二阶段：最终镜像 (Final Image)
# 此阶段只包含运行应用所必需的文件，非常轻量和安全。
# =========================================================================
FROM nvidia/cuda:12.9.1-cudnn-runtime-ubuntu24.04

# 再次设置环境变量，但不包括构建时的镜像源
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    # 将虚拟环境的 bin 目录加入 PATH，这样可以直接执行 python, pip, celery 等命令
    PATH="/opt/venv/bin:$PATH" \
    # 设置 PYTHONPATH，帮助 Python 解释器找到我们的模块
    PYTHONPATH=/app

# 安装运行时所必需的系统依赖
# 注意：这里不再需要 build-essential, python-dev, lib*-dev 等编译工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 创建一个非 root 用户和组，并赋予其对应用目录的所有权
# 出于安全考虑，不使用 root 用户运行应用
RUN groupadd --gid 1001 appuser && \
    useradd --uid 1001 --gid 1001 --shell /bin/bash --create-home appuser && \
    mkdir -p /app && \
    chown -R appuser:appuser /app

# 切换到非 root 用户
USER appuser

# 设置工作目录
WORKDIR /app

# 从构建器阶段复制已安装好所有依赖的Python虚拟环境
# 这是多阶段构建的核心优势：只引入纯净的依赖，不引入任何编译工具
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
# 修复虚拟环境中的符号链接，使其指向 final 阶段的正确解释器
RUN ln -sf /usr/bin/python3 /opt/venv/bin/python && \
    ln -sf /usr/bin/pip3 /opt/venv/bin/pip

# 复制应用程序源代码，并确保所有者是 appuser
# 这种分层复制可以优化缓存：只有当公共代码改变时，才会使相关层失效
COPY --chown=appuser:appuser services/common                      /app/services/common
COPY --chown=appuser:appuser services/workers/pyannote_audio_service /app/services/workers/pyannote_audio_service
COPY --chown=appuser:appuser config.yml                         /app/config.yml

# 将工作目录切换到服务所在的目录
WORKDIR /app/services/workers/pyannote_audio_service

# 定义容器启动时执行的默认命令
CMD ["celery", "-A", "app.tasks.celery_app", "worker", "-l", "info", "-Q", "pyannote_audio_queue"]