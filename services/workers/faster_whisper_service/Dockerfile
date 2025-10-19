FROM nvidia/cuda:12.9.1-cudnn-runtime-ubuntu24.04

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# 安装系统依赖，使用Ubuntu默认的Python3并升级到最新版本
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    software-properties-common \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    # 创建 Python 和 pip 的符号链接
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip


# 设置工作目录
WORKDIR /app

# 复制 requirements.txt
COPY services/workers/faster_whisper_service/requirements.txt /app/requirements.txt

# 配置 pip 使用阿里云源并安装 Python 依赖
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --break-system-packages -r /app/requirements.txt

# 复制服务代码和共享模块
COPY services/common /app/services/common
COPY services/workers/faster_whisper_service /app/services/workers/faster_whisper_service
COPY config.yml /app/config.yml

# 设置 Python 路径
ENV PYTHONPATH=/app

# 默认命令
CMD ["celery", "-A", "services.workers.faster_whisper_service.app.celery_app", "worker", "-l", "info", "-Q", "faster_whisper_queue", "--concurrency=1"]
