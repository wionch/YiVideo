# FunASR 组件与 transcribe_audio Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 新增 `funasr_service` 与 `funasr.transcribe_audio` 节点，输出核心字段对齐 `faster_whisper.transcribe_audio`，并支持 FunASR 扩展字段与说话人标签。

**Architecture:** 独立 `funasr_service`（Celery + Executor + subprocess 推理脚本），复用 `BaseNodeExecutor`、`run_gpu_command` 与 GPU 锁；输出结构对齐 `faster_whisper`，在 `segments` 增加 `speaker` 等扩展。

**Tech Stack:** Python、Celery、FunASR、ModelScope、Docker Compose、pytest（容器内）。

---

## 执行约束与准备

- **所有 pytest 必须在容器内执行**（遵循仓库要求）。
- 宿主机 pip 可能被 PEP 668 限制，**不在宿主机安装依赖**。

### Task 0: 准备可用容器与执行上下文

**Files:** 无

**Step 1: 获取运行中的容器名**

```
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
```

Expected: 输出容器列表，选择**挂载代码目录**的容器（优先 api_gateway 或 wservice）。

**Step 2: 若无容器运行，先启动基础容器（挂载代码目录）**

```
docker compose up -d api_gateway
```

Expected: api_gateway 容器启动成功。

**Step 3: 记录容器名**

在后续步骤中使用 `<container_name>` 替换容器名（确保容器已挂载 `/app` 代码）。

---

### Task 1: 创建服务骨架与最小可导入结构

**Files:**
- Create: `services/workers/funasr_service/__init__.py`
- Create: `services/workers/funasr_service/app/__init__.py`
- Create: `services/workers/funasr_service/executors/__init__.py`
- Create: `services/workers/funasr_service/requirements.txt`
- Create: `services/workers/funasr_service/Dockerfile`

**Step 1: 写入 requirements.txt（最小可运行依赖）**

```text
funasr
modelscope
huggingface_hub
torch>=1.13
```

**Step 2: 写入 Dockerfile（对齐 faster_whisper_service 基线）**

```dockerfile
# Dockerfile
FROM nvidia/cuda:12.9.1-cudnn-runtime-ubuntu24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/bin/python

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY services/workers/funasr_service/requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

FROM nvidia/cuda:12.9.1-cudnn-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1001 appuser && \
    useradd --uid 1001 --gid 1001 --shell /bin/bash --create-home appuser && \
    mkdir -p /app && \
    chown -R appuser:appuser /app

USER appuser
WORKDIR /app

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
RUN ln -sf /usr/bin/python3 /opt/venv/bin/python && \
    ln -sf /usr/bin/pip3 /opt/venv/bin/pip

COPY --chown=appuser:appuser services/common /app/services/common
COPY --chown=appuser:appuser services/workers/funasr_service /app/services/workers/funasr_service
COPY --chown=appuser:appuser config.yml /app/config.yml

WORKDIR /app/services/workers/funasr_service
CMD ["celery", "-A", "app.celery_app", "worker", "-l", "info", "-Q", "funasr_queue", "--concurrency=1", "-n", "funasr_worker@%h"]
```

**Step 3: 验证可导入结构**

Run (容器内):
```
docker exec -it <container_name> python -c "import services.workers.funasr_service"
```
Expected: 无异常输出。

**Step 4: Commit**

```bash
git add services/workers/funasr_service
git commit -m "feat: 初始化 funasr 服务目录结构"
```

---

### Task 2: 编写 FunASR 输出映射单测（words/segments/speaker）

**Files:**
- Create: `tests/unit/funasr/test_output_mapping.py`

**Step 1: Write the failing test**

