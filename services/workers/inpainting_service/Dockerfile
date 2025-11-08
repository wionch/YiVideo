# services/workers/inpainting_service/Dockerfile

# 1. 使用在 docker-compose.yml 中定义的基础镜像
FROM yivideo-base:latest

# 2. 设置工作目录为项目根目录
WORKDIR /app

# 3. 安装系统依赖 (如果需要，在此处添加)
# RUN apt-get update && apt-get install -y ...

# 4. 优化Docker缓存：先复制并安装Python依赖
# 注意：现在路径需要从项目根目录开始
COPY ./services/workers/inpainting_service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r /tmp/requirements.txt

# 5. 复制所有服务相关的源代码到工作目录
COPY ./services /app/services

# 6. 将项目根目录 /app 添加到 PYTHONPATH，以便能找到 services.common 等共享模块
ENV PYTHONPATH "${PYTHONPATH}:/app"

# 7. 为 CMD 设置正确的工作目录
WORKDIR /app/services/workers/inpainting_service

# 8. 定义容器启动时执行的默认命令 (会被 docker-compose 的 command 覆盖, 但作为默认值是好的)
CMD ["celery", "-A", "app.tasks.celery_app", "worker", "-l", "info", "-Q", "inpainting_queue"]