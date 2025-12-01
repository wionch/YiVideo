# 变更：为WService字幕处理节点增加input_data参数支持

## 为什么

目前YiVideo工作流系统中的三个WService字幕处理节点存在以下限制：

1. **`wservice.merge_speaker_segments`**: 完全依赖工作流上下文从上游阶段自动获取数据，硬编码从 `faster_whisper.transcribe_audio` 和 `pyannote_audio.diarize_speakers` 获取输出
2. **`wservice.merge_with_word_timestamps`**: 与 `merge_speaker_segments` 相同问题，完全依赖硬编码的上游节点
3. **`wservice.prepare_tts_segments`**: 虽然有 `_get_segments_from_source_stages` 函数用于自动搜索源数据，但不支持显式的input_data参数传入

**问题影响**：
- 这些节点无法在单任务模式下独立运行
- 用户无法通过input_data显式传入数据源，必须依赖工作流上下文
- 不符合YiVideo"配置而非编码"的核心设计理念
- 限制了工作流的灵活性和复用性

## 什么会改变

### 需要修改的节点

#### 1. `wservice.merge_speaker_segments`

**新增参数**：
- `segments_file` (string, 可选): 转录数据文件路径，支持 `${{...}}` 动态引用
- `diarization_file` (string, 可选): 说话人分离数据文件路径，支持 `${{...}}` 动态引用
- `segments_data` (array, 可选): 直接传入转录片段数据（JSON格式）
- `speaker_segments_data` (array, 可选): 直接传入说话人片段数据（JSON格式）

**参数优先级**：
1. 显式传入的节点参数（segments_data/speaker_segments_data）
2. 显式传入的文件路径参数（segments_file/diarization_file）
3. input_data中的参数
4. 上游节点输出（faster_whisper.transcribe_audio / pyannote_audio.diarize_speakers）
5. 默认值（抛出错误）

#### 2. `wservice.merge_with_word_timestamps`

**新增参数**：
- `segments_file` (string, 可选): 包含词级时间戳的转录数据文件路径，支持 `${{...}}` 动态引用
- `diarization_file` (string, 可选): 说话人分离数据文件路径，支持 `${{...}}` 动态引用
- `segments_data` (array, 可选): 直接传入转录片段数据（必须包含词级时间戳）
- `speaker_segments_data` (array, 可选): 直接传入说话人片段数据（JSON格式）

**参数优先级**：
1. 显式传入的节点参数（segments_data/speaker_segments_data）
2. 显式传入的文件路径参数（segments_file/diarization_file）
3. input_data中的参数
4. 上游节点输出（faster_whisper.transcribe_audio / pyannote_audio.diarize_speakers）
5. 默认值（抛出错误）

#### 3. `wservice.prepare_tts_segments`

**增强参数**：
- `segments_file` (string, 可选): 字幕片段数据文件路径，支持 `${{...}}` 动态引用
- `segments_data` (array, 可选): 直接传入字幕片段数据（JSON格式）
- `source_stage_names` (array, 可选): 自定义源阶段名称列表，替代默认搜索列表

**参数优先级**：
1. 显式传入的节点参数（segments_data）
2. 显式传入的文件路径参数（segments_file）
3. input_data中的参数
4. 从指定或默认源阶段搜索（_get_segments_from_source_stages）

### 实现方案

#### 采用现有的统一参数管理模块

**重要发现**：项目已经拥有完善的统一参数管理模块 `services.common.parameter_resolver`：

- **`resolve_parameters()`**: 解析节点参数中的 `${{...}}` 动态引用
- **`get_param_with_fallback()`**: 智能参数获取，支持多级回退机制
- **参数优先级**: node_params → input_data → 上游节点 → 默认值

其他所有服务（pyannote_audio_service、indextts_service、ffmpeg_service、paddleocr_service）都已经采用此模式。

#### 标准化实现流程

为三个WService节点采用标准的参数获取流程：

```python
def enhanced_task_implementation(self, context: dict) -> dict:
    """采用标准化参数解析的任务实现"""
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)
    
    try:
        # 1. 标准化参数解析（采用项目标准模式）
        from services.common.parameter_resolver import resolve_parameters, get_param_with_fallback
        
        node_params = workflow_context.input_params.get('node_params', {}).get(stage_name, {})
        if node_params:
            resolved_params = resolve_parameters(node_params, workflow_context.model_dump())
            logger.info(f"[{stage_name}] 参数解析完成: {resolved_params}")
        else:
            resolved_params = {}
        
        # 记录实际使用的输入参数
        recorded_input_params = resolved_params.copy()
        
        # 2. 使用 get_param_with_fallback 获取参数（支持完整回退机制）
        if stage_name == 'wservice.merge_speaker_segments':
            return self._handle_merge_speaker_parameters(resolved_params, workflow_context, recorded_input_params)
        elif stage_name == 'wservice.merge_with_word_timestamps':
            return self._handle_merge_word_timestamps_parameters(resolved_params, workflow_context, recorded_input_params)
        elif stage_name == 'wservice.prepare_tts_segments':
            return self._handle_prepare_tts_parameters(resolved_params, workflow_context, recorded_input_params)
            
    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
    finally:
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)
    
    return workflow_context.model_dump()
```

#### 具体参数获取逻辑