```python
from services.workers.funasr_service.executors.transcribe_executor import (
    map_words, build_segments, normalize_speaker, build_segments_from_payload
)

def test_map_words_with_timestamps():
    words, count = map_words([
        {"text": "你好", "start": 0.1, "end": 0.5},
        {"text": "世界", "start": 0.6, "end": 1.0},
    ], enable=True)
    assert count == 2
    assert words[0]["word"] == "你好"
    assert words[1]["start"] == 0.6


def test_build_segments_fallback_when_no_words():
    segments = build_segments(text="hello", words=[], audio_duration=2.0, speaker=None)
    assert segments[0]["start"] == 0.0
    assert segments[0]["end"] == 2.0


def test_normalize_speaker_optional():
    assert normalize_speaker(None) is None
    assert normalize_speaker("spk1") == "spk1"


def test_build_segments_from_payload_uses_segments():
    payload = {"segments": [{"start": 0.0, "end": 1.0, "text": "hi", "speaker": "spk1"}]}
    segments = build_segments_from_payload(payload, audio_duration=1.0, enable_word_timestamps=False)
    assert segments[0]["speaker"] == "spk1"


def test_build_segments_from_payload_uses_timestamps():
    payload = {"text": "hi", "time_stamps": [{"text": "hi", "start": 0.0, "end": 1.0}]}
    segments = build_segments_from_payload(payload, audio_duration=1.0, enable_word_timestamps=True)
    assert "words" in segments[0]
```

**Step 2: Run test to verify it fails**

Run (容器内):
```
docker exec -it <container_name> pytest /app/tests/unit/funasr/test_output_mapping.py -v
```
Expected: FAIL（模块或函数未定义）。

**Step 3: Write minimal implementation**

在 `services/workers/funasr_service/executors/transcribe_executor.py` 添加：

```python
from __future__ import annotations

from typing import Any, Dict, List, Tuple

def map_words(time_stamps: List[Dict[str, Any]] | None, enable: bool) -> Tuple[list, int]:
    if not enable or not time_stamps:
        return [], 0
    words = []
    for item in time_stamps:
        words.append({
            "word": item.get("text", ""),
            "start": item.get("start", 0.0),
            "end": item.get("end", 0.0),
            "probability": None,
        })
    return words, len(words)


def normalize_speaker(speaker: str | None) -> str | None:
    if speaker is None:
        return None
    value = str(speaker).strip()
    return value or None


def build_segments(text: str, words: list, audio_duration: float, speaker: str | None) -> List[Dict[str, Any]]:
    if words:
        start = words[0].get("start", 0.0)
        end = words[-1].get("end", audio_duration)
    else:
        start, end = 0.0, audio_duration
    segment = {
        "id": 0,
        "start": start,
        "end": end,
        "text": text or "",
    }
    if words:
        segment["words"] = words
    spk = normalize_speaker(speaker)
    if spk is not None:
        segment["speaker"] = spk
    return [segment]


def build_segments_from_payload(payload: Dict[str, Any], audio_duration: float, enable_word_timestamps: bool) -> List[Dict[str, Any]]:
    segments = payload.get("segments") or []
    if segments:
        normalized = []
        for idx, seg in enumerate(segments):
            item = dict(seg)
            if "id" not in item:
                item["id"] = idx
            normalized.append(item)
        return normalized
    words, _ = map_words(payload.get("time_stamps"), enable=enable_word_timestamps)
    return build_segments(
        text=payload.get("text", ""),
        words=words,
        audio_duration=audio_duration,
        speaker=payload.get("speaker"),
    )
```

**Step 4: Run test to verify it passes**

```
docker exec -it <container_name> pytest /app/tests/unit/funasr/test_output_mapping.py -v
```
Expected: PASS。

**Step 5: Commit**

```bash
git add services/workers/funasr_service/executors/transcribe_executor.py tests/unit/funasr/test_output_mapping.py
git commit -m "feat: 新增 funasr 输出映射辅助函数"
```

---

### Task 3: 构建标准化输出 JSON 的单测

**Files:**
- Create: `tests/unit/funasr/test_output_json.py`

**Step 1: Write the failing test**

```python
from services.workers.funasr_service.executors.transcribe_executor import build_transcribe_json


def test_build_transcribe_json_has_core_fields():
    data = build_transcribe_json(
        stage_name="funasr.transcribe_audio",
        workflow_id="wf-1",
        audio_file_name="demo.wav",
        segments=[{"id": 0, "start": 0.0, "end": 1.0, "text": "hi"}],
        audio_duration=1.0,
        language="zh",
        model_name="FunAudioLLM/Fun-ASR-Nano-2512",
        device="cuda",
        enable_word_timestamps=False,
        transcribe_duration=0.5,
        funasr_metadata={"vad_model": "fsmn-vad"},
    )
    assert data["metadata"]["task_name"] == "funasr.transcribe_audio"
    assert data["statistics"]["total_segments"] == 1
```

