# Design Patterns

*Detected patterns from C3.1 analysis*

## /opt/wionch/docker/Skill_Seekers/.skillseeker-cache/qwen3-asr/repos/0_QwenLM_Qwen3-ASR/finetuning/qwen3_asr_sft.py

### Command

- **Class**: `DataCollatorForQwen3ASRFinetuning`
- **Confidence**: 0.50

## /opt/wionch/docker/Skill_Seekers/.skillseeker-cache/qwen3-asr/repos/0_QwenLM_Qwen3-ASR/qwen_asr/core/transformers_backend/configuration_qwen3_asr.py

### Strategy

- **Class**: `Qwen3ASRAudioEncoderConfig`
- **Confidence**: 0.50

### Strategy

- **Class**: `Qwen3ASRTextConfig`
- **Confidence**: 0.50

### Strategy

- **Class**: `Qwen3ASRThinkerConfig`
- **Confidence**: 0.50

### Factory

- **Class**: `Qwen3ASRConfig`
- **Confidence**: 0.60

### Strategy

- **Class**: `Qwen3ASRConfig`
- **Confidence**: 0.70

## /opt/wionch/docker/Skill_Seekers/.skillseeker-cache/qwen3-asr/repos/0_QwenLM_Qwen3-ASR/qwen_asr/core/transformers_backend/modeling_qwen3_asr.py

### Adapter

- **Class**: `Qwen3ASRTextRMSNorm`
- **Confidence**: 0.50

### Strategy

- **Class**: `Qwen3ASRTextRMSNorm`
- **Confidence**: 0.50

### Decorator

- **Class**: `Qwen3ASRTextAttention`
- **Confidence**: 0.30

### Strategy

- **Class**: `Qwen3ASRTextAttention`
- **Confidence**: 0.70

### Strategy

- **Class**: `Qwen3ASRTextMLP`
- **Confidence**: 0.70

### Decorator

- **Class**: `Qwen3ASRThinkerTextDecoderLayer`
- **Confidence**: 0.30

### Strategy

- **Class**: `Qwen3ASRThinkerTextDecoderLayer`
- **Confidence**: 0.70

### Strategy

- **Class**: `Qwen3ASRPreTrainedModel`
- **Confidence**: 0.90

### Factory

- **Class**: `Qwen3ASRPreTrainedModelForConditionalGeneration`
- **Confidence**: 0.90

### Adapter

- **Class**: `Qwen3ASRPreTrainedModelForConditionalGeneration`
- **Confidence**: 0.50

### Strategy

- **Class**: `Qwen3ASRPreTrainedModelForConditionalGeneration`
- **Confidence**: 0.50

### TemplateMethod

- **Class**: `Qwen3ASRPreTrainedModelForConditionalGeneration`
- **Confidence**: 0.60

### Strategy

- **Class**: `Qwen3ASRAudioAttention`
- **Confidence**: 0.70

### Strategy

- **Class**: `Qwen3ASRAudioEncoderLayer`
- **Confidence**: 0.70

### Strategy

- **Class**: `SinusoidsPositionEmbedding`
- **Confidence**: 0.70

### Factory

- **Class**: `Qwen3ASRAudioEncoder`
- **Confidence**: 0.60

### Decorator

- **Class**: `Qwen3ASRAudioEncoder`
- **Confidence**: 0.30

### Adapter

- **Class**: `Qwen3ASRAudioEncoder`
- **Confidence**: 0.50

### Strategy

- **Class**: `Qwen3ASRAudioEncoder`
- **Confidence**: 0.50

### Decorator

- **Class**: `Qwen3ASRThinkerTextRotaryEmbedding`
- **Confidence**: 0.30

### Adapter

- **Class**: `Qwen3ASRThinkerTextRotaryEmbedding`
- **Confidence**: 0.50

### Strategy

- **Class**: `Qwen3ASRThinkerTextRotaryEmbedding`
- **Confidence**: 0.50

### Strategy

- **Class**: `Qwen3ASRThinkerTextMLP`
- **Confidence**: 0.70

### Adapter

- **Class**: `Qwen3ASRThinkerTextRMSNorm`
- **Confidence**: 0.50

### Strategy

- **Class**: `Qwen3ASRThinkerTextRMSNorm`
- **Confidence**: 0.50

### Decorator

- **Class**: `Qwen3ASRThinkerTextAttention`
- **Confidence**: 0.30

### Strategy

- **Class**: `Qwen3ASRThinkerTextAttention`
- **Confidence**: 0.70

### Decorator

- **Class**: `Qwen3ASRThinkerTextModel`
- **Confidence**: 0.30

### Strategy

- **Class**: `Qwen3ASRThinkerTextModel`
- **Confidence**: 0.70

### Factory

- **Class**: `Qwen3ASRThinkerForConditionalGeneration`
- **Confidence**: 0.90

### Decorator

- **Class**: `Qwen3ASRThinkerForConditionalGeneration`
- **Confidence**: 0.30

