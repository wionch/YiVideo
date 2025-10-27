# IndexTTS Service 部署指南

## 概述

本文档详细介绍如何在生产环境中部署 IndexTTS Service，包括 Docker 容器化部署、模型配置和性能优化。

## 部署架构

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   API Gateway   │    │     Redis       │    │  IndexTTS       │
│   (Port: 8788)  │◄──►│   (Message)     │◄──►│  Service        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
                       ┌─────────────────┐              │
                       │     Models      │◄─────────────┘
                       │   IndexTTS2     │
                       └─────────────────┘
```

## 系统要求

### 硬件要求

- **GPU**: NVIDIA GPU (支持 CUDA 12.9+)
- **显存**: 8GB+ (推荐 12GB+)
- **内存**: 16GB+ 系统内存
- **存储**: 50GB+ 可用空间（用于模型和缓存）
- **网络**: 稳定的互联网连接（用于模型下载）

### 软件要求

- **Docker**: 20.10+
- **Docker Compose**: 2.0+
- **CUDA**: 12.9+
- **GPU驱动**: 与 CUDA 版本兼容

## 快速部署

### 1. 克隆项目

```bash
git clone <repository-url>
cd YiVideo
```

### 2. 配置环境

```bash
# 创建模型目录
mkdir -p ./models/indextts

# IndexTTS2 源码会在构建 Docker 镜像时通过 git clone 自动获取
# 无需手动复制，详见 Dockerfile 中的配置
```

### 3. 构建和启动服务

```bash
# 构建服务镜像
docker-compose build indextts_service

# 启动服务
docker-compose up -d indextts_service

# 查看服务状态
docker-compose ps indextts_service
```

### 4. 验证部署

```bash
# 查看服务日志
docker-compose logs -f indextts_service

# 检查服务健康状态
curl http://localhost:8788/api/v1/monitoring/health

# 进入容器测试
docker-compose exec indextts_service python services/workers/indextts_service/test_indextts.py --check-env
```

## 详细配置

### 1. Docker Compose 配置

```yaml
# docker-compose.yml (部分配置)
indextts_service:
  container_name: indextts_service
  runtime: nvidia
  build:
    context: .
    dockerfile: ./services/workers/indextts_service/Dockerfile
  ports:
    - "7860:7860"  # WebUI端口
  volumes:
    - ./models/indextts:/models/indextts  # 模型存储
    - ./share:/share                     # 共享存储
    - ./config.yml:/app/config.yml      # 配置文件
  environment:
    - INDEX_TTS_USE_FP16=true           # 启用FP16
    - INDEX_TTS_USE_DEEPSPEED=false      # DeepSpeed优化
    - CUDA_VISIBLE_DEVICES=0            # GPU设备
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
      limits:
        memory: 8G  # 内存限制
```

### 2. 环境变量配置

创建 `.env` 文件：

```bash
# GPU配置
CUDA_VISIBLE_DEVICES=0
INDEX_TTS_USE_FP16=true
INDEX_TTS_USE_DEEPSPEED=false
INDEX_TTS_USE_CUDA_KERNEL=false

# 缓存配置
HF_HOME=/app/.cache/huggingface
TRANSFORMERS_CACHE=/app/.cache/transformers
TORCH_HOME=/app/.cache/torch

# Redis配置
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
```

### 3. 模型管理

#### 自动下载

服务启动时会自动下载 IndexTTS2 模型：

```bash
# 查看模型下载进度
docker-compose logs -f indextts_service | grep -i "download\|model"

# 检查模型文件
docker-compose exec indextts_service ls -la /models/indextts/checkpoints/
```

#### 手动下载（推荐）

```bash
# 进入容器
docker-compose exec indextts_service bash

# 下载模型
cd /tmp/index-tts
uv tool install "huggingface-hub[cli]"
hf download IndexTeam/IndexTTS-2 --local-dir=/models/indextts/checkpoints
```

#### 验证模型完整性

```bash
# 检查必需文件
docker-compose exec indextts_service bash -c "
  ls -la /models/indextts/checkpoints/ | grep -E '(config\.yaml|gpt\.pth|s2mel\.pth|bpe\.model)'
"
```

必需文件清单：
- `config.yaml` - 模型配置文件
- `gpt.pth` - GPT模型权重
- `s2mel.pth` - S2Mel模型权重
- `bpe.model` - BPE模型文件
- `wav2vec2bert_stats.pt` - 音频特征统计

## 性能优化

### 1. GPU 优化

```yaml
# docker-compose.yml 优化配置
environment:
  - INDEX_TTS_USE_FP16=true      # 减少显存占用50%
  - INDEX_TTS_USE_DEEPSPEED=true  # 加速推理（可选）
  - INDEX_TTS_USE_CUDA_KERNEL=true # CUDA内核优化（可选）
```

### 2. 内存优化

```yaml
deploy:
  resources:
    reservations:
      memory: 4G
    limits:
      memory: 8G
```

### 3. 并发优化

```bash
# 在 app.py 中调整
celery_app.conf.update(
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=10,  # 每个worker处理10个任务后重启
    task_soft_time_limit=1800,      # 30分钟软超时
    task_time_limit=2100,           # 35分钟硬超时
)
```

### 4. 缓存优化

```yaml
volumes:
  - ./models/indextts/cache:/app/.cache/indextts  # 模型缓存
  - ./models/app/cache:/app/.cache/huggingface   # HuggingFace缓存
  - ./models/root/cache:/app/.cache/transformers # Transformers缓存
