# services/api_gateway/app/main.py
# -*- coding: utf-8 -*-

"""
API Gateway的主应用文件。

使用FastAPI创建Web服务，提供单节点任务与文件操作端点。
"""
from datetime import datetime

from fastapi import FastAPI, Request

from services.common.logger import get_logger

logger = get_logger('main')

# --- FastAPI 应用初始化 ---

app = FastAPI(
    title="YiVideo Single Task API",
    description="仅提供单节点任务执行与文件操作接口。",
    version="1.1.0"
)

# 导入监控模块
from .monitoring import monitoring_api

# 导入新添加的模块
from .file_operations import get_file_operations_router
from .single_task_api import get_single_task_router

# 集成监控API路由
monitoring_router = monitoring_api.get_router()
app.include_router(monitoring_router)

# 集成文件操作API路由
file_operations_router = get_file_operations_router()
app.include_router(file_operations_router)

# 集成单任务API路由
single_task_router = get_single_task_router()
app.include_router(single_task_router)

# --- 测试端点定义 ---

@app.get("/test")
@app.post("/test")
async def test_endpoint(request: Request):
    """
    测试端点，打印所有请求的headers和body
    """
    # 获取所有headers
    headers = dict(request.headers)
    
    # 获取请求方法
    method = request.method
    
    # 获取请求URL
    url = str(request.url)
    
    # 获取客户端IP
    client_ip = request.client.host if request.client else "Unknown"
    
    # 记录请求信息
    logger.info(f"收到{method}请求到{url}")
    logger.info(f"客户端IP: {client_ip}")
    logger.info("请求Headers:")
    for key, value in headers.items():
        logger.info(f"  {key}: {value}")
    
    # 获取请求body
    body_content = None
    content_length = 0
    
    try:
        # 尝试读取请求体
        if method in ["POST", "PUT", "PATCH"]:
            # 读取原始body
            body_bytes = await request.body()
            content_length = len(body_bytes)
            
            if content_length > 0:
                # 尝试解码为文本
                try:
                    body_content = body_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    # 如果不是UTF-8，显示为十六进制
                    body_content = body_bytes.hex()
                    
                logger.info(f"请求Body (长度: {content_length} bytes):")
                if content_length > 1024:  # 如果body太长，只显示前1024字符
                    logger.info(f"  {body_content[:1024]}...")
                else:
                    logger.info(f"  {body_content}")
            else:
                logger.info("请求Body: 空")
        else:
            logger.info("GET请求，无Body内容")
            
    except Exception as e:
        logger.error(f"读取请求Body时出错: {e}")
        body_content = f"Error reading body: {str(e)}"
    
    # 返回响应
    return {
        "status": "success",
        "message": "Test endpoint received your request",
        "request_info": {
            "method": method,
            "url": url,
            "client_ip": client_ip,
            "content_length": content_length
        },
        "headers": headers,
        "body": body_content,
        "timestamp": datetime.now().isoformat()
    }

# --- API 端点定义 ---

@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("正在初始化API Gateway...")

    try:
        # 初始化监控服务
        monitoring_api.initialize_monitoring()
        logger.info("监控服务初始化完成")
    except Exception as e:
        logger.error(f"监控服务初始化失败: {e}")

    logger.info("API Gateway 初始化完成")


@app.get("/", include_in_schema=False)
def root():
    """根路径，用于简单的健康检查。"""
    return {"message": "YiVideo Single Task API is running."}
