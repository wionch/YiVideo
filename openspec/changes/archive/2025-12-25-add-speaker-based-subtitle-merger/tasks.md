# Implementation Tasks

## 任务概述
本文档定义了实现 `wservice.merge_speaker_based_subtitles` 功能节点的具体任务列表。任务按依赖关系排序，标注了可并行化的工作。

## 任务列表

### Phase 1: 核心算法实现 (Core Algorithm)

#### Task 1.1: 实现词级时间戳扁平化函数
**描述**：创建工具函数，将转录文件的嵌套结构（segments → words）扁平化为单一词列表。

**输入**：
```python
transcript_segments: List[Dict]  # 包含 segments，每个 segment 有 words 数组
```

**输出**：
```python
all_words: List[Dict]  # 扁平化的词列表，每个词包含 start, end, word, probability, speaker
```

**验证**：
- ✅ 单元测试：验证扁平化后的词数量正确
- ✅ 单元测试：验证词的时间戳保留原始值
- ✅ 单元测试：验证词按 start 时间排序

**文件**：`services/common/subtitle/word_timestamp_utils.py`（新建）

**依赖**：无

**预计工作量**：0.5 天

---

#### Task 1.2: 实现时间重叠判断函数
**描述**：创建函数判断词级时间戳与 Diarization segment 的重叠关系。

**函数签名**：
```python
def calculate_overlap_ratio(
    word_start: float,
    word_end: float,
    segment_start: float,
    segment_end: float
) -> float:
    """
    计算词级时间戳与 segment 的重叠比例。

    Returns:
        重叠比例 (0.0 ~ 1.0)，0.0 表示无重叠，1.0 表示完全包含
    """
```

**验证**：
- ✅ 单元测试：完全包含（返回 1.0）
- ✅ 单元测试：部分重叠（返回 0.0 ~ 1.0）
- ✅ 单元测试：无重叠（返回 0.0）
- ✅ 单元测试：边界情况（word_start == segment_start）

**文件**：`services/common/subtitle/word_timestamp_utils.py`

**依赖**：无

**预计工作量**：0.5 天

---

#### Task 1.3: 实现词级时间戳匹配核心算法
**描述**：实现主合并逻辑，将词级时间戳匹配到 Diarization segments。

**函数签名**：
```python
def match_words_to_speaker_segments(
    all_words: List[Dict],
    diarization_segments: List[Dict],
    overlap_threshold: float = 0.5
) -> List[Dict]:
    """
    将词级时间戳匹配到说话人 segments。

    Args:
        all_words: 扁平化的词列表（已排序）
        diarization_segments: 说话人 segments 列表
        overlap_threshold: 重叠阈值（默认 0.5）

    Returns:
        合并后的 segments 列表
    """
```

**算法要点**：
- 遍历每个 Diarization segment
- 使用二分查找找到第一个可能重叠的 word
- 收集所有重叠比例 ≥ threshold 的 words
- 构建输出 segment（包含 text, word_count, words, match_quality）

**验证**：
- ✅ 单元测试：匹配完全包含的 words
- ✅ 单元测试：匹配部分重叠的 words（threshold=0.5）
- ✅ 单元测试：处理无匹配词的 segment
- ✅ 单元测试：验证输出 segments 数量与 Diarization 一致
- ✅ 单元测试：验证 text 字段拼接正确

**文件**：`services/common/subtitle/speaker_based_merger.py`（新建）

**依赖**：Task 1.1, Task 1.2

**预计工作量**：2 天

---

#### Task 1.4: 实现匹配质量指标计算
**描述**：为每个合并后的 segment 计算匹配质量指标。

**函数签名**：
```python
def calculate_match_quality(
    matched_words: List[Dict],
    segment_start: float,
    segment_end: float
) -> Dict[str, Any]:
    """
    计算匹配质量指标。

    Returns:
        {
            "matched_words": int,
            "total_words_in_range": int,
            "coverage_ratio": float,
            "partial_overlaps": int,
            "full_matches": int
        }
    """
```

**验证**：
- ✅ 单元测试：全部完全匹配
- ✅ 单元测试：包含部分重叠
- ✅ 单元测试：无匹配词
- ✅ 单元测试：coverage_ratio 计算正确

**文件**：`services/common/subtitle/speaker_based_merger.py`

**依赖**：Task 1.3

**预计工作量**：1 天

---

### Phase 2: 节点执行器实现 (Node Executor)

#### Task 2.1: 创建节点执行器类
**描述**：创建 `WServiceMergeSpeakerBasedSubtitlesExecutor` 类，继承 `BaseNodeExecutor`。