### Adapter

- **Class**: `Qwen3ASRThinkerForConditionalGeneration`
- **Confidence**: 0.50

### Strategy

- **Class**: `Qwen3ASRThinkerTextPreTrainedModel`
- **Confidence**: 0.50

### Decorator

- **Class**: `Qwen3ASRForConditionalGeneration`
- **Confidence**: 0.30

### Adapter

- **Class**: `Qwen3ASRForConditionalGeneration`
- **Confidence**: 0.50

### Strategy

- **Class**: `Qwen3ASRForConditionalGeneration`
- **Confidence**: 0.50

## /opt/wionch/docker/Skill_Seekers/.skillseeker-cache/qwen3-asr/repos/0_QwenLM_Qwen3-ASR/qwen_asr/core/transformers_backend/processing_qwen3_asr.py

### ChainOfResponsibility

- **Class**: `Qwen3ASRProcessorKwargs`
- **Confidence**: 0.60

### Factory

- **Class**: `Qwen3ASRProcessor`
- **Confidence**: 0.60

### Decorator

- **Class**: `Qwen3ASRProcessor`
- **Confidence**: 0.30

### Adapter

- **Class**: `Qwen3ASRProcessor`
- **Confidence**: 0.50

### Command

- **Class**: `Qwen3ASRProcessor`
- **Confidence**: 0.70

### ChainOfResponsibility

- **Class**: `Qwen3ASRProcessor`
- **Confidence**: 0.60

## /opt/wionch/docker/Skill_Seekers/.skillseeker-cache/qwen3-asr/repos/0_QwenLM_Qwen3-ASR/qwen_asr/core/vllm_backend/qwen3_asr.py

### Strategy

- **Class**: `SinusoidsPositionEmbedding`
- **Confidence**: 0.70

### Strategy

- **Class**: `Qwen3ASRAudioAttention`
- **Confidence**: 0.70

### Strategy

- **Class**: `Qwen3ASRAudioEncoderLayer`
- **Confidence**: 0.70

### Factory

- **Class**: `Qwen3ASRAudioEncoder`
- **Confidence**: 0.60

### Decorator

- **Class**: `Qwen3ASRAudioEncoder`
- **Confidence**: 0.30

### Adapter

- **Class**: `Qwen3ASRAudioEncoder`
- **Confidence**: 0.50

### Strategy

- **Class**: `Qwen3ASRAudioEncoder`
- **Confidence**: 0.50

### Factory

- **Class**: `Qwen3ASRProcessingInfo`
- **Confidence**: 0.90

### Adapter

- **Class**: `Qwen3ASRProcessingInfo`
- **Confidence**: 0.50

### Factory

- **Class**: `Qwen3ASRDummyInputsBuilder`
- **Confidence**: 0.90

### Builder

- **Class**: `Qwen3ASRDummyInputsBuilder`
- **Confidence**: 0.70

### Factory

- **Class**: `Qwen3ASRMultiModalProcessor`
- **Confidence**: 0.90

### Adapter

- **Class**: `Qwen3ASRMultiModalProcessor`
- **Confidence**: 0.50

### Observer

- **Class**: `Qwen3ASRMultiModalProcessor`
- **Confidence**: 0.65

### ChainOfResponsibility

- **Class**: `Qwen3ASRMultiModalProcessor`
- **Confidence**: 0.60

### Factory

- **Class**: `Qwen3ASRForConditionalGeneration`
- **Confidence**: 0.90

### Decorator

- **Class**: `Qwen3ASRForConditionalGeneration`
- **Confidence**: 0.30

### Adapter

- **Class**: `Qwen3ASRForConditionalGeneration`
- **Confidence**: 0.50

### Strategy

- **Class**: `Qwen3ASRForConditionalGeneration`
- **Confidence**: 0.50

### TemplateMethod

- **Class**: `Qwen3ASRForConditionalGeneration`
- **Confidence**: 0.50

## /opt/wionch/docker/Skill_Seekers/.skillseeker-cache/qwen3-asr/repos/0_QwenLM_Qwen3-ASR/qwen_asr/inference/qwen3_asr.py

### Factory

- **Class**: `Qwen3ASRModel`
- **Confidence**: 0.90

### Decorator

- **Class**: `Qwen3ASRModel`
- **Confidence**: 0.30

## /opt/wionch/docker/Skill_Seekers/.skillseeker-cache/qwen3-asr/repos/0_QwenLM_Qwen3-ASR/qwen_asr/inference/qwen3_forced_aligner.py

### ChainOfResponsibility

- **Class**: `Qwen3ForceAlignProcessor`
- **Confidence**: 0.60

### Factory

- **Class**: `ForcedAlignResult`
- **Confidence**: 0.50

### Factory

- **Class**: `Qwen3ForcedAligner`
- **Confidence**: 0.60

### Decorator

- **Class**: `Qwen3ForcedAligner`
- **Confidence**: 0.30

