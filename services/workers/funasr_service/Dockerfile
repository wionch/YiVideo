# syntax=docker/dockerfile:1.6
# ============================================================================
# 第一阶段：构建器 (Builder)
# ============================================================================
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 AS builder

ARG PIP_EXTRA_INDEX_URL=
# 使用 CUDA 12.1 PyTorch wheels (兼容 PyTorch 2.0-2.5，避免下载 2.10 预览版)
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cu121
ARG TORCH_EXTRA_INDEX_URL=
ARG NVIDIA_PYPI_INDEX_URL=https://mirrors.cloud.tencent.com/nvidia-pypi/simple
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn \
    PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL} \
    PIP_DEFAULT_TIMEOUT=100 \
    PIP_RETRIES=5

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    sed -i 's@http://archive.ubuntu.com/ubuntu/@https://mirrors.aliyun.com/ubuntu/@g' /etc/apt/sources.list && \
    sed -i 's@http://security.ubuntu.com/ubuntu/@https://mirrors.aliyun.com/ubuntu/@g' /etc/apt/sources.list && \
    apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/bin/python

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY services/workers/funasr_service/requirements.txt requirements.txt

# 如果存在本地 wheelhouse 目录，优先从本地安装（离线构建）
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/wheelhouse \
    --mount=type=bind,source=services/workers/funasr_service/wheelhouse,target=/local-wheels \
    pip install --upgrade pip && \
    PIP_TORCH_EXTRA_ARGS="" && \
    if [ -n "${TORCH_EXTRA_INDEX_URL}" ]; then PIP_TORCH_EXTRA_ARGS="--extra-index-url ${TORCH_EXTRA_INDEX_URL}"; fi && \
    PIP_NVIDIA_EXTRA_ARGS="" && \
    if [ -n "${NVIDIA_PYPI_INDEX_URL}" ]; then PIP_NVIDIA_EXTRA_ARGS="--extra-index-url ${NVIDIA_PYPI_INDEX_URL}"; fi && \
    # 优先级：本地 wheels > 缓存 > 在线下载
    if [ -d /local-wheels ] && [ "$(ls -A /local-wheels 2>/dev/null)" ]; then \
        echo "使用本地 wheelhouse 进行离线安装..." && \
        pip install --no-index --find-links /local-wheels torch torchaudio && \
        pip install --no-index --find-links /local-wheels -r requirements.txt; \
    else \
        echo "在线下载并缓存 wheels..." && \
        pip download -d /wheelhouse torch torchaudio --index-url ${TORCH_INDEX_URL} ${PIP_TORCH_EXTRA_ARGS} ${PIP_NVIDIA_EXTRA_ARGS} && \
        pip download -d /wheelhouse -r requirements.txt ${PIP_NVIDIA_EXTRA_ARGS} && \
        pip install --no-index --find-links /wheelhouse torch torchaudio && \
        pip install --no-index --find-links /wheelhouse -r requirements.txt; \
    fi

# ============================================================================
# 第二阶段：最终镜像 (Final Image)
# ============================================================================
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    # ModelScope 缓存配置（持久化模型存储）
    MODELSCOPE_CACHE=/app/.cache/modelscope \
    TORCH_HOME=/app/.cache/torch

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    sed -i 's@http://archive.ubuntu.com/ubuntu/@https://mirrors.aliyun.com/ubuntu/@g' /etc/apt/sources.list && \
    sed -i 's@http://security.ubuntu.com/ubuntu/@https://mirrors.aliyun.com/ubuntu/@g' /etc/apt/sources.list && \
    apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/bin/python

RUN groupadd --gid 1001 appuser && \
    useradd --uid 1001 --gid 1001 --shell /bin/bash --create-home appuser && \
    mkdir -p /app /app/.cache/modelscope /app/.cache/torch && \
    chown -R appuser:appuser /app

USER appuser
WORKDIR /app

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

COPY --chown=appuser:appuser services/common /app/services/common
COPY --chown=appuser:appuser services/workers/funasr_service /app/services/workers/funasr_service
COPY --chown=appuser:appuser config.yml /app/config.yml

WORKDIR /app/services/workers/funasr_service

CMD ["celery", "-A", "app.celery_app", "worker", "-l", "info", "-Q", "funasr_queue", "--concurrency=1"]
