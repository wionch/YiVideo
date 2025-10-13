# services/workers/paddleocr_service/Dockerfile

# 1. 使用 PaddlePaddle 官方镜像作为基础镜像
# 基于 Ubuntu 22.04 + CUDA 12.9 + Python 3.10
# FROM ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddle:3.2.0-gpu-cuda12.9-cudnn9.9
FROM nvidia/cuda:12.9.1-cudnn-devel-ubuntu24.04

# 2. 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# 3. 安装系统依赖 (特别是 OpenCV 需要的和基础工具)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Python 3.12 和 pip
    python3.12 \
    python3-pip \
    python3.12-dev \
    python3.12-venv \
    # OpenCV需要的图形库
    libgl1  \
    # 基础构建工具
    build-essential \
    wget \
    curl \
    git \
    # FFmpeg (使用预编译版本，如需GPU加速需重新编译)
    ffmpeg \
    # 清理缓存
    && rm -rf /var/lib/apt/lists/* \
    # 创建 Python 和 pip 的符号链接
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip

# 4. 设置工作目录为项目根目录
WORKDIR /app

# 5. 优化Docker缓存：先复制并安装Python依赖
# 注意：现在路径需要从项目根目录开始
COPY ./services/workers/paddleocr_service/requirements.txt /tmp/requirements.txt

# # 5.1 安装与CUDA 12.9兼容的PyTorch版本
# RUN pip install --no-cache-dir --upgrade pip && \
#     pip install --no-cache-dir \
#     torch==2.4.0 torchvision==0.19.0 torchaudio==2.4.0 \
#     --index-url https://download.pytorch.org/whl/cu124

# 5.2 安装其他Python依赖
RUN python -m pip install paddlepaddle-gpu==3.2.0 --break-system-packages -i https://www.paddlepaddle.org.cn/packages/stable/cu129/
RUN pip install --no-cache-dir --break-system-packages -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r /tmp/requirements.txt

# 5.3 安装 PyTorch (使用官方 PyTorch 索引，选择与 CUDA 12.x 兼容的版本)
# 注意：PyTorch 官方可能没有专门为 CUDA 12.9 编译的包，但为 12.1 编译的包通常可以兼容
RUN python -m pip install torch --break-system-packages --index-url https://download.pytorch.org/whl/cu129

# 6. 复制所有服务相关的源代码到工作目录
# 这是解决 ModuleNotFoundError 的核心步骤
COPY ./services /app/services

# 7. 确保正确的PYTHONPATH配置
# 注意：ENV PYTHONPATH=/app 已经在上面设置过了，这里不需要重复设置

# 8. 为 CMD 设置正确的工作目录
WORKDIR /app/services/workers/paddleocr_service

# 9. 定义容器启动时执行的默认命令
CMD ["celery", "-A", "app.tasks.celery_app", "worker", "-l", "info", "-Q", "paddleocr_queue"]
