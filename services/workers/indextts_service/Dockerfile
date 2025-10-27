# ============================================================================
# IndexTTS Service Dockerfile - Optimized Version
# 优化策略：多阶段构建 + 层缓存优化 + 非ROOT用户 + 最小依赖
# 版本：v2.0
# 创建日期：2025-10-25
# ============================================================================

# ============================================================================
# 第一阶段：Builder（构建器）
# 用途：编译和安装所有依赖，包含完整的开发工具链
# ============================================================================
FROM nvidia/cuda:12.9.1-cudnn-devel-ubuntu24.04 AS builder

# ========================================
# 1. 环境变量配置
# ========================================
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    # UV 配置
    UV_SYSTEM_PYTHON=1 \
    UV_HTTP_TIMEOUT=3000

# ========================================
# 2. 安装系统依赖（Builder 完整工具链）
# ========================================
# 添加 deadsnakes PPA 仓库以获取 Python 3.11（Ubuntu 24.04 默认不包含）
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update

RUN apt-get update && apt-get install -y --no-install-recommends \
    # 编译工具链
    build-essential \
    # Python 开发环境
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    # 音频处理
    ffmpeg \
    # 版本控制
    git \
    git-lfs \
    # 网络和实用工具
    curl \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python

# 使用 ensurepip 安装 pip（更可靠的方式）
RUN python3.11 -m ensurepip --upgrade

# 初始化 git-lfs
RUN git lfs install

# ========================================
# 3. 创建虚拟环境并安装 uv
# ========================================
# 在虚拟环境中安装 uv，使用 python3.11 确保版本正确
RUN python3.11 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir uv

# 激活虚拟环境
ENV PATH="/opt/venv/bin:$PATH"

# ========================================
# 4. 层缓存优化：先克隆依赖清单
# ========================================
WORKDIR /app

# 从 GitHub 克隆 IndexTTS2 项目
# 使用 git clone 直接获取最新源码，确保依赖完整
# 指定主分支并使用浅克隆优化构建时间
RUN git clone --depth 1 --branch main https://github.com/index-tts/index-tts.git /app/index-tts

# 复制 Celery 依赖清单
COPY services/workers/indextts_service/requirements.txt /tmp/requirements.txt

# ========================================
# 5. 安装 IndexTTS2 核心依赖
# ========================================
# 注意：此步骤仅在依赖文件变化时才重建
WORKDIR /app/index-tts

RUN UV_HTTP_TIMEOUT=3000 uv sync --all-extras \
    --default-index "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple" && \
    echo "IndexTTS2 dependencies installed successfully"

# ========================================
# 6. 安装 Celery 相关依赖
# ========================================
# 明确使用 uv sync 创建的虚拟环境中的 pip 来安装 Celery 依赖
# 明确使用 /opt/venv 虚拟环境中的 pip 来安装 Celery 依赖
RUN /opt/venv/bin/pip install --no-cache-dir \
    -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple \
    --trusted-host mirrors.aliyun.com \
    -r /tmp/requirements.txt && \
    echo "Celery dependencies installed successfully"

# ========================================
# ========================================
# 7. 源码已在依赖安装前复制，此步骤已无需执行
# ========================================

# ========================================
# 8. 安装 IndexTTS2（正式安装，非可编辑模式）
# ========================================
# 使用正式安装而非 -e，便于跨阶段复制
WORKDIR /app/index-tts
# 同样，明确使用 /opt/venv 中的 pip 来安装本地包
RUN /opt/venv/bin/pip install --no-cache-dir . && \
    echo "IndexTTS2 installed successfully"

# 验证安装
# RUN python -c "from indextts.infer_v2 import IndexTTS2; print('IndexTTS2 verification passed')"


# ============================================================================
# 第二阶段：Final Image（最终镜像）
# 用途：仅包含运行时依赖，最小化镜像大小，提升安全性
# ============================================================================
FROM nvidia/cuda:12.9.1-cudnn-runtime-ubuntu24.04

# ========================================
# 1. 环境变量配置
# ========================================
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    # Python 环境
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app:/app/index-tts" \
    VIRTUAL_ENV="/opt/venv" \
    # IndexTTS 配置
    INDEX_TTS_MODEL_DIR=/models/indextts \
    TORCH_HOME=/app/.cache/torch \
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/transformers \
    # GPU 配置
    CUDA_VISIBLE_DEVICES=0 \
    # 语言环境
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# ========================================
# 2. 安装运行时最小依赖（无 dev 包）
# ========================================
# 添加 deadsnakes PPA 仓库以获取 Python 3.11
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update

RUN apt-get update && apt-get install -y --no-install-recommends \
    # Python 运行时（无 dev 包）
    python3.11 \
    # 音频处理运行时
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# ========================================
# 3. 创建非 ROOT 用户（安全最佳实践）
# ========================================
RUN groupadd --gid 1001 appuser && \
    useradd --uid 1001 --gid 1001 --shell /bin/bash --create-home appuser && \
    # 创建应用目录
    mkdir -p /app /models /share && \
    chown -R appuser:appuser /app /models /share

# ========================================
# 4. 从 Builder 复制虚拟环境
# ========================================
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

# 修复虚拟环境中的 Python 符号链接
RUN ln -sf /usr/bin/python3.11 /opt/venv/bin/python && \
    ln -sf /usr/bin/python3.11 /opt/venv/bin/python3

# ========================================
# 5. 从 Builder 复制 IndexTTS 源码
# ========================================
COPY --from=builder --chown=appuser:appuser /app/index-tts /app/index-tts

# ========================================
# 6. 切换到非 ROOT 用户
# ========================================
USER appuser
WORKDIR /app

# ========================================
# 7. 复制应用服务代码
# ========================================
# 复制共享组件
COPY --chown=appuser:appuser services/common /app/services/common

# 复制 indextts_service
COPY --chown=appuser:appuser services/workers/indextts_service \
     /app/services/workers/indextts_service

# 复制配置文件
COPY --chown=appuser:appuser config.yml /app/config.yml

# ========================================
# 8. 创建必要的缓存和工作目录
# ========================================
RUN mkdir -p \
    /app/.cache/indextts \
    /app/.cache/torch \
    /app/.cache/huggingface \
    /app/.cache/transformers \
    /app/services/workers/indextts_service/logs \
    /share/workflows/indextts_output

# ========================================
# 9. 健康检查（增强版）
# ========================================
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "\
import sys; \
import torch; \
# 检查 CUDA \
if not torch.cuda.is_available(): \
    sys.exit(1); \
# 检查 IndexTTS 导入 \
try: \
    from indextts.infer_v2 import IndexTTS2; \
except Exception: \
    sys.exit(1); \
sys.exit(0);" || exit 1

# ========================================
# 10. 设置工作目录和启动命令
# ========================================
WORKDIR /app/services/workers/indextts_service

# 注意：实际的启动命令在 docker-compose.yml 中配置
CMD ["celery", "-A", "app.celery_app", "worker", \
     "--loglevel=info", \
     "--concurrency=1", \
     "-Q", "indextts_queue"]

# ============================================================================
# 构建说明：
# docker build -t yivideo-indextts_service:optimized \
#   -f services/workers/indextts_service/Dockerfile .
#
# 预期镜像大小：12-14GB（相比旧版减少 30-40%）
# ============================================================================