**Step 2: Run test to verify it fails**

```
docker exec -it <container_name> pytest /app/tests/unit/funasr/test_output_json.py -v
```
Expected: FAIL。

**Step 3: Write minimal implementation**

在 `services/workers/funasr_service/executors/transcribe_executor.py` 添加：

```python
import time

def build_transcribe_json(
    stage_name: str,
    workflow_id: str,
    audio_file_name: str,
    segments: List[Dict[str, Any]],
    audio_duration: float,
    language: str,
    model_name: str,
    device: str,
    enable_word_timestamps: bool,
    transcribe_duration: float,
    funasr_metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    total_segments = len(segments)
    total_words = sum(len(seg.get("words", [])) for seg in segments)
    avg_duration = 0.0
    if total_segments > 0:
        avg_duration = sum(seg.get("end", 0) - seg.get("start", 0) for seg in segments) / total_segments
    metadata = {
        "task_name": stage_name,
        "workflow_id": workflow_id,
        "audio_file": audio_file_name,
        "total_duration": audio_duration,
        "language": language,
        "word_timestamps_enabled": enable_word_timestamps,
        "model_name": model_name,
        "device": device,
        "transcribe_method": "funasr-subprocess",
        "created_at": time.time(),
    }
    if funasr_metadata:
        metadata["funasr"] = funasr_metadata
    return {
        "metadata": metadata,
        "segments": segments,
        "statistics": {
            "total_segments": total_segments,
            "total_words": total_words,
            "transcribe_duration": transcribe_duration,
            "average_segment_duration": avg_duration,
        },
    }
```

**Step 4: Run test to verify it passes**

```
docker exec -it <container_name> pytest /app/tests/unit/funasr/test_output_json.py -v
```
Expected: PASS。

**Step 5: Commit**

```bash
git add services/workers/funasr_service/executors/transcribe_executor.py tests/unit/funasr/test_output_json.py
git commit -m "feat: 新增 funasr 转录输出构建"
```

---

### Task 4: 构建推理命令与参数覆盖单测

**Files:**
- Create: `tests/unit/funasr/test_infer_command.py`

**Step 1: Write the failing test**

```python
from services.workers.funasr_service.executors.transcribe_executor import build_infer_command


def test_build_infer_command_contains_required_flags():
    cmd = build_infer_command(
        audio_path="/tmp/a.wav",
        output_file="/tmp/out.json",
        model_name="paraformer-zh",
        device="cuda:0",
        enable_word_timestamps=True,
        vad_model="fsmn-vad",
        punc_model="ct-punc",
        spk_model="cam++",
        language="auto",
        hotwords=["魔搭"],
        batch_size_s=60,
        use_itn=True,
        merge_vad=True,
        merge_length_s=15,
        trust_remote_code=False,
        remote_code=None,
        model_revision="v2.0.4",
        vad_model_revision="v2.0.4",
        punc_model_revision="v2.0.4",
        spk_model_revision="v2.0.2",
        lm_model="damo/speech_transformer_lm_zh-cn-common-vocab8404-pytorch",
        lm_weight=0.15,
        beam_size=10,
    )
    cmd_str = " ".join(cmd)
    assert "--audio_path" in cmd_str
    assert "--model_name paraformer-zh" in cmd_str
```

**Step 2: Run test to verify it fails**

```
docker exec -it <container_name> pytest /app/tests/unit/funasr/test_infer_command.py -v
```
Expected: FAIL。

**Step 3: Write minimal implementation**

在 `services/workers/funasr_service/executors/transcribe_executor.py` 添加：

