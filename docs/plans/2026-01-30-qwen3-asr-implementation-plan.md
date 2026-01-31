# Qwen3-ASR 节点实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 新增 `qwen3_asr.transcribe_audio` 独立节点与服务，输出结构完全对齐 `faster_whisper.transcribe_audio`。

**Architecture:** 独立 `qwen3_asr_service` + Celery 任务入口 + Executor + subprocess 推理脚本；支持 `vllm/transformers` 后端，CPU 仅允许 `transformers`。

**Tech Stack:** Python 3.11, Celery, qwen-asr, vLLM, transformers, torch/torchaudio, Docker

---

## Task 0: 创建服务目录与基础文件

**Files:**
- Create: `services/workers/qwen3_asr_service/__init__.py`
- Create: `services/workers/qwen3_asr_service/requirements.txt`
- Create: `services/workers/qwen3_asr_service/Dockerfile`
- Create: `services/workers/qwen3_asr_service/app/__init__.py`
- Create: `services/workers/qwen3_asr_service/app/celery_app.py`
- Create: `services/workers/qwen3_asr_service/app/tasks.py`
- Create: `services/workers/qwen3_asr_service/app/qwen3_asr_infer.py`
- Create: `services/workers/qwen3_asr_service/executors/__init__.py`
- Create: `services/workers/qwen3_asr_service/executors/transcribe_executor.py`

**Step 1: 创建目录与占位文件**

```bash
mkdir -p services/workers/qwen3_asr_service/app
mkdir -p services/workers/qwen3_asr_service/executors
printf "" > services/workers/qwen3_asr_service/__init__.py
printf "" > services/workers/qwen3_asr_service/app/__init__.py
printf "" > services/workers/qwen3_asr_service/executors/__init__.py
```

**Step 2: 追加 requirements.txt**

```text
# services/workers/qwen3_asr_service/requirements.txt
qwen-asr[vllm]
transformers
torch
torchaudio
soundfile
```

**Step 3: 写入 Dockerfile (对齐 faster_whisper_service 基线)**

```dockerfile
# services/workers/qwen3_asr_service/Dockerfile
# 与 faster_whisper_service 保持同一 CUDA 基线
# 实际镜像版本从 services/workers/faster_whisper_service/Dockerfile 复制
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y \
    python3.11 python3-pip ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY services/workers/qwen3_asr_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/workers/qwen3_asr_service /app/services/workers/qwen3_asr_service
COPY services/common /app/services/common
COPY app /app/app

WORKDIR /app/services/workers/qwen3_asr_service
CMD ["celery", "-A", "app.celery_app", "worker", "-l", "info", "-Q", "qwen3_asr_queue", "--concurrency=1", "-n", "qwen3_asr_worker@%h"]
```

**Step 4: Commit**

```bash
git add services/workers/qwen3_asr_service
# 注意：提交信息中文 + Conventional Commits

git commit -m "feat(qwen3_asr): 初始化服务目录结构"
```

---

## Task 1: 语言映射与参数校验（TDD）

**Files:**
- Modify: `services/workers/qwen3_asr_service/executors/transcribe_executor.py`
- Create: `tests/unit/qwen3_asr/test_language_mapping.py`

**Step 0: 创建测试目录**

```bash
mkdir -p tests/unit/qwen3_asr
```

**Step 1: 编写失败测试 - 语言映射**

```python
# tests/unit/qwen3_asr/test_language_mapping.py
import pytest
from services.workers.qwen3_asr_service.executors.transcribe_executor import map_language


def test_language_mapping_auto_none():
    assert map_language(None) is None
    assert map_language("") is None
    assert map_language("auto") is None


def test_language_mapping_basic():
    assert map_language("zh") == "Chinese"
    assert map_language("zh-CN") == "Chinese"
    assert map_language("cn") == "Chinese"
    assert map_language("en") == "English"
    assert map_language("en-US") == "English"


def test_language_mapping_passthrough():
    assert map_language("Japanese") == "Japanese"
```

