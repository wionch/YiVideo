# 系统通用故障排除指南

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
- ASR或说话人分离服务内部错误

**解决方案**:
```bash
# 检查详细日志
docker-compose logs --tail=100 api_gateway
docker-compose logs --tail=100 faster_whisper_service
docker-compose logs --tail=100 pyannote_audio_service

# 检查数据库连接
docker-compose exec redis redis-cli ping

# 检查 GPU 状态
nvidia-smi

# 检查 ASR 服务状态
docker exec faster_whisper_service celery -A app.celery_app inspect active

# 检查说话人分离服务状态
docker exec pyannote_audio_service celery -A app.celery_app inspect active
```

### ASR 与说话人分离服务特定错误 (faster-whisper & pyannote)

#### 模型加载错误

**错误信息**: "Failed to load ASR/Diarization model"

**可能原因**:
- ASR (Faster-Whisper) 或说话人分离 (Pyannote) 模型文件损坏
- 网络连接问题，无法从 Hugging Face 下载模型
- 显存不足

**解决方案**:
```bash
# 检查模型文件 (路径取决于 config.yml)
# ls -la /path/to/your/model/cache/

# 清理模型缓存
# rm -rf /path/to/your/model/cache/*

# 触发模型重新下载
docker-compose restart faster_whisper_service pyannote_audio_service
```

#### Hugging Face 认证错误

**错误信息**: "Failed to download model from Hugging Face Hub" 或 "Authorization required" (通常来自 `pyannote_audio_service`)

**可能原因**:
- HF_TOKEN 环境变量未设置或无效
- use_auth_token 参数未正确配置
- 网络连接问题

**解决方案**:
```bash
# 1. 检查 HF_TOKEN 是否配置 (主要影响 pyannote_audio_service)
docker exec pyannote_audio_service env | grep HF_TOKEN

# 2. 如果需要，重新构建容器
docker-compose build pyannote_audio_service --no-cache
docker-compose up -d pyannote_audio_service

# 3. 验证
docker-compose logs --tail=20 pyannote_audio_service
```


#### Faster-Whisper 后端问题

**错误信息**: "Faster-Whisper initialization failed" 或性能下降

**可能原因**:
- ctranslate2 版本不兼容
- faster-whisper 配置错误
- GPU 驱动问题

**解决方案**:
```bash
# 1. 检查 faster-whisper 依赖版本
docker exec faster_whisper_service pip list | grep -E "(faster-whisper|ctranslate2)"

# 2. 验证配置
grep -A 10 "faster_whisper" config.yml

# 3. 测试原生后端降级

# 4. 重启服务
docker-compose restart faster_whisper_service

# 5. 性能对比测试 (示例)
# time python scripts/performance_benchmark.py --service faster_whisper
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
faster_whisper_service:
  batch_size: 2  # 减小批处理大小

# 重启服务
docker-compose restart faster_whisper_service
```

#### 音频处理错误

**错误信息**: "Audio processing failed"

**可能原因**:
- 音频格式不支持
- 音频文件损坏
- FFmpeg 不可用

**解决方案**:
```bash
# 检查 FFmpeg (通常在 ffmpeg_service 中)
docker-compose exec ffmpeg_service ffmpeg -version

# 验证音频文件
docker-compose exec ffmpeg_service ffprobe /app/videos/test.mp4

# 重新安装 FFmpeg
docker-compose build --no-cache ffmpeg_service
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
faster_whisper_service:
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
env | grep -i -E "(faster_whisper|pyannote)"

# 检查 Docker 环境变量
docker-compose exec api_gateway env
```

#### 解决方案

```bash
# 1. 设置环境变量
export CUDA_VISIBLE_DEVICES=0
# export OBSOLETE_WHISPERX_MODEL_PATH=/app/models

# 2. 更新 docker-compose.yml
environment:
  - CUDA_VISIBLE_DEVICES=0
  # - OBSOLETE_WHISPERX_MODEL_PATH=/app/models
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
docker-compose logs faster_whisper_service | grep "execution_time"
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

## ASR 与说话人分离服务 Docker 构建最佳实践

### 🔧 构建前检查

#### 1. 环境验证
```bash
# 检查基础镜像
docker pull ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddle:3.1.1-gpu-cuda11.8-cudnn8.9

