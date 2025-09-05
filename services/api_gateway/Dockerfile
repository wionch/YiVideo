
# ./services/api_gateway/Dockerfile
FROM yivideo-base:latest

COPY requirements.txt .
# 安装所有依赖, 包括 gunicorn
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app .

# 使用 Gunicorn 启动 4 个 Uvicorn worker 进程
# -w 4: 指定 4 个 worker 进程 (可根据 CPU 核心数调整)
# -k uvicorn.workers.UvicornWorker: 指定使用 Uvicorn 作为 worker 类
# main:app: 指向 main.py 文件中的 app 实例
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--host", "0.0.0.0", "--port", "8000"]
