# WhisperX 运维手册

**版本**: 2.0
**状态**: 精简版
**最后更新**: 2025-09-29

## 目录

1. [系统概述](#系统概述)
2. [日常运维](#日常运维)
3. [监控告警](#监控告警)
4. [性能维护](#性能维护)
5. [应急预案](#应急预案)
6. [维护计划](#维护计划)

---

## 系统概述

### 架构组件
- **API 网关** (`api_gateway`): 系统入口，基于 FastAPI
- **Faster Whisper 服务** (`faster_whisper_service`): 核心语音识别服务
- **Pyannote Audio 服务** (`pyannote_audio_service`): 说话人分离服务
- **Redis**: 消息队列和状态存储
- **监控系统**: 性能指标收集和告警
- **GPU 资源管理**: 智能锁和心跳机制

### 关键特性
- **Faster-Whisper 后端**: 4x 性能提升
- **GPU 锁管理**: 避免资源竞争
- **智能监控**: 全面的性能指标收集
- **自动告警**: 多级告警机制
- **配置驱动**: 灵活的参数调整

---

## 日常运维

### 1. 服务状态检查

```bash
# 检查所有服务状态
docker-compose ps

# 检查服务日志
docker-compose logs --tail=50 api_gateway
docker-compose logs --tail=50 faster_whisper_service
docker-compose logs --tail=50 pyannote_audio_service

# 检查系统健康状态
curl http://localhost:8788/health

# 检查 GPU 状态
nvidia-smi
```

### 2. 资源监控

```bash
# 检查内存使用
free -h

# 检查磁盘空间
df -h

# 检查 GPU 锁状态
curl http://localhost:8788/api/v1/monitoring/gpu-lock/health

# 检查 Redis 连接
curl http://localhost:6379/ping
```

### 3. 日志管理

```bash
# 查看错误日志
docker-compose logs faster_whisper_service | grep ERROR
docker-compose logs pyannote_audio_service | grep ERROR

# 日志轮转
logrotate -f /etc/logrotate.d/yivideo

# 清理旧日志
find logs/ -name "*.log" -mtime +30 -delete
```

### 4. 性能检查

```bash
# 检查服务响应时间
curl -w "Response time: %{time_total}s\n" http://localhost:8788/health

# 检查GPU使用情况
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv

# 检查系统资源使用
docker stats --no-stream
```

---

## 监控告警

### 1. 关键监控指标

#### 服务健康指标
- **API 响应时间**: < 1秒
- **成功率**: > 95%
- **GPU 使用率**: < 90%
- **内存使用率**: < 85%

#### 业务指标
- **音频处理速度**: < 2秒/分钟音频
- **批处理效率**: > 80%
- **错误率**: < 5%
- **重试率**: < 10%

### 2. 告警规则

#### 高优先级告警
- 服务完全不可用
- GPU 资源耗尽
- 数据存储空间不足
- 系统级错误

#### 中优先级告警
- API 响应时间超过阈值
- 成功率低于 90%
- GPU 使用率超过 80%
- 内存泄漏检测

#### 低优先级告警
- 性能下降趋势
- 配置变更提醒
- 维护提醒

### 3. 告警处理

```bash
# 查看当前告警
curl http://localhost:8788/api/v1/monitoring/alerts

# 查看告警历史
curl http://localhost:8788/api/v1/monitoring/alerts/history

# 手动处理告警
curl -X POST http://localhost:8788/api/v1/monitoring/alerts/acknowledge \
  -d '{"alert_id": "alert_123", "action": "acknowledge"}'
```

---

## 性能维护

### 1. 定期性能检查

```bash
# 运行性能基准测试 (示例)
# python scripts/performance_benchmark.py --service faster_whisper

# 检查模型性能
curl http://localhost:8788/api/v1/model/info

# 检查系统负载
top -p $(pgrep -f "faster_whisper")
```

### 2. 配置优化

根据硬件配置调整参数：

#### 高性能配置 (RTX 3060+)
```yaml
faster_whisper_service:
  batch_size: 8
  faster_whisper_threads: 8
  compute_type: "float16"
```

#### 内存受限配置
```yaml
faster_whisper_service:
  batch_size: 2
  compute_type: "int8"
  faster_whisper_threads: 4
```

#### CPU 配置
```yaml
faster_whisper_service:
  device: "cpu"
  batch_size: 1
  use_faster_whisper: false
```

### 3. 清理和维护

```bash
# 清理模型缓存
# 注意: 模型缓存路径已在 `config.yml` 中定义
# rm -rf /path/to/your/model/cache/*

# 清理日志文件
find logs/ -name "*.log" -size +100M -delete

# 重启服务释放内存
docker-compose restart faster_whisper_service pyannote_audio_service
```

---

## 应急预案

### 1. 服务故障

#### API 网关故障
```bash
# 检查服务状态
docker-compose ps api_gateway

# 重启服务
docker-compose restart api_gateway

# 检查配置
docker-compose config
```

#### WhisperX 服务故障
```bash
# 检查 GPU 状态
nvidia-smi

# 检查模型状态
curl http://localhost:8788/api/v1/model/info

# 重启服务
docker-compose restart faster_whisper_service pyannote_audio_service

# 检查日志
docker-compose logs --tail=100 faster_whisper_service
```

### 2. 资源问题

#### GPU 资源耗尽
```bash
# 检查 GPU 使用情况
nvidia-smi

# 释放 GPU 锁
curl -X POST http://localhost:8788/api/v1/monitoring/release-lock \
  -d '{"lock_key": "gpu_lock:0"}'

# 重启相关服务
docker-compose restart faster_whisper_service pyannote_audio_service
```

#### 内存不足
```bash
# 检查内存使用
free -h

# 清理缓存
sync; echo 1 > /proc/sys/vm/drop_caches

# 重启服务
docker-compose restart
```

### 3. 数据问题

#### Redis 数据丢失
```bash
# 检查 Redis 状态
docker-compose ps redis

# 重启 Redis
docker-compose restart redis

# 检查数据持久化
ls -la /data/redis/
```

#### 文件系统问题
```bash
# 检查磁盘空间
df -h

# 清理临时文件
find /tmp -type f -mtime +7 -delete

# 检查文件系统
fsck /dev/sdX
```

---

## 维护计划

### 1. 日常维护 (每日)

- [ ] 检查服务状态
- [ ] 检查系统资源使用
- [ ] 查看错误日志
- [ ] 检查告警状态
- [ ] 验证备份状态

### 2. 周期维护 (每周)

- [ ] 性能基准测试
- [ ] 清理日志文件
- [ ] 检查安全更新
- [ ] 验证数据完整性
- [ ] 检查配置优化

### 3. 月度维护 (每月)

- [ ] 系统更新和补丁
- [ ] 容量规划评估
- [ ] 灾难恢复演练
- [ ] 性能调优
- [ ] 文档更新

### 4. 季度维护 (每季度)

- [ ] 架构评估
- [ ] 安全审计
- [ ] 容量规划
- [ ] 技术债务清理

---

## 相关文档

- **部署指南**: `../deployment/DEPLOYMENT_GUIDE.md`
- **故障排除**: `./TROUBLESHOOTING_GUIDE.md`

---

*文档版本: 2.0 | 最后更新: 2025-09-29 | 状态: 精简版*