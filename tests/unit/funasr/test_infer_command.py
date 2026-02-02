from services.workers.funasr_service.executors.transcribe_executor import (
    build_infer_command,
)


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
        hotwords=["magic"],
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
