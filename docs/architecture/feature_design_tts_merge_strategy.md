# 字幕参考音合并施工方案

## 1. 概述

### 1.1. 目标

为 `IndexTTS` 语音合成引擎提供符合 `[3, 10]` 秒时长要求的高质量参考音频片段。本方案将通过在 `faster_whisper_service` 中添加一个新的工作流节点 `faster_whisper.merge_for_tts` 来实现字幕的智能合并与分割。

### 1.2. 集成策略

新功能将完全集成在现有的 `faster_whisper_service` 中，以复用现有组件并简化维护。主要涉及以下文件的修改和创建：

*   **创建新模块**: `services/workers/faster_whisper_service/app/tts_merger.py`
*   **添加新任务**: `services/workers/faster_whisper_service/app/tasks.py`
*   **更新工作流示例**: `docs/development/WORKFLOW_EXAMPLES.md` (可选)

## 2. 核心参数定义

新节点 `faster_whisper.merge_for_tts` 将接受以下参数，这些参数可在工作流请求的 `node_params` 中进行配置。

| 参数名 | 默认值 | 描述 |
| :--- | :--- | :--- |
| `min_duration` | 3.0 | 合并后片段的最小目标时长（秒）。 |
| `max_duration` | 10.0 | 合并后片段的最大目标时长（秒）。 |
| `max_gap` | 1.0 | 相邻字幕片段之间允许合并的最大时间间隔（秒）。 |
| `split_on_punctuation` | `false` | 是否在遇到句末标点符号时强制停止合并。默认为`false`，只根据时长和间隔合并。 |

## 3. 详细设计与实现

### 3.1. 文件结构与模块职责

#### `services/workers/faster_whisper_service/app/tts_merger.py` (新建)

该文件将包含核心的合并与分割逻辑，封装在 `TtsMerger` 类中。

```python
# tts_merger.py (伪代码)

from typing import List, Dict

class TtsMerger:
    def __init__(self, config: Dict):
        self.min_duration = config.get('min_duration', 3.0)
        self.max_duration = config.get('max_duration', 10.0)
        self.max_gap = config.get('max_gap', 1.0)
        self.split_on_punctuation = config.get('split_on_punctuation', False)
        # 句末标点符号集
        self.PUNCTUATION = set("。！？.”")

    def merge_segments(self, segments: List[Dict]) -> List[Dict]:
        """主入口函数，执行完整的合并与优化流程"""
        
        # 1. 按说话人对所有片段进行分组
        speaker_groups = self._group_by_speaker(segments)
        
        final_segments = []
        for speaker, speaker_segments in speaker_groups.items():
            # 2. 对每个说话人的片段执行初步合并
            preliminary_merged = self._preliminary_merge(speaker_segments)
            
            # 3. 对合并后的片段进行优化调整
            optimized_segments = self._optimize_segments(preliminary_merged)
            final_segments.extend(optimized_segments)
            
        # 4. 按开始时间对最终结果排序
        final_segments.sort(key=lambda x: x['start'])
        return final_segments

    def _group_by_speaker(self, segments: List[Dict]) -> Dict[str, List[Dict]]:
        # 实现按说话人分组的逻辑...
        pass

    def _preliminary_merge(self, segments: List[Dict]) -> List[Dict]:
        # 实现阶段一：初步迭代合并的逻辑...
        # 遍历片段，根据合并条件（说话人、间隔、时长、标点）构建合并组
        pass

    def _optimize_segments(self, segments: List[Dict]) -> List[Dict]:
        # 实现阶段二：优化调整的逻辑...
        # 处理过长和过短的片段
        pass
        
    def _split_long_segment(self, segment: Dict) -> List[Dict]:
        # 实现智能分割逻辑...
        # 优先在标点处切分
        pass
        
    def _handle_short_segments(self, segments: List[Dict]) -> List[Dict]:
        # 实现二次合并或标记丢弃逻辑...
        pass

```

#### `services/workers/faster_whisper_service/app/tasks.py` (修改)

在该文件中添加新的 Celery 任务 `merge_for_tts`。