# 验证网络连接
curl -I https://huggingface.co
curl -I https://pypi.org/simple/faster-whisper
curl -I https://pypi.org/simple/pyannote-audio

# 检查磁盘空间
df -h /var/lib/docker
```

#### 2. 依赖版本确认
```bash
# 检查服务依赖版本
pip show faster-whisper
pip show pyannote.audio

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
docker-compose build faster_whisper_service pyannote_audio_service --no-cache

# 或者选择性清理缓存
docker builder prune -f
```

### 🐛 常见构建问题解决


#### 2. 网络超时
```dockerfile
# 设置国内镜像源
RUN pip install --no-cache-dir -i http://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
    faster-whisper pyannote.audio

# 增加超时时间
RUN pip install --timeout 300 --retries 3 faster-whisper pyannote.audio
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
docker-compose ps faster_whisper_service pyannote_audio_service

# 验证 Celery Worker
docker exec faster_whisper_service celery -A app.celery_app inspect active
docker exec pyannote_audio_service celery -A app.celery_app inspect active

# 测试模型加载
docker exec faster_whisper_service python -c "from faster_whisper import WhisperModel; print('Import successful')"
docker exec pyannote_audio_service python -c "from pyannote.audio import Pipeline; print('Import successful')"
```

#### 2. 配置验证
```bash
# 检查环境变量
docker exec faster_whisper_service env | grep "TRANSFORMERS"
docker exec pyannote_audio_service env | grep "HF_"

# 检查缓存目录 (路径取决于 config.yml)
# docker exec <service_name> ls -la /path/to/your/model/cache/
```

#### 3. 性能验证
```bash
# 运行简单测试 (示例)
# python scripts/test_service.py --service faster_whisper

# 检查日志
docker-compose logs --tail=50 faster_whisper_service

# 监控资源使用
docker stats faster_whisper_service
```

### 🚀 生产部署建议

#### 1. 镜像管理
```bash
# 标记生产镜像
docker tag yivideo-faster_whisper_service:latest yivideo-faster_whisper_service:v2.0.1
docker tag yivideo-pyannote_audio_service:latest yivideo-pyannote_audio_service:v2.0.1

# 推送到私有仓库
docker push registry.example.com/yivideo-faster_whisper_service:v2.0.1
docker push registry.example.com/yivideo-pyannote_audio_service:v2.0.1
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
  asr_net:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

---

## 总结

本故障排除指南提供了 YiVideo 系统常见问题的诊断和解决方案，以及Docker构建的最佳实践。请按照本指南的步骤进行故障排除，如仍无法解决问题，请联系技术支持。

定期进行系统维护和性能监控，可以有效预防问题的发生。

---

# IndexTTS2 故障排除指南

## 概述

本指南提供 IndexTTS2 语音合成服务常见问题的诊断和解决方案。

## 系统状态检查

### 基础状态检查

```bash
# 1. 检查服务状态
docker-compose ps | grep indextts

# 2. 检查服务健康状态
docker exec indextts_service python3 -c "
from services.workers.indextts_service.app import health_check
result = health_check()
print('健康检查结果:', result)
"

# 3. 检查 GPU 状态
docker exec indextts_service nvidia-smi

# 4. 检查 Redis 连接
docker exec indextts_service python3 -c "
import redis
r = redis.Redis(host='redis', port=6379, db=2)
print('Redis连接状态:', r.ping())
"
```

### 日志检查

```bash
# 查看实时日志
docker-compose logs -f indextts_service

# 查看最近的错误日志
docker-compose logs --tail=100 indextts_service | grep -i error

# 查看GPU相关日志
docker-compose logs indextts_service | grep -i gpu
```

## 常见错误及解决方案

### 错误类型1: 参数验证错误

#### 错误信息: "输入文本不能为空"

**症状**:
```
{'status': 'error', 'error': '输入文本不能为空', 'task_id': 'abc123'}
```

