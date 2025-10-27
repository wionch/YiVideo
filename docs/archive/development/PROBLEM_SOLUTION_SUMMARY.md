# IndexTTS 模型加载卡死问题 - 解决方案总结

## 问题现象

### 症状描述
- **成功案例**: `webui.py --model_dir /models/indextts/checkpoints` 正常运行
- **失败案例**: `test_basic_tts.py` 卡在下载 `semantic_codec/model.safetensors` (177MB)

### 错误日志
```
semantic_codec/model.safetensors:   0%|                    | 0.00/177M [00:00<?, ?B/s]
```

## 根本原因分析

### 1. HuggingFace 缓存损坏

**发现过程**：
```bash
# 符号链接存在
/app/.cache/huggingface/hub/models--amphion--MaskGCT/.../semantic_codec/model.safetensors
  -> ../../../blobs/ec947271175d8cad75ec37e83aa487e27c97a0f72a303393772da5ffa84bddf2

# 但实际的 blob 文件不存在！
/app/.cache/huggingface/hub/blobs/ec947271... ❌ 文件缺失
```

**HuggingFace 缓存机制**：
- 实际文件存储在 `blobs/` 目录（内容寻址存储）
- `models--xxx/snapshots/` 中的文件是符号链接
- 符号链接断裂时，`hf_hub_download` 会尝试重新下载

### 2. 网络连接问题

当检测到缓存不完整时：
- `hf_hub_download` 尝试从 HuggingFace Hub 下载
- 如果网络不稳定或无法访问，下载会卡住
- 表现为进度条长时间停在 0%

### 3. 代码层面固有问题

**问题代码** (`indextts/infer_v2.py` 约第80-82行)：
```python
semantic_codec = build_semantic_codec(self.cfg.semantic_codec)
semantic_code_ckpt = hf_hub_download("amphion/MaskGCT", filename="semantic_codec/model.safetensors")
safetensors.torch.load_model(semantic_codec, semantic_code_ckpt)
```

**关键问题**：
- ❌ 每次初始化都调用 `hf_hub_download`，即使在离线环境
- ❌ 没有优先使用本地模型的逻辑
- ❌ 缺少完全离线模式的支持

### 4. 为什么 webui.py 能正常工作？

**可能原因**：
1. 之前成功下载过完整的模型文件
2. 使用了不同的缓存路径（观察到下载到 `/app/index-tts/checkpoints/hf_cache/`）
3. 启动时网络条件较好

## 解决方案

### ✅ 方案1：清理损坏的缓存（立即生效）

```bash
# 进入容器
docker exec -it indextts_service bash

# 删除损坏的缓存
rm -rf /app/.cache/huggingface/hub/models--amphion--MaskGCT

# 重新运行脚本（会重新下载）
cd /app/index-tts
python test_basic_tts.py
```

**优点**：简单直接，一次性解决
**缺点**：需要网络访问，重新下载 177MB

### ✅ 方案2：使用修复版脚本（已验证）

创建修复版脚本 `/app/index-tts/test_basic_tts_fixed.py`：

```python
#!/usr/bin/env python3
import os
import sys

# 确保缓存目录存在
os.makedirs('/app/.cache/huggingface/hub/blobs', exist_ok=True)

# 导入 IndexTTS2
from indextts.infer_v2 import IndexTTS2

print('>>> 初始化 IndexTTS2...')
tts = IndexTTS2(
    cfg_path="/models/indextts/checkpoints/config.yaml",
    model_dir="/models/indextts/checkpoints",
    use_fp16=True,
    use_cuda_kernel=False,
    use_deepspeed=False
)

print('>>> 开始生成语音...')
text = "Translate for me, what is a surprise!"
tts.infer(
    spk_audio_prompt='/app/videos/223.wav',     # 使用绝对路径
    text=text,
    output_path="/app/index-tts/gen.wav",       # 使用绝对路径
    verbose=True
)

print('✓ 语音生成完成！')
```

**验证结果**：
```
✓ 语音生成完成！
>> wav file saved to: /app/index-tts/gen.wav
>> Total inference time: 24.24 seconds
>> Generated audio length: 6.33 seconds
```

### 🔧 方案3：源码级修复（推荐用于生产）

修改 `indextts/infer_v2.py`，优先使用本地模型：

