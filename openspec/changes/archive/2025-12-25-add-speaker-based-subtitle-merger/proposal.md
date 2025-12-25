# Proposal: 基于说话人时间区间的字幕合并节点

## 变更 ID
`add-speaker-based-subtitle-merger`

## 变更类型
**feat** - 新功能

## 问题陈述 (Problem Statement)

### 当前状态
现有的 `wservice.merge_with_word_timestamps` 节点实现了基于**转录文件时间区间**的字幕合并逻辑：
- **时间基准**：以 Faster-Whisper 转录结果的 segment 时间区间为基准
- **合并方式**：在转录 segment 内部，根据词级时间戳匹配说话人标签
- **输出特征**：45 个 segments（与转录文件一致），每个 segment 包含完整的词级时间戳和说话人信息

**数据流向**：
```
转录文件 (时间戳) ──┐
                   ├──→ 合并文件 (以转录时间为基准)
Diarization (标签) ──┘
```

### 需求缺口
在某些业务场景下，需要以**说话人识别文件的时间区间**为基准生成字幕：

**场景 1：说话人优先的字幕展示**
- 需求：按说话人的实际发言时间段切分字幕，而非按转录的语义段落
- 示例：视频会议记录，需要精确标注每个人的发言起止时间

**场景 2：多说话人对话分析**
- 需求：基于 Diarization 的 58 个细粒度片段生成字幕，保留说话停顿信息
- 示例：对话分析系统，需要区分说话人的每次发言间隔

**场景 3：时间轴对齐验证**
- 需求：验证 Diarization 时间区间与转录词级时间戳的对齐质量
- 示例：质量检测工具，需要对比两种时间基准的差异

### 当前解决方案的局限性
现有的 `merge_with_word_timestamps` 节点**无法**满足上述需求，因为：
1. **时间基准固定**：强制使用转录文件的时间区间，无法切换到 Diarization 时间基准
2. **粒度不可调**：输出 segments 数量固定为 45（转录文件数量），无法生成 58 个 Diarization 片段
3. **逻辑耦合**：合并逻辑与转录时间戳深度耦合，难以扩展

## 提议的解决方案 (Proposed Solution)

### 核心思路
新增一个独立的功能节点 `wservice.merge_speaker_based_subtitles`，实现**基于说话人时间区间的字幕合并逻辑**。

### 关键特性

#### 1. 时间基准反转
- **输入**：
  - Diarization 文件（58 个 speaker segments）
  - 转录文件（45 个 transcript segments，包含词级时间戳）
- **输出**：
  - 58 个 segments，每个 segment 的时间区间来自 Diarization
  - 每个 segment 包含匹配到的词级时间戳数据

**数据流向**：
```
Diarization (时间戳) ──┐
                      ├──→ 合并文件 (以 Diarization 时间为基准)
转录文件 (词数据)    ──┘
```

#### 2. 词级时间戳匹配算法
对于每个 Diarization segment `[diar_start, diar_end]`：
1. **遍历转录文件的所有 words**
2. **时间重叠判断**：
   ```python
   word_start >= diar_start and word_end <= diar_end
   ```
3. **收集匹配的 words**：构建该 Diarization segment 的词列表
4. **生成文本**：拼接匹配词的 `word` 字段
5. **计算统计**：word_count, duration 等

#### 3. 边界情况处理
- **完全包含**：word 完全在 Diarization segment 内 → 直接匹配
- **部分重叠**：word 跨越 Diarization segment 边界 → 可选策略：
  - 策略 A（默认）：按重叠比例分配（如重叠 >50% 则匹配）
  - 策略 B：严格模式，仅匹配完全包含的 words
- **无匹配**：Diarization segment 内无任何 word → 输出空字幕（保留时间区间）