**类结构**：
```python
class WServiceMergeSpeakerBasedSubtitlesExecutor(BaseNodeExecutor):
    """
    基于说话人时间区间的字幕合并执行器。

    输入参数:
        - segments_data (list, 可选): 直接传入转录片段数据
        - speaker_segments_data (list, 可选): 直接传入说话人片段数据
        - segments_file (str, 可选): 转录数据文件路径
        - diarization_file (str, 可选): 说话人分离数据文件路径
        - overlap_threshold (float, 可选): 重叠阈值（默认 0.5）

    输出字段:
        - merged_segments_file (str): 合并后的片段文件路径
    """

    def validate_input(self) -> None:
        """验证输入参数"""

    def execute_core_logic(self) -> Dict[str, Any]:
        """执行合并核心逻辑"""

    def get_cache_key_fields(self) -> List[str]:
        """返回缓存键字段"""

    def get_required_output_fields(self) -> List[str]:
        """返回必需输出字段"""
```

**验证**：
- ✅ 单元测试：`validate_input` 检查必需参数
- ✅ 单元测试：`get_cache_key_fields` 返回正确字段
- ✅ 单元测试：`get_required_output_fields` 返回正确字段

**文件**：`services/workers/wservice/executors/merge_speaker_based_subtitles_executor.py`（新建）

**依赖**：Task 1.3, Task 1.4

**预计工作量**：1 天

---

#### Task 2.2: 实现参数获取逻辑
**描述**：实现 `_get_transcript_segments` 和 `_get_speaker_segments` 方法，支持多种参数来源。

**优先级**：
1. 直接传入的数据对象（`segments_data`, `speaker_segments_data`）
2. 文件路径（`segments_file`, `diarization_file`）
3. 上游节点输出（`faster_whisper.transcribe_audio`, `pyannote_audio.diarize_speakers`）

**验证**：
- ✅ 单元测试：从直接传入的数据对象获取
- ✅ 单元测试：从文件路径加载
- ✅ 单元测试：从上游节点输出获取
- ✅ 单元测试：参数缺失时抛出清晰错误

**文件**：`services/workers/wservice/executors/merge_speaker_based_subtitles_executor.py`

**依赖**：Task 2.1

**预计工作量**：1.5 天

---

#### Task 2.3: 实现文件处理逻辑
**描述**：实现文件路径规范化、MinIO URL 下载、文件加载等辅助方法。

**方法列表**：
- `_normalize_path(file_path: str) -> str`
- `_download_if_needed(file_path: str) -> str`
- `_load_segments_from_file(segments_file: str) -> List[Dict]`
- `_load_speaker_data_from_file(diarization_file: str) -> Dict[str, Any]`

**验证**：
- ✅ 单元测试：规范化绝对路径
- ✅ 单元测试：规范化相对路径（`share/` 前缀）
- ✅ 单元测试：下载 MinIO URL
- ✅ 单元测试：加载 JSON 文件
- ✅ 单元测试：文件不存在时的错误处理

**文件**：`services/workers/wservice/executors/merge_speaker_based_subtitles_executor.py`

**依赖**：Task 2.1

**预计工作量**：1 天

**可并行化**：可与 Task 2.2 并行开发

---

#### Task 2.4: 实现核心执行逻辑
**描述**：实现 `execute_core_logic` 方法，调用核心算法并保存结果。

**流程**：
1. 获取转录 segments 和说话人 segments
2. 验证词级时间戳存在性
3. 验证说话人 segments 格式
4. 调用核心合并算法
5. 为合并后的 segments 分配 ID
6. 保存结果到文件
7. 返回输出字段

**验证**：
- ✅ 集成测试：使用真实数据文件测试完整流程
- ✅ 集成测试：验证输出文件格式
- ✅ 集成测试：验证输出 segments 数量

**文件**：`services/workers/wservice/executors/merge_speaker_based_subtitles_executor.py`

**依赖**：Task 2.1, Task 2.2, Task 2.3, Task 1.3, Task 1.4

**预计工作量**：1.5 天

---

### Phase 3: 节点注册与集成 (Registration & Integration)

#### Task 3.1: 注册节点到 WService
**描述**：在 WService 的节点注册表中添加新节点。

**修改文件**：
- `services/workers/wservice/app/tasks.py`：添加任务函数
- `services/workers/wservice/executors/__init__.py`：导出执行器类

**任务函数签名**：
```python
@app.task(
    bind=True,
    name="wservice.merge_speaker_based_subtitles",
    base=StandardTaskInterface
)
def merge_speaker_based_subtitles(self: Task, context: dict) -> dict:
    """基于说话人时间区间的字幕合并任务"""
    executor = WServiceMergeSpeakerBasedSubtitlesExecutor(
        stage_name="wservice.merge_speaker_based_subtitles",
        context=WorkflowContext.from_dict(context)
    )
    return executor.execute(context)
```