```python
import sys
from pathlib import Path

def build_infer_command(
    audio_path: str,
    output_file: str,
    model_name: str,
    device: str,
    enable_word_timestamps: bool,
    vad_model: str | None,
    punc_model: str | None,
    spk_model: str | None,
    language: str | None,
    hotwords: list | None,
    batch_size_s: int | None,
    use_itn: bool | None,
    merge_vad: bool | None,
    merge_length_s: int | None,
    trust_remote_code: bool | None,
    remote_code: str | None,
    model_revision: str | None,
    vad_model_revision: str | None,
    punc_model_revision: str | None,
    spk_model_revision: str | None,
    lm_model: str | None,
    lm_weight: float | None,
    beam_size: int | None,
) -> list[str]:
    infer_script = Path(__file__).resolve().parents[1] / "app" / "funasr_infer.py"
    cmd = [
        sys.executable,
        str(infer_script),
        "--audio_path", audio_path,
        "--output_file", output_file,
        "--model_name", model_name,
        "--device", device,
    ]
    if enable_word_timestamps:
        cmd.append("--enable_word_timestamps")
    if vad_model:
        cmd += ["--vad_model", vad_model]
    if punc_model:
        cmd += ["--punc_model", punc_model]
    if spk_model:
        cmd += ["--spk_model", spk_model]
    if language:
        cmd += ["--language", language]
    if hotwords:
        cmd += ["--hotwords", ",".join(hotwords)]
    if batch_size_s is not None:
        cmd += ["--batch_size_s", str(batch_size_s)]
    if use_itn is not None:
        cmd += ["--use_itn", str(use_itn).lower()]
    if merge_vad is not None:
        cmd += ["--merge_vad", str(merge_vad).lower()]
    if merge_length_s is not None:
        cmd += ["--merge_length_s", str(merge_length_s)]
    if trust_remote_code is not None:
        cmd += ["--trust_remote_code", str(trust_remote_code).lower()]
    if remote_code:
        cmd += ["--remote_code", remote_code]
    if model_revision:
        cmd += ["--model_revision", model_revision]
    if vad_model_revision:
        cmd += ["--vad_model_revision", vad_model_revision]
    if punc_model_revision:
        cmd += ["--punc_model_revision", punc_model_revision]
    if spk_model_revision:
        cmd += ["--spk_model_revision", spk_model_revision]
    if lm_model:
        cmd += ["--lm_model", lm_model]
    if lm_weight is not None:
        cmd += ["--lm_weight", str(lm_weight)]
    if beam_size is not None:
        cmd += ["--beam_size", str(beam_size)]
    return cmd
```

**Step 4: Run test to verify it passes**

```
docker exec -it <container_name> pytest /app/tests/unit/funasr/test_infer_command.py -v
```
Expected: PASS。

**Step 5: Commit**

```bash
git add services/workers/funasr_service/executors/transcribe_executor.py tests/unit/funasr/test_infer_command.py
git commit -m "feat: 新增 funasr 推理命令构建"
```

---

### Task 5: 实现推理脚本 funasr_infer.py（含单测）

**Files:**
- Create: `services/workers/funasr_service/app/funasr_infer.py`
- Create: `tests/unit/funasr/test_infer_payload.py`

**Step 1: Write the failing test**

```python
from services.workers.funasr_service.app.funasr_infer import build_infer_payload, normalize_model_output, parse_hotwords


def test_build_infer_payload_base_fields():
    payload = build_infer_payload(
        text="hi",
        language="en",
        audio_duration=1.2,
        time_stamps=[],
        segments=[],
        speaker=None,
        extra={"lid": "en"},
        transcribe_duration=0.3,
    )
    assert payload["text"] == "hi"
    assert payload["audio_duration"] == 1.2


def test_normalize_model_output_sentence_info():
    raw = {"sentence_info": [{"start": 0.0, "end": 1.0, "text": "hi", "spk": "S1"}]}
    payload = normalize_model_output(raw)
    assert payload["segments"][0]["speaker"] == "S1"


def test_normalize_model_output_time_stamps():
    raw = {"text": "hi", "time_stamps": [{"text": "hi", "start": 0.0, "end": 1.0}]}
    payload = normalize_model_output(raw)
    assert payload["time_stamps"]


def test_normalize_model_output_time_stamp_alias():
    raw = {"time_stamp": [{"text": "hi", "start": 0.0, "end": 1.0}]}
    payload = normalize_model_output(raw)
    assert payload["time_stamps"]


def test_parse_hotwords_accepts_json_and_csv():
    assert parse_hotwords("[\"魔搭\",\"开放时间\"]") == ["魔搭", "开放时间"]
    assert parse_hotwords("魔搭,开放时间") == ["魔搭", "开放时间"]
    assert parse_hotwords("魔搭") == ["魔搭"]
```