```

## 监控和维护

### 1. 健康检查

```bash
# 服务健康检查
curl http://localhost:8788/api/v1/monitoring/health

# GPU锁状态检查
curl http://localhost:8788/api/v1/monitoring/gpu-lock/health

# 任务状态检查
curl http://localhost:8788/api/v1/celery/active_tasks
```

### 2. 日志管理

```bash
# 查看实时日志
docker-compose logs -f indextts_service

# 查看错误日志
docker-compose logs indextts_service | grep ERROR

# 日志轮转配置
# 在 Dockerfile 中配置日志目录
RUN mkdir -p /app/services/workers/indextts_service/logs
```

### 3. 资源监控

```bash
# GPU使用情况
watch -n 1 nvidia-smi

# 内存使用情况
docker stats indextts_service

# 磁盘使用情况
df -h /models
```

## WebUI 部署

### 1. 启动 WebUI

```bash
# 方法1: 在现有容器中启动
docker-compose exec indextts_service bash -c "
  cd /models/indextts && \
  source /tmp/index-tts/.venv/bin/activate && \
  python /tmp/index-tts/webui.py --host 0.0.0.0 --port 7860 --fp16 --model_dir ./checkpoints
"

# 方法2: 创建独立的 WebUI 服务
# 在 docker-compose.yml 中添加
indextts_webui:
  extends:
    file: docker-compose.yml
    service: indextts_service
  container_name: indextts_webui
  command: >
    bash -c "
      cd /models/indextts &&
      source /tmp/index-tts/.venv/bin/activate &&
      python /tmp/index-tts/webui.py --host 0.0.0.0 --port 7860 --fp16 --model_dir ./checkpoints
    "
  ports:
    - "7860:7860"
```

### 2. 访问 WebUI

- **本地访问**: http://localhost:7860
- **局域网访问**: http://服务器IP:7860
- **安全访问**: 通过 Nginx 或 API Gateway 反向代理

## 故障排除

### 常见错误及解决方案

#### 1. 模型下载失败

```
错误: 无法下载IndexTTS2模型
解决:
1. 检查网络连接
2. 使用镜像源：export HF_ENDPOINT=https://hf-mirror.com
3. 手动下载模型文件
```

#### 2. GPU内存不足

```
错误: CUDA out of memory
解决:
1. 启用FP16: INDEX_TTS_USE_FP16=true
2. 减少并发数: --concurrency=1
3. 增加GPU交换空间
```

#### 3. 模型加载失败

```
错误: Required file ./checkpoints/config.yaml does not exist
解决:
1. 检查模型目录路径
2. 验证模型文件完整性
3. 重新下载模型
```

#### 4. WebUI无法访问

```
错误: 连接被拒绝
解决:
1. 检查端口映射: docker-compose ps
2. 检查防火墙设置
3. 验证WebUI进程状态
```

### 调试命令

```bash
# 进入调试模式
docker-compose exec indextts_service bash

# 检查Python环境
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"

# 测试模型加载
python -c "
import sys
sys.path.append('/tmp/index-tts')
from indextts.infer_v2 import IndexTTS2
print('IndexTTS2导入成功')
"

# 检查Celery任务
celery -A services.workers.indextts_service.app.celery_app inspect active
```

## 扩展部署

### 1. 多节点部署

```yaml
# docker-compose.yml
indextts_service_1:
  extends:
    service: indextts_service
  container_name: indextts_service_1
  environment:
    - CUDA_VISIBLE_DEVICES=0

indextts_service_2:
  extends:
    service: indextts_service
  container_name: indextts_service_2
  environment:
    - CUDA_VISIBLE_DEVICES=1
```

### 2. 负载均衡

```nginx
# nginx.conf
upstream indextts_backend {
    server indextts_service_1:8788;
    server indextts_service_2:8788;
}

server {
    listen 80;
    location / {
        proxy_pass http://indextts_backend;
    }
}
```

### 3. 模型版本管理

```bash
# 支持多版本模型
./models/indextts/
├── checkpoints/          # 默认版本
├── checkpoints_v2.0/     # 版本2.0
└── checkpoints_latest/   # 最新版本
```

## 安全考虑

### 1. 网络安全

```yaml
# 限制端口暴露
ports:
  - "127.0.0.1:8788:80"  # 仅本地访问API
  - "7860:7860"          # WebUI可外部访问
```

### 2. 访问控制

```bash
# 在WebUI中添加认证
# 或通过API Gateway统一认证
```

### 3. 数据安全

```bash
# 敏感配置加密
echo "API_KEY" | docker secret create indextts_api_key -
```

## 备份和恢复

### 1. 模型备份

```bash
# 备份模型文件
tar -czf indextts_models_$(date +%Y%m%d).tar.gz ./models/indextts/

# 恢复模型文件
tar -xzf indextts_models_20251012.tar.gz
```

### 2. 配置备份

```bash
# 备份配置
cp docker-compose.yml docker-compose.yml.backup
cp .env .env.backup
```

## 许可证

IndexTTS2 模型遵循其原始许可证。本服务代码遵循 MIT 许可证。