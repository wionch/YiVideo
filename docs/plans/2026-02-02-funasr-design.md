# FunASR 组件与 transcribe_audio 节点设计

## 目标与范围

- 目标：新增 `funasr_service` 与 `funasr.transcribe_audio` 功能节点，输出**核心字段与 `faster_whisper.transcribe_audio` 对齐**，同时允许 FunASR 扩展字段。
- 默认模型：`FunAudioLLM/Fun-ASR-Nano-2512`。
- 重点能力：ASR 转写；在 `paraformer-zh-spk` 场景输出段级 `speaker` 字段。
- 不做内容：字幕生成、翻译与文本优化由现有节点承担。

## 需求与约束

- **KISS**：复用现有 ASR 服务形态，不引入复杂抽象层。
- **DRY**：复用 `BaseNodeExecutor`、路径构建与子进程工具。
- **SRP**：`funasr_service` 只负责 ASR 与输出文件生成。
- 输出必须兼容现有下游：核心字段结构对齐 `faster_whisper.transcribe_audio`。

## 目标模型与官方能力（摘要）

来源：FunASR 官方 README_zh 提供的模型仓库与示例。

- **Fun-ASR-Nano-2512**：多语言 ASR（中文/英文/日语及方言），适合作为默认模型。
- **SenseVoiceSmall**：ASR + LID + SER + AED，适合需要语音理解扩展信息的场景。
- **paraformer-zh**：中文 ASR，官方说明支持时间戳输出，非实时。
- **paraformer-en**：英文 ASR，非实时。
- **paraformer-zh-spk**：在 ASR 基础上启用说话人模型（spk），输出说话人标签。

## 官方样例（抽取关键参数）

- **Fun-ASR-Nano**：`AutoModel(model=Fun-ASR-Nano-2512, vad_model=fsmn-vad, vad_kwargs, batch_size_s)`
- **SenseVoiceSmall**：`AutoModel(model=SenseVoiceSmall, vad_model, language=auto, use_itn, merge_vad, merge_length_s)` + `rich_transcription_postprocess`
- **Paraformer**：`AutoModel(model=paraformer-zh, vad_model, punc_model, spk_model 可选, hotword)`

> 设计中仅使用上述参数族，确保与官方示例一致。

## 架构与组件

新增服务目录：`services/workers/funasr_service/`

- `app/celery_app.py`：Celery 应用配置，队列 `funasr_queue`
- `app/tasks.py`：任务入口 `funasr.transcribe_audio`
- `executors/transcribe_executor.py`：执行器（下载、参数解析、输出构建）
- `app/funasr_infer.py`：子进程推理脚本（FunASR AutoModel）
- `Dockerfile`、`requirements.txt`

与 `faster_whisper_service` / `qwen3_asr_service` 形态一致，保证可维护性与部署一致性。

## 数据流

1. API Gateway 接收 `task_name=funasr.transcribe_audio`
2. 投递到 `funasr_queue`
3. Executor 下载音频并构建推理命令
4. 子进程运行 `funasr_infer.py`，生成中间结果
5. Executor 构建标准 `segments_file` 并返回核心字段

## 输入与输出设计

### 输入（input_data）

必填：
- `audio_path`

可选（覆盖配置）：
- `model_name` / `device` / `enable_word_timestamps`
- `vad_model` / `punc_model` / `spk_model`
- `language` / `hotword`
- `batch_size_s` / `use_itn` / `merge_vad` / `merge_length_s`

### 输出（与 faster_whisper 核心对齐）

核心字段：
- `segments_file`
- `audio_duration` / `language` / `model_name` / `device`
- `enable_word_timestamps`
- `statistics`（`total_segments/total_words/transcribe_duration/average_segment_duration`）
- `segments_count`

`segments_file` JSON：
- `metadata`：`task_name/workflow_id/audio_file/total_duration/language/word_timestamps_enabled/model_name/device/transcribe_method/created_at`
- `segments`：`id/start/end/text/words`（有词级时间戳时）
- `statistics`

扩展字段（不影响兼容）：
- `segments[i].speaker`：仅 `paraformer-zh-spk` 输出
- `metadata.funasr`：记录 `vad_model/punc_model/spk_model/use_itn/batch_size_s/merge_vad` 等
- `segments[i].funasr_attrs`：可选承载 SenseVoice 的 LID/SER/AED 结果

## 推理脚本设计（funasr_infer.py）

- 统一使用 `funasr.AutoModel`。
- 根据模型与参数选择性启用：`vad_model`、`punc_model`、`spk_model`。
- 对 SenseVoice：可选执行 `rich_transcription_postprocess`，并保留扩展属性。
- 结果输出规范化：
  - 无时间戳时退化为单段覆盖全音频
  - words 结构统一映射为 `word/start/end/probability`

## 错误处理与日志

- 参数缺失（`audio_path`）或文件不存在 → 直接抛错
- 子进程失败/超时 → 记录 stdout/stderr 摘要并抛错
- 输出为空 → 仍生成 `segments_file`，至少包含一段空文本
- 说话人输出异常 → 记录告警并将 `speaker` 置空

## 配置与部署

### config.yml（新增示例）

```yaml
funasr_service:
  model_name: "FunAudioLLM/Fun-ASR-Nano-2512"
  device: "cuda"
  enable_word_timestamps: true
  vad_model: "fsmn-vad"
  punc_model: "ct-punc"
  spk_model: "cam++"
  language: "auto"
  use_itn: true
  merge_vad: true
  merge_length_s: 15
  batch_size_s: 60
```

### Docker

- `docker compose build funasr_service`
- `docker compose up -d funasr_service`

## 测试策略

单元测试：
- 输出结构映射与回退逻辑（含 `speaker` 扩展）
- 参数覆盖与命令行构建

集成验证（容器内）：
- 短音频转写生成 `segments_file`
- `paraformer-zh-spk` 场景包含 `segments.speaker`

## 未确定项（上线前补齐）

- ModelScope 模型卡细节（许可证/语言覆盖范围/模型输入约束）需在上线前补证。

## 实施清单（后续）

1. 创建 `funasr_service` 目录与基础文件
2. 实现 `funasr_infer.py`（AutoModel + 参数映射）
3. 实现 `transcribe_executor.py` 与输出构建
4. 接入 `config.yml`、`docker-compose.yml`、API Gateway 路由
5. 补齐单元测试与容器内验证