**Step 2: Run test to verify it fails**

```
docker exec -it <container_name> pytest /app/tests/unit/funasr/test_infer_payload.py -v
```
Expected: FAIL。

**Step 3: Write minimal implementation**

```python
# services/workers/funasr_service/app/funasr_infer.py
from __future__ import annotations

import argparse
import json
import time
from typing import Any, Dict


def normalize_model_output(raw: Dict[str, Any]) -> Dict[str, Any]:
    time_stamps = raw.get("time_stamps") or raw.get("timestamp") or raw.get("time_stamp") or []
    speaker = raw.get("speaker") or raw.get("spk")
    segments = []
    for idx, item in enumerate(raw.get("sentence_info", []) or raw.get("sentences", [])):
        seg = {
            "id": idx,
            "start": item.get("start", 0.0),
            "end": item.get("end", 0.0),
            "text": item.get("text", ""),
        }
        spk = item.get("speaker") or item.get("spk")
        if spk:
            seg["speaker"] = spk
        segments.append(seg)
    extra = raw.get("extra") or {}
    for key in ("lid", "ser", "aed"):
        if key in raw and key not in extra:
            extra[key] = raw[key]
    return {
        "text": raw.get("text", ""),
        "time_stamps": time_stamps,
        "segments": segments,
        "speaker": speaker,
        "extra": extra,
    }


def parse_hotwords(value: str | None) -> list:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(item) for item in data if str(item).strip()]
        except Exception:
            pass
    if "," in text:
        return [item.strip() for item in text.split(",") if item.strip()]
    return [text]


def build_infer_payload(
    text: str,
    language: str,
    audio_duration: float,
    time_stamps: list,
    segments: list,
    speaker: str | None,
    extra: dict | None,
    transcribe_duration: float,
) -> Dict[str, Any]:
    payload = {
        "text": text or "",
        "language": language or "unknown",
        "audio_duration": audio_duration,
        "time_stamps": time_stamps or [],
        "segments": segments or [],
        "speaker": speaker,
        "transcribe_duration": transcribe_duration,
    }
    if extra:
        payload["extra"] = extra
    return payload
```

**Step 4: Run test to verify it passes**

```
docker exec -it <container_name> pytest /app/tests/unit/funasr/test_infer_payload.py -v
```
Expected: PASS。

**Step 5: 完成 funasr_infer.py 主流程**

```python
# 伪代码结构（需完整实现）
# - 解析 CLI 参数（hotwords 支持 JSON 列表或逗号分隔字符串）
# - 初始化 AutoModel（含 model_revision / *_revision / trust_remote_code / remote_code）
# - 调用 model.generate（传入 hotwords 列表、language、batch_size_s、use_itn 等）
# - normalize_model_output 统一字段（segments/time_stamps/speaker/extra）
# - build_infer_payload 生成标准输出
# - 写入 output_file JSON
# - 提供 main() 入口供 subprocess 调用
```

**Step 6: Commit**

```bash
git add services/workers/funasr_service/app/funasr_infer.py tests/unit/funasr/test_infer_payload.py
git commit -m "feat: 新增 funasr 推理脚本"
```

---

### Task 6: 实现 Executor 主流程（子进程 + 输出构建）

**Files:**
- Modify: `services/workers/funasr_service/executors/transcribe_executor.py`
- Create: `tests/unit/funasr/test_executor_pipeline.py`

**Step 1: Write the failing test**

```python
import json
from pathlib import Path
from services.workers.funasr_service.executors.transcribe_executor import FunASRTranscribeExecutor


def test_executor_pipeline(mocker, tmp_path):
    executor = FunASRTranscribeExecutor("funasr.transcribe_audio", mocker.Mock())
    executor.context.workflow_id = "wf-1"
    executor.context.shared_storage_path = "/share/workflows/wf-1"
    executor.get_input_data = lambda: {"audio_path": "/tmp/demo.wav"}
    mocker.patch("services.workers.funasr_service.executors.transcribe_executor.get_file_service").return_value.resolve_and_download.return_value = "/tmp/demo.wav"
    mocker.patch("services.workers.funasr_service.executors.transcribe_executor.os.path.exists", return_value=True)
    mocker.patch("services.workers.funasr_service.executors.transcribe_executor.build_node_output_path", return_value=str(tmp_path / "out.json"))
    mocker.patch("services.workers.funasr_service.executors.transcribe_executor.ensure_directory")
    fake_payload = {
        "text": "hi",
        "language": "en",
        "audio_duration": 1.0,
        "time_stamps": [],
        "speaker": None,
        "transcribe_duration": 0.2,
    }
    mocker.patch("services.workers.funasr_service.executors.transcribe_executor._run_infer", return_value=fake_payload)
    result = executor.execute()
    assert "segments_file" in result.output
```