**验证**：
- ✅ 单元测试：任务注册成功
- ✅ 单元测试：任务可通过 Celery 调用
- ✅ 集成测试：通过 API Gateway 调用任务

**文件**：
- `services/workers/wservice/app/tasks.py`
- `services/workers/wservice/executors/__init__.py`

**依赖**：Task 2.4

**预计工作量**：0.5 天

---

#### Task 3.2: 添加工作流配置示例
**描述**：创建示例工作流配置文件，演示如何使用新节点。

**示例配置**：
```json
{
  "workflow_id": "video_to_subtitle_speaker_based",
  "stages": [
    {
      "name": "faster_whisper.transcribe_audio",
      "params": {
        "audio_path": "${{input_data.audio_path}}",
        "word_timestamps": true
      }
    },
    {
      "name": "pyannote_audio.diarize_speakers",
      "params": {
        "audio_path": "${{input_data.audio_path}}"
      }
    },
    {
      "name": "wservice.merge_speaker_based_subtitles",
      "params": {
        "overlap_threshold": 0.5
      }
    }
  ]
}
```

**验证**：
- ✅ E2E 测试：使用示例配置执行完整工作流
- ✅ E2E 测试：验证输出文件生成

**文件**：`docs/examples/workflows/video_to_subtitle_speaker_based.json`（新建）

**依赖**：Task 3.1

**预计工作量**：0.5 天

---

### Phase 4: 测试与文档 (Testing & Documentation)

#### Task 4.1: 编写单元测试
**描述**：为核心算法和工具函数编写单元测试。

**测试文件**：
- `tests/unit/common/subtitle/test_word_timestamp_utils.py`
- `tests/unit/common/subtitle/test_speaker_based_merger.py`
- `tests/unit/workers/wservice/test_merge_speaker_based_subtitles_executor.py`

**覆盖率目标**：> 90%

**验证**：
- ✅ 运行 `pytest tests/unit/common/subtitle/ -v`
- ✅ 运行 `pytest tests/unit/workers/wservice/test_merge_speaker_based_subtitles_executor.py -v`
- ✅ 运行 `pytest --cov=services/common/subtitle --cov=services/workers/wservice/executors`

**依赖**：Task 1.1, Task 1.2, Task 1.3, Task 1.4, Task 2.1, Task 2.2, Task 2.3, Task 2.4

**预计工作量**：2 天

---

#### Task 4.2: 编写集成测试
**描述**：使用真实数据文件测试完整流程。

**测试场景**：
- 从上游节点获取数据
- 从文件路径加载数据
- 处理 58 个 Diarization segments
- 验证输出格式和质量

**测试文件**：
- `tests/integration/workers/wservice/test_merge_speaker_based_subtitles_integration.py`

**测试数据**：
- 使用 `share/workflows/video_to_subtitle_task/nodes/` 下的真实数据文件

**验证**：
- ✅ 运行 `pytest tests/integration/workers/wservice/test_merge_speaker_based_subtitles_integration.py -v`
- ✅ 验证输出 segments 数量为 58
- ✅ 验证匹配质量指标

**依赖**：Task 3.1

**预计工作量**：1.5 天

---

#### Task 4.3: 编写 E2E 测试
**描述**：测试完整的工作流执行。

**测试场景**：
- 通过 API Gateway 提交工作流
- 验证所有节点成功执行
- 验证最终输出文件

**测试文件**：
- `tests/e2e/workflows/test_video_to_subtitle_speaker_based.py`

**验证**：
- ✅ 运行 `pytest tests/e2e/workflows/test_video_to_subtitle_speaker_based.py -v`
- ✅ 验证工作流状态为 SUCCESS
- ✅ 验证输出文件存在且格式正确

**依赖**：Task 3.2

**预计工作量**：1 天

---

#### Task 4.4: 编写用户文档
**描述**：编写节点使用文档和 API 参考。

**文档内容**：
- 节点功能说明
- 输入参数详解
- 输出格式说明
- 使用示例
- 常见问题 FAQ

**文件**：
- `docs/nodes/wservice/merge_speaker_based_subtitles.md`（新建）
- `docs/api/nodes.md`（更新）
- `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`（**必需更新**）