#### 4. 输出格式
```json
[
  {
    "id": 1,
    "start": 12.062843750000003,  // 来自 Diarization
    "end": 13.277843750000002,    // 来自 Diarization
    "duration": 1.2149999999999999,
    "speaker": "SPEAKER_00",
    "text": "Well, little kitty,",  // 拼接匹配的 words
    "word_count": 3,
    "words": [
      {
        "word": " Well,",
        "start": 11.4,  // 保留原始词级时间戳
        "end": 12.24,
        "probability": 0.64111328125,
        "speaker": "SPEAKER_00"
      },
      // ... 其他匹配的 words
    ],
    "speaker_confidence": 1.0,
    "match_quality": {  // 新增：匹配质量指标
      "matched_words": 3,
      "total_words_in_range": 3,
      "coverage_ratio": 1.0
    }
  }
]
```

### 与现有节点的对比

| 特性 | `merge_with_word_timestamps` | `merge_speaker_based_subtitles` (新) |
|------|------------------------------|--------------------------------------|
| **时间基准** | 转录文件 (45 segments) | Diarization 文件 (58 segments) |
| **输出数量** | 45 个 segments | 58 个 segments |
| **主要用途** | 语义连贯的字幕 | 说话人优先的字幕 |
| **词级时间戳** | 完整保留 | 完整保留 |
| **匹配方向** | Diarization → Transcript | Transcript → Diarization |
| **空白处理** | 无（转录必有文本） | 支持（Diarization 可能无对应词） |

### 技术实现要点

#### 1. 复用现有基础设施
- **继承 `BaseNodeExecutor`**：复用参数解析、文件处理、缓存机制
- **复用 `get_param_with_fallback`**：统一参数获取逻辑
- **复用 `build_node_output_path`**：标准化输出路径

#### 2. 核心算法伪代码
```python
def merge_speaker_based_subtitles(diarization_segments, transcript_segments):
    # 预处理：提取所有词级时间戳到扁平列表
    all_words = []
    for seg in transcript_segments:
        for word in seg['words']:
            all_words.append({
                'word': word['word'],
                'start': word['start'],
                'end': word['end'],
                'probability': word.get('probability'),
                'speaker': seg.get('speaker')  # 继承 segment 的 speaker
            })

    # 按时间排序（优化查找性能）
    all_words.sort(key=lambda w: w['start'])

    # 遍历 Diarization segments
    merged_segments = []
    for diar_seg in diarization_segments:
        matched_words = []

        # 二分查找优化：找到第一个可能重叠的 word
        for word in all_words:
            if word['end'] < diar_seg['start']:
                continue  # word 在 segment 之前
            if word['start'] > diar_seg['end']:
                break  # word 在 segment 之后，后续无需检查

            # 判断重叠
            if is_overlapping(word, diar_seg):
                matched_words.append(word)

        # 构建输出 segment
        merged_seg = {
            'id': len(merged_segments) + 1,
            'start': diar_seg['start'],
            'end': diar_seg['end'],
            'duration': diar_seg['duration'],
            'speaker': diar_seg['speaker'],
            'text': ''.join(w['word'] for w in matched_words),
            'word_count': len(matched_words),
            'words': matched_words,
            'speaker_confidence': diar_seg.get('speaker_confidence', 1.0),
            'match_quality': calculate_match_quality(matched_words, diar_seg)
        }
        merged_segments.append(merged_seg)

    return merged_segments
```

#### 3. 性能优化
- **时间复杂度**：O(W + D)，其中 W 为总词数，D 为 Diarization segments 数
- **空间复杂度**：O(W)，扁平化词列表
- **优化策略**：
  - 词列表预排序
  - 二分查找起始位置
  - 提前终止遍历

### 依赖关系
- **上游依赖**：
  - `faster_whisper.transcribe_audio`（提供词级时间戳）
  - `pyannote_audio.diarize_speakers`（提供说话人时间区间）
- **下游消费**：
  - 字幕导出节点（SRT/VTT/ASS）
  - 质量分析工具
  - 多说话人对话系统

### 兼容性保证
- **不影响现有节点**：`merge_with_word_timestamps` 保持不变
- **独立部署**：新节点独立实现，无破坏性变更
- **配置可选**：工作流可自由选择使用哪种合并策略

