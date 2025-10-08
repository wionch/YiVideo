# WhisperX显存释放问题修复报告

## 问题描述

WhisperX服务在执行任务后出现显存无法完全释放的问题：
- **任务执行前**: 1GB/12GB
- **任务执行中**: 4-5GB/12GB（正常）
- **任务结束后**: 2.4GB/12GB（**异常**，应该降至~1GB）

## 根本原因分析

### 1. faster-whisper模型未正确释放
```python
# 原有代码存在的问题
model = WhisperModel(...)  # 创建模型，占用1-2GB显存
# ... 使用模型 ...
_cleanup_gpu_memory(stage_name, locals_to_delete=['model'])  # ❌ 参数无效
return result  # model对象仍在作用域内
```

**问题**：
- `_cleanup_gpu_memory()` 的 `locals_to_delete` 参数由于Python作用域限制**无法工作**
- 模型对象在函数返回前未被删除，持续占用GPU显存
- 缺少显式的 `.cpu()` 和 `del` 操作

### 2. GPU清理函数效率不足
- 垃圾回收轮数不够
- CUDA缓存清理不够激进
- 缺少多设备支持

## 修复方案

### 修改1: 显式释放faster-whisper模型

**文件**: `services/workers/whisperx_service/app/tasks.py`

**修改位置**: `_execute_transcription()` 函数 (第229-256行)

```python
# 显式释放faster-whisper模型
logger.info(f"[{stage_name}] 开始释放faster-whisper模型...")
try:
    # 如果是CUDA模式，将模型移至CPU
    if device == 'cuda':
        import torch
        if hasattr(model, 'model'):
            # faster-whisper内部模型对象
            if hasattr(model.model, 'cpu'):
                model.model.cpu()
        # 尝试移动整个模型对象
        if hasattr(model, 'cpu'):
            model.cpu()

    # 删除模型引用
    del model
    logger.info(f"[{stage_name}] faster-whisper模型已删除")

    # 强制垃圾回收
    import gc
    collected = gc.collect()
    logger.info(f"[{stage_name}] 垃圾回收: 清理了 {collected} 个对象")

except Exception as e:
    logger.warning(f"[{stage_name}] 释放模型时出错: {e}")

# 执行GPU显存清理（不再需要无效的locals_to_delete参数）
_cleanup_gpu_memory(stage_name)
```

### 修改2: 优化GPU清理函数

**文件**: `services/workers/whisperx_service/app/tasks.py`

**修改位置**: `_cleanup_gpu_memory()` 函数 (第450-526行)

**主要改进**:
1. **移除无效参数**: 删除 `locals_to_delete` 参数
2. **增强CUDA清理**: 多设备多轮清理
   ```python
   # 激进的CUDA缓存清理 - 增强版
   for device_id in range(torch.cuda.device_count()):
       try:
           with torch.cuda.device(device_id):
               # 多轮清理以确保彻底释放
               for _ in range(3):
                   torch.cuda.empty_cache()
                   torch.cuda.ipc_collect()
                   gc.collect()
       except:
           pass
   ```
3. **增加垃圾回收轮数**: 从3轮增加到5轮
4. **优化日志输出**: 更详细的显存状态记录

### 修改3: 修正说话人分离清理调用

**文件**: `services/workers/whisperx_service/app/tasks.py`

**修改位置**: `_execute_speaker_diarization()` 函数 (第444-445行)

```python
# 执行统一的GPU显存清理
_cleanup_gpu_memory(stage_name)  # 移除无效的locals_to_delete参数
```

## 验证方法

### 方法1: 使用Python测试脚本（推荐）

```bash
# 在whisperx_service目录下
python test_gpu_memory_release.py
```

### 方法2: 使用Shell测试脚本

```bash
# 添加执行权限
chmod +x test_gpu_memory_release.sh

# 运行测试
./test_gpu_memory_release.sh
```

### 方法3: 手动验证

```bash
# 1. 查看初始显存
nvidia-smi

# 2. 发送测试请求
curl --request POST \
  --url http://localhost:8788/v1/workflows \
  --header 'content-type: application/json' \
  --data '{
  "video_path": "/app/videos/223.mp4",
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_audio",
      "whisperx.generate_subtitles"
    ]
  }
}'

# 3. 等待任务完成（约30-60秒）
# 4. 再次查看显存，应该接近初始值（±500MB以内）
nvidia-smi
```

## 预期效果

修复后的显存占用情况：
- **任务执行前**: ~1GB/12GB
- **任务执行中**: 4-5GB/12GB（峰值）
- **任务结束后**: ~1-1.5GB/12GB（**正常**，显存增长<500MB）

## 技术要点

1. **Python垃圾回收机制**
   - 局部变量在函数返回前不会被回收
   - 需要显式 `del` 删除大对象引用
   - 强制 `gc.collect()` 触发垃圾回收

2. **PyTorch CUDA内存管理**
   - `.cpu()` 将模型移至CPU内存
   - `torch.cuda.empty_cache()` 清理未使用的缓存
   - `torch.cuda.ipc_collect()` 清理进程间共享内存

3. **faster-whisper特殊处理**
   - 模型内部有嵌套的 `model.model` 对象
   - 需要递归清理内部模型引用

## 后续建议

1. **监控显存使用**: 在生产环境中定期检查显存释放情况
2. **优化模型加载**: 考虑模型复用，避免频繁加载/卸载
3. **容器资源限制**: 通过Docker设置合理的GPU显存限制

## 相关文件

- **修改文件**:
  - `services/workers/whisperx_service/app/tasks.py`

- **测试脚本**:
  - `services/workers/whisperx_service/test_gpu_memory_release.py`
  - `services/workers/whisperx_service/test_gpu_memory_release.sh`

- **相关文档**:
  - `docs/whisperx/WHISPERX_COMPLETE_GUIDE.md`
  - `docs/reference/GPU_LOCK_COMPLETE_GUIDE.md`