**Step 2: Run test to verify it fails**

```
docker exec -it <container_name> pytest /app/tests/unit/funasr/test_executor_pipeline.py -v
```
Expected: FAIL。

**Step 3: Write minimal implementation**

在 `transcribe_executor.py` 实现：
- 继承 `BaseNodeExecutor`
- 下载音频（`file_service.resolve_and_download`）
- 读取 `CONFIG.get("funasr_service", {})`
- 归一化参数（`hotword/hotwords`、`use_itn/itn`、`*_revision` 优先级）
- Fun-ASR-Nano 若 `enable_word_timestamps=True` 或 `spk_model` 配置 → 自动降级 + 记录 `metadata.funasr.warnings`
- 生成 `output_file`（`/share/workflows/<task_id>/tmp`）
- 调用 `_run_infer`（含 `gpu_lock`）
- 使用 `build_segments_from_payload`：若 payload 含 `segments` → 优先使用；否则 `time_stamps` → `map_words` → `build_segments`
- 构建 `funasr_metadata`（记录模型/参数/降级信息）
- 输出 `segments_file` 并返回核心字段

补充 `_run_infer` 参考实现（放在 `transcribe_executor.py`）：

```python
from services.common.subprocess_utils import run_gpu_command

def _run_infer(cmd: list[str], stage_name: str, cwd: str) -> dict:
    result = run_gpu_command(cmd, stage_name=stage_name, timeout=1800, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f\"subprocess 失败: {result.stderr}\")
    output_path = cmd[cmd.index(\"--output_file\") + 1]
    with open(output_path, \"r\", encoding=\"utf-8\") as f:
        return json.load(f)
```

**Step 4: Run test to verify it passes**

```
docker exec -it <container_name> pytest /app/tests/unit/funasr/test_executor_pipeline.py -v
```
Expected: PASS。

**Step 5: Commit**

```bash
git add services/workers/funasr_service/executors/transcribe_executor.py tests/unit/funasr/test_executor_pipeline.py
git commit -m "feat: 实现 funasr executor 主流程"
```

---

### Task 7: 接入 Celery 任务入口

**Files:**
- Create: `services/workers/funasr_service/app/celery_app.py`
- Create: `services/workers/funasr_service/app/tasks.py`
- Create: `tests/unit/funasr/test_tasks_import.py`

**Step 1: Write the failing test**

```python
def test_tasks_importable():
    import services.workers.funasr_service.app.tasks  # noqa: F401
```

**Step 2: Run test to verify it fails**

```
docker exec -it <container_name> pytest /app/tests/unit/funasr/test_tasks_import.py -v
```
Expected: FAIL。

**Step 3: Write minimal implementation**

```python
# app/celery_app.py
from services.common.celery_app_factory import create_celery_app
celery_app = create_celery_app("funasr_service", include=["services.workers.funasr_service.app.tasks"])

# app/tasks.py
from services.workers.funasr_service.app.celery_app import celery_app
from services.workers.funasr_service.executors.transcribe_executor import FunASRTranscribeExecutor
from services.common.context import WorkflowContext
from services.common import state_manager

@celery_app.task(bind=True, name="funasr.transcribe_audio")
def transcribe_audio(self, context: dict) -> dict:
    workflow_context = WorkflowContext(**context)
    executor = FunASRTranscribeExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()
```

**Step 4: Run test to verify it passes**

```
docker exec -it <container_name> pytest /app/tests/unit/funasr/test_tasks_import.py -v
```
Expected: PASS。

**Step 5: Commit**

```bash
git add services/workers/funasr_service/app/celery_app.py services/workers/funasr_service/app/tasks.py tests/unit/funasr/test_tasks_import.py
git commit -m "feat: 新增 funasr Celery 任务入口"
```

