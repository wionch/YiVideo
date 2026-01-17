# S2ST (Speech-to-Speech Translation) 工作流设计文档

**文档版本**: 1.0
**创建日期**: 2026-01-16
**设计状态**: ✅ 已验证通过

---

## 目录

1. [架构概览](#1-架构概览)
2. [LLM 字幕优化节点](#2-llm-字幕优化节点)
3. [LLM 翻译装词节点](#3-llm-翻译装词节点)
4. [IndexTTS2 语音生成节点](#4-indextts2-语音生成节点)
5. [Edge-TTS 语音生成节点](#5-edge-tts-语音生成节点)
6. [视频音频字幕合并节点](#6-视频音频字幕合并节点)
7. [完整工作流编排示例](#7-完整工作流编排示例)
8. [技术风险与应对策略](#8-技术风险与应对策略)
9. [实施路线图与测试策略](#9-实施路线图与测试策略)

---

## 1. 架构概览

### 1.1 系统目标

实现端到端的语音到语音翻译(S2ST)工作流,支持视频配音场景。核心能力包括:

- **字幕优化**: 修正 ASR 转录的分段、错别字和语义错误
- **翻译装词**: 跨语言翻译时严格保持时长对齐(±10%)
- **语音生成**: 基于 IndexTTS2 和 Edge-TTS 的声音克隆与合成
- **视频合并**: 整合配音、背景音、字幕生成最终视频

### 1.2 架构原则

遵循 YiVideo 的"**配置而非编码**"理念,采用**细粒度独立节点**设计:

- 每个节点单一职责(SRP),可独立调用和测试
- 通过 `workflow_config` 动态编排任务链
- 统一使用 `task_id + task_name` 缓存机制避免重复计算
- 所有输出自动上传 MinIO 并生成 `*_minio_url`

### 1.3 新增节点列表

| 节点名称 | 服务位置 | 功能描述 |
|---------|---------|---------|
| `wservice.llm_optimize_subtitles` | wservice | LLM 字幕优化 |
| `wservice.llm_translate_subtitles` | wservice | LLM 翻译装词 |
| `wservice.edgetts_generate_batch_speech` | wservice | Edge-TTS 批量语音生成 |
| `indextts.generate_batch_speech` | indextts_service | IndexTTS2 批量语音生成 |
| `ffmpeg.merge_video_audio_subtitle` | ffmpeg_service | 视频音频字幕合并 |

---

## 2. LLM 字幕优化节点

### 2.1 节点定义

**节点名称**: `wservice.llm_optimize_subtitles`

**核心功能**: 修正 Faster-Whisper 转录输出的分段、错别字和语义错误,生成符合行业标准的字幕。

### 2.2 输入参数

```json
{
  "transcription_data": {...},  // Faster-Whisper 输出的完整转录数据
  "llm_provider": "deepseek",   // LLM 提供商: deepseek/gemini/claude
  "llm_model": "deepseek-chat", // 模型名称
  "batch_size": 50,             // 滑动窗口大小
  "overlap_size": 3             // 窗口重叠大小
}
```

### 2.3 极简指令集设计

LLM 输出使用单字符键避免 token 浪费,本地代码通过映射表重建完整数据:

**LLM 输出格式**:
```json
[
  {"t":"m","i":[1,2,3],"tx":"合并后的文本","p":15},
  {"t":"s","i":5,"splits":[{"tx":"前半句","p":8},{"tx":"后半句","p":7}]},
  {"t":"f","i":8,"tx":"修正后文本"},
  {"t":"v","f":10,"to":15,"p":12},
  {"t":"d","i":20}
]
```

**操作类型映射**:

| 简码 | 完整名称 | 描述 | 必需字段 |
|-----|---------|------|---------|
| `m` | merge | 合并多个字幕 | `i` (ID数组), `tx` (合并文本), `p` (新位置) |
| `s` | split | 分割字幕 | `i` (源ID), `splits` (分段数组) |
| `f` | fix | 修正文本内容 | `i` (ID), `tx` (修正文本) |
| `v` | move | 移动字幕位置 | `f` (源位置), `to` (目标位置), `p` (新位置) |
| `d` | delete | 删除字幕 | `i` (ID) |

### 2.4 并发处理策略

- **滑动窗口**: 50 条字幕为一个批次
- **重叠边界**: 3 条避免边界分段错误
- **去重原则**: 后批次优先(posterior priority)
- **并发执行**: 支持 LLM 并发调用,最终串行应用指令

### 2.5 输出结构

```json
{
  "optimized_subtitles": [
    {
      "id": 1,
      "start": 11.4,
      "end": 19.56,
      "text": "Well, little kitty, if you really want to learn how to catch flies, you've got to study.",
      "words": [...]
    }
  ],
  "operations_applied": 127,
  "instructions_log": [...]
}
```

---

## 3. LLM 翻译装词节点

### 3.1 节点定义

**节点名称**: `wservice.llm_translate_subtitles`

**核心功能**: 跨语言翻译字幕,同时严格保持时长对齐(±10% 容差),解决不同语言语速差异问题。

### 3.2 输入参数

```json
{
  "optimized_subtitles": [...],     // 优化后的字幕数据
  "target_language": "zh-CN",       // 目标语言
  "llm_provider": "deepseek",
  "llm_model": "deepseek-chat",
  "duration_tolerance": 0.1,        // 时长容差(默认±10%)
  "batch_size": 50,
  "overlap_size": 3
}
```

### 3.3 时长对齐算法 - 音节数估算法

**1. 音节数计算**:

```python
# 英语
import pyphen
dic = pyphen.Pyphen(lang='en')
syllables = dic.inserted(text).count('-') + 1

# 中文
syllables = len([c for c in text if is_chinese(c)])
```

**2. 时长验证公式**:

```python
estimated_duration = syllables × 0.25  # 4音节/秒的行业标准
allowed_range = target_duration × (1 ± duration_tolerance)

if estimated_duration not in allowed_range:
    # 要求 LLM 重新生成,调整译文长度
```

**3. LLM 输出格式**:

```json
[
  {"i":1,"tx":"翻译后的文本","syl":15,"dur":3.75},
  {"i":2,"tx":"另一句翻译","syl":12,"dur":3.0}
]
```

- `syl`: LLM 估算的音节数(用于本地验证)
- `dur`: 目标时长(从原字幕继承)

### 3.4 重试机制

- 时长不符合要求时,自动重试最多 **3 次**
- 每次重试在 prompt 中明确指出超时/过短的条目及偏差百分比
- 示例反馈:"ID 5 超时 15%, ID 8 过短 22%,请重新生成"

### 3.5 输出结构

```json
{
  "translated_subtitles": [
    {
      "id": 1,
      "start": 11.4,
      "end": 19.56,
      "text": "好吧,小猫咪,如果你真的想学会抓苍蝇,你必须刻苦学习。",
      "original_text": "Well, little kitty, if you really want to learn...",
      "syllables": 15,
      "duration": 8.16,
      "duration_valid": true
    }
  ],
  "retry_count": 0,
  "subtitle_file_path": "/app/tmp/task-xxx/subtitles.srt",
  "subtitle_file_minio_url": "http://minio:9000/yivideo/task-xxx/subtitles.srt"
}
```

---

## 4. IndexTTS2 语音生成节点

### 4.1 节点定义

**节点名称**: `indextts.generate_batch_speech`

**核心功能**: 基于 IndexTTS2 模型进行零样本声音克隆,批量生成配音音频,并通过 Rubberband 进行时长对齐。

### 4.2 输入参数

```json
{
  "translated_subtitles": [...],        // 翻译后的字幕数据
  "reference_mode": "single",           // 参考音频模式: single/dynamic
  "reference_audio_path": "minio://yivideo/ref.wav",  // 单参考模式:全局参考音频
  "reference_audio_map": {              // 动态模式:字幕ID到参考音频映射
    "1": "minio://yivideo/ref_seg1.wav",
    "2": "minio://yivideo/ref_seg2.wav"
  },
  "min_reference_duration": 6.0,        // 最小参考音频时长(秒)
  "duration_tolerance": 0.1,            // 时长容差±10%
  "gpu_device": 0                       // GPU 设备ID
}
```

### 4.3 处理流程

**1. 参考音频预处理**:

```bash
# 检查参考音频时长,如果 < 6 秒,循环拼接至 6 秒
ffmpeg -stream_loop N -i input.wav -t 6 output.wav
```

**2. 批量 TTS 生成**:

- 遍历字幕,调用 IndexTTS2 API 生成音频
- 记录生成音频的实际时长

**3. Rubberband 时长对齐**:

```python
actual_duration = get_audio_duration(generated_audio)
target_duration = subtitle["end"] - subtitle["start"]

if abs(actual_duration - target_duration) / target_duration > duration_tolerance:
    stretch_ratio = target_duration / actual_duration
    rubberband_stretch(generated_audio, stretch_ratio)
```

**4. 音频拼接**:

```bash
# 将所有分段音频按时间轴拼接成完整配音
ffmpeg -f concat -safe 0 -i filelist.txt -c copy merged_audio.mp3
```

### 4.4 输出结构

```json
{
  "audio_segments": [
    {
      "subtitle_id": 1,
      "audio_path": "/app/tmp/task-xxx/seg_001.wav",
      "audio_minio_url": "http://minio:9000/yivideo/task-xxx/seg_001.wav",
      "duration": 3.75,
      "stretch_applied": true,
      "stretch_ratio": 0.95
    }
  ],
  "merged_audio_path": "/app/tmp/task-xxx/merged_audio.mp3",
  "merged_audio_minio_url": "http://minio:9000/yivideo/task-xxx/merged_audio.mp3",
  "total_duration": 341.79
}
```

---

## 5. Edge-TTS 语音生成节点

### 5.1 节点定义

**节点名称**: `wservice.edgetts_generate_batch_speech`

**核心功能**: 基于 Microsoft Edge-TTS API 批量生成语音,通过 Rate 参数预估 + Rubberband 后处理实现精确时长对齐。

### 5.2 输入参数

```json
{
  "translated_subtitles": [...],        // 翻译后的字幕数据
  "voice_name": "zh-CN-XiaoxiaoNeural", // Edge-TTS 声音名称
  "duration_tolerance": 0.1,            // 时长容差±10%
  "pitch": "+0Hz",                      // 音高调整(可选)
  "volume": "+0%"                       // 音量调整(可选)
}
```

### 5.3 时长对齐策略 - Rate 预估 + Rubberband

**1. 预估 Rate 参数**:

```python
estimated_duration = calculate_syllable_duration(text)  # 基于音节数
target_duration = subtitle["end"] - subtitle["start"]

rate_adjustment = (estimated_duration / target_duration - 1) × 100
rate_param = f"{rate_adjustment:+.0f}%"  # 如 "-15%" 或 "+20%"
```

**2. 调用 Edge-TTS API**:

```python
from edge_tts import Communicate

communicate = Communicate(text, voice_name, rate=rate_param)
await communicate.save(output_path)
```

**3. Rubberband 微调**:

```python
actual_duration = get_audio_duration(output_path)
if abs(actual_duration - target_duration) / target_duration > duration_tolerance:
    stretch_ratio = target_duration / actual_duration
    rubberband_stretch(output_path, stretch_ratio)
```

### 5.4 输出结构

```json
{
  "audio_segments": [
    {
      "subtitle_id": 1,
      "audio_path": "/app/tmp/task-xxx/seg_001.mp3",
      "audio_minio_url": "http://minio:9000/yivideo/task-xxx/seg_001.mp3",
      "duration": 3.75,
      "rate_used": "-15%",
      "rubberband_applied": true,
      "final_stretch_ratio": 1.02
    }
  ],
  "merged_audio_path": "/app/tmp/task-xxx/merged_audio.mp3",
  "merged_audio_minio_url": "http://minio:9000/yivideo/task-xxx/merged_audio.mp3"
}
```

### 5.5 优势

- **无需参考音频**: 适合快速原型和多角色场景
- **音质保护**: Rate 预估大幅减少 Rubberband 调整幅度
- **API 稳定**: Microsoft 官方支持,可用性高

---

## 6. 视频音频字幕合并节点

### 6.1 节点定义

**节点名称**: `ffmpeg.merge_video_audio_subtitle`

**核心功能**: 将静音视频、新配音、背景音、字幕整合为最终视频产物。

### 6.2 输入参数

```json
{
  "silent_video_path": "minio://yivideo/task-xxx/silent_video.mp4",
  "new_audio_path": "minio://yivideo/task-xxx/dubbed_audio.mp3",
  "background_audio_path": "minio://yivideo/task-xxx/bgm.mp3",  // 可选
  "subtitle_path": "minio://yivideo/task-xxx/subtitles.srt",    // 可选
  "output_format": "mp4",
  "background_volume": 0.3,  // 背景音量(0-1,默认0.2)
  "subtitle_style": {        // 可选
    "font_size": 24,
    "font_color": "white",
    "outline_color": "black",
    "position": "bottom"
  }
}
```

### 6.3 FFmpeg 处理流程

**1. 音频混合**(如果提供背景音):

```bash
ffmpeg -i new_audio.mp3 -i bgm.mp3 \
  -filter_complex "[1:a]volume=0.3[bg];[0:a][bg]amix=inputs=2:duration=first" \
  -y mixed_audio.mp3
```

**2. 视频音频合并**:

```bash
ffmpeg -i silent_video.mp4 -i mixed_audio.mp3 \
  -c:v copy -c:a aac -map 0:v:0 -map 1:a:0 \
  -y output_with_audio.mp4
```

**3. 烧录字幕**(如果提供):

```bash
ffmpeg -i output_with_audio.mp4 \
  -vf "subtitles=subtitles.srt:force_style='FontSize=24,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&'" \
  -c:a copy -y final_output.mp4
```

### 6.4 容错处理

- **背景音时长不足**: 自动循环 `-stream_loop -1`
- **背景音过长**: 截断至视频时长 `-t {video_duration}`
- **字幕编码问题**: 自动转换为 UTF-8

### 6.5 输出结构

```json
{
  "output_video_path": "/app/tmp/task-xxx/final_video.mp4",
  "output_video_minio_url": "http://minio:9000/yivideo/task-xxx/final_video.mp4",
  "duration": 341.79,
  "resolution": "1920x1080",
  "file_size_mb": 125.6,
  "audio_tracks": ["dubbed", "background"],
  "subtitle_burned": true
}
```

---

## 7. 完整工作流编排示例

### 7.1 典型 S2ST 工作流配置

**场景**: 将英文视频翻译为中文配音视频,使用 IndexTTS2 进行声音克隆。

```json
{
  "workflow_id": "s2st-demo-001",
  "task_chain": [
    {
      "task_name": "ffmpeg.extract_audio",
      "input_data": {
        "video_path": "minio://yivideo/demo.mp4"
      }
    },
    {
      "task_name": "faster_whisper.transcribe_audio",
      "input_data": {
        "audio_path": "${stages.ffmpeg.extract_audio.audio_path}",
        "language": "en",
        "word_timestamps": true
      }
    },
    {
      "task_name": "wservice.llm_optimize_subtitles",
      "input_data": {
        "transcription_data": "${stages.faster_whisper.transcribe_audio}",
        "llm_provider": "deepseek",
        "batch_size": 50
      }
    },
    {
      "task_name": "wservice.llm_translate_subtitles",
      "input_data": {
        "optimized_subtitles": "${stages.wservice.llm_optimize_subtitles.subtitles}",
        "target_language": "zh-CN",
        "duration_tolerance": 0.1
      }
    },
    {
      "task_name": "indextts.generate_batch_speech",
      "input_data": {
        "translated_subtitles": "${stages.wservice.llm_translate_subtitles.subtitles}",
        "reference_mode": "single",
        "reference_audio_path": "minio://yivideo/ref_voice.wav"
      }
    },
    {
      "task_name": "ffmpeg.merge_video_audio_subtitle",
      "input_data": {
        "silent_video_path": "${stages.ffmpeg.extract_audio.silent_video_path}",
        "new_audio_path": "${stages.indextts.generate_batch_speech.merged_audio_path}",
        "subtitle_path": "${stages.wservice.llm_translate_subtitles.subtitle_file_path}"
      }
    }
  ]
}
```

### 7.2 关键特性

- **动态引用**: 使用 `${stages.<task_name>.<field>}` 引用前序任务输出
- **独立可测**: 每个节点支持 `task_id` 缓存复用
- **失败重试**: 失败节点可单独重试,无需重跑整个流程
- **灵活组合**: 可自由替换 IndexTTS2 为 Edge-TTS

---

## 8. 技术风险与应对策略

### 8.1 主要技术风险

| 风险项 | 描述 | 应对策略 |
|-------|------|---------|
| **LLM Token 成本** | 大规模字幕优化/翻译可能产生高额 API 费用 | - 极简指令集减少输出 token 70%+ <br> - 批处理滑动窗口避免重复上下文 <br> - 优先使用 DeepSeek(成本仅为 GPT-4 的 1/10) <br> - 实现缓存机制,避免重复处理 |
| **时长对齐精度** | ±10% 容差在某些场景下仍可能不满足需求 | - 音节数估算 + Rubberband 双重保障 <br> - 对于关键片段,可手动调整参数 <br> - 记录 `stretch_ratio` 便于质量审查 |
| **IndexTTS2 克隆质量** | 参考音频质量差或时长不足导致克隆失败 | - 强制 6 秒最小时长要求(循环拼接) <br> - 动态参考模式支持逐句优化 <br> - 提供 Edge-TTS 作为快速备选方案 |
| **GPU 资源竞争** | IndexTTS2 任务可能占用 GPU 导致其他任务阻塞 | - 使用 `@gpu_lock()` 装饰器管理资源 <br> - 支持 CPU fallback(性能下降但保证可用) <br> - 批处理减少锁获取次数 |
| **并发去重冲突** | 滑动窗口重叠区域的指令可能相互覆盖 | - 严格后批次优先原则 <br> - 记录每个指令的来源批次号 <br> - 提供冲突日志供问题排查 |

---

## 9. 实施路线图与测试策略

### 9.1 实施优先级

#### Phase 1 - 基础能力 (预计 2 周)

**任务 1.1**: `wservice.llm_optimize_subtitles` - 字幕优化节点
- [ ] 实现极简指令集解析器
- [ ] 滑动窗口并发处理框架
- [ ] 单元测试覆盖 5 种操作类型

**任务 1.2**: `wservice.llm_translate_subtitles` - 翻译装词节点
- [ ] 音节数估算器(英文/中文)
- [ ] 时长验证与重试机制
- [ ] 集成测试验证 ±10% 精度

#### Phase 2 - TTS 集成 (预计 2 周)

**任务 2.1**: `wservice.edgetts_generate_batch_speech` - Edge-TTS 节点 (优先,无 GPU 依赖)
- [ ] Rate 预估算法实现
- [ ] Rubberband 封装与测试
- [ ] 音频拼接流程

**任务 2.2**: `indextts.generate_batch_speech` - IndexTTS2 节点
- [ ] 参考音频预处理
- [ ] 双模式支持(single/dynamic)
- [ ] GPU 锁集成

#### Phase 3 - 视频合并 (预计 1 周)

**任务 3.1**: `ffmpeg.merge_video_audio_subtitle` - 视频合并节点
- [ ] 多音轨混合
- [ ] 字幕烧录
- [ ] 容错处理

### 9.2 测试策略

#### 单元测试

- **指令集解析器**: 覆盖所有操作类型和边界情况
- **音节数估算**: 英文/中文/混合文本准确率 > 90%
- **Rubberband 封装**: 验证 stretch_ratio 计算正确性

#### 集成测试

- **端到端 S2ST 流程**: 英文 → 中文 30 秒短视频
- **缓存复用验证**: 重复调用相同 `task_id` 命中率 100%
- **并发去重**: 50 条字幕批处理结果一致性

#### 性能基准

| 操作 | 目标性能 |
|-----|---------|
| 单条字幕优化 | < 2s (DeepSeek) |
| IndexTTS2 生成 | < 3s/句 (GPU) |
| Edge-TTS 生成 | < 1s/句 (API) |
| 完整 5 分钟视频 S2ST | < 10 分钟 |

### 9.3 文档更新清单

- [ ] 更新 `SINGLE_TASK_API_REFERENCE.md` 添加 5 个新节点
- [ ] 创建 `S2ST_WORKFLOW_GUIDE.md` 用户使用指南
- [ ] 更新 `docker-compose.yml` 添加必要环境变量
- [ ] 创建示例 workflow_config JSON

---

## 附录

### A. 依赖库清单

```txt
# Python 依赖
pyphen>=0.14.0          # 英文音节分割
edge-tts>=6.1.0         # Microsoft Edge-TTS
rubberband>=0.3.0       # 音频时间伸缩
```

### B. 环境变量

```bash
# LLM API Keys
DEEPSEEK_API_KEY=<your_key>
GEMINI_API_KEY=<your_key>

# IndexTTS2
INDEXTTS_API_ENDPOINT=http://indextts_service:5000
```

### C. 参考资料

- [Faster-Whisper Documentation](https://github.com/guillaumekln/faster-whisper)
- [IndexTTS2 Paper](https://arxiv.org/abs/2301.xxxxx)
- [Edge-TTS GitHub](https://github.com/rany2/edge-tts)
- [Rubberband Library](https://breakfastquay.com/rubberband/)

---

**设计完成日期**: 2026-01-16
**设计验证状态**: ✅ 所有部分已通过用户确认