**SINGLE_TASK_API_REFERENCE.md 更新要求**：
- 在 `wservice.merge_with_word_timestamps` 节点后添加新节点文档
- 遵循现有格式：复用判定 + 功能概述 + 请求体示例 + WorkflowContext 示例 + 参数表
- 参考位置：第 1204-1259 行（`wservice.merge_with_word_timestamps` 节点）
- **参考模板**：`openspec/changes/add-speaker-based-subtitle-merger/SINGLE_TASK_API_REFERENCE_template.md`
- 示例结构：
  ```markdown
  #### wservice.merge_speaker_based_subtitles
  复用判定：`stages.wservice.merge_speaker_based_subtitles.status=SUCCESS` 且 `output.merged_segments_file` 非空即命中复用；等待态返回 `status=pending`；未命中按正常流程执行。
  功能概述：基于说话人时间区间合并字幕，输出 segments 数量与 Diarization 一致，保留完整词级时间戳。
  请求体：...
  WorkflowContext 示例：...
  参数表：...
  ```

**验证**：
- ✅ 文档包含完整的参数说明
- ✅ 文档包含至少 2 个使用示例
- ✅ 文档包含常见错误和解决方案
- ✅ **SINGLE_TASK_API_REFERENCE.md 已更新并通过格式检查**

**依赖**：Task 3.2

**预计工作量**：1 天

**可并行化**：可与 Task 4.3 并行开发

---

### Phase 5: 性能优化与验证 (Performance Optimization)

#### Task 5.1: 性能基准测试
**描述**：测试不同规模数据的处理性能。

**测试场景**：
- 小规模：5 分钟视频，约 1,000 词，50 segments
- 中规模：30 分钟视频，约 6,000 词，300 segments
- 大规模：60 分钟视频，约 10,000 词，500 segments

**性能目标**：
- 小规模：< 5 秒
- 中规模：< 15 秒
- 大规模：< 30 秒

**验证**：
- ✅ 运行性能测试脚本
- ✅ 记录处理时间和内存占用
- ✅ 验证是否满足性能目标

**文件**：`tests/performance/test_merge_speaker_based_subtitles_performance.py`（新建）

**依赖**：Task 4.2

**预计工作量**：1 天

---

#### Task 5.2: 性能优化（如需要）
**描述**：根据基准测试结果进行性能优化。

**优化策略**：
- 使用 `bisect` 模块优化二分查找
- 缓存词列表排序结果
- 减少不必要的对象复制
- 使用生成器优化内存占用

**验证**：
- ✅ 重新运行性能基准测试
- ✅ 验证优化后性能提升 > 20%

**依赖**：Task 5.1

**预计工作量**：1 天（可选，仅在性能不达标时执行）

---

## 任务依赖关系图

```
Phase 1: 核心算法实现
  Task 1.1 (扁平化) ──┐
  Task 1.2 (重叠判断) ─┼──→ Task 1.3 (匹配算法) ──→ Task 1.4 (质量指标)
                      │
Phase 2: 节点执行器实现
  Task 2.1 (执行器类) ──┼──→ Task 2.2 (参数获取) ──┐
                      │                          │
                      └──→ Task 2.3 (文件处理) ──┼──→ Task 2.4 (核心执行)
                                                 │
Phase 3: 节点注册与集成
  Task 3.1 (节点注册) ──────────────────────────┼──→ Task 3.2 (工作流示例)
                                                 │
Phase 4: 测试与文档
  Task 4.1 (单元测试) ──────────────────────────┤
  Task 4.2 (集成测试) ──────────────────────────┼──→ Task 5.1 (性能测试)
  Task 4.3 (E2E 测试) ──────────────────────────┤
  Task 4.4 (用户文档) ──────────────────────────┘

Phase 5: 性能优化
  Task 5.1 (性能测试) ──→ Task 5.2 (性能优化, 可选)
```

## 并行化建议

以下任务可并行开发：

**并行组 1**（Phase 1）：
- Task 1.1 + Task 1.2（不同开发者）

**并行组 2**（Phase 2）：
- Task 2.2 + Task 2.3（不同开发者）

**并行组 3**（Phase 4）：
- Task 4.3 + Task 4.4（不同开发者）

## 总预计工作量

- **Phase 1**：4 天
- **Phase 2**：5 天
- **Phase 3**：1 天
- **Phase 4**：5.5 天
- **Phase 5**：1-2 天

**总计**：16.5 - 17.5 天（约 3.5 周）

如果采用并行开发（2 名开发者），可缩短至：**12 - 13 天**（约 2.5 周）

## 里程碑 (Milestones)

- **M1 (Day 4)**：核心算法实现完成，通过单元测试
- **M2 (Day 9)**：节点执行器实现完成，通过集成测试
- **M3 (Day 10)**：节点注册完成，可通过 API 调用
- **M4 (Day 15.5)**：所有测试和文档完成
- **M5 (Day 17.5)**：性能优化完成（如需要），准备发布
