# Qwen3-ASR 节点设计（qwen3_asr.transcribe_audio）

## 背景与目标
- 参考 `faster_whisper.transcribe_audio`，新增一个独立的 Qwen3-ASR 语音识别节点。
- 节点作为独立 worker 服务运行，支持 `transformers` 与 `vllm` 两种后端。
- 输出结构与 `faster_whisper.transcribe_audio` 完全一致，确保下游兼容。

## 约束与非目标
- `audio_path` 为必填参数，不做智能回退。
- 首版支持 GPU + CPU：CPU 仅允许 `transformers` 后端，`vllm` 仅 GPU。
- `enable_word_timestamps=true` 时启用强制对齐模型。
- 不引入额外复杂架构（KISS / YAGNI）。

## 服务与组件
- 新增服务目录：`services/workers/qwen3_asr_service/`
- 关键组件：
  - `app/celery_app.py`：Celery 应用
  - `app/tasks.py`：任务入口（`qwen3_asr.transcribe_audio`）
  - `executors/transcribe_executor.py`：节点执行器
  - `app/qwen3_asr_infer.py`：subprocess 推理脚本
- 队列与 Worker 命名：
  - 队列：`qwen3_asr_queue`
  - Worker：`qwen3_asr_worker`

## 配置与依赖
- `config.yml` 新增 `qwen3_asr_service` 配置块：
  - `device`（默认 `cuda`）
  - `backend`（默认 `vllm`）
  - `model_size`（默认 `0.6B`）
  - `enable_word_timestamps`（默认 `true`）
  - `forced_aligner_model`（默认 `Qwen/Qwen3-ForcedAligner-0.6B`）
- `requirements.txt` 包含：`qwen-asr`、`qwen-asr[vllm]`、`transformers`、`torch`、`torchaudio` 等
- Dockerfile：基线镜像与 `faster_whisper_service` 保持一致，参考官方 Docker 方案的依赖组合，但不引入 `shm_size` 配置。

## Docker 部署与配置
- `docker-compose.yml` 新增服务 `qwen3_asr_service`：
  - `build.context` 与 `dockerfile` 指向 `services/workers/qwen3_asr_service/Dockerfile`
  - `container_name` 建议命名为 `yivideo-qwen3-asr`
  - `environment` 继承通用环境变量；支持可选 `HF_TOKEN` 加速模型下载
  - `volumes` 挂载服务代码与 `services/common`，并挂载模型缓存目录 `/root/.cache`
  - `deploy.resources.reservations.devices` 申请 `nvidia` GPU
  - `command` 使用 Celery worker，队列 `qwen3_asr_queue`，并发 `1`
  - `depends_on` 建议包含 `redis`、`minio`
  - `networks` 与现有服务保持一致（如 `yivideo-network`）
- Dockerfile 关键点：
  - CUDA runtime 版本与 `faster_whisper_service` 保持一致
  - 安装 `python3.11`、`ffmpeg`、`libsndfile1`
  - 安装 `qwen-asr[vllm]`、`transformers`、`torch`、`torchaudio` 等依赖

## API 接入与路由
- 在 `services/api_gateway/app/single_task_api.py` 注册 `qwen3_asr.transcribe_audio`
- 在 `services/api_gateway/app/single_task_executor.py` 或等价映射中加入 `qwen3_asr` 组
- 任务由 API Gateway 投递到 `qwen3_asr_queue`

## 数据流
1. API Gateway 接收 `task_name=qwen3_asr.transcribe_audio` 请求
2. 投递到 `qwen3_asr_queue`
3. Executor 下载音频 → 校验 → 解析参数
4. GPU 模式使用 `gpu_lock`；CPU 模式跳过锁
5. subprocess 运行推理脚本，生成转录结果
6. 输出 `segments_file`，结构完全对齐 `faster_whisper.transcribe_audio`

## 参数解析优先级
- `input_data` > `config.yml` > 内置默认值
- 使用与现有节点一致的参数解析工具（如 `parameter_resolver`）
- 若运行环境仅 CPU 且未显式指定 `backend`，默认回退为 `transformers`
- 若显式指定 `backend=vllm` 且 `device=cpu`，直接报错

## 输入参数
- `audio_path`（必填）
- `backend`（`vllm`/`transformers`）
- `model_size`（`0.6B`/`1.7B`）
- `language`（如 `auto`/`zh`/`en`）
- `enable_word_timestamps`（默认 `true`）
- `forced_aligner_model`（默认 `Qwen/Qwen3-ForcedAligner-0.6B`）

## 语言参数映射
- `language` 支持用户输入短码与全称：\n
  - `auto` / 空值 / `None` → 传 `None`（自动识别）\n
  - `zh` / `zh-CN` / `cn` → `Chinese`\n
  - `en` / `en-US` → `English`\n
- 其他值直接透传给 Qwen3-ASR（按官方支持语言清单处理）

## 输出字段（与 faster_whisper 一致）
- `segments_file`
- `audio_duration`
- `language`
- `model_name`
- `device`
- `enable_word_timestamps`
- `statistics`
- `segments_count`

## 复用与缓存判定
- 复用规则对齐 `faster_whisper.transcribe_audio`：
  - `stages.qwen3_asr.transcribe_audio.status=SUCCESS` 且 `output.segments_file` 非空视为可复用
  - 等待态返回 `status=pending`、`reuse_info.state=pending`
- 缓存键依赖 `audio_path` 与关键参数（`backend`、`model_size`、`language`、`enable_word_timestamps`）

## 输出文件与 MinIO
- `segments_file` 生成路径与命名方式对齐现有转录节点（使用 `path_builder`）
- 当 `core.auto_upload_to_minio=true` 时，由 state_manager 追加 `segments_file_minio_url`

## vLLM 运行约束
- vLLM 初始化代码需包裹在 `if __name__ == '__main__':` 规避 `spawn` 问题
- GPU 选择建议使用 `CUDA_VISIBLE_DEVICES`
- 启用词级时间戳时建议使用 FlashAttention2（可选，不做强制）

## words 映射规则（保持兼容）
- Qwen3 输出 `time_stamps` 时，将其映射为 `words` 列表：\n
  - 字段：`word`、`start`、`end`、`probability`\n
  - `word` 取时间戳片段文本；`start/end` 取秒级时间；`probability` 置为 `null`（若无原生置信度）\n
- 当 `enable_word_timestamps=false` 时，不输出 `words` 字段；`statistics.total_words` 置为 `0`

## 错误处理
- `audio_path` 缺失/为空 → 直接报错
- `device=cpu` 且 `backend=vllm` → 抛 `ValueError`
- subprocess 失败 → 抛 `RuntimeError` 并记录 stdout/stderr
- 结果文件不存在/解析失败 → 抛 `RuntimeError`

## 测试与验证（容器内执行）
- 单测：参数校验、后端约束、词级时间戳开关
- 集成验证：提交任务，检查 `segments_file` 结构与 `words` 输出
- 错误路径：缺失参数、无输出文件、subprocess 非 0
- 覆盖 vLLM + 强制对齐路径（`backend=vllm` + `enable_word_timestamps=true`）

示例命令（容器内执行）：

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/test_qwen3_asr_executor.py -v
```

## 兼容性与复用
- `segments_file` JSON 结构严格复用 `faster_whisper.transcribe_audio`（`metadata/segments/statistics`）
- 仅新增 Qwen3 专用输入参数，不新增输出字段
