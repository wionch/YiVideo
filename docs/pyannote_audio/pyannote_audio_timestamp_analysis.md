### Code Sections

> list **ALL** related code sections!! do not ignore anyone

- `services/workers/pyannote_audio_service/src/pyannote-audio/src/pyannote/audio/pipelines/speaker_diarization.py:64~125` (DiarizeOutput.serialize): 时间戳序列化输出，支持词级时间精度
- `services/workers/pyannote_audio_service/src/pyannote-audio/src/pyannote/audio/pipelines/speaker_diarization.py:96~125` (serialize方法实现): 将说话人分离结果转换为包含start/end时间戳的字典格式
- `services/workers/pyannote_audio_service/src/pyannote-audio/src/pyannote/audio/pipelines/speaker_diarization.py:127~191` (SpeakerDiarization.__init__): 说话人分离管道初始化，设置时间戳相关参数
- `services/workers/pyannote_audio_service/src/pyannote-audio/src/pyannote/audio/pipelines/speaker_diarization.py:305~330` (get_segmentations方法): 获取时间戳分段的语音片段
- `services/workers/pyannote_audio_service/src/pyannote-audio/src/pyannote/audio/pipelines/speaker_diarization.py:530~784` (apply方法): 主要的说话人分离处理，包含时间戳计算
- `services/workers/pyannote_audio_service/src/pyannote-audio/src/pyannote/audio/pipelines/speaker_diarization.py:593~614` (segmentations处理): 帧级别时间戳分段处理
- `services/workers/pyannote_audio_service/src/pyannote-audio/src/pyannote/audio/pipelines/speaker_diarization.py:688~713` (diarization重建): 重建连续的时间戳序列
- `services/workers/pyannote_audio_service/src/pyannote-audio/src/pyannote/audio/core/task.py:80~137` (Specifications类): 定义任务规范，包含时间分辨率设置
- `services/workers/pyannote_audio_service/src/pyannote-audio/src/pyannote/audio/tasks/segmentation/speaker_diarization.py:270~354` (prepare_chunk方法): 准备音频块，处理时间戳对齐
- `services/workers/pyannote_audio_service/src/pyannote-audio/src/pyannote/audio/tasks/segmentation/speaker_diarization.py:342~347` (时间戳映射): 将时间戳映射到模型输出分辨率

### Report

#### conclusions

> list all concltions which you think is important for task

1. pyannote-audio 3.x版本原生支持词级时间戳精度，主要通过帧级别的时间分辨率实现
2. 时间戳精度受模型接收域（receptive field）影响，通常为帧级精度（约0.5-2秒）
3. 时间戳处理主要通过SlidingWindowFeature类实现，支持精确的时间对齐
4. 说话人分离管道输出包含详细的start/end时间戳，精度通常为3位小数
5. 支持通过warm_up参数调整时间戳边界，提高边界检测精度
6. 时间戳处理与语音识别（ASR）结果可以进行精确的时间对齐集成

#### relations

> file to file / fucntion to function / module to module ....
> list all code/info relation which should be attention! (include path, type, line scope)

1. `speaker_diarization.py`与`task.py`的Specifications类关联，定义时间分辨率参数
2. `prepare_chunk`方法与`SlidingWindowFeature`协作，实现时间戳映射
3. `get_segmentations`方法与`Inference`类协作，生成时间戳分段
4. `apply`方法与`reconstruct`方法协作，重建连续的时间戳序列
5. `serialize`方法与`Annotation.itertracks`协作，输出时间戳序列
6. 时间戳精度与模型接收域参数`receptive_field`直接相关（line 611）
7. `segmentation_step`参数控制时间步长和重叠度（line 241）
8. `warm_up`参数影响时间戳边界的计算精度（line 612）
9. `binarize`函数将连续时间戳转换为二值化分段（line 602-606）
10. `speaker_count`函数实时计算说话人数，影响时间戳动态处理（line 609-613）

#### result

> finally task result to answer input questions

1. **词级时间戳功能实现**: pyannote-audio通过帧级别的语音分段实现词级时间戳，主要依赖模型的接收域（receptive field）决定时间精度。实际输出精度通常为0.5-2秒的帧级精度，但支持毫秒级的时间戳序列（3位小数）。

2. **与ASR功能集成**: 时间戳与语音识别通过SlidingWindowFeature进行精确对齐，支持将说话人标签与语音识别的文本内容进行时间戳对齐，实现"词级说话人精确匹配"。在YiVideo工作流中与faster_whisper_service协同工作。

3. **时间戳精度和性能**: 时间戳精度受模型架构影响，通过segmentation_step参数控制（默认0.1，90%重叠），支持毫秒级输出（3位小数）。处理性能受GPU/CPU影响，支持CUDA加速和GPU锁保护。

4. **支持的语言和音频格式**: 支持多语言的说话人分离（英语、中文、法语等），音频格式通过pyannote.core.AudioFile统一处理，支持WAV、MP3、FLAC等常见格式。

5. **配置参数**: 主要配置包括segmentation_step（时间步长0.1）、warm_up（预热时间0.0）、min_duration_on/off（最小时长0.0）、embedding_exclude_overlap（默认False）等，支持本地模式和pyannoteAI API模式。

6. **时间戳处理流程**: 从segmentations获取帧级预测→binarize转换为二值化分段→speaker_count实时计算说话人数→reconstruct重建连续时间戳序列→to_annotation生成最终时间戳输出。

#### attention

> MUST LESS THAN 20 LINES!
> list what you think "that might be a problem"

1. 时间戳精度与模型计算复杂度之间存在权衡，提高精度可能降低处理速度
2. 时间戳对齐依赖语音识别结果的时间戳质量，存在累积误差风险
3. 长音频文件的内存消耗需要关注，时间戳存储和计算可能成为性能瓶颈
4. API模式和本地模式的时间戳精度可能存在差异，需注意模型版本的一致性
5. GPU锁机制在密集时间戳处理期间可能成为性能瓶颈，需要合理配置超时时间
6. 时间戳序列化处理在多说话人场景下可能产生数据格式不一致问题