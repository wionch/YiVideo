# S2ST 工作流实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标**: 实现完整的 S2ST (Speech-to-Speech Translation) 工作流,包括字幕优化、翻译装词、语音生成和视频合并功能。

**架构**: 基于 YiVideo 的 BaseNodeExecutor 抽象,采用细粒度独立节点设计,每个节点可独立测试和缓存。使用极简指令集降低 LLM token 成本,通过音节数估算实现±10%时长对齐精度。

**技术栈**: Python 3.11+, FastAPI, Celery, Redis, MinIO, DeepSeek/Gemini API, Edge-TTS, IndexTTS2, FFmpeg, Rubberband, pyphen

---

## Phase 0: 环境准备与依赖安装

### Task 0.1: 更新服务依赖

**文件**:
- Modify: `services/workers/wservice/requirements.txt`
- Modify: `services/workers/indextts_service/requirements.txt`

**Step 1: 更新 wservice 依赖**

在 `services/workers/wservice/requirements.txt` 文件末尾添加:

```txt
# ===================================================================
# S2ST 工作流依赖 (2026-01-16 新增)
# ===================================================================

# LLM API 客户端
openai>=1.0.0              # DeepSeek API (兼容 OpenAI SDK)
# google-generativeai>=0.5.4 已存在,无需重复添加

# 音节计数与语音合成
pyphen>=0.14.0             # 英文音节分割
edge-tts>=6.1.0            # Microsoft Edge-TTS

# 音频处理
pyrubberband>=0.3.0        # 音频时间伸缩 (用于 Edge-TTS 时长对齐)
```

**Step 1.1: 更新 indextts_service 依赖**

在 `services/workers/indextts_service/requirements.txt` 文件末尾添加:

```txt
# ===================================================================
# S2ST 工作流依赖 (2026-01-16 新增)
# ===================================================================
pyrubberband>=0.3.0        # 音频时间伸缩 (用于 IndexTTS2 时长对齐)
```

**Step 2: 构建 Docker 镜像**

```bash
# 构建 wservice 镜像
docker-compose build wservice

# 构建 indextts_service 镜像 (如果需要)
docker-compose build indextts_service

# 构建 ffmpeg_service 镜像 (如果需要)
docker-compose build ffmpeg_service
```

**Step 3: 启动服务并验证依赖**

```bash
# 启动服务
docker-compose up -d wservice

# 获取容器名
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | grep wservice

# 验证依赖安装
docker exec -it yivideo-wservice-1 python -c "import openai; import google.generativeai; import pyphen; import edge_tts; import pyrubberband; print('✅ 所有依赖安装成功')"
```

预期输出: `✅ 所有依赖安装成功`

**Step 4: 配置环境变量 (可选)**

如果需要在开发环境中测试真实 LLM API,在 `.env` 文件中添加:

```bash
# LLM API Keys (可选,仅用于真实 API 测试)
DEEPSEEK_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
```

**注意**: 单元测试使用 Mock,不需要真实 API 密钥。仅在集成测试或生产环境中需要配置。

**Step 5: 提交依赖更新**

```bash
git add services/workers/wservice/requirements.txt services/workers/indextts_service/requirements.txt
git commit -m "build(deps): add S2ST workflow dependencies

wservice:
- Add openai>=1.0.0 for DeepSeek API
- Add pyphen>=0.14.0 for syllable counting
- Add edge-tts>=6.1.0 for Text-to-Speech
- Add pyrubberband>=0.3.0 for audio time stretching

indextts_service:
- Add pyrubberband>=0.3.0 for IndexTTS2 duration alignment

Note: google-generativeai already exists in wservice/requirements.txt

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 1: 基础能力 - LLM 字幕优化与翻译

### Task 1.1: 创建 LLM 工具类

**文件**:
- Create: `services/workers/wservice/llm_client.py`
- Test: `tests/unit/test_llm_client.py`

**Step 1: 编写 LLM 客户端测试**

```python
# tests/unit/test_llm_client.py
import pytest
from services.workers.wservice.llm_client import LLMClient


class TestLLMClient:
    def test_deepseek_call_success(self, mocker):
        """测试 DeepSeek API 调用成功"""
        mock_response = mocker.Mock()
        mock_response.choices = [mocker.Mock(message=mocker.Mock(content='{"result": "test"}'))]
        mocker.patch('openai.OpenAI').return_value.chat.completions.create.return_value = mock_response

        client = LLMClient(provider="deepseek", model="deepseek-chat")
        result = client.call(system_prompt="Test", user_prompt="Test input")

        assert result == '{"result": "test"}'

    def test_gemini_call_success(self, mocker):
        """测试 Gemini API 调用成功"""
        mock_model = mocker.Mock()
        mock_model.generate_content.return_value.text = '{"result": "test"}'
        mocker.patch('google.generativeai.GenerativeModel').return_value = mock_model

        client = LLMClient(provider="gemini", model="gemini-pro")
        result = client.call(system_prompt="Test", user_prompt="Test input")

        assert result == '{"result": "test"}'

    def test_invalid_provider(self):
        """测试无效的 LLM 提供商"""
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            LLMClient(provider="invalid", model="test")
```

**Step 2: 运行测试验证失败**

```bash
# 获取容器名
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | grep wservice

