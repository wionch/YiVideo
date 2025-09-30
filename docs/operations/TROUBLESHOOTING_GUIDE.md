# WhisperX 故障排除指南

## 目录

1. [快速诊断](#快速诊断)
2. [常见错误代码](#常见错误代码)
3. [性能问题](#性能问题)
4. [资源问题](#资源问题)
5. [网络问题](#网络问题)
6. [配置问题](#配置问题)
7. [调试工具](#调试工具)
8. [联系支持](#联系支持)

---

## 快速诊断

### 诊断流程图

```
开始
  ↓
检查服务状态 → 正常 → 检查工作流执行
  ↓                      ↓
异常                    正常 → 问题解决
  ↓                      ↓
检查日志文件            异常 → 检查输入数据
  ↓                      ↓
修复问题                正常 → 检查配置
  ↓                      ↓
重启服务                异常 → 检查环境
  ↓                      ↓
验证修复                修复环境
  ↓                      ↓
问题解决                重启服务
```

### 快速检查清单

```bash
# 1. 检查服务状态
docker-compose ps
docker-compose logs --tail=50

# 2. 检查系统资源
nvidia-smi
free -h
df -h

# 3. 检查网络连接
curl http://localhost:8788/health
curl http://localhost:6379/ping

# 4. 检查 GPU 锁状态
curl http://localhost:8788/api/v1/monitoring/gpu-lock/health

# 5. 检查最近的工作流
curl http://localhost:8788/v1/workflows/recent
```

---

## 常见错误代码

### API 错误 (4xx/5xx)

#### 400 Bad Request

**错误信息**: "Bad Request: invalid input parameters"

**可能原因**:
- 请求参数格式错误
- 缺少必需参数
- 参数值不在有效范围内

**解决方案**:
```bash
# 检查请求格式
curl -X POST http://localhost:8788/v1/workflows \
  -H "Content-Type: application/json" \
  -d '{"video_path": "/app/videos/test.mp4"}'

# 验证参数
python scripts/validate_request.py
```

#### 401 Unauthorized

**错误信息**: "Unauthorized: invalid API key"

**可能原因**:
- API 密钥无效或缺失
- 认证服务不可用

**解决方案**:
```bash
# 检查 API 密钥配置
grep -r "api_key" config.yml

# 重启认证服务
docker-compose restart auth_service
```

#### 404 Not Found

**错误信息**: "Not Found: workflow does not exist"

**可能原因**:
- 工作流 ID 不存在
- 工作流已过期

**解决方案**:
```bash
# 检查工作流状态
curl http://localhost:8788/v1/workflows/status/{workflow_id}

# 查看最近的工作流
curl http://localhost:8788/v1/workflows/recent
```

#### 500 Internal Server Error

**错误信息**: "Internal Server Error"

**可能原因**:
- 服务器内部错误
- 数据库连接失败
- GPU 资源不足
- WhisperX 构建问题

**解决方案**:
```bash
# 检查详细日志
docker-compose logs --tail=100 api_gateway
docker-compose logs --tail=100 whisperx_service

# 检查数据库连接
docker-compose exec redis redis-cli ping

# 检查 GPU 状态
nvidia-smi

# 检查 WhisperX 服务状态
docker exec whisperx_service celery -A app.tasks.celery_app inspect active
```

### WhisperX 特定错误

#### 模型加载错误

**错误信息**: "Failed to load WhisperX model"

**可能原因**:
- 模型文件损坏
- 网络连接问题
- 显存不足

**解决方案**:
```bash
# 检查模型文件
ls -la /app/.cache/whisperx/

# 清理模型缓存
rm -rf /app/.cache/whisperx/*

# 重新下载模型
docker-compose restart whisperx_service
```

#### Hugging Face 认证错误

**错误信息**: "Failed to download model from Hugging Face Hub" 或 "Authorization required"

**可能原因**:
- HF_TOKEN 环境变量未设置或无效
- use_auth_token 参数未正确配置
- 网络连接问题

**解决方案**:
```bash
# 1. 检查 HF_TOKEN 是否配置
docker exec whisperx_service env | grep HF_TOKEN

# 2. 验证 use_auth_token 修复
docker exec whisperx_service sh -c 'grep -n "HF_TOKEN" /usr/local/lib/python3.10/dist-packages/whisperx/asr.py'

# 3. 如果修复未生效，重新构建容器
docker-compose build whisperx_service --no-cache
docker-compose up -d whisperx_service

# 4. 验证修复
docker-compose logs --tail=20 whisperx_service | grep "Hugging Face Token"
```

#### Docker 构建错误

**错误信息**: "sed command failed" 或 "file not found"

**可能原因**:
- WhisperX 版本更新导致文件路径变化
- sed 命令模式不匹配
- 构建权限问题

**解决方案**:
```bash
# 1. 检查 WhisperX 安装位置
docker exec whisperx_service python -c "import whisperx; print(whisperx.__file__)"

# 2. 手动验证文件存在
docker exec whisperx_service ls -la /usr/local/lib/python3.10/dist-packages/whisperx/

# 3. 检查当前内容
docker exec whisperx_service grep -n "use_auth_token" /usr/local/lib/python3.10/dist-packages/whisperx/asr.py

# 4. 如需手动修复
docker exec whisperx_service sh -c 'sed -i "s/use_auth_token=None/use_auth_token=os.getenv(\"HF_TOKEN\")/g" /usr/local/lib/python3.10/dist-packages/whisperx/asr.py'
```

#### Faster-Whisper 后端问题

**错误信息**: "Faster-Whisper initialization failed" 或性能下降

**可能原因**:
- ctranslate2 版本不兼容
- faster-whisper 配置错误
- GPU 驱动问题

**解决方案**:
```bash
# 1. 检查依赖版本
docker exec whisperx_service pip list | grep -E "(faster-whisper|ctranslate2)"

# 2. 验证配置
grep -A 10 "faster_whisper" config.yml

# 3. 测试原生后端降级
# 编辑 config.yml 临时禁用 faster-whisper
whisperx_service:
  use_faster_whisper: false

# 4. 重启服务
docker-compose restart whisperx_service

# 5. 性能对比测试
time python scripts/test_whisperx_performance.py
```

#### GPU 内存不足

**错误信息**: "CUDA out of memory"

**可能原因**:
- 批处理大小过大
- 模型过大
- 其他进程占用显存

**解决方案**:
```bash
# 检查显存使用
nvidia-smi

# 调整批处理大小
# 编辑 config.yml
whisperx_service:
  batch_size: 2  # 减小批处理大小

# 重启服务
docker-compose restart whisperx_service
```

#### 音频处理错误

**错误信息**: "Audio processing failed"

**可能原因**:
- 音频格式不支持
- 音频文件损坏
- FFmpeg 不可用

**解决方案**:
```bash
# 检查 FFmpeg
docker-compose exec whisperx_service ffmpeg -version

# 验证音频文件
docker-compose exec whisperx_service ffprobe /app/videos/test.mp4

# 重新安装 FFmpeg
docker-compose build --no-cache whisperx_service
```

---

## 性能问题

### 执行时间过长

#### 诊断步骤

```bash
# 1. 检查 GPU 利用率
watch -n 1 nvidia-smi

# 2. 检查 CPU 使用
htop

# 3. 检查磁盘 I/O
iostat -x 1

# 4. 检查网络带宽
iftop

# 5. 运行性能分析
python scripts/performance_analysis.py
```

#### 优化方案

```yaml
# config.yml 优化
whisperx_service:
  batch_size: 4              # 优化批处理大小
  compute_type: "float16"    # 使用半精度
  use_faster_whisper: true    # 启用 Faster-Whisper
  faster_whisper_threads: 4  # 优化线程数

pipeline:
  detect_keyframes: true     # 启用关键帧检测
  use_image_concat: true     # 启用图像拼接
```

### 内存泄漏

#### 诊断步骤

```bash
# 1. 监控内存使用
watch -n 1 'free -h'

# 2. 检查 Docker 容器内存
docker stats --format "table {{.Container}}\t{{.MemUsage}}"

# 3. 分析内存使用
python scripts/memory_analysis.py
```

#### 解决方案

```python
# 添加内存清理代码
import torch
import gc

def cleanup_memory():
    """清理内存"""
    torch.cuda.empty_cache()
    gc.collect()
```

### GPU 利用率低

#### 诊断步骤

```bash
# 1. 检查 GPU 状态
nvidia-smi dmon

# 2. 检查 GPU 进程
nvidia-smi pmon

# 3. 检查 CUDA 版本
nvcc --version
```

#### 解决方案

```bash
# 1. 优化批处理大小
# 调整 config.yml 中的 batch_size

# 2. 启用 GPU 加速
确保 config.yml 中 device: "cuda"

# 3. 检查 GPU 驱动
sudo nvidia-smi --query-gpu=driver_version,name --format=csv
```

---

## 资源问题

### CPU 资源不足

#### 诊断

```bash
# 检查 CPU 使用率
top
htop

# 检查 CPU 核心数
nproc

# 检查进程数
ps aux | wc -l
```

#### 解决方案

```bash
# 1. 限制进程数
ulimit -u 4096

# 2. 优化 CPU 亲和性
taskset -c 0,1,2,3 python script.py

# 3. 升级 CPU 或增加核心数
```

### 内存不足

#### 诊断

```bash
# 检查内存使用
free -h
cat /proc/meminfo

# 检查内存泄漏
valgrind --leak-check=full python script.py
```

#### 解决方案

```bash
# 1. 增加交换空间
sudo fallocate -l 4G /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 2. 优化内存使用
# 调整 config.yml 中的内存相关参数

# 3. 增加物理内存
```

### 磁盘空间不足

#### 诊断

```bash
# 检查磁盘使用
df -h
du -sh /app/*

# 查找大文件
find /app -type f -size +100M
```

#### 解决方案

```bash
# 1. 清理日志文件
find /logs -name "*.log" -mtime +7 -delete

# 2. 清理临时文件
find /tmp -name "*.tmp" -delete

# 3. 清理 Docker 缓存
docker system prune -f

# 4. 扩展磁盘空间
```

---

## 网络问题

### 连接超时

#### 诊断

```bash
# 检查网络连接
ping 8.8.8.8

# 检查端口监听
netstat -tlnp | grep 8788

# 检查防火墙
sudo ufw status
```

#### 解决方案

```bash
# 1. 检查防火墙设置
sudo ufw allow 8788
sudo ufw allow 6379

# 2. 重启网络服务
sudo systemctl restart network

# 3. 检查 DNS 配置
cat /etc/resolv.conf
```

### Redis 连接问题

#### 诊断

```bash
# 检查 Redis 状态
docker-compose ps redis
docker-compose logs redis

# 测试 Redis 连接
redis-cli -h redis -p 6379 ping
```

#### 解决方案

```bash
# 1. 重启 Redis
docker-compose restart redis

# 2. 检查 Redis 配置
docker-compose exec redis redis-cli config get *

# 3. 检查网络连接
docker-compose exec redis redis-cli info clients
```

### API 限流

#### 诊断

```bash
# 检查 API 请求频率
curl -I http://localhost:8788/health

# 检查限流配置
grep -r "rate_limit" config.yml
```

#### 解决方案

```yaml
# 调整限流配置
api_gateway:
  rate_limit:
    requests_per_minute: 100
    burst_size: 10
```

---

## 配置问题

### 配置文件错误

#### 诊断

```bash
# 验证配置文件
python scripts/validate_config.py

# 检查配置文件语法
python -c "import yaml; yaml.safe_load(open('config.yml'))"
```

#### 解决方案

```bash
# 1. 备份当前配置
cp config.yml config.yml.backup

# 2. 使用默认配置
cp config.yml.default config.yml

# 3. 重新配置
python scripts/setup_config.py
```

### 环境变量问题

#### 诊断

```bash
# 检查环境变量
env | grep -i whisperx

# 检查 Docker 环境变量
docker-compose exec api_gateway env
```

#### 解决方案

```bash
# 1. 设置环境变量
export CUDA_VISIBLE_DEVICES=0
export WHISPERX_MODEL_PATH=/app/models

# 2. 更新 docker-compose.yml
environment:
  - CUDA_VISIBLE_DEVICES=0
  - WHISPERX_MODEL_PATH=/app/models
```

---

## 调试工具

### 日志分析工具

```bash
# 1. 实时日志监控
docker-compose logs -f --tail=100

# 2. 错误日志过滤
docker-compose logs 2>&1 | grep -i error

# 3. 性能日志分析
docker-compose logs whisperx_service | grep "execution_time"
```

### 性能分析工具

```python
# 性能分析脚本
import time
import psutil
import torch

def analyze_performance():
    """分析系统性能"""
    print("=== 性能分析报告 ===")
    print(f"CPU 使用率: {psutil.cpu_percent()}%")
    print(f"内存使用率: {psutil.virtual_memory().percent}%")

    if torch.cuda.is_available():
        print(f"GPU 显存使用: {torch.cuda.memory_allocated()/1024**3:.2f}GB")
        print(f"GPU 利用率: {get_gpu_utilization()}%")

def get_gpu_utilization():
    """获取 GPU 利用率"""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
            capture_output=True, text=True
        )
        return float(result.stdout.strip())
    except:
        return 0.0
```

### 健康检查工具

```bash
#!/bin/bash
# 健康检查脚本

echo "=== 系统健康检查 ==="

# 检查服务状态
echo "1. 检查服务状态..."
docker-compose ps

# 检查 API 健康度
echo "2. 检查 API 健康度..."
curl -f http://localhost:8788/health || echo "API 不健康"

# 检查 Redis 连接
echo "3. 检查 Redis 连接..."
docker-compose exec redis redis-cli ping || echo "Redis 连接失败"

# 检查 GPU 状态
echo "4. 检查 GPU 状态..."
nvidia-smi --query-gpu=utilization.gpu,name --format=csv,noheader,nounits

# 检查磁盘空间
echo "5. 检查磁盘空间..."
df -h | grep -E "Filesystem|/dev/sda"
```

---

## 联系支持

### 支持渠道

- **技术支持**: support@yivideo.com
- **紧急联系**: +86-xxx-xxxx-xxxx
- **GitHub Issues**: https://github.com/yivideo/issues
- **文档中心**: https://docs.yivideo.com

### 报告问题时请提供

1. **系统信息**:
   ```bash
   uname -a
   docker --version
   docker-compose --version
   nvidia-smi
   ```

2. **日志文件**:
   ```bash
   docker-compose logs > logs.txt
   ```

3. **配置文件**:
   ```bash
   cat config.yml
   ```

4. **错误描述**:
   - 问题描述
   - 复现步骤
   - 期望结果
   - 实际结果

### 常见问题解答

**Q: 如何提高处理速度？**
A: 调整批处理大小，启用 Faster-Whisper，优化 GPU 配置。

**Q: 如何处理 GPU 内存不足？**
A: 减小批处理大小，使用半精度，清理显存缓存。

**Q: 如何监控系统性能？**
A: 使用 Prometheus + Grafana，查看性能仪表板。

**Q: 如何备份系统数据？**
A: 定期备份配置文件和 Redis 数据。

---

## WhisperX Docker 构建最佳实践

### 🔧 构建前检查

#### 1. 环境验证
```bash
# 检查基础镜像
docker pull ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddle:3.1.1-gpu-cuda11.8-cudnn8.9

# 验证网络连接
curl -I https://huggingface.co
curl -I https://pypi.org/simple/whisperx

# 检查磁盘空间
df -h /var/lib/docker
```

#### 2. 依赖版本确认
```bash
# 检查 WhisperX 最新版本
pip show whisperx

# 确认兼容的依赖版本
pip show faster-whisper ctranslate2
```

### 🏗️ 构建过程优化

#### 1. 分层构建策略
```dockerfile
# 基础系统层
FROM ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddle:3.1.1-gpu-cuda11.8-cudnn8.9

# 系统依赖层 (变化频率低)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsox-dev libsndfile1-dev curl wget git && \
    rm -rf /var/lib/apt/lists/*

# Python 依赖层 (变化频率中等)
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# 应用代码层 (变化频率高)
COPY . /app/
```

#### 2. 缓存优化
```bash
# 使用 --no-cache 重新构建
docker-compose build whisperx_service --no-cache

# 或者选择性清理缓存
docker builder prune -f
```

### 🐛 常见构建问题解决

#### 1. sed 命令失败
```bash
# 检查目标文件是否存在
docker run --rm ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddle:3.1.1-gpu-cuda11.8-cudnn8.9 \
  sh -c 'ls -la /usr/local/lib/python3.10/dist-packages/whisperx/'

# 验证 sed 模式
echo 'use_auth_token=None' | sed 's/use_auth_token=None/use_auth_token=os.getenv("HF_TOKEN")/g'
```

#### 2. 网络超时
```dockerfile
# 设置国内镜像源
RUN pip install --no-cache-dir -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
    whisperx

# 增加超时时间
RUN pip install --timeout 300 --retries 3 whisperx
```

#### 3. 权限问题
```dockerfile
# 确保正确的用户权限
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    chmod -R 755 /app/.cache
```

### ✅ 构建验证清单

#### 1. 功能验证
```bash
# 检查服务状态
docker-compose ps whisperx_service

# 验证 Celery Worker
docker exec whisperx_service celery -A app.tasks.celery_app inspect active

# 测试模型加载
docker exec whisperx_service python -c "import whisperx; print('Import successful')"
```

#### 2. 配置验证
```bash
# 检查环境变量
docker exec whisperx_service env | grep -E "(HF_|WHISPERX|TRANSFORMERS)"

# 验证 use_auth_token 修复
docker exec whisperx_service sh -c 'grep -n "HF_TOKEN" /usr/local/lib/python3.10/dist-packages/whisperx/asr.py'

# 检查缓存目录
docker exec whisperx_service ls -la /app/.cache/
```

#### 3. 性能验证
```bash
# 运行简单测试
python scripts/test_whisperx_service.py

# 检查日志
docker-compose logs --tail=50 whisperx_service

# 监控资源使用
docker stats whisperx_service
```

### 🚀 生产部署建议

#### 1. 镜像管理
```bash
# 标记生产镜像
docker tag yivideo-whisperx_service:latest yivideo-whisperx_service:v2.0.1

# 推送到私有仓库
docker push registry.example.com/yivideo-whisperx_service:v2.0.1
```

#### 2. 健康检查
```dockerfile
# 在 Dockerfile 中添加健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD celery -A app.tasks.celery_app inspect active || exit 1
```

#### 3. 日志管理
```yaml
# 在 docker-compose.yml 中配置日志
logging:
  driver: "json-file"
  options:
    max-size: "100m"
    max-file: "5"
```

### 📊 性能调优

#### 1. 资源限制
```yaml
# docker-compose.yml 中的资源配置
deploy:
  resources:
    limits:
      memory: 8G
      cpus: '4'
    reservations:
      memory: 4G
      cpus: '2'
```

#### 2. 存储优化
```yaml
# 使用 tmpfs 提升临时文件性能
tmpfs:
  - /tmp
```

#### 3. 网络优化
```yaml
# 使用专用网络
networks:
  whisperx_net:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

---

## 总结

本故障排除指南提供了 WhisperX 系统常见问题的诊断和解决方案，以及Docker构建的最佳实践。请按照本指南的步骤进行故障排除，如仍无法解决问题，请联系技术支持。

定期进行系统维护和性能监控，可以有效预防问题的发生。