## 规范增量 (Spec Deltas)

本提案将创建以下规范增量：

### 1. `speaker-based-subtitle-merger` (新规范)
- **Requirement 1**：基于说话人时间区间的字幕合并
  - Scenario: 匹配词级时间戳到 Diarization segments
  - Scenario: 处理无匹配词的 Diarization segments
  - Scenario: 计算匹配质量指标

- **Requirement 2**：输出格式与质量保证
  - Scenario: 输出 segments 数量与 Diarization 一致
  - Scenario: 保留完整的词级时间戳信息
  - Scenario: 提供匹配质量统计

## 实施任务 (Implementation Tasks)

详见 `tasks.md`。

## 验证计划 (Validation Plan)

### 单元测试
- 测试词级时间戳匹配算法
- 测试边界情况处理（完全包含、部分重叠、无匹配）
- 测试匹配质量计算

### 集成测试
- 使用真实的 Diarization 和转录文件测试完整流程
- 验证输出 segments 数量为 58
- 验证词级时间戳完整性

### 对比测试
- 对比 `merge_with_word_timestamps` 和 `merge_speaker_based_subtitles` 的输出差异
- 验证两种时间基准的互补性

### 文档同步验证
- ✅ 节点信息已同步到 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
- ✅ API 参考文档包含完整的请求/响应示例
- ✅ 参数表与实际实现一致

## 风险与缓解 (Risks & Mitigation)

### 风险 1：词级时间戳与 Diarization 时间不对齐
- **影响**：部分 Diarization segments 可能无法匹配到任何词
- **缓解**：
  - 支持配置重叠阈值（默认 50%）
  - 输出匹配质量指标，便于识别低质量片段
  - 保留空字幕 segments，避免丢失时间信息

### 风险 2：性能问题（大量词级时间戳）
- **影响**：处理长视频时可能耗时较长
- **缓解**：
  - 使用二分查找优化
  - 词列表预排序
  - 提前终止遍历

### 风险 3：输出文件过大
- **影响**：58 个 segments 可能导致文件体积增大
- **缓解**：
  - 支持配置是否输出匹配质量指标
  - 支持压缩存储

## 替代方案 (Alternatives Considered)

### 方案 A：扩展现有节点
在 `merge_with_word_timestamps` 中添加参数 `time_base="transcript"|"diarization"`。

**优点**：
- 代码复用率高
- 减少节点数量

**缺点**：
- 增加现有节点复杂度
- 两种逻辑耦合，难以维护
- 违反单一职责原则

**决策**：❌ 不采用，因为两种合并逻辑差异较大，独立实现更清晰。

### 方案 B：后处理转换
先使用 `merge_with_word_timestamps` 生成结果，再通过后处理脚本转换为 Diarization 时间基准。

**优点**：
- 无需修改核心代码

**缺点**：
- 增加额外处理步骤
- 无法直接从源数据生成，效率低
- 难以集成到工作流引擎

**决策**：❌ 不采用，因为不符合工作流引擎的设计理念。

## 成功标准 (Success Criteria)

- ✅ 新节点成功生成 58 个 segments（与 Diarization 一致）
- ✅ 每个 segment 的时间区间来自 Diarization 文件
- ✅ 词级时间戳完整保留，无数据丢失
- ✅ 匹配质量指标准确反映对齐情况
- ✅ 通过所有单元测试和集成测试
- ✅ 性能满足要求（处理 5 分钟视频 < 5 秒）
- ✅ 文档完整，包含使用示例
- ✅ **节点信息已同步到 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`**

## 参考资料 (References)

- 现有实现：`services/workers/wservice/executors/merge_with_word_timestamps_executor.py`
- 相关规范：`openspec/specs/speaker-diarization/spec.md`
- 相关规范：`openspec/specs/faster-whisper-service/spec.md`
- 字幕合并工具：`services/common/subtitle/subtitle_merger.py`