**Step 2: 运行测试验证失败**

Run (容器内):

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/qwen3_asr/test_language_mapping.py -v
```

Expected: FAIL (map_language 未定义)

**Step 3: 最小实现语言映射函数**

```python
# services/workers/qwen3_asr_service/executors/transcribe_executor.py

def map_language(language: str | None) -> str | None:
    """将短码映射为 Qwen3-ASR 认可的语言标识"""
    if language is None:
        return None
    lang = str(language).strip()
    if not lang:
        return None
    low = lang.lower()
    if low in {"auto"}:
        return None
    if low in {"zh", "zh-cn", "cn"}:
        return "Chinese"
    if low in {"en", "en-us"}:
        return "English"
    return lang
```

**Step 4: 运行测试验证通过**

Run (容器内):

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/qwen3_asr/test_language_mapping.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add services/workers/qwen3_asr_service/executors/transcribe_executor.py tests/unit/qwen3_asr/test_language_mapping.py

git commit -m "feat(qwen3_asr): 添加语言参数映射"
```

---

## Task 2: Executor 核心逻辑与 words 映射（TDD）

**Files:**
- Modify: `services/workers/qwen3_asr_service/executors/transcribe_executor.py`
- Create: `tests/unit/qwen3_asr/test_executor_validation.py`
- Create: `tests/unit/qwen3_asr/test_words_mapping.py`

**Step 1: 编写失败测试 - 参数校验与 words 规则**

```python
# tests/unit/qwen3_asr/test_executor_validation.py
import pytest
from services.workers.qwen3_asr_service.executors.transcribe_executor import (
    Qwen3ASRTranscribeExecutor,
)


def test_missing_audio_path_raises(mocker):
    executor = Qwen3ASRTranscribeExecutor()
    executor.context = mocker.Mock()
    executor.stage_name = "qwen3_asr.transcribe_audio"
    executor.get_input_data = lambda: {}
    with pytest.raises(ValueError):
        executor.validate_input()
```

```python
# tests/unit/qwen3_asr/test_words_mapping.py
from services.workers.qwen3_asr_service.executors.transcribe_executor import map_words


def test_map_words_disabled():
    assert map_words(None, enable=False) == ([], 0)


def test_map_words_enabled():
    time_stamps = [
        {"text": "你好", "start": 0.0, "end": 0.5},
        {"text": "世界", "start": 0.5, "end": 1.0},
    ]
    words, total = map_words(time_stamps, enable=True)
    assert total == 2
    assert words[0]["word"] == "你好"
    assert words[0]["start"] == 0.0
    assert words[0]["end"] == 0.5
    assert words[0]["probability"] is None
```

**Step 2: 运行测试验证失败**

Run (容器内):

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/qwen3_asr/test_executor_validation.py -v
pytest /app/tests/unit/qwen3_asr/test_words_mapping.py -v
```

Expected: FAIL (Qwen3ASRTranscribeExecutor/map_words 未完整实现)

**Step 3: 最小实现核心校验与 words 映射**

```python
# services/workers/qwen3_asr_service/executors/transcribe_executor.py
from typing import Any, Dict, List


def map_words(time_stamps: List[Dict[str, Any]] | None, enable: bool) -> tuple[list, int]:
    if not enable:
        return [], 0
    if not time_stamps:
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
```

**Step 4: 运行测试验证通过**

Run (容器内):

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/qwen3_asr/test_executor_validation.py -v
pytest /app/tests/unit/qwen3_asr/test_words_mapping.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add services/workers/qwen3_asr_service/executors/transcribe_executor.py \
  tests/unit/qwen3_asr/test_executor_validation.py \
  tests/unit/qwen3_asr/test_words_mapping.py

git commit -m "feat(qwen3_asr): 增加参数校验与词级映射"
```

---

## Task 3: 推理脚本与 subprocess 调用（TDD）