**原因**: 缺少必需的 `text` 参数

**解决方案**:
```json
{
  "workflow_config": {
    "text": "这里是要转换的文本内容",
    // ... 其他参数
  }
}
```

#### 错误信息: "输出路径不能为空"

**症状**:
```
{'status': 'error', 'error': '输出路径不能为空', 'task_id': 'abc123'}
```

**原因**: 缺少必需的 `output_path` 参数

**解决方案**:
```json
{
  "workflow_config": {
    "output_path": "/share/workflows/output/speech.wav",
    // ... 其他参数
  }
}
```

#### 错误信息: "缺少必需参数: spk_audio_prompt"

**症状**:
```
{'status': 'error', 'error': '缺少必需参数: spk_audio_prompt (说话人参考音频)', 'hint': 'IndexTTS2是基于参考音频的语音合成系统，必须提供说话人参考音频'}
```

**原因**: 缺少必需的说话人参考音频

**解决方案**:
```json
{
  "workflow_config": {
    "spk_audio_prompt": "/share/reference/speaker_sample.wav",
    // ... 其他参数
  }
}
```

#### 错误信息: "参考音频文件不存在"

**症状**:
```
{'status': 'error', 'error': '参考音频文件不存在: /path/to/reference.wav'}
```

**原因**: 指定的参考音频文件路径不存在

**诊断步骤**:
```bash
# 检查文件是否存在
docker exec indextts_service ls -la /path/to/reference.wav

# 检查文件权限
docker exec indextts_service stat /path/to/reference.wav

# 检查文件格式
docker exec indextts_service file /path/to/reference.wav
```

**解决方案**:
```bash
# 1. 确保参考音频文件存在
docker exec indextts_service mkdir -p /share/reference/
docker cp /path/to/your/reference.wav /share/reference/

# 2. 验证文件可读
docker exec indextts_service chmod 644 /share/reference/reference.wav

# 3. 更新工作流配置使用正确的路径
```

### 错误类型2: GPU相关错误

#### 错误信息: CUDA out of memory

**症状**:
```
RuntimeError: CUDA out of memory
```

**诊断步骤**:
```bash
# 检查GPU内存使用
docker exec indextts_service nvidia-smi

# 检查GPU进程
docker exec indextts_service ps aux | grep python

# 检查模型大小
docker exec indextts_service du -sh /models/indextts/
```

**解决方案**:
```yaml
# 编辑 config.yml
indextts_service:
  use_fp16: true                    # 启用FP16节省显存
  use_deepspeed: false              # 禁用DeepSpeed
  num_workers: 1                    # 保持单工作进程
```

```bash
# 重启服务
docker-compose restart indextts_service
```

#### 错误信息: GPU not available

**症状**:
```
RuntimeError: No CUDA GPUs are available
```

**诊断步骤**:
```bash
# 检查NVIDIA驱动
nvidia-smi

# 检查Docker GPU支持
docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi

# 检查容器GPU挂载
docker inspect indextts_service | grep -A 10 -B 10 DeviceRequests
```

**解决方案**:
```yaml
# docker-compose.yml 中确保GPU挂载正确
indextts_service:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

### 错误类型3: 文件系统错误

#### 错误信息: 无法创建输出目录

**症状**:
```
{'status': 'error', 'error': '无法创建输出目录 /share/output: Permission denied'}
```

**诊断步骤**:
```bash
# 检查目录权限
docker exec indextts_service ls -la /share/

# 检查磁盘空间
docker exec indextts_service df -h

# 尝试手动创建目录
docker exec indextts_service mkdir -p /share/workflows/output/test
```

**解决方案**:
```bash
# 修复目录权限
docker exec indextts_service chmod -R 755 /share/workflows/

# 确保目录可写
docker exec indextts_service touch /share/workflows/output/.write_test
```

#### 错误信息: 模型文件不存在

**症状**:
```
FileNotFoundError: [Errno 2] No such file or directory: '/models/indextts/checkpoints/config.yaml'
```

**诊断步骤**:
```bash
# 检查模型目录
docker exec indextts_service ls -la /models/indextts/

