

# **开发施工文档：字幕时间轴精度优化重构**

## 1. 项目背景与目标

### 1.1. 背景
当前的`后处理器`模块通过“下一条字幕的起始帧”来推断“上一条字幕的结束帧”。此逻辑虽然简洁，但存在一个核心缺陷：当一条字幕结束后是长时间的空白，而不是另一条字幕时，它会错误地将该字幕的时长延长至覆盖整个空白期，导致时间轴精度严重下降。

### 1.2. 目标
本次重构的目标是**彻底解决时间轴精度问题**。我们将通过改造流水线的数据流，使`后处理器`能够明确地获知**字幕消失**的事件，从而精确地确定每一条字幕的起止时间。

## 2. 核心设计思路

我们将废弃在模块间仅传递“关键帧帧号”的简单做法，转而采用一个更丰富的**事件驱动模型**。

1.  **引入`ChangeType`**: 定义一个枚举类型来描述关键帧的变化性质。
    ```python
    from enum import Enum, auto

    class ChangeType(Enum):
        TEXT_APPEARED = auto()      # 文本出现 (从无到有)
        TEXT_DISAPPEARED = auto()   # 文本消失 (从有到无)
        CONTENT_CHANGED = auto()    # 文本内容变化 (从有到有，但内容不同)
    ```

2.  **改造数据流**:
    *   `变化检测器`不再仅输出帧号列表，而是输出一个包含变化类型的事件列表：`List[Tuple[int, ChangeType]]`。
    *   `OCR引擎`根据事件类型决定是否进行识别，并将事件类型随识别结果向下传递。
    *   `后处理器`根据接收到的事件流来精确构建字幕片段。

## 3. 影响范围

本次重构将涉及以下三个核心模块的修改：

*   `pipeline/modules/change_detector.py`
*   `pipeline/modules/ocr.py`
*   `pipeline/modules/postprocessor.py`

## 4. 施工阶段与步骤

请严格按照以下顺序分阶段执行。

### **阶段一：改造 `ChangeDetector`**

**目标**：使其能够输出带有变化类型的事件列表。

1.  **修改 `_detect_change_points` 方法**:
    *   在方法内部，重写其核心循环逻辑。
    *   **新逻辑**:
        ```python
        # ...
        key_events = []
        # 第0帧特殊处理，如果非空白则为APPEARED
        is_blank_list = (stds < blank_threshold)
        if not is_blank_list[0]:
            key_events.append((0, ChangeType.TEXT_APPEARED))

        for i in range(1, len(hashes)):
            prev_is_blank = is_blank_list[i-1]
            curr_is_blank = is_blank_list[i]

            if prev_is_blank and not curr_is_blank:
                # 从无到有
                key_events.append((i, ChangeType.TEXT_APPEARED))
            elif not prev_is_blank and curr_is_blank:
                # 从有到无
                key_events.append((i, ChangeType.TEXT_DISAPPEARED))
            elif not prev_is_blank and not curr_is_blank:
                # 都是有，判断内容是否变化
                hamming_distance = np.count_nonzero(hashes[i-1] != hashes[i])
                if hamming_distance > self.hamming_threshold:
                    key_events.append((i, ChangeType.CONTENT_CHANGED))
        
        # 返回事件列表，而不是简单的索引列表
        return key_events
        ```
2.  **修改 `find_key_frames` 方法**:
    *   确保此公有方法返回 `_detect_change_points` 产生的新事件列表 `List[Tuple[int, ChangeType]]`。

### **阶段二：改造 `BatchOCREngine`**

**目标**：适配新的事件输入，并向下游传递更丰富的信息。

1.  **修改 `recognize` 方法**:
    *   输入参数 `key_frame_indices` 应重命名为 `change_events`，其类型为 `List[Tuple[int, ChangeType]]`。
    *   **过滤需要OCR的帧**:
        ```python
        frames_to_ocr = [
            frame_idx for frame_idx, event_type in change_events 
            if event_type in [ChangeType.TEXT_APPEARED, ChangeType.CONTENT_CHANGED]
        ]
        # ...后续的解码和识别只针对 frames_to_ocr ...
        ```
    *   **改造返回结果**:
        *   OCR识别完成后，需要将识别文本与原始的`change_events`重新关联。
        *   最终返回给`后处理器`的数据结构应为：`{帧索引: (识别文本, 变化类型)}`。对于 `TEXT_DISAPPEARED` 事件，其文本值可以为`None`或空字符串。
        *   **示例返回**:
            ```python
            {
                100: ('文本A', ChangeType.TEXT_APPEARED),
                350: (None, ChangeType.TEXT_DISAPPEARED),
                500: ('文本B', ChangeType.TEXT_APPEARED)
            }
            ```

### **阶段三：重构 `Postprocessor`**

**目标**：基于新的事件流，实现精确的片段构建逻辑。

1.  **修改 `format` 方法**:
    *   确保其能接收并正确解析阶段二产出的新 `ocr_results` 结构。
2.  **重写 `_build_segments` 方法**:
    *   这是本次重构的核心。
    *   **新逻辑**:
        ```python
        # 1. 将 ocr_results 字典按帧号排序成事件列表
        sorted_events = sorted(ocr_results.items())

        segments = []
        active_segment = None

        for i, (frame_idx, (text, event_type)) in enumerate(sorted_events):
            if event_type in [ChangeType.TEXT_APPEARED, ChangeType.CONTENT_CHANGED]:
                # 一个新字幕的开始，意味着上一个字幕的结束
                if active_segment:
                    active_segment['end_frame'] = frame_idx - 1
                    segments.append(active_segment)
                
                # 开始新的 active_segment
                active_segment = {
                    'start_frame': frame_idx,
                    'text': text,
                    'bbox': ... # bbox信息需要从ocr_results获取
                }

            elif event_type == ChangeType.TEXT_DISAPPEARED:
                # 字幕消失事件，明确地结束当前片段
                if active_segment:
                    active_segment['end_frame'] = frame_idx - 1
                    segments.append(active_segment)
                    active_segment = None # 结束了，进入空白期

        # 循环结束后，处理最后一段有效的字幕
        if active_segment:
            active_segment['end_frame'] = total_frames - 1
            segments.append(active_segment)

        return segments
        ```
3.  **确认 `_clean_and_format_segments`**:
    *   此方法的逻辑（转换时间戳、过滤短字幕）基本无需改动，可以复用。

## 5. 预期成果

*   流水线将能够精确识别字幕的开始和结束时间点，即使字幕结束后是长时间的空白。
*   输出的 `.precise.json` 文件中的 `startTime` 和 `endTime` 将具有更高的准确性。
*   整体字幕提取质量得到显著提升。

## 6. 风险与回滚计划

*   **风险**: 本次重构涉及三个核心模块之间的数据契约变更，任何一个环节出错都可能导致流水线中断。
*   **施工建议**:
    1.  **创建新分支**: 所有修改都应在新的Git分支（如 `feature/timeline-accuracy`）上进行，不要直接修改主分支。
    2.  **分步验证**: 每完成一个阶段的改造，建议在该模块的出口处添加 `print` 语句，手动验证其输出的数据结构是否符合新设计的要求。
    3.  **端到端测试**: 全部改造完成后，使用一个包含“淡入淡出”和“长空白期”的测试视频进行完整的端到端测试，验证最终输出的字幕文件是否准确。
*   **回滚计划**: 如果在测试中发现严重问题且难以快速修复，只需切换回修改前的主分支，即可立即恢复到原始的、稳定的版本。