```python
# tasks.py (伪代码)

# ... 导入 TtsMerger ...
from .tts_merger import TtsMerger

# ... 其他任务 ...

@celery_app.task(bind=True, name='faster_whisper.merge_for_tts')
def merge_for_tts(self, context: dict) -> dict:
    """
    为TTS参考音合并字幕片段的工作流节点。
    """
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    # ... 初始化阶段状态 ...

    try:
        # 1. 获取输入字幕文件
        # 优先从 generate_subtitle_files 阶段获取 speaker_json_path
        # 如果没有，则从 transcribe_audio 阶段获取 segments_file
        subtitle_file_path = # ... 实现获取路径的逻辑 ...
        
        with open(subtitle_file_path, 'r', encoding='utf-8') as f:
            subtitle_data = json.load(f)
        segments = subtitle_data.get('segments', [])

        # 2. 获取节点配置参数
        node_params = workflow_context.get_node_params(stage_name)
        
        # 3. 初始化并执行合并
        merger = TtsMerger(config=node_params)
        merged_segments = merger.merge_segments(segments)

        # 4. 准备输出
        # 将合并后的 segments 写入新的 JSON 文件
        output_file_path = # ... 构建输出文件路径 ...
        with open(output_file_path, 'w', encoding='utf-8') as f:
            # ... 写入包含 merged_segments 的新JSON数据 ...
        
        output_data = {
            "merged_tts_segments_path": output_file_path,
            "statistics": {
                "original_count": len(segments),
                "merged_count": len(merged_segments),
                "merged_items": len(segments) - len(merged_segments)
            }
        }
        
        # ... 更新工作流状态并返回 ...

    except Exception as e:
        # ... 错误处理 ...
    
    return workflow_context.model_dump()

```

### 3.2. 算法描述（更新后）

#### 阶段一：初步迭代合并

此阶段的目标是根据核心规则，将连续的、符合条件的短字幕合并成一个“片段组”。

**算法描述:**

1.  **按说话人分组**: 首先，将所有输入的字幕片段按 `speaker` 字段进行分组。后续的合并操作将在每个说话人分组内部独立进行。
2.  **迭代合并**: 对每个说话人的片段列表，执行以下操作：
    a. 初始化一个空的结果列表 `preliminary_merged` 和一个空的当前合并组 `current_merge_group`。
    b. 遍历该说话人的所有片段 `S_current`。
    c. 如果 `current_merge_group` 为空，将 `S_current` 添加进去。
    d. 否则，检查 `S_current` 是否能与 `current_merge_group` 合并：
        i.   **时间间隔限制**: `S_current.start - current_merge_group.end` <= `max_gap`。
        ii.  **总时长上限**: `(current_merge_group.end - current_merge_group.start) + S_current.duration` <= `max_duration`。
        iii. **句子完整性 (可选)**: 如果 `split_on_punctuation` 为 `true`，检查组内最后一个片段的文本是否以句末标点结尾。
    e. 如果所有条件满足，则将 `S_current` 加入 `current_merge_group`。否则，固化当前组，并用 `S_current` 开始一个新组。
3.  遍历结束后，固化最后一组。

#### 阶段二：优化调整

对初步合并的结果进行微调。

1.  **过长片段处理**: 遍历所有片段，若 `duration > max_duration`，则使用 `_split_long_segment` 方法进行分割。分割点优先选择标点符号处。
2.  **过短片段处理**: 遍历所有片段，若 `duration < min_duration`，则尝试与相邻（前后）的、**同说话人**的片段进行二次合并。此次合并只检查总时长是否超过 `max_duration`，并使用 `max_gap` 作为间隔限制。如果无法合并，则标记或丢弃该片段。

## 4. 工作流集成

### 4.1. 任务注册

`faster_whisper.merge_for_tts` 任务的队列应为 `faster_whisper_queue`，这在 `workflow_factory.py` 中通过任务名前缀自动推断，无需额外配置。

### 4.2. 示例工作流 (`workflow_chain`)

```json
{
  "video_path": "/app/videos/example.mp4",
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_audio",
      "faster_whisper.transcribe_audio",
      "pyannote_audio.diarize_speakers",
      "faster_whisper.generate_subtitle_files",
      "faster_whisper.merge_for_tts"
    ]
  },
  "faster_whisper.merge_for_tts": {
      "min_duration": 3.5,
      "max_duration": 9.5,
      "max_gap": 0.8,
      "split_on_punctuation": true
  }
}
```

这份施工方案提供了明确的实现路径，下一步即可开始编码。