---

### Task 8: 接入配置与路由

**Files:**
- Modify: `config.yml`
- Modify: `docker-compose.yml`
- Modify: `services/api_gateway/app/single_task_api.py`
- Modify: `services/api_gateway/app/single_task_executor.py`
- Create: `tests/unit/test_fun_asr_routing.py`

**Step 1: Write the failing test**

```python
def test_fun_asr_registered():
    from services.api_gateway.app.single_task_api import TASK_CATEGORY_MAPPING
    assert "funasr" in TASK_CATEGORY_MAPPING
    assert "funasr.transcribe_audio" in TASK_CATEGORY_MAPPING["funasr"]
```

**Step 2: Run test to verify it fails**

```
docker exec -it <container_name> pytest /app/tests/unit/test_fun_asr_routing.py -v
```
Expected: FAIL。

**Step 3: Write minimal implementation**

- `config.yml` 添加 `funasr_service` 默认配置（已在设计文档中给出）
- `docker-compose.yml` 新增 `funasr_service` 服务（参照 `qwen3_asr_service`，使用以下模板）
  ```yaml
  funasr_service:
    <<: *celery-worker-base
    container_name: funasr_service
    build:
      <<: *build-base
      dockerfile: ${YIVIDEO_ROOT}/services/workers/funasr_service/Dockerfile
    command: ['celery', '-A', 'app.celery_app', 'worker', '-l', 'info', '-Q', 'funasr_queue', '--concurrency=1', '-n', 'funasr_worker@%h']
    volumes:
      - *vol-services
      - *vol-videos
      - *vol-locks
      - *vol-tmp
      - *vol-worktrees
      - *vol-tests
      - *vol-share
      - *vol-config-yml
      - *vol-config-dir
      - *vol-ssh
      - *vol-gemini
      - *vol-hf-cache
      - *vol-tf-cache
    environment:
      <<: [*base-env, *gpu-env, *cache-env]
      CELERY_WORKER_NAME: funasr_worker
      HF_TOKEN: ${HF_TOKEN}
    deploy:
      <<: *gpu-deploy
  ```
- `single_task_api.py` 增加 `funasr` 组与 `funasr.transcribe_audio`
- `single_task_executor.py` 将 `funasr` 加入服务清单与队列映射

**Step 4: Run test to verify it passes**

```
docker exec -it <container_name> pytest /app/tests/unit/test_fun_asr_routing.py -v
```
Expected: PASS。

**Step 5: Commit**

```bash
git add config.yml docker-compose.yml services/api_gateway/app/single_task_api.py services/api_gateway/app/single_task_executor.py tests/unit/test_fun_asr_routing.py
git commit -m "feat: 接入 funasr 配置与路由"
```

---

### Task 9: 更新单任务 API 参考文档

**Files:**
- Modify: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`

**Step 1: Write the failing doc test (manual checklist)**

新增 `funasr.transcribe_audio` 小节（结构与 qwen3_asr/faster_whisper 对齐）。

**Step 2: Update docs**

内容包含：功能概述、输入参数、输出字段、复用判定。

**Step 3: Commit**

```bash
git add docs/technical/reference/SINGLE_TASK_API_REFERENCE.md
git commit -m "docs: 增加 funasr 单任务 API 参考"
```

---

### Task 10: 最小集成验证（容器内）

**Step 1: 启动服务**

```
docker compose build funasr_service
docker compose up -d funasr_service
```

**Step 2: 运行最小转写任务**

```
docker exec -it <container_name> python -c "from services.workers.funasr_service.app.funasr_infer import main; print('ok')"
```

Expected: 打印 ok。

**Step 3: 运行 pytest 关键用例**

```
docker exec -it <container_name> pytest /app/tests/unit/funasr -v
```

Expected: 全部 PASS。

**Step 4: Commit（如需）**

无代码变更则跳过。

---

## 验证与回归清单（执行阶段）

- funasr 输出结构与 `faster_whisper.transcribe_audio` 核心字段一致
- Fun-ASR-Nano 时间戳/说话人自动降级
- paraformer-zh-spk 输出 `segments.speaker`
- API Gateway 路由可达 `funasr.transcribe_audio`
