
from fastapi import FastAPI
from celery import Celery

app = FastAPI(title="YiVideo API Gateway")

# 这里的 broker 和 backend 地址应该从环境变量读取，但为简化暂用硬编码
# 实际项目中会用 Pydantic 的 Settings Management
celery_app = Celery(
    "tasks", 
    broker="redis://redis:6379/0", 
    backend="redis://redis:6379/0"
)

@app.get("/")
def read_root():
    return {"message": "Welcome to YiVideo API Gateway"}

# 示例：如何异步调用一个任务
@app.post("/tasks/test")
def run_test_task():
    # 调用一个名为 'test_task' 的 Celery 任务
    # 注意：这个任务需要在某个 Worker 中被定义
    task = celery_app.send_task("test_task", args=["hello world"])
    return {"task_id": task.id}

@app.get("/tasks/{task_id}")
def get_task_status(task_id: str):
    # 获取任务状态
    task_result = celery_app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": task_result.status,
        "result": task_result.result
    }

