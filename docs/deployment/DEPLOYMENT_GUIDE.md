# WhisperX 生产环境部署指南

## 目录

1. [部署前准备](#部署前准备)
2. [环境要求](#环境要求)
3. [部署步骤](#部署步骤)
4. [配置优化](#配置优化)
5. [监控配置](#监控配置)
6. [安全配置](#安全配置)
7. [性能调优](#性能调优)
8. [维护操作](#维护操作)
9. [故障恢复](#故障恢复)

---

## 部署前准备

### 1. 系统要求检查

在部署之前，请确保系统满足以下要求：

- **操作系统**: Ubuntu 20.04/22.04 LTS 或 CentOS 7/8
- **CPU**: 最少 8 核，推荐 16 核
- **内存**: 最少 32GB，推荐 64GB
- **存储**: 最少 500GB SSD，推荐 1TB
- **GPU**: NVIDIA RTX 3060 或更高，至少 12GB 显存
- **网络**: 稳定的互联网连接，带宽至少 100Mbps

### 2. 软件依赖

```bash
# 基础软件
sudo apt update
sudo apt install -y \
    curl \
    wget \
    git \
    python3 \
    python3-pip \
    docker.io \
    docker-compose \
    nginx \
    certbot \
    python3-certbot-nginx

# 验证安装
docker --version
docker-compose --version
python3 --version
```

### 3. 用户和权限

```bash
# 创建专用用户
sudo useradd -m -s /bin/bash whisperx
sudo usermod -aG docker whisperx
sudo usermod -aG sudo whisperx

# 切换到专用用户
sudo su - whisperx
```

---

## 环境要求

### 系统配置

```bash
# 内核参数优化
sudo tee -a /etc/sysctl.conf << EOF
# 网络优化
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 65536 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
net.core.netdev_max_backlog = 5000
net.ipv4.tcp_congestion_control = bbr

# 文件系统优化
vm.swappiness = 10
vm.dirty_ratio = 60
vm.dirty_background_ratio = 2
fs.file-max = 1000000

# GPU 优化
vm.nr_hugepages = 1024
EOF

# 应用内核参数
sudo sysctl -p
```

### Docker 配置

```bash
# 创建 Docker 配置目录
sudo mkdir -p /etc/docker

# 配置 Docker 守护进程
sudo tee /etc/docker/daemon.json << EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "3"
  },
  "storage-driver": "overlay2",
  "storage-opts": [
    "overlay2.override_kernel_check=true"
  ],
  "default-runtime": "runc",
  "runtimes": {
    "nvidia": {
      "path": "/usr/bin/nvidia-container-runtime",
      "runtimeArgs": []
    }
  },
  "default-runtime": "nvidia"
}
EOF

# 重启 Docker 服务
sudo systemctl restart docker
sudo systemctl enable docker
```

### NVIDIA 驱动安装

```bash
# 安装 NVIDIA 驱动
sudo apt install -y nvidia-driver-470 nvidia-cuda-toolkit

# 验证驱动安装
nvidia-smi

# 安装 NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update
sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker
```

---

## 部署步骤

### 1. 代码准备

```bash
# 克隆代码仓库
git clone https://github.com/your-org/YiVideo.git
cd YiVideo

# 创建必要目录
mkdir -p /opt/yivideo/{logs,data,backup,config}
mkdir -p /opt/yivideo/videos/{input,output,temp}

# 设置权限
sudo chown -R whisperx:whisperx /opt/yivideo
chmod -R 755 /opt/yivideo
```

### 2. 配置文件准备

```bash
# 复制配置文件
cp config.yml /opt/yivideo/config/
cp docker-compose.yml /opt/yivideo/config/

# 创建环境配置文件
cat > /opt/yivideo/config/.env << EOF
# 基础配置
ENVIRONMENT=production
VERSION=1.0.0
DEBUG=false

# 网络配置
API_HOST=0.0.0.0
API_PORT=8788
REDIS_HOST=redis
REDIS_PORT=6379

# GPU 配置
CUDA_VISIBLE_DEVICES=0
NVIDIA_VISIBLE_DEVICES=0

# WhisperX 配置 (新增)
HF_TOKEN=hf_your_huggingface_token_here
WHISPERX_MODEL_CACHE_DIR=/app/.cache/whisperx
HF_HOME=/app/.cache/huggingface
TRANSFORMERS_CACHE=/app/.cache/transformers

# 监控配置
PROMETHEUS_HOST=prometheus
PROMETHEUS_PORT=9090
GRAFANA_HOST=grafana
GRAFANA_PORT=3000
EOF
```

### 3. SSL 证书配置

```bash
# 申请 SSL 证书
sudo certbot --nginx -d your-domain.com

# 创建证书目录
sudo mkdir -p /etc/ssl/yivideo
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem /etc/ssl/yivideo/
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem /etc/ssl/yivideo/

# 设置权限
sudo chown -R whisperx:whisperx /etc/ssl/yivideo
sudo chmod 600 /etc/ssl/yivideo/*
```

### 4. 服务部署

```bash
# 构建镜像
cd /opt/yivideo
docker-compose build --no-cache

# 启动服务
docker-compose up -d

# 验证服务状态
docker-compose ps
```

### 5. 监控系统部署

```bash
# 部署监控系统
docker-compose -f docker-compose.monitoring.yml up -d

# 验证监控服务
curl http://localhost:9090/targets
curl http://localhost:3000/api/health
```

---

## 配置优化

### 1. WhisperX 配置优化

```yaml
# config.yml
whisperx_service:
  # 性能优化
  model_name: "large-v2"
  compute_type: "float16"
  batch_size: 8
  use_faster_whisper: true
  faster_whisper_threads: 8

  # 资源管理
  device: "cuda"
  language: "zh"
  enable_word_timestamps: true
  enable_diarization: false

  # 内存优化
  audio_sample_rate: 16000
  audio_channels: 1

# GPU 锁优化
gpu_lock:
  poll_interval: 0.5
  max_wait_time: 300
  lock_timeout: 600
  exponential_backoff: true

# 系统优化
core:
  workflow_ttl_days: 7
  cleanup_temp_files: true

pipeline:
  detect_keyframes: true
  use_image_concat: true
  concat_batch_size: 10
  frame_cache_strategy: "memory"
```

### 2. 数据库优化

```yaml
# Redis 配置
redis:
  maxmemory: 4gb
  maxmemory-policy: allkeys-lru
  save: "900 1 300 10 60 10000"
  tcp-keepalive: 300
  timeout: 0
```

### 3. 网络优化

```yaml
# 网络配置
networks:
  default:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16

services:
  api_gateway:
    networks:
      - default
    deploy:
      resources:
        limits:
          cpus: '4.0'
          memory: 8G
        reservations:
          cpus: '2.0'
          memory: 4G
```

---

## 监控配置

### 1. Prometheus 配置

```yaml
# monitoring/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "rules/*.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'whisperx'
    static_configs:
      - targets: ['whisperx_service:8080']
    scrape_interval: 30s
    metrics_path: '/metrics'

  - job_name: 'api_gateway'
    static_configs:
      - targets: ['api_gateway:8788']
    scrape_interval: 15s
    metrics_path: '/metrics'

  - job_name: 'redis'
    static_configs:
      - targets: ['redis:6379']
```

### 2. Grafana 配置

```yaml
# monitoring/grafana/provisioning/datasources/datasources.yml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true

  - name: Redis
    type: redis-datasource
    access: proxy
    url: redis:6379
    database: 0
```

### 3. 告警规则

```yaml
# monitoring/rules/alerts.yml
groups:
  - name: whisperx.alerts
    rules:
      - alert: WhisperxExecutionTimeHigh
        expr: whisperx_execution_time_seconds > 300
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "WhisperX 执行时间过长"
          description: "执行时间超过 5 分钟: {{ $value }}s"

      - alert: WhisperxGpuMemoryHigh
        expr: gpu_memory_used_gb > 8
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "GPU 显存使用过高"
          description: "GPU 显存使用超过 8GB: {{ $value }}GB"
```

---

## 安全配置

### 1. 网络安全

```bash
# 配置防火墙
sudo ufw enable
sudo ufw default deny incoming
sudo ufw default allow outgoing

# 允许必要端口
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 8788/tcp

# 限制 Docker 端口访问
sudo ufw deny 2375/tcp
sudo ufw deny 2376/tcp
```

### 2. 认证配置

```yaml
# API 认证配置
api_gateway:
  auth:
    enabled: true
    jwt_secret: "your-jwt-secret-key"
    token_expire_hours: 24

  rate_limit:
    enabled: true
    requests_per_minute: 100
    burst_size: 10
```

### 3. 数据加密

```bash
# 加密敏感配置
sudo apt install -y ansible-vault

# 创建加密配置文件
ansible-vault encrypt /opt/yivideo/config/secrets.yml
```

---

## 性能调优

### 1. GPU 性能优化

```bash
# 设置 GPU 性能模式
sudo nvidia-smi -i 0 -pm 1  # 持久模式
sudo nvidia-smi -i 0 -lgc 0,0  # 最高性能

# 监控 GPU 性能
watch -n 1 nvidia-smi
```

### 2. 内存优化

```bash
# 配置大页内存
echo 1024 | sudo tee /proc/sys/vm/nr_hugepages
sudo mkdir -p /dev/hugepages
sudo mount -t hugetlbfs nodev /dev/hugepages

# 优化内存分配
echo 'vm.nr_hugepages = 1024' | sudo tee -a /etc/sysctl.conf
```

### 3. 文件系统优化

```bash
# 使用 tmpfs 挂载临时目录
sudo mount -t tmpfs -o size=10g tmpfs /opt/yivideo/videos/temp

# 优化文件系统参数
sudo tune2fs -o journal_data_writeback /dev/sda1
```

---

## 维护操作

### 1. 日常维护

```bash
# 日志轮转
sudo tee /etc/logrotate.d/yivideo << EOF
/opt/yivideo/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 whisperx whisperx
    postrotate
        docker-compose exec api_gateway python -c "import logging; logging.getLogger().handlers[0].doRollover()"
    endscript
}
EOF

# 备份脚本
cat > /opt/yivideo/scripts/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/yivideo/backup"
DATE=$(date +%Y%m%d_%H%M%S)

# 创建备份
docker-compose exec redis redis-cli --rdb $BACKUP_DIR/redis_$DATE.rdb
tar -czf $BACKUP_DIR/config_$DATE.tar.gz /opt/yivideo/config/

# 清理旧备份
find $BACKUP_DIR -name "*.rdb" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete
EOF

chmod +x /opt/yivideo/scripts/backup.sh
```

### 2. 定期维护

```bash
# 添加到 crontab
sudo crontab -e

# 每日凌晨 2 点执行备份
0 2 * * * /opt/yivideo/scripts/backup.sh

# 每小时检查服务状态
0 * * * * /opt/yivideo/scripts/health_check.sh

# 每周日凌晨 3 点清理日志
0 3 * * 0 /opt/yivideo/scripts/cleanup_logs.sh
```

---

## 故障恢复

### 1. 服务故障恢复

```bash
# 服务重启脚本
cat > /opt/yivideo/scripts/restart_services.sh << 'EOF'
#!/bin/bash

echo "重启 WhisperX 服务..."

# 停止服务
docker-compose down

# 清理资源
docker system prune -f

# 重启服务
docker-compose up -d

# 等待服务启动
sleep 30

# 健康检查
curl -f http://localhost:8788/health || echo "健康检查失败"
EOF

chmod +x /opt/yivideo/scripts/restart_services.sh
```

### 2. 数据恢复

```bash
# 数据恢复脚本
cat > /opt/yivideo/scripts/restore_data.sh << 'EOF'
#!/bin/bash

BACKUP_FILE=$1
if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file>"
    exit 1
fi

echo "恢复数据从: $BACKUP_FILE"

# 停止服务
docker-compose down

# 恢复配置
tar -xzf $BACKUP_FILE -C /

# 重启服务
docker-compose up -d
EOF

chmod +x /opt/yivideo/scripts/restore_data.sh
```

### 3. 紧急恢复流程

```bash
# 紧急恢复脚本
cat > /opt/yivideo/scripts/emergency_recovery.sh << 'EOF'
#!/bin/bash

echo "=== 紧急恢复流程 ==="

# 1. 检查系统状态
echo "1. 检查系统状态..."
nvidia-smi
free -h
df -h

# 2. 重启服务
echo "2. 重启服务..."
docker-compose down
docker-compose up -d

# 3. 验证服务
echo "3. 验证服务..."
sleep 30
curl http://localhost:8788/health

# 4. 检查监控
echo "4. 检查监控..."
curl http://localhost:9090/targets
curl http://localhost:3000/api/health

echo "紧急恢复完成"
EOF

chmod +x /opt/yivideo/scripts/emergency_recovery.sh
```

---

## 部署验证

### 1. 部署后验证

```bash
# 运行部署验证
python scripts/production_deployment.py

# 检查服务状态
curl http://localhost:8788/health
curl http://localhost:9090/targets
curl http://localhost:3000/api/health

# 性能测试
python scripts/whisperx_performance_benchmark.py
```

### 2. 生产环境检查清单

- [ ] 所有服务正常运行
- [ ] SSL 证书有效
- [ ] 监控系统正常
- [ ] 告警系统正常
- [ ] 备份系统正常
- [ ] 性能指标正常
- [ ] 安全配置正确
- [ ] 日志系统正常

---

## 总结

本部署指南提供了 WhisperX 系统在生产环境中的完整部署方案。请严格按照本指南执行部署操作，并确保所有安全和性能要求都得到满足。

定期进行系统维护和监控，确保系统的稳定运行。如遇到问题，请参考故障恢复部分进行处理。