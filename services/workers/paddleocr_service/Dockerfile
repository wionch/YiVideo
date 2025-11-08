# Dockerfile

# =========================================================================
# 第一阶段：构建器 (Builder)
# 这个阶段用于安装所有开发工具和编译Python依赖。
# =========================================================================
FROM nvidia/cuda:12.9.1-cudnn-runtime-ubuntu24.04 AS builder

# 设置环境变量，避免交互式提示
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# 安装编译时所必需的系统依赖
# 包括：Python开发头文件、编译工具链、git等
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3-pip \
    python3.12-dev \
    python3.12-venv \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip

# 设置工作目录
WORKDIR /app

# 仅复制 requirements.txt 文件，以利用Docker的层缓存机制
# 当 requirements.txt 没有变化时，下面安装依赖的步骤不会重新执行
COPY ./services/workers/paddleocr_service/requirements.txt /app/requirements.txt

# 安装所有Python依赖到一个独立的虚拟环境中
# 使用虚拟环境可以方便地将所有依赖项复制到下一阶段
# --no-cache-dir 避免缓存，减小此阶段的体积
# 合并所有 pip install 命令到一个 RUN 指令中，减少镜像层数
RUN python -m venv /opt/venv && \
    . /opt/venv/bin/activate && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir paddlepaddle-gpu==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/ && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu129 && \
    pip install --no-cache-dir -r requirements.txt -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com

# =========================================================================
# 第二阶段：最终镜像 (Final Image)
# 这个阶段只包含运行应用所必需的环境和文件。
# =========================================================================
FROM nvidia/cuda:12.9.1-cudnn-runtime-ubuntu24.04

# 再次设置环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
# 将虚拟环境的 bin 目录加入 PATH，这样可以直接执行 python, pip 等命令
ENV PATH="/opt/venv/bin:$PATH"
# 设置 PYTHONPATH，让 Python 能找到我们的模块
ENV PYTHONPATH=/app

# 安装运行时所必需的系统依赖
# 注意：这里不再需要 build-essential, python-dev, git 等编译工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    libgl1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 创建一个非 root 用户和组，并创建应用目录
# 出于安全考虑，不使用 root 用户运行应用
RUN groupadd --gid 1001 appuser && \
    useradd --uid 1001 --gid 1001 --shell /bin/bash --create-home appuser && \
    mkdir -p /app && \
    chown -R appuser:appuser /app

# 切换到非 root 用户
USER appuser

# 设置工作目录
WORKDIR /app

# 从构建器阶段复制已安装好的Python虚拟环境
# 这是多阶段构建的核心优势：只引入纯净的依赖，不引入编译工具
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

# 修复虚拟环境中的符号链接，使其指向 final 阶段的正确解释器
RUN ln -sf /usr/bin/python3.12 /opt/venv/bin/python && \
    ln -sf /usr/bin/pip3 /opt/venv/bin/pip

# 复制应用程序源代码
COPY --chown=appuser:appuser ./services /app/services

# 切换工作目录到服务所在的目录
WORKDIR /app/services/workers/paddleocr_service

# 定义容器启动时执行的默认命令
# 使用虚拟环境中的 celery（绝对路径）
CMD ["/opt/venv/bin/celery", "-A", "app.tasks.celery_app", "worker", "-l", "info", "-Q", "paddleocr_queue"]