**Files:**
- Modify: `services/workers/qwen3_asr_service/app/qwen3_asr_infer.py`
- Modify: `services/workers/qwen3_asr_service/app/tasks.py`
- Modify: `services/workers/qwen3_asr_service/executors/transcribe_executor.py`
- Create: `tests/unit/qwen3_asr/test_subprocess_invocation.py`

**Step 1: 编写失败测试 - subprocess 调用参数**

```python
# tests/unit/qwen3_asr/test_subprocess_invocation.py
import json
from pathlib import Path
from services.workers.qwen3_asr_service.executors.transcribe_executor import build_infer_command


def test_build_infer_command(tmp_path):
    out = tmp_path / "out.json"
    cmd = build_infer_command(
        audio_path="/tmp/a.wav",
        output_file=str(out),
        model_name="Qwen/Qwen3-ASR-0.6B",
        backend="vllm",
        language="Chinese",
        enable_word_timestamps=True,
        forced_aligner_model="Qwen/Qwen3-ForcedAligner-0.6B",
    )
    cmd_str = " ".join(cmd)
    assert "--audio_path" in cmd_str
    assert "--backend" in cmd_str
    assert "vllm" in cmd_str
    assert "--language" in cmd_str
```

**Step 2: 运行测试验证失败**

Run (容器内):

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/qwen3_asr/test_subprocess_invocation.py -v
```

Expected: FAIL (build_infer_command 未实现)

**Step 3: 最小实现 subprocess 命令构建**

```python
# services/workers/qwen3_asr_service/executors/transcribe_executor.py
import sys
from pathlib import Path


def build_infer_command(
    audio_path: str,
    output_file: str,
    model_name: str,
    backend: str,
    language: str | None,
    enable_word_timestamps: bool,
    forced_aligner_model: str | None,
) -> list[str]:
    infer_script = Path(__file__).resolve().parents[1] / "app" / "qwen3_asr_infer.py"
    cmd = [
        sys.executable,
        str(infer_script),
        "--audio_path", audio_path,
        "--output_file", output_file,
        "--model_name", model_name,
        "--backend", backend,
    ]
    if language:
        cmd += ["--language", language]
    if enable_word_timestamps:
        cmd += ["--enable_word_timestamps"]
    if forced_aligner_model:
        cmd += ["--forced_aligner_model", forced_aligner_model]
    return cmd
```

**Step 4: 运行测试验证通过**

Run (容器内):

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/qwen3_asr/test_subprocess_invocation.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add services/workers/qwen3_asr_service/executors/transcribe_executor.py tests/unit/qwen3_asr/test_subprocess_invocation.py

git commit -m "feat(qwen3_asr): 添加推理脚本命令构建"
```

---

## Task 4: Executor 完整实现与输出落盘（TDD）

**Files:**
- Modify: `services/workers/qwen3_asr_service/executors/transcribe_executor.py`
- Create: `tests/unit/qwen3_asr/test_executor_output.py`

**Step 1: 编写失败测试 - 输出结构对齐**

```python
# tests/unit/qwen3_asr/test_executor_output.py
import json
from pathlib import Path
from services.workers.qwen3_asr_service.executors.transcribe_executor import build_transcribe_json


def test_build_transcribe_json_structure(tmp_path):
    segments = [
        {"id": 0, "start": 0.0, "end": 1.0, "text": "你好", "words": []}
    ]
    payload = build_transcribe_json(
        stage_name="qwen3_asr.transcribe_audio",
        workflow_id="workflow-123",
        audio_file_name="demo.wav",
        segments=segments,
        audio_duration=1.0,
        language="zh",
        model_name="Qwen/Qwen3-ASR-0.6B",
        device="cuda",
        enable_word_timestamps=False,
        transcribe_duration=0.5,
    )
    assert "metadata" in payload
    assert "segments" in payload
    assert "statistics" in payload
```

**Step 2: 运行测试验证失败**

