# services/api_gateway/Dockerfile

# 1. 使用轻量级的官方Python镜像
FROM python:3.10-slim-buster

# 2. 设置环境变量
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app

# 3. 创建并设置工作目录
WORKDIR /app

# 4. 复制并安装依赖
# 这一步保持不变，它需要从构建上下文中找到正确的文件
COPY ./services/api_gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 复制所有服务代码到工作目录
# 这将创建 /app/services/api_gateway, /app/services/common 等结构
COPY ./services /app/services/

# 6. 暴露容器的80端口
EXPOSE 80

# 7. 定义容器启动时执行的命令
# 使用完整的模块路径来指定FastAPI应用实例
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "services.api_gateway.app.main:app", "--bind", "0.0.0.0:80"]