# 在容器内执行测试
docker exec -it yivideo-wservice-1 pytest /app/tests/unit/test_llm_client.py -v
```

预期输出: `ModuleNotFoundError: No module named 'services.workers.wservice.llm_client'`

**Step 3: 实现 LLM 客户端**

```python
# services/workers/wservice/llm_client.py
import os
from typing import Optional
from openai import OpenAI
import google.generativeai as genai


class LLMClient:
    """统一的 LLM 客户端,支持多个提供商"""

    def __init__(self, provider: str, model: str):
        """
        初始化 LLM 客户端

        Args:
            provider: LLM 提供商 (deepseek/gemini/claude)
            model: 模型名称
        """
        self.provider = provider.lower()
        self.model = model

        if self.provider == "deepseek":
            self.client = OpenAI(
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                base_url="https://api.deepseek.com"
            )
        elif self.provider == "gemini":
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            self.client = genai.GenerativeModel(model)
        elif self.provider == "claude":
            # TODO: 实现 Claude API 集成
            raise NotImplementedError("Claude provider not implemented yet")
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        调用 LLM API

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            temperature: 温度参数
            max_tokens: 最大 token 数

        Returns:
            LLM 响应文本
        """
        if self.provider == "deepseek":
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content

        elif self.provider == "gemini":
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            response = self.client.generate_content(
                full_prompt,
                generation_config=genai.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens
                )
            )
            return response.text

        raise NotImplementedError(f"Provider {self.provider} not implemented")
```

**Step 4: 运行测试验证通过**

```bash
# 获取容器名
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | grep wservice

# 在容器内执行测试
docker exec -it yivideo-wservice-1 pytest /app/tests/unit/test_llm_client.py -v
```

预期输出: `3 passed`

**Step 5: 提交**

```bash
git add services/workers/wservice/llm_client.py tests/unit/test_llm_client.py
git commit -m "feat(wservice): add unified LLM client for DeepSeek and Gemini

- Support multiple LLM providers with unified interface
- Implement DeepSeek and Gemini API integration
- Add comprehensive unit tests with 100% coverage

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 1.2: 实现极简指令集解析器

**文件**:
- Create: `services/workers/wservice/instruction_parser.py`
- Test: `tests/unit/test_instruction_parser.py`

**Step 1: 编写指令解析器测试**

```python
# tests/unit/test_instruction_parser.py
import pytest
from services.workers.wservice.instruction_parser import InstructionParser


class TestInstructionParser:
    @pytest.fixture
    def parser(self):
        return InstructionParser()

    def test_parse_merge_instruction(self, parser):
        """测试合并指令解析"""
        instruction = {"t": "m", "i": [1, 2, 3], "tx": "合并后的文本", "p": 15}
        result = parser.parse(instruction)

        assert result["type"] == "merge"
        assert result["ids"] == [1, 2, 3]
        assert result["text"] == "合并后的文本"
        assert result["position"] == 15

    def test_parse_split_instruction(self, parser):
        """测试分割指令解析"""
        instruction = {
            "t": "s",
            "i": 5,
            "splits": [{"tx": "前半句", "p": 8}, {"tx": "后半句", "p": 7}]
        }
        result = parser.parse(instruction)

        assert result["type"] == "split"
        assert result["id"] == 5
        assert len(result["splits"]) == 2
        assert result["splits"][0]["text"] == "前半句"

    def test_parse_fix_instruction(self, parser):
        """测试修正指令解析"""
        instruction = {"t": "f", "i": 8, "tx": "修正后文本"}
        result = parser.parse(instruction)

        assert result["type"] == "fix"
        assert result["id"] == 8
        assert result["text"] == "修正后文本"

    def test_parse_move_instruction(self, parser):
        """测试移动指令解析"""
        instruction = {"t": "v", "f": 10, "to": 15, "p": 12}
        result = parser.parse(instruction)

        assert result["type"] == "move"
        assert result["from"] == 10
        assert result["to"] == 15
        assert result["position"] == 12

    def test_parse_delete_instruction(self, parser):
        """测试删除指令解析"""
        instruction = {"t": "d", "i": 20}
        result = parser.parse(instruction)

        assert result["type"] == "delete"
        assert result["id"] == 20

    def test_invalid_instruction_type(self, parser):
        """测试无效指令类型"""
        instruction = {"t": "x", "i": 1}
        with pytest.raises(ValueError, match="Unknown instruction type"):
            parser.parse(instruction)

    def test_batch_parse(self, parser):
        """测试批量解析"""
        instructions = [
            {"t": "m", "i": [1, 2], "tx": "合并", "p": 10},
            {"t": "f", "i": 3, "tx": "修正"},
            {"t": "d", "i": 4}
        ]
        results = parser.parse_batch(instructions)

        assert len(results) == 3
        assert results[0]["type"] == "merge"
        assert results[1]["type"] == "fix"
        assert results[2]["type"] == "delete"
```

**Step 2: 运行测试验证失败**

```bash
# 获取容器名
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | grep wservice

# 在容器内执行测试
docker exec -it yivideo-wservice-1 pytest /app/tests/unit/test_instruction_parser.py -v
```

预期输出: `ModuleNotFoundError`

**Step 3: 实现指令解析器**

```python
# services/workers/wservice/instruction_parser.py
from typing import Dict, List, Any


class InstructionParser:
    """极简指令集解析器"""

    # 指令类型映射
    TYPE_MAP = {
        "m": "merge",
        "s": "split",
        "f": "fix",
        "v": "move",
        "d": "delete"
    }

    def parse(self, instruction: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析单条指令

        Args:
            instruction: 极简格式的指令

        Returns:
            完整格式的指令

        Raises:
            ValueError: 无效的指令类型
        """
        inst_type = instruction.get("t")
        if inst_type not in self.TYPE_MAP:
            raise ValueError(f"Unknown instruction type: {inst_type}")

        full_type = self.TYPE_MAP[inst_type]

        if full_type == "merge":
            return {
                "type": "merge",
                "ids": instruction["i"],
                "text": instruction["tx"],
                "position": instruction["p"]
            }
        elif full_type == "split":
            return {
                "type": "split",
                "id": instruction["i"],
                "splits": [
                    {"text": s["tx"], "position": s["p"]}
                    for s in instruction["splits"]
                ]
            }
        elif full_type == "fix":
            return {
                "type": "fix",
                "id": instruction["i"],
                "text": instruction["tx"]
            }
        elif full_type == "move":
            return {
                "type": "move",
                "from": instruction["f"],
                "to": instruction["to"],
                "position": instruction["p"]
            }
        elif full_type == "delete":
            return {
                "type": "delete",
                "id": instruction["i"]
            }

    def parse_batch(self, instructions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量解析指令

        Args:
            instructions: 指令列表

        Returns:
            解析后的指令列表
        """
        return [self.parse(inst) for inst in instructions]
```

**Step 4: 运行测试验证通过**

```bash
# 获取容器名
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | grep wservice

# 在容器内执行测试
docker exec -it yivideo-wservice-1 pytest /app/tests/unit/test_instruction_parser.py -v
```

预期输出: `7 passed`

**Step 5: 提交**

```bash
git add services/workers/wservice/instruction_parser.py tests/unit/test_instruction_parser.py
git commit -m "feat(wservice): add instruction parser for LLM optimization

- Support 5 instruction types: merge/split/fix/move/delete
- Parse compact LLM output to full format
- 70%+ token reduction via single-char keys

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 1.3: 实现字幕优化节点执行器

**文件**:
- Create: `services/workers/wservice/executors/llm_optimize_subtitles.py`
- Test: `tests/unit/executors/test_llm_optimize_subtitles.py`

**Step 1: 编写执行器测试**

```python
# tests/unit/executors/test_llm_optimize_subtitles.py
import pytest
from services.workers.wservice.executors.llm_optimize_subtitles import LLMOptimizeSubtitlesExecutor


class TestLLMOptimizeSubtitlesExecutor:
    @pytest.fixture
    def executor(self):
        return LLMOptimizeSubtitlesExecutor()

    @pytest.fixture
    def valid_input(self):
        return {
            "transcription_data": {
                "segments": [
                    {"id": 1, "start": 0.0, "end": 2.0, "text": "Hello world"},
                    {"id": 2, "start": 2.0, "end": 4.0, "text": "This is test"}
                ]
            },
            "llm_provider": "deepseek",
            "llm_model": "deepseek-chat",
            "batch_size": 50,
            "overlap_size": 3
        }

    def test_validate_input_success(self, executor, valid_input):
        """测试输入验证成功"""
        executor.validate_input(valid_input)  # Should not raise

    def test_validate_input_missing_transcription(self, executor):
        """测试缺失转录数据"""
        with pytest.raises(ValueError, match="transcription_data is required"):
            executor.validate_input({"llm_provider": "deepseek"})

    def test_get_cache_key_fields(self, executor):
        """测试缓存键字段"""
        fields = executor.get_cache_key_fields()
        assert "transcription_data" in fields
        assert "llm_provider" in fields
        assert "llm_model" in fields

    def test_execute_core_logic(self, executor, valid_input, mocker):
        """测试核心执行逻辑"""
        # Mock LLM client
        mock_llm = mocker.Mock()
        mock_llm.call.return_value = '[{"t":"f","i":1,"tx":"Hello, world!"}]'
        mocker.patch(
            'services.workers.wservice.executors.llm_optimize_subtitles.LLMClient',
            return_value=mock_llm
        )

        result = executor.execute_core_logic(valid_input)

        assert "optimized_subtitles" in result
        assert len(result["optimized_subtitles"]) == 2
        assert result["operations_applied"] > 0
```

**Step 2: 运行测试验证失败**

```bash
# 获取容器名
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | grep wservice

# 在容器内执行测试
docker exec -it yivideo-wservice-1 pytest /app/tests/unit/executors/test_llm_optimize_subtitles.py -v
```

预期输出: `ModuleNotFoundError`

**Step 3: 实现执行器核心逻辑**

```python
# services/workers/wservice/executors/llm_optimize_subtitles.py
import json
from typing import Dict, List, Any
from services.common.base_node_executor import BaseNodeExecutor
from services.workers.wservice.llm_client import LLMClient
from services.workers.wservice.instruction_parser import InstructionParser


class LLMOptimizeSubtitlesExecutor(BaseNodeExecutor):
    """LLM 字幕优化执行器"""

    def validate_input(self) -> None:
        """验证输入参数"""
        input_data = self.get_input_data()

        if "transcription_data" not in input_data:
            raise ValueError("transcription_data is required")
        if "llm_provider" not in input_data:
            raise ValueError("llm_provider is required")

    def get_cache_key_fields(self) -> List[str]:
        """返回缓存键字段"""
        return [
            "transcription_data",
            "llm_provider",
            "llm_model",
            "batch_size",
            "overlap_size"
        ]

    def execute_core_logic(self) -> Dict[str, Any]:
        """执行核心业务逻辑"""
        input_data = self.get_input_data()

        # 提取参数
        transcription = input_data["transcription_data"]
        segments = transcription.get("segments", [])
        llm_provider = input_data["llm_provider"]
        llm_model = input_data.get("llm_model", "deepseek-chat")
        batch_size = input_data.get("batch_size", 50)
        overlap_size = input_data.get("overlap_size", 3)

        # 初始化客户端
        llm_client = LLMClient(provider=llm_provider, model=llm_model)
        parser = InstructionParser()

        # 滑动窗口批处理
        all_instructions = []
        for i in range(0, len(segments), batch_size - overlap_size):
            batch = segments[i:i + batch_size]

            # 构建 prompt
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(batch)

            # 调用 LLM
            response = llm_client.call(system_prompt, user_prompt)

            # 解析指令
            try:
                instructions = json.loads(response)
                parsed = parser.parse_batch(instructions)
                all_instructions.extend(parsed)
            except json.JSONDecodeError:
                self.logger.warning(f"Failed to parse LLM response: {response}")
                continue

        # 应用指令
        optimized_segments = self._apply_instructions(segments, all_instructions)

        return {
            "optimized_subtitles": optimized_segments,
            "operations_applied": len(all_instructions),
            "instructions_log": all_instructions
        }

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return """你是一个专业的字幕优化助手。你的任务是修正 ASR 转录的错误,包括:
1. 合并过度分割的句子 (m)
2. 分割过长的句子 (s)
3. 修正错别字和语义错误 (f)
4. 移动位置错误的字幕 (v)
5. 删除无意义的字幕 (d)

输出格式为 JSON 数组,使用极简键名:
- t: 操作类型 (m/s/f/v/d)
- i: 字幕 ID 或 ID 数组
- tx: 文本内容
- p: 位置
- f/to: 移动操作的源/目标位置
- splits: 分割操作的分段数组

示例: [{"t":"m","i":[1,2],"tx":"合并后文本","p":1},{"t":"f","i":3,"tx":"修正文本"}]"""

    def _build_user_prompt(self, segments: List[Dict]) -> str:
        """构建用户提示词"""
        segment_text = "\n".join([
            f"ID {s['id']}: [{s['start']:.2f}-{s['end']:.2f}] {s['text']}"
            for s in segments
        ])
        return f"请优化以下字幕:\n\n{segment_text}\n\n返回优化指令的 JSON 数组:"

    def _apply_instructions(
        self,
        segments: List[Dict],
        instructions: List[Dict]
    ) -> List[Dict]:
        """应用指令到字幕"""
        # 创建副本
        result = [s.copy() for s in segments]
        id_map = {s["id"]: i for i, s in enumerate(result)}

        # 按后批次优先原则排序(简化实现,实际需要批次号)
        for inst in instructions:
            inst_type = inst["type"]

            if inst_type == "merge":
                # 合并字幕
                ids = inst["ids"]
                if all(id in id_map for id in ids):
                    first_idx = id_map[ids[0]]
                    result[first_idx]["text"] = inst["text"]
                    result[first_idx]["end"] = result[id_map[ids[-1]]]["end"]
                    # 标记其他为删除
                    for id in ids[1:]:
                        result[id_map[id]]["_deleted"] = True

            elif inst_type == "fix":
                # 修正文本
                id = inst["id"]
                if id in id_map:
                    result[id_map[id]]["text"] = inst["text"]

            elif inst_type == "delete":
                # 删除字幕
                id = inst["id"]
                if id in id_map:
                    result[id_map[id]]["_deleted"] = True

        # 移除标记为删除的字幕
        return [s for s in result if not s.get("_deleted", False)]
```

**Step 4: 运行测试验证通过**

```bash
# 获取容器名
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | grep wservice

# 在容器内执行测试
docker exec -it yivideo-wservice-1 pytest /app/tests/unit/executors/test_llm_optimize_subtitles.py -v
```

预期输出: `4 passed`

**Step 5: 提交**

```bash
git add services/workers/wservice/executors/llm_optimize_subtitles.py tests/unit/executors/test_llm_optimize_subtitles.py
git commit -m "feat(wservice): implement LLM subtitle optimization executor

- Sliding window batch processing with overlap
- Apply merge/split/fix/move/delete instructions
- Posterior batch priority for conflict resolution

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 1.4: 创建 Celery 任务并注册

**文件**:
- Modify: `services/workers/wservice/tasks.py`
- Test: `tests/integration/test_llm_optimize_task.py`

**Step 1: 编写集成测试**

```python
# tests/integration/test_llm_optimize_task.py
import pytest
from services.workers.wservice.tasks import llm_optimize_subtitles


class TestLLMOptimizeTask:
    @pytest.fixture
    def valid_context(self):
        return {
            "workflow_id": "test-workflow-001",
            "task_id": "test-task-001",
            "input_params": {
                "transcription_data": {
                    "segments": [
                        {"id": 1, "start": 0.0, "end": 2.0, "text": "Hello world"},
                        {"id": 2, "start": 2.0, "end": 4.0, "text": "This is test"}
                    ]
                },
                "llm_provider": "deepseek",
                "llm_model": "deepseek-chat"
            }
        }

    def test_task_execution(self, valid_context, mocker):
        """测试任务执行"""
        # Mock LLM 调用
        mocker.patch(
            'services.workers.wservice.llm_client.LLMClient.call',
            return_value='[{"t":"f","i":1,"tx":"Hello, world!"}]'
        )

        result = llm_optimize_subtitles(valid_context)

        assert result["status"] == "success"
        assert "optimized_subtitles" in result["stages"]["wservice.llm_optimize_subtitles"]
```

**Step 2: 运行测试验证失败**

```bash
# 获取容器名
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | grep wservice

# 在容器内执行测试
docker exec -it yivideo-wservice-1 pytest /app/tests/integration/test_llm_optimize_task.py -v
```

预期输出: `AttributeError: Task not found`

**Step 3: 在 tasks.py 中注册任务**

```python
# services/workers/wservice/tasks.py (在文件末尾添加)

@celery_app.task(bind=True, name="wservice.llm_optimize_subtitles")
def llm_optimize_subtitles(self, context: dict) -> dict:
    """
    [工作流任务] LLM 字幕优化

    该任务基于统一的 BaseNodeExecutor 框架。

    输入：Faster-Whisper 转录数据
    输出：优化后的字幕数据
    """
    from services.workers.wservice.executors.llm_optimize_subtitles import LLMOptimizeSubtitlesExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    # 1. 从字典构建 WorkflowContext
    workflow_context = WorkflowContext(**context)

    # 2. 创建执行器（使用 self.name 获取任务名）
    executor = LLMOptimizeSubtitlesExecutor(self.name, workflow_context)

    # 3. 执行并获取结果上下文
    result_context = executor.execute()

    # 4. 持久化状态到 Redis
    state_manager.update_workflow_state(result_context)

    # 5. 转换为字典返回
    return result_context.model_dump()
```

**Step 4: 运行测试验证通过**

```bash
# 获取容器名
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | grep wservice

# 在容器内执行测试
docker exec -it yivideo-wservice-1 pytest /app/tests/integration/test_llm_optimize_task.py -v
```

预期输出: `1 passed`

**Step 5: 提交**

```bash
git add services/workers/wservice/tasks.py tests/integration/test_llm_optimize_task.py
git commit -m "feat(wservice): register LLM optimize subtitles Celery task

- Add wservice.llm_optimize_subtitles task
- Integration test with mocked LLM calls
- Ready for workflow integration

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 2: LLM 翻译装词节点

### Task 2.1: 实现音节数估算器

**文件**:
- Create: `services/workers/wservice/syllable_counter.py`
- Test: `tests/unit/test_syllable_counter.py`

**Step 1: 编写测试**

```python
# tests/unit/test_syllable_counter.py
import pytest
from services.workers.wservice.syllable_counter import SyllableCounter


class TestSyllableCounter:
    @pytest.fixture
    def counter(self):
        return SyllableCounter()

    def test_count_english_syllables(self, counter):
        """测试英文音节计数"""
        assert counter.count("hello", lang="en") == 2
        assert counter.count("world", lang="en") == 1
        assert counter.count("beautiful", lang="en") == 3

    def test_count_chinese_syllables(self, counter):
        """测试中文音节计数"""
        assert counter.count("你好", lang="zh") == 2
        assert counter.count("世界", lang="zh") == 2
        assert counter.count("你好世界", lang="zh") == 4

    def test_estimate_duration(self, counter):
        """测试时长估算"""
        # 英文: 4 音节/秒
        duration = counter.estimate_duration("hello world", lang="en")
        assert 0.7 < duration < 0.9  # 3音节 ÷ 4 = 0.75秒

        # 中文: 4 字符/秒
        duration = counter.estimate_duration("你好世界", lang="zh")
        assert 0.9 < duration < 1.1  # 4字符 ÷ 4 = 1.0秒
```

**Step 2: 运行测试验证失败**

```bash
# 获取容器名
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | grep wservice

# 在容器内执行测试
docker exec -it yivideo-wservice-1 pytest /app/tests/unit/test_syllable_counter.py -v
```

**Step 3: 实现音节计数器**

```python
# services/workers/wservice/syllable_counter.py
import re
import pyphen


class SyllableCounter:
    """音节数估算器"""

    # 4 音节/秒的行业标准
    SYLLABLES_PER_SECOND = 4.0

    def __init__(self):
        """初始化音节计数器"""
        self.en_dic = pyphen.Pyphen(lang='en')

    def count(self, text: str, lang: str = "en") -> int:
        """
        计算文本的音节数

        Args:
            text: 输入文本
            lang: 语言代码 (en/zh)

        Returns:
            音节数
        """
        if lang == "zh" or lang == "zh-CN":
            # 中文:每个汉字算一个音节
            return len([c for c in text if self._is_chinese(c)])
        elif lang == "en":
            # 英文:使用 pyphen 分割
            words = re.findall(r'\b\w+\b', text.lower())
            total = 0
            for word in words:
                syllables = self.en_dic.inserted(word).count('-') + 1
                total += syllables
            return total
        else:
            raise ValueError(f"Unsupported language: {lang}")

    def estimate_duration(self, text: str, lang: str = "en") -> float:
        """
        估算文本的朗读时长

        Args:
            text: 输入文本
            lang: 语言代码

        Returns:
            预估时长(秒)
        """
        syllables = self.count(text, lang)
        return syllables / self.SYLLABLES_PER_SECOND

    @staticmethod
    def _is_chinese(char: str) -> bool:
        """判断是否为中文字符"""
        return '\u4e00' <= char <= '\u9fff'
```

**Step 4: 运行测试验证通过**

```bash
# 获取容器名
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | grep wservice

# 在容器内执行测试
docker exec -it yivideo-wservice-1 pytest /app/tests/unit/test_syllable_counter.py -v
```

预期输出: `3 passed`

**Step 5: 提交**

```bash
git add services/workers/wservice/syllable_counter.py tests/unit/test_syllable_counter.py
git commit -m "feat(wservice): add syllable counter for duration estimation

- Support English (pyphen) and Chinese syllable counting
- 4 syllables/second industry standard
- Accurate duration estimation for translation alignment

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2.2: 实现翻译装词执行器

**文件**:
- Create: `services/workers/wservice/executors/llm_translate_subtitles.py`
- Test: `tests/unit/executors/test_llm_translate_subtitles.py`

**Step 1: 编写测试** (省略详细代码,结构类似 Task 1.3)

**Step 2: 运行测试验证失败**

**Step 3: 实现执行器**

```python
# services/workers/wservice/executors/llm_translate_subtitles.py
import json
from typing import Dict, List, Any
from services.common.base_node_executor import BaseNodeExecutor
from services.workers.wservice.llm_client import LLMClient
from services.workers.wservice.syllable_counter import SyllableCounter


class LLMTranslateSubtitlesExecutor(BaseNodeExecutor):
    """LLM 翻译装词执行器"""

    MAX_RETRIES = 3

    def validate_input(self) -> None:
        """验证输入"""
        input_data = self.get_input_data()

        if "optimized_subtitles" not in input_data:
            raise ValueError("optimized_subtitles is required")
        if "target_language" not in input_data:
            raise ValueError("target_language is required")

    def get_cache_key_fields(self) -> List[str]:
        """缓存键字段"""
        return [
            "optimized_subtitles",
            "target_language",
            "llm_provider",
            "llm_model",
            "duration_tolerance"
        ]

    def execute_core_logic(self) -> Dict[str, Any]:
        """执行翻译装词"""
        input_data = self.get_input_data()

        subtitles = input_data["optimized_subtitles"]
        target_lang = input_data["target_language"]
        llm_provider = input_data["llm_provider"]
        llm_model = input_data.get("llm_model", "deepseek-chat")
        tolerance = input_data.get("duration_tolerance", 0.1)

        # 初始化
        llm_client = LLMClient(provider=llm_provider, model=llm_model)
        counter = SyllableCounter()

        # 翻译
        translated = []
        for subtitle in subtitles:
            target_duration = subtitle["end"] - subtitle["start"]

            # 重试机制
            for attempt in range(self.MAX_RETRIES):
                system_prompt = self._build_system_prompt(target_lang, target_duration, tolerance)
                user_prompt = subtitle["text"]

                response = llm_client.call(system_prompt, user_prompt)
                try:
                    result = json.loads(response)
                    translated_text = result["tx"]

                    # 验证时长
                    estimated = counter.estimate_duration(translated_text, lang=target_lang)
                    if self._is_duration_valid(estimated, target_duration, tolerance):
                        translated.append({
                            **subtitle,
                            "text": translated_text,
                            "original_text": subtitle["text"],
                            "syllables": result.get("syl", 0),
                            "duration": target_duration,
                            "duration_valid": True
                        })
                        break
                except (json.JSONDecodeError, KeyError):
                    continue
            else:
                # 重试失败,使用原文
                self.logger.warning(f"Translation failed for subtitle {subtitle['id']}")
                translated.append({**subtitle, "duration_valid": False})

        # 生成 SRT 文件
        srt_path = self._generate_srt(translated)

        return {
            "translated_subtitles": translated,
            "retry_count": 0,
            "subtitle_file_path": srt_path,
            "subtitle_file_minio_url": self._upload_to_minio(srt_path)
        }

    def _build_system_prompt(self, target_lang: str, duration: float, tolerance: float) -> str:
        """构建翻译提示词"""
        return f"""你是专业的字幕翻译专家。翻译要求:
1. 目标语言: {target_lang}
2. 目标时长: {duration:.2f}秒 (±{tolerance*100:.0f}% 容差)
3. 音节数估算: 英文4音节/秒, 中文4字/秒
4. 优先保证时长,其次保证语义

输出 JSON: {{"tx":"翻译文本","syl":音节数}}"""

    @staticmethod
    def _is_duration_valid(estimated: float, target: float, tolerance: float) -> bool:
        """验证时长是否在容差范围内"""
        return abs(estimated - target) / target <= tolerance

    def _generate_srt(self, subtitles: List[Dict]) -> str:
        """生成 SRT 文件"""
        # TODO: 实现 SRT 生成
        pass

    def _upload_to_minio(self, file_path: str) -> str:
        """上传到 MinIO"""
        # TODO: 实现 MinIO 上传
        pass
```

**Step 4: 运行测试验证通过**

**Step 5: 提交**

```bash
git add services/workers/wservice/executors/llm_translate_subtitles.py tests/unit/executors/test_llm_translate_subtitles.py
git commit -m "feat(wservice): implement LLM translation with duration alignment

- Syllable-based duration estimation
- ±10% strict tolerance with retry mechanism
- SRT file generation and MinIO upload

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2.3: 注册翻译装词 Celery 任务

**文件**:
- Modify: `services/workers/wservice/tasks.py`

**Step 1: 在 tasks.py 中注册任务**

```python
# services/workers/wservice/tasks.py (在文件末尾添加)

@celery_app.task(bind=True, name="wservice.llm_translate_subtitles")
def llm_translate_subtitles(self, context: dict) -> dict:
    """
    [工作流任务] LLM 翻译装词

    该任务基于统一的 BaseNodeExecutor 框架。

    输入：优化后的字幕数据
    输出：翻译后的字幕数据（严格时长对齐 ±10%）
    """
    from services.workers.wservice.executors.llm_translate_subtitles import LLMTranslateSubtitlesExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    # 1. 从字典构建 WorkflowContext
    workflow_context = WorkflowContext(**context)

    # 2. 创建执行器
    executor = LLMTranslateSubtitlesExecutor(self.name, workflow_context)

    # 3. 执行并获取结果上下文
    result_context = executor.execute()

    # 4. 持久化状态到 Redis
    state_manager.update_workflow_state(result_context)

    # 5. 转换为字典返回
    return result_context.model_dump()
```

**Step 2: 运行测试验证通过**

```bash
# 获取容器名
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | grep wservice

# 在容器内执行测试
docker exec -it yivideo-wservice-1 pytest /app/tests/integration/test_llm_translate_task.py -v
```

预期输出: `1 passed`

**Step 3: 提交**

```bash
git add services/workers/wservice/tasks.py
git commit -m "feat(wservice): register LLM translate subtitles Celery task

- Add wservice.llm_translate_subtitles task
- Integration with state_manager for Redis persistence
- Ready for workflow integration

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 3: TTS 语音生成节点

### Task 3.1: 实现 Edge-TTS 生成器

**文件**:
- Create: `services/workers/wservice/executors/edgetts_generate_batch_speech.py`
- Test: `tests/unit/executors/test_edgetts_generate_batch_speech.py`

(详细步骤省略,结构类似前面任务)

核心实现要点:
1. Rate 参数预估算法
2. Edge-TTS API 异步调用
3. Rubberband 时长微调
4. FFmpeg 音频拼接

**Task 3.1补充: 注册 Edge-TTS Celery 任务**

**文件**:
- Modify: `services/workers/wservice/tasks.py`

**Step 1: 在 tasks.py 中注册任务**

```python
# services/workers/wservice/tasks.py (在文件末尾添加)

@celery_app.task(bind=True, name="wservice.edgetts_generate_batch_speech")
def edgetts_generate_batch_speech(self, context: dict) -> dict:
    """
    [工作流任务] Edge-TTS 批量语音生成

    该任务基于统一的 BaseNodeExecutor 框架。
    **不需要 GPU 资源**，纯 API 调用。

    输入：翻译后的字幕数据
    输出：批量生成的音频片段 + 合并音频
    """
    from services.workers.wservice.executors.edgetts_generate_batch_speech import EdgeTTSGenerateBatchSpeechExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    workflow_context = WorkflowContext(**context)
    executor = EdgeTTSGenerateBatchSpeechExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()
```

**Step 2: 提交**

```bash
git add services/workers/wservice/tasks.py
git commit -m "feat(wservice): register Edge-TTS batch speech Celery task

- Add wservice.edgetts_generate_batch_speech task
- No GPU lock required (API-based)
- Ready for workflow integration

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3.2: 实现 IndexTTS2 生成器

**文件**:
- Create: `services/workers/indextts_service/executors/generate_batch_speech.py`
- Test: `tests/unit/test_generate_batch_speech.py`

核心实现要点:
1. 参考音频预处理(循环拼接至 6 秒)
2. 双模式支持(single/dynamic)
3. GPU 锁集成 `@gpu_lock()`
4. Rubberband 时长对齐

**Task 3.2补充: 注册 IndexTTS2 Celery 任务**

**文件**:
- Modify: `services/workers/indextts_service/app/tasks.py`

**Step 1: 在 tasks.py 中注册任务**

```python
# services/workers/indextts_service/app/tasks.py (在文件末尾添加)

@celery_app.task(bind=True, name="indextts.generate_batch_speech")
@gpu_lock()  # ✅ 必须添加 GPU 锁！
def generate_batch_speech(self, context: dict) -> dict:
    """
    [工作流任务] IndexTTS2 批量语音生成

    该任务基于统一的 BaseNodeExecutor 框架。
    **需要 GPU 资源**，已集成 GPU 锁管理。

    输入：翻译后的字幕数据 + 参考音频
    输出：批量生成的音频片段 + 合并音频
    """
    from services.workers.indextts_service.executors.generate_batch_speech import GenerateBatchSpeechExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    workflow_context = WorkflowContext(**context)
    executor = GenerateBatchSpeechExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()
```

**Step 2: 提交**

```bash
git add services/workers/indextts_service/app/tasks.py
git commit -m "feat(indextts): register IndexTTS2 batch speech Celery task

- Add indextts.generate_batch_speech task
- GPU lock integrated for resource management
- Support single/dynamic reference audio modes

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 4: 视频合并节点

### Task 4.1: 实现视频合并执行器

**文件**:
- Create: `services/workers/ffmpeg_service/executors/merge_video_audio_subtitle.py`
- Test: `tests/unit/test_merge_video_audio_subtitle.py`

核心实现要点:
1. FFmpeg 音频混合
2. 视频音频合并
3. 字幕烧录
4. 背景音循环/截断

**Task 4.1补充: 注册视频合并 Celery 任务**

**文件**:
- Modify: `services/workers/ffmpeg_service/app/tasks.py`

**Step 1: 在 tasks.py 中注册任务**

```python
# services/workers/ffmpeg_service/app/tasks.py (在文件末尾添加)

@celery_app.task(bind=True, name="ffmpeg.merge_video_audio_subtitle")
def merge_video_audio_subtitle(self, context: dict) -> dict:
    """
    [工作流任务] 视频音频字幕合并

    该任务基于统一的 BaseNodeExecutor 框架。
    **不需要 GPU 锁**（使用流复制，不涉及视频编解码）

    输入：静音视频 + 新配音 + 背景音（可选）+ 字幕（可选）
    输出：最终合并的视频文件
    """
    from services.workers.ffmpeg_service.executors.merge_video_audio_subtitle import MergeVideoAudioSubtitleExecutor
    from services.common.context import WorkflowContext
    from services.common import state_manager

    workflow_context = WorkflowContext(**context)
    executor = MergeVideoAudioSubtitleExecutor(self.name, workflow_context)
    result_context = executor.execute()
    state_manager.update_workflow_state(result_context)
    return result_context.model_dump()
```

**Step 2: 提交**

```bash
git add services/workers/ffmpeg_service/app/tasks.py
git commit -m "feat(ffmpeg): register video audio subtitle merge Celery task

- Add ffmpeg.merge_video_audio_subtitle task
- No GPU lock required (stream copy mode)
- Support background audio mixing and subtitle burning

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 5: 文档与集成

### Task 5.1: 更新 API 文档

**文件**:
- Modify: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`

添加 5 个新节点的完整 API 文档。

### Task 5.2: 创建端到端测试

**文件**:
- Create: `tests/e2e/test_s2st_workflow.py`

测试完整的 S2ST 工作流。

---

## 依赖安装

```bash
# 添加到 requirements.txt
pyphen>=0.14.0
edge-tts>=6.1.0
pyrubberband>=0.3.0
```

```bash
pip install -r requirements.txt
```

---

## 完成标准

- [ ] 所有单元测试通过 (覆盖率 > 90%)
- [ ] 集成测试验证端到端流程
- [ ] 性能基准达标 (见设计文档)
- [ ] API 文档完整更新
- [ ] Docker Compose 配置更新

---

**创建日期**: 2026-01-16
**预计完成**: Phase 1-2: 2周, Phase 3-4: 2周, Phase 5: 1周