# 检查检查点目录
docker exec indextts_service ls -la /models/indextts/checkpoints/

# 检查模型文件完整性
docker exec indextts_service find /models/indextts/ -name "*.yaml" -o -name "*.pt" | head -10
```

**解决方案**:
```bash
# 重新下载模型（如果需要）
# 这通常需要重新构建容器或手动下载模型文件

# 检查Docker卷挂载
docker volume ls | grep indextts
docker volume inspect yivideo_indextts_models_volume
```

### 错误类型4: 网络和服务错误

#### 错误信息: Redis连接失败

**症状**:
```
ConnectionError: Error 111 connecting to redis:6379
```

**诊断步骤**:
```bash
# 检查Redis服务状态
docker-compose ps | grep redis

# 测试Redis连接
docker exec redis redis-cli ping

# 检查网络连接
docker exec indextts_service ping redis
```

**解决方案**:
```bash
# 重启Redis服务
docker-compose restart redis

# 检查网络配置
docker network ls | grep wionch
```

#### 错误信息: 任务超时

**症状**:
```
TaskTimeoutError: Task indextts.generate_speech timed out after 1800 seconds
```

**诊断步骤**:
```bash
# 检查任务状态
docker exec indextts_service python3 -c "
from services.common.locks import SmartGpuLockManager
manager = SmartGpuLockManager()
print('当前锁状态:', manager.get_lock_info())
"

# 检查GPU使用情况
docker exec indextts_service nvidia-smi
```

**解决方案**:
```yaml
# 增加超时时间
# 在 celery_app.conf.update 中调整
task_soft_time_limit: 3600  # 60分钟软超时
task_time_limit: 4200       # 70分钟硬超时
```

## 性能问题诊断

### 处理速度慢

**症状**: 任务执行时间过长

**诊断步骤**:
```bash
# 1. 检查GPU利用率
watch -n 2 "docker exec indextts_service nvidia-smi"

# 2. 检查系统资源
docker stats indextts_service

# 3. 查看详细日志
docker-compose logs indextts_service | grep -E "(处理时间|GPU|memory)"
```

**优化建议**:
```yaml
indextts_service:
  use_fp16: true                    # 启用FP16
  max_text_tokens_per_segment: 80  # 减少分段长度
  enable_monitoring: true            # 启用监控
```

### 内存使用过高

**症状**: 内存占用持续增长

**诊断步骤**:
```bash
# 检查内存使用
docker stats indextts_service --no-stream

# 检查Python进程内存
docker exec indextts_service python3 -c "
import psutil
p = psutil.Process()
print(f'内存使用: {p.memory_info().rss / 1024 / 1024:.2f} MB')
"

# 检查GPU内存
docker exec indextts_service nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

**解决方案**:
```python
# 在任务完成后强制清理GPU内存
import torch
if torch.cuda.is_available():
    torch.cuda.empty_cache()
```

## 配置问题

### 配置文件不生效

**症状**: 修改配置后没有生效

**诊断步骤**:
```bash
# 1. 验证配置文件语法
python3 -c "
import yaml
with open('/app/config.yml', 'r') as f:
    config = yaml.safe_load(f)
    print('indextts_service配置:', config.get('indextts_service', 'NOT_FOUND'))
"

# 2. 检查服务是否加载了新配置
docker-compose logs indextts_service | grep -E "(配置|config|Configuration)"

# 3. 重启服务
docker-compose restart indextts_service
```

### 环境变量冲突

**症状**: 环境变量设置不正确

**诊断步骤**:
```bash
# 检查环境变量
docker exec indextts_service env | grep INDEX_TTS

# 检查配置优先级
docker exec indextts_service python3 -c "
from services.common.config_loader import get_config
config = get_config()
print('use_fp16:', config.get('indextts_service', {}).get('use_fp16'))
print('环境变量use_fp16:', config.get('use_fp16', 'NOT_SET'))
"
```

## 日志分析

### 常用日志命令

