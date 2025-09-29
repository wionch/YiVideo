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

**解决方案**:
```bash
# 检查详细日志
docker-compose logs --tail=100 api_gateway
docker-compose logs --tail=100 whisperx_service

# 检查数据库连接
docker-compose exec redis redis-cli ping

# 检查 GPU 状态
nvidia-smi
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

## 总结

本故障排除指南提供了 WhisperX 系统常见问题的诊断和解决方案。请按照本指南的步骤进行故障排除，如仍无法解决问题，请联系技术支持。

定期进行系统维护和性能监控，可以有效预防问题的发生。