Run (容器内):

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/qwen3_asr/test_executor_output.py -v
```

Expected: FAIL (build_transcribe_json 未实现)

**Step 3: 最小实现输出构造函数**

```python
# services/workers/qwen3_asr_service/executors/transcribe_executor.py
import time
from typing import Any, Dict, List


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
) -> Dict[str, Any]:
    total_segments = len(segments)
    total_words = sum(len(seg.get("words", [])) for seg in segments)
    avg_duration = 0
    if total_segments > 0:
        avg_duration = sum(seg.get("end", 0) - seg.get("start", 0) for seg in segments) / total_segments
    return {
        "metadata": {
            "task_name": stage_name,
            "workflow_id": workflow_id,
            "audio_file": audio_file_name,
            "total_duration": audio_duration,
            "language": language,
            "word_timestamps_enabled": enable_word_timestamps,
            "model_name": model_name,
            "device": device,
            "transcribe_method": "qwen3-asr-subprocess",
            "created_at": time.time(),
        },
        "segments": segments,
        "statistics": {
            "total_segments": total_segments,
            "total_words": total_words,
            "transcribe_duration": transcribe_duration,
            "average_segment_duration": avg_duration,
        },
    }
```

**Step 4: 运行测试验证通过**

Run (容器内):

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/qwen3_asr/test_executor_output.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add services/workers/qwen3_asr_service/executors/transcribe_executor.py tests/unit/qwen3_asr/test_executor_output.py

git commit -m "feat(qwen3_asr): 输出结构与 faster_whisper 对齐"
```

---

## Task 5: 推理脚本实现（TDD）

**Files:**
- Modify: `services/workers/qwen3_asr_service/app/qwen3_asr_infer.py`
- Create: `tests/unit/qwen3_asr/test_infer_payload.py`

**Step 1: 编写失败测试 - 推理输出 JSON 结构**

```python
# tests/unit/qwen3_asr/test_infer_payload.py
import json
from services.workers.qwen3_asr_service.app import qwen3_asr_infer


def test_build_infer_payload_structure():
    payload = qwen3_asr_infer.build_infer_payload(
        text="hello",
        language="English",
        time_stamps=None,
        audio_duration=1.0,
        transcribe_duration=0.5,
    )
    assert "text" in payload
    assert "language" in payload
    assert "time_stamps" in payload
    assert "audio_duration" in payload
    assert "transcribe_duration" in payload
```

**Step 2: 运行测试验证失败**

Run (容器内):

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/qwen3_asr/test_infer_payload.py -v
```

Expected: FAIL (build_infer_payload 未实现)

**Step 3: 实现推理脚本与 payload 构建**

```python
# services/workers/qwen3_asr_service/app/qwen3_asr_infer.py
import argparse
import json
import os
import time
import soundfile as sf
from qwen_asr import Qwen3ASRModel


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio_path", required=True)
    parser.add_argument("--output_file", required=True)
    parser.add_argument("--model_name", required=True)
    parser.add_argument("--backend", required=True, choices=["vllm", "transformers"])
    parser.add_argument("--language", default=None)
    parser.add_argument("--enable_word_timestamps", action="store_true")
    parser.add_argument("--forced_aligner_model", default=None)
    return parser.parse_args()


def build_infer_payload(text, language, time_stamps, audio_duration, transcribe_duration):
    return {
        "text": text,
        "language": language,
        "time_stamps": time_stamps,
        "audio_duration": audio_duration,
        "transcribe_duration": transcribe_duration,
    }