```bash
# 查看最近的错误
docker-compose logs --tail=50 indextts_service | grep -i error

# 查看GPU相关日志
docker-compose logs indextts_service | grep -i gpu

# 查看任务执行日志
docker-compose logs indextts_service | grep "开始执行\|完成\|失败"

# 查看性能相关日志
docker-compose logs indextts_service | grep -E "(时间|秒|分钟|性能)"
```

### 日志分析技巧

1. **时间戳匹配**: 找到特定任务的时间戳
2. **错误模式**: 识别重复出现的错误模式
3. **性能指标**: 提取处理时间、内存使用等指标

## 恢复操作

### 服务重启

```bash
# 软重启
docker-compose restart indextts_service

# 强制重启
docker-compose stop indextts_service
docker-compose start indextts_service

# 重建容器
docker-compose up -d --force-recreate indextts_service
```

### 数据恢复

```bash
# 备份重要数据
docker exec indextts_service tar -czf /share/backup/indextts_backup_$(date +%Y%m%d).tar.gz /share/workflows/ /share/reference/

# 清理临时文件
docker exec indextts_service find /tmp -name "*.tmp" -delete
docker exec indextts_service find /share/tmp -name "*.wav" -delete
```

### 重置配置

```bash
# 恢复默认配置
docker exec indextts_service cp /app/config.yml.backup /app/config.yml

# 重新加载配置
docker-compose restart indextts_service
```

## 监控和预防

### 定期检查脚本

```bash
#!/bin/bash
# health_check.sh

echo "=== IndexTTS2 健康检查 ==="

# 检查服务状态
if docker-compose ps | grep indextts_service | grep -q "Up"; then
    echo "✅ IndexTTS2 服务运行正常"
else
    echo "❌ IndexTTS2 服务未运行"
    exit 1
fi

# 检查GPU状态
if docker exec indextts_service nvidia-smi &>/dev/null; then
    echo "✅ GPU 可用"
else
    echo "❌ GPU 不可用"
    exit 1
fi

# 检查Redis连接
if docker exec indextts_service python3 -c "import redis; r=redis.Redis(host='redis', port=6379, db=2); r.ping()" &>/dev/null; then
    echo "✅ Redis 连接正常"
else
    echo "❌ Redis 连接失败"
    exit 1
fi

# 检查磁盘空间
disk_usage=$(docker exec indextts_service df /share | awk 'NR==2 {print $5}')
if [[ ${disk_usage%?} -lt 90 ]]; then
    echo "✅ 磁盘空间充足 (${disk_usage})"
else
    echo "⚠️ 磁盘空间不足 (${disk_usage})"
fi

echo "=== 健康检查完成 ==="
```

### 性能监控脚本

```bash
#!/bin/bash
# performance_monitor.sh

echo "=== IndexTTS2 性能监控 ==="

# GPU使用率
echo "GPU使用率:"
docker exec indextts_service nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits

# 内存使用
echo "内存使用:"
docker stats indextts_service --no-stream | awk 'NR==2 {print $4}'} | sed 's/MiB/MB/'

# 活跃任务数
echo "活跃任务数:"
docker exec indextts_service python3 -c "
from services.common.locks import SmartGpuLockManager
try:
    manager = SmartGpuLockManager()
    status = manager.get_lock_info()
    if status:
        print('GPU被占用')
    else:
        print('GPU空闲')
except:
    print('无法获取GPU状态')
"

echo "=== 性能监控完成 ==="
```

## 联系支持

如果以上解决方案都无法解决您的问题，请：

1. **收集日志**:
   ```bash
   docker-compose logs indextts_service > indextts_debug.log 2>&1
   ```

2. **收集系统信息**:
   ```bash
   docker exec indextts_service python3 -c "
   import torch
   import sys
   print('Python版本:', sys.version)
   print('PyTorch版本:', torch.__version__)
   print('CUDA版本:', torch.version.cuda)
   print('GPU数量:', torch.cuda.device_count())
   if torch.cuda.is_available():
       print('GPU名称:', torch.cuda.get_device_name(0))
   "
   ```

3. **提供详细错误信息**:
   - 完整的错误堆栈
   - 重现步骤
   - 使用的配置和参数

将这些信息提交给技术支持团队以获得进一步的帮助。