```python
# 在 __init__ 方法中修改
# 修改前
semantic_code_ckpt = hf_hub_download("amphion/MaskGCT", filename="semantic_codec/model.safetensors")

# 修改后
local_semantic_path = os.path.join(self.model_dir, "semantic_codec/model.safetensors")
if os.path.exists(local_semantic_path):
    # 优先使用本地文件
    semantic_code_ckpt = local_semantic_path
    print(f">> Using local semantic_codec: {semantic_code_ckpt}")
else:
    # 本地文件不存在时才下载
    try:
        semantic_code_ckpt = hf_hub_download(
            "amphion/MaskGCT",
            filename="semantic_codec/model.safetensors",
            local_files_only=False
        )
        print(f">> Downloaded semantic_codec: {semantic_code_ckpt}")
    except Exception as e:
        raise RuntimeError(f"Failed to load semantic_codec: {e}")
```

**优点**：
- ✅ 优先使用本地模型，避免不必要的网络请求
- ✅ 兼容离线和在线环境
- ✅ 适用于生产环境部署

### ⚠️ 方案4：离线模式（需要完整缓存）

如果环境完全离线且模型已存在：

```python
import os

# 设置完全离线模式
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

# 然后初始化 IndexTTS2
from indextts.infer_v2 import IndexTTS2
tts = IndexTTS2(...)
```

**注意**：此方案要求缓存完整，不适用于缓存已损坏的情况。

## 调试工具

### 缓存路径检查脚本

已创建 `/app/index-tts/debug_cache_paths.py`：

```bash
# 在容器内运行
cd /app/index-tts
python debug_cache_paths.py
```

**输出内容**：
- 环境变量状态
- HuggingFace/Transformers/Torch 缓存路径
- 缓存目录权限信息
- semantic_codec 模型文件位置

### 快速诊断命令

```bash
# 检查缓存完整性
find /app/.cache/huggingface/hub -name '*semantic*' -o -name '*codec*'

# 检查符号链接是否有效
find /app/.cache/huggingface/hub -type l -xtype l  # 找出断裂的链接

# 检查环境变量
docker exec indextts_service env | grep -E "HF_|TRANSFORMERS_|TORCH_"

# 检查缓存目录权限
docker exec indextts_service ls -lah /app/.cache/huggingface/
```

## 最佳实践建议

### 生产环境部署

1. **预先下载模型**
   ```dockerfile
   # 在 Dockerfile 中
   RUN python -c "from huggingface_hub import hf_hub_download; \
       hf_hub_download('amphion/MaskGCT', 'semantic_codec/model.safetensors')"
   ```

2. **本地化模型文件**
   - 将模型文件直接放入 `/models/indextts/checkpoints/semantic_codec/`
   - 修改代码优先使用本地路径

3. **使用镜像站点**
   ```bash
   # 使用清华镜像
   export HF_ENDPOINT=https://hf-mirror.com
   ```

### 开发环境

1. **定期检查缓存健康**
   ```bash
   # 删除损坏的缓存
   find /app/.cache/huggingface/hub -type l -xtype l -delete
   ```

2. **统一缓存管理**
   - 使用 `HF_HOME` 环境变量
   - 确保目录权限正确（避免 root/非root 混用）

3. **网络配置**
   - 确保可以访问 HuggingFace Hub
   - 配置代理（如需要）

### 容器化最佳实践

```yaml
# docker-compose.yml
services:
  indextts_service:
    environment:
      - HF_HOME=/app/.cache/huggingface
      - HF_HUB_ENABLE_HF_TRANSFER=0
    volumes:
      - huggingface_cache_volume:/app/.cache/huggingface

volumes:
  huggingface_cache_volume:
```

## 问题总结

| 方面 | 问题 | 解决方案 |
|------|------|---------|
| **缓存机制** | 符号链接断裂 | 清理缓存并重新下载 |
| **网络访问** | 无法连接 HuggingFace Hub | 预先下载或使用镜像 |
| **代码逻辑** | 固定使用 `hf_hub_download` | 修改源码，本地优先 |
| **路径问题** | 相对路径不正确 | 使用绝对路径 |
| **权限问题** | root/appuser 混用 | 统一使用 root 或配置权限 |

## 验证清单

- ✅ 环境变量配置正确
- ✅ 缓存目录存在且权限正确
- ✅ 模型文件完整（blob 文件存在）
- ✅ 网络可访问 HuggingFace Hub（或使用离线模式）
- ✅ 参考音频文件存在且路径正确
- ✅ 输出目录有写权限

## 相关文件

生成的文件：
- `/app/index-tts/test_basic_tts_fixed.py` - 修复版测试脚本 ✅
- `/app/index-tts/debug_cache_paths.py` - 缓存诊断工具 ✅
- `/app/index-tts/gen.wav` - 生成的测试音频 ✅

---

**生成时间**: 2025-10-26
**问题状态**: ✅ 已解决
**验证结果**: 修复版脚本运行成功，音频生成正常