def main():
    args = parse_args()
    start = time.time()
    audio, sr = sf.read(args.audio_path)
    cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if cuda_visible:
        print(f"CUDA_VISIBLE_DEVICES={cuda_visible}")

    if args.backend == "vllm":
        model = Qwen3ASRModel.LLM(
            model=args.model_name,
            forced_aligner=args.forced_aligner_model if args.enable_word_timestamps else None,
        )
    else:
        model = Qwen3ASRModel.from_pretrained(
            args.model_name,
            forced_aligner=args.forced_aligner_model if args.enable_word_timestamps else None,
        )

    results = model.transcribe(
        audio=(audio, sr),
        language=args.language,
        return_time_stamps=args.enable_word_timestamps,
    )

    item = results[0]
    payload = build_infer_payload(
        text=item.text,
        language=item.language,
        time_stamps=getattr(item, "time_stamps", None),
        audio_duration=getattr(item, "duration", None),
        transcribe_duration=time.time() - start,
    )

    with open(args.output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
```

补充说明：
- vLLM 使用默认显存策略；显卡选择依赖 `CUDA_VISIBLE_DEVICES` 环境变量（已打印日志便于排查）。

**Step 4: 运行测试验证通过**

Run (容器内):

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/qwen3_asr/test_infer_payload.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add services/workers/qwen3_asr_service/app/qwen3_asr_infer.py tests/unit/qwen3_asr/test_infer_payload.py

git commit -m "feat(qwen3_asr): 完成推理脚本与输出构建"
```

---

## Task 6: Celery 入口与执行器集成（TDD）

**Files:**
- Modify: `services/workers/qwen3_asr_service/executors/transcribe_executor.py`
- Modify: `services/workers/qwen3_asr_service/app/celery_app.py`
- Modify: `services/workers/qwen3_asr_service/app/tasks.py`
- Create: `tests/unit/qwen3_asr/test_executor_pipeline.py`

**Step 1: 编写失败测试 - 执行器管线**

```python
# tests/unit/qwen3_asr/test_executor_pipeline.py
import json
from pathlib import Path
import pytest
from services.workers.qwen3_asr_service.executors.transcribe_executor import (
    Qwen3ASRTranscribeExecutor,
)


def test_executor_parses_subprocess_output(mocker, tmp_path):
    executor = Qwen3ASRTranscribeExecutor()
    executor.context = mocker.Mock()
    executor.context.workflow_id = "workflow-123"
    executor.context.shared_storage_path = "/share/workflows/workflow-123"
    executor.stage_name = "qwen3_asr.transcribe_audio"
    executor.get_input_data = lambda: {"audio_path": "/tmp/demo.wav"}

    mocker.patch("services.workers.qwen3_asr_service.executors.transcribe_executor.get_file_service").return_value.resolve_and_download.return_value = "/tmp/demo.wav"
    mocker.patch("services.workers.qwen3_asr_service.executors.transcribe_executor.os.path.exists", return_value=True)
    mocker.patch("services.workers.qwen3_asr_service.executors.transcribe_executor.build_node_output_path", return_value=str(tmp_path / "out.json"))
    mocker.patch("services.workers.qwen3_asr_service.executors.transcribe_executor.ensure_directory")

    fake_output = tmp_path / "infer.json"
    fake_output.write_text(json.dumps({
        "text": "hello",
        "language": "English",
        "time_stamps": [
            {"text": "hello", "start": 0.0, "end": 0.5},
        ],
        "audio_duration": 1.0,
        "transcribe_duration": 0.5,
    }), encoding="utf-8")

    mocker.patch("services.workers.qwen3_asr_service.executors.transcribe_executor.run_gpu_command").return_value.returncode = 0
    mocker.patch("services.workers.qwen3_asr_service.executors.transcribe_executor._read_infer_output", return_value=json.loads(fake_output.read_text()))

    result = executor.execute_core_logic()
    assert "segments_file" in result
    assert result["segments_count"] >= 1
```

**Step 2: 运行测试验证失败**

Run (容器内):

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/qwen3_asr/test_executor_pipeline.py -v
```

Expected: FAIL (execute_core_logic 未实现完整管线)

**Step 3: 实现 Celery 应用与任务入口**

```python
# services/workers/qwen3_asr_service/app/celery_app.py
from celery import Celery

celery_app = Celery(
    'qwen3_asr_tasks',
    broker='redis://redis:6379/0',
    backend='redis://redis:6379/0',
    include=['services.workers.qwen3_asr_service.app.tasks'],
)
```

```python
# services/workers/qwen3_asr_service/app/tasks.py
from services.workers.qwen3_asr_service.app.celery_app import celery_app
from services.workers.qwen3_asr_service.executors.transcribe_executor import Qwen3ASRTranscribeExecutor


@celery_app.task(bind=True, name='qwen3_asr.transcribe_audio')
def transcribe_audio(self, context: dict) -> dict:
    executor = Qwen3ASRTranscribeExecutor()
    return executor.execute(self, context)
```

**Step 4: 实现 subprocess 调用与输出写入**

```python
# services/workers/qwen3_asr_service/executors/transcribe_executor.py
import os
import json
import time
from pathlib import Path
from typing import Any, Dict, List
from services.common.base_node_executor import BaseNodeExecutor
from services.common.config_loader import CONFIG
from services.common.file_service import get_file_service
from services.common.locks import gpu_lock
from services.common.path_builder import build_node_output_path, ensure_directory
from services.common.subprocess_utils import run_gpu_command


def _read_infer_output(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise RuntimeError(f"推理输出不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# 分段策略：参考 faster_whisper.transcribe_audio 的输出语义
# - 有 time_stamps：按连续时间戳组装 segments，start/end 取首尾词时间，id 递增
# - 无 time_stamps：退化为单段覆盖全音频（与 faster_whisper 至少输出一个 segment 的行为一致）
def _build_segments(text: str, time_stamps: List[Dict[str, Any]] | None, audio_duration: float, enable_words: bool):
    words, _ = map_words(time_stamps, enable=enable_words)
    if words:
        start = words[0].get("start", 0.0)
        end = words[-1].get("end", audio_duration)
    else:
        start = 0.0
        end = audio_duration
    segment = {
        "id": 0,
        "start": start,
        "end": end,
        "text": text or "",
    }
    if enable_words:
        segment["words"] = words
    return [segment]


def _run_infer(cmd: list[str], stage_name: str, cwd: str) -> Dict[str, Any]:
    result = run_gpu_command(cmd, stage_name=stage_name, timeout=1800, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"subprocess 失败: {result.stderr}")
    return _read_infer_output(cmd[cmd.index("--output_file") + 1])


@gpu_lock()
def _run_infer_with_gpu_lock(cmd: list[str], stage_name: str, cwd: str) -> Dict[str, Any]:
    return _run_infer(cmd, stage_name, cwd)


class Qwen3ASRTranscribeExecutor(BaseNodeExecutor):
    def validate_input(self) -> None:
        input_data = self.get_input_data()
        if not input_data.get("audio_path"):
            raise ValueError("缺少必需参数: audio_path")

    def execute_core_logic(self) -> Dict[str, Any]:
        input_data = self.get_input_data()
        audio_path = input_data["audio_path"]

        file_service = get_file_service()
        audio_path = file_service.resolve_and_download(audio_path, self.context.shared_storage_path)
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        service_config = CONFIG.get("qwen3_asr_service", {})
        backend = input_data.get("backend", service_config.get("backend", "vllm"))
        model_size = input_data.get("model_size", service_config.get("model_size", "0.6B"))
        language = map_language(input_data.get("language", service_config.get("language")))
        enable_word_timestamps = input_data.get(
            "enable_word_timestamps", service_config.get("enable_word_timestamps", True)
        )
        forced_aligner_model = input_data.get(
            "forced_aligner_model",
            service_config.get("forced_aligner_model", "Qwen/Qwen3-ForcedAligner-0.6B"),
        )
        device = input_data.get("device", service_config.get("device", "cuda"))

        if device == "cpu" and backend == "vllm":
            raise ValueError("CPU 模式不支持 vllm 后端")
        if device == "cpu" and "backend" not in input_data:
            backend = "transformers"

        task_id = self.context.workflow_id
        tmp_dir = f"/share/workflows/{task_id}/tmp"
        os.makedirs(tmp_dir, exist_ok=True)
        output_file = Path(tmp_dir) / f"qwen3_asr_result_{int(time.time() * 1000)}.json"

        model_name = f"Qwen/Qwen3-ASR-{model_size}"
        cmd = build_infer_command(
            audio_path=audio_path,
            output_file=str(output_file),
            model_name=model_name,
            backend=backend,
            language=language,
            enable_word_timestamps=enable_word_timestamps,
            forced_aligner_model=forced_aligner_model if enable_word_timestamps else None,
        )

        payload = _run_infer_with_gpu_lock(cmd, self.stage_name, str(Path(__file__).parent)) if device != "cpu" else _run_infer(cmd, self.stage_name, str(Path(__file__).parent))

        segments = _build_segments(
            text=payload.get("text", ""),
            time_stamps=payload.get("time_stamps"),
            audio_duration=payload.get("audio_duration") or 0,
            enable_words=enable_word_timestamps,
        )

        transcribe_data = build_transcribe_json(
            stage_name=self.stage_name,
            workflow_id=self.context.workflow_id,
            audio_file_name=os.path.basename(audio_path),
            segments=segments,
            audio_duration=payload.get("audio_duration") or 0,
            language=payload.get("language") or (language or "unknown"),
            model_name=model_name,
            device=device,
            enable_word_timestamps=enable_word_timestamps,
            transcribe_duration=payload.get("transcribe_duration") or 0,
        )

        workflow_short_id = self.context.workflow_id[:8]
        segments_file = build_node_output_path(
            task_id=self.context.workflow_id,
            node_name=self.stage_name,
            file_type="data",
            filename=f"transcribe_data_{workflow_short_id}.json",
        )
        ensure_directory(segments_file)
        with open(segments_file, "w", encoding="utf-8") as f:
            json.dump(transcribe_data, f, ensure_ascii=False, indent=2)

        return {
            "segments_file": segments_file,
            "audio_duration": payload.get("audio_duration") or 0,
            "language": payload.get("language") or (language or "unknown"),
            "model_name": model_name,
            "device": device,
            "enable_word_timestamps": enable_word_timestamps,
            "statistics": transcribe_data["statistics"],
            "segments_count": len(segments),
        }
```

**Step 5: 运行测试验证通过**

Run (容器内):

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/qwen3_asr/test_executor_pipeline.py -v
```

Expected: PASS

**Step 6: Commit**

```bash
git add services/workers/qwen3_asr_service/app/celery_app.py \\
  services/workers/qwen3_asr_service/app/tasks.py \\
  services/workers/qwen3_asr_service/executors/transcribe_executor.py \\
  tests/unit/qwen3_asr/test_executor_pipeline.py

git commit -m "feat(qwen3_asr): 实现 executor 主流程"
```

---

## Task 6b: 缓存键与复用判定（TDD）

**Files:**
- Modify: `services/workers/qwen3_asr_service/executors/transcribe_executor.py`
- Create: `tests/unit/qwen3_asr/test_cache_keys.py`

**Step 1: 编写失败测试 - 缓存键与必需输出**

```python
# tests/unit/qwen3_asr/test_cache_keys.py
from services.workers.qwen3_asr_service.executors.transcribe_executor import (
    Qwen3ASRTranscribeExecutor,
)


def test_cache_key_fields():
    executor = Qwen3ASRTranscribeExecutor()
    fields = executor.get_cache_key_fields()
    assert fields == [
        "audio_path",
        "backend",
        "model_size",
        "language",
        "enable_word_timestamps",
    ]


def test_required_output_fields():
    executor = Qwen3ASRTranscribeExecutor()
    assert executor.get_required_output_fields() == ["segments_file"]
```

**Step 2: 运行测试验证失败**

Run (容器内):

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/qwen3_asr/test_cache_keys.py -v
```

Expected: FAIL (get_cache_key_fields/get_required_output_fields 未实现)

**Step 3: 实现缓存键与必需输出字段**

```python
# services/workers/qwen3_asr_service/executors/transcribe_executor.py
def get_cache_key_fields(self):
    return [
        "audio_path",
        "backend",
        "model_size",
        "language",
        "enable_word_timestamps",
    ]


def get_required_output_fields(self):
    return ["segments_file"]
```

**Step 4: 运行测试验证通过**

Run (容器内):

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/qwen3_asr/test_cache_keys.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add services/workers/qwen3_asr_service/executors/transcribe_executor.py tests/unit/qwen3_asr/test_cache_keys.py

git commit -m "feat(qwen3_asr): 补充缓存键与必需输出"
```

---

## Task 7: 配置与 API 接入

**Files:**
- Modify: `config.yml`
- Modify: `services/api_gateway/app/single_task_api.py`
- Modify: `services/api_gateway/app/single_task_executor.py`
- Modify: `docker-compose.yml`
- Modify: `services/api_gateway/app/monitoring/prometheus_config.py` (可选)

**Step 1: 添加配置块**

```yaml
# config.yml
qwen3_asr_service:
  device: cuda
  backend: vllm
  model_size: "0.6B"
  enable_word_timestamps: true
  forced_aligner_model: "Qwen/Qwen3-ForcedAligner-0.6B"
```

**Step 2: 注册单任务节点**

```python
# services/api_gateway/app/single_task_api.py
SUPPORTED_SINGLE_TASKS = {
    "qwen3_asr": [
        "qwen3_asr.transcribe_audio",
    ],
}
```

```python
# services/api_gateway/app/single_task_executor.py
SINGLE_TASK_EXECUTORS = {
    "qwen3_asr": "qwen3_asr_queue",
}
```

**Step 3: docker-compose 增加服务**

```yaml
qwen3_asr_service:
  build:
    context: .
    dockerfile: services/workers/qwen3_asr_service/Dockerfile
  container_name: yivideo-qwen3-asr
  environment:
    <<: *common-env
    CELERY_WORKER_NAME: qwen3_asr_worker
    HF_TOKEN: ${HF_TOKEN}
  volumes:
    - ./services/workers/qwen3_asr_service:/app/services/workers/qwen3_asr_service
    - ./services/common:/app/services/common
    - share_data:/share
    - model_cache:/root/.cache
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
  networks:
    - yivideo-network
  depends_on:
    - redis
    - minio
  command: >
    celery -A app.celery_app worker
    --loglevel=info
    --concurrency=1
    --queues=qwen3_asr_queue
    -n qwen3_asr_worker@%h
```

**Step 4: Commit**

```bash
git add config.yml services/api_gateway/app/single_task_api.py \
  services/api_gateway/app/single_task_executor.py docker-compose.yml

git commit -m "feat(qwen3_asr): 接入配置与路由"
```

---

## Task 8: 更新 API 文档与参考

**Files:**
- Modify: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`

**Step 1: 增加 qwen3_asr.transcribe_audio 章节**

- 描述功能、输入参数、输出示例（结构与 faster_whisper 对齐）
- 说明 `audio_path` 必填且不回退
- 说明 `backend`、`model_size`、`language`、`enable_word_timestamps`、`forced_aligner_model`
- 标记复用规则与 `segments_file_minio_url` 行为

**Step 2: Commit**

```bash
git add docs/technical/reference/SINGLE_TASK_API_REFERENCE.md

git commit -m "docs(qwen3_asr): 增加单任务 API 参考"
```

---

## Task 9: 容器内集成验证

**Step 1: 启动服务**

```bash
docker compose build qwen3_asr_service
docker compose up -d qwen3_asr_service
```

**Step 2: 容器内跑单测**

```bash
docker exec -it <container_name> bash
pytest /app/tests/unit/qwen3_asr -v
```

Expected: 全部 PASS

**Step 3: 提交最小任务验证**

- 使用 Single Task API 提交任务
- 验证 `backend=vllm` 且 `enable_word_timestamps=true` 的主路径
- 验证 `segments_file` 结构、`words` 字段、MinIO 追加字段

**Step 4: 记录验证结论**

- 若未运行集成测试，说明原因

---

## 说明
- 所有 pytest 与调试必须在容器内执行（仓库约束）。
- 词级时间戳输出遵循 `words` 兼容结构，`probability` 为空。
- CPU 环境默认回退 `transformers`，显式 `vllm` 则报错。