**merge_speaker_segments 示例**：
```python
def _handle_merge_speaker_parameters(self, resolved_params, workflow_context, recorded_input_params):
    """处理merge_speaker_segments的参数获取逻辑"""
    
    # 1. 尝试直接获取片段数据
    transcript_segments = get_param_with_fallback(
        "segments_data", 
        resolved_params, 
        workflow_context,
        fallback_from_input_data=True
    )
    
    speaker_segments = get_param_with_fallback(
        "speaker_segments_data", 
        resolved_params, 
        workflow_context,
        fallback_from_input_data=True
    )
    
    # 2. 如果没有直接数据，尝试文件路径
    if not transcript_segments:
        segments_file = get_param_with_fallback(
            "segments_file", 
            resolved_params, 
            workflow_context,
            fallback_from_input_data=True
        )
        if segments_file:
            transcript_segments = load_segments_from_file(segments_file)
            recorded_input_params['segments_file'] = segments_file
    
    if not speaker_segments:
        diarization_file = get_param_with_fallback(
            "diarization_file", 
            resolved_params, 
            workflow_context,
            fallback_from_input_data=True
        )
        if diarization_file:
            speaker_data = load_speaker_data_from_file(diarization_file)
            speaker_segments = speaker_data.get('speaker_enhanced_segments')
            recorded_input_params['diarization_file'] = diarization_file
    
    # 3. 最后回退到原有逻辑
    if not transcript_segments:
        transcribe_stage = workflow_context.stages.get('faster_whisper.transcribe_audio')
        transcript_segments = get_segments_data(transcribe_stage.output, 'segments')
        recorded_input_params['fallback_source'] = 'faster_whisper.transcribe_audio'
    
    if not speaker_segments:
        diarize_stage = workflow_context.stages.get('pyannote_audio.diarize_speakers')
        speaker_segments = get_speaker_data(diarize_stage.output).get('speaker_enhanced_segments')
        recorded_input_params['fallback_source'] = 'pyannote_audio.diarize_speakers'
    
    # 记录最终使用的参数
    workflow_context.stages[self.name].input_params = recorded_input_params
    
    # 验证数据并执行合并逻辑...
```

### 单任务模式调用示例

#### 示例1：merge_speaker_segments直接传数据
```json
{
    "task_name": "wservice.merge_speaker_segments",
    "input_data": {
        "segments_data": [
            {"start": 0.0, "end": 3.5, "text": "这是第一段字幕"},
            {"start": 4.0, "end": 7.2, "text": "这是第二段字幕"}
        ],
        "speaker_segments_data": [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
            {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01"}
        ]
    }
}
```

#### 示例2：merge_with_word_timestamps通过文件路径
```json
{
    "task_name": "wservice.merge_with_word_timestamps", 
    "input_data": {
        "segments_file": "/share/transcription/segments_with_words.json",
        "diarization_file": "/share/diarization/speaker_segments.json"
    }
}
```

#### 示例3：prepare_tts_segments使用动态引用
```json
{
    "task_name": "wservice.prepare_tts_segments",
    "input_data": {
        "segments_data": "${{ stages.wservice.merge_speaker_segments.output.merged_segments }}"
    }
}
```

## 影响

### 受影响的文件

#### 代码文件
- `services/workers/wservice/app/tasks.py` - 主要修改文件
- `services/common/parameter_resolver.py` - 可能需要轻微调整（如有新需求）

#### 文档文件  
- `docs/technical/reference/WORKFLOW_NODES_REFERENCE.md` - 更新三个节点的参数说明

### 兼容性评估
- **向后兼容**: ✅ 完全兼容，现有工作流不受影响
- **破坏性变更**: ❌ 无，所有变更都是新增可选参数
- **API变更**: ✅ 增强现有API，增加可选参数支持

### 风险评估
- **低风险**: 参数获取逻辑已经成熟，只需要在现有基础上增加支持
- **回退方案**: 如果出现问题，可以回退到原有逻辑
- **测试覆盖**: 需要针对新参数获取路径进行充分测试

## 验证标准

1. **参数解析正确性**: 新参数能够正确从input_data获取和解析
2. **向后兼容性**: 现有工作流模式不受影响，继续正常工作
3. **动态引用支持**: input_data中的参数支持 `${{...}}` 动态引用语法
4. **错误处理**: 当必需参数缺失时，能够提供清晰的错误信息
5. **文档一致性**: 文档描述与代码实现完全一致
6. **单任务模式**: 所有三个节点都能在单任务模式下独立运行

### 验收测试

#### 测试场景1：input_data直接传数据
- 调用 `wservice.merge_speaker_segments` 传入 `segments_data` 和 `speaker_segments_data`
- 验证能够正确处理并返回合并结果

#### 测试场景2：input_data传文件路径
- 调用 `wservice.merge_with_word_timestamps` 传入 `segments_file` 和 `diarization_file`
- 验证能够从文件加载数据并处理

#### 测试场景3：动态引用
- 在工作流中调用 `wservice.prepare_tts_segments` 使用 `${{...}}` 引用上游节点输出
- 验证动态引用能够正确解析

#### 测试场景4：向后兼容
- 使用现有工作流配置验证三个节点的原始功能不受影响
- 确保所有现有测试用例继续通过

## 技术细节

### 文件加载逻辑
扩展现有的 `load_segments_from_file` 和 `load_speaker_data_from_file` 函数以支持新的数据结构。

### 参数验证
为每个节点添加必要的数据格式验证：
- segments数据必须包含start、end、text字段
- speaker_segments数据必须包含start、end、speaker字段  
- 词级时间戳数据必须包含words字段

### 错误处理增强
- 详细的参数缺失错误信息
- 数据格式验证错误提示
- 文件路径不存在时的友好错误信息
