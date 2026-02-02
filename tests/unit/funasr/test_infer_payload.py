from types import SimpleNamespace

import services.workers.funasr_service.app.funasr_infer as funasr_infer
from services.workers.funasr_service.app.funasr_infer import (
    build_infer_payload,
    main,
    normalize_model_output,
    parse_hotwords,
    run_infer,
)


def test_build_infer_payload_base_fields():
    payload = build_infer_payload(
        text="hi",
        language="en",
        audio_duration=1.2,
        time_stamps=[],
        segments=[],
        speaker=None,
        extra={"lid": "en"},
        transcribe_duration=0.3,
    )
    assert payload["text"] == "hi"
    assert payload["audio_duration"] == 1.2


def test_normalize_model_output_sentence_info():
    raw = {"sentence_info": [{"start": 0.0, "end": 1.0, "text": "hi", "spk": "S1"}]}
    payload = normalize_model_output(raw)
    assert payload["segments"][0]["speaker"] == "S1"


def test_normalize_model_output_time_stamps():
    raw = {"text": "hi", "time_stamps": [{"text": "hi", "start": 0.0, "end": 1.0}]}
    payload = normalize_model_output(raw)
    assert payload["time_stamps"]


def test_normalize_model_output_time_stamp_alias():
    raw = {"time_stamp": [{"text": "hi", "start": 0.0, "end": 1.0}]}
    payload = normalize_model_output(raw)
    assert payload["time_stamps"]


def test_parse_hotwords_accepts_json_and_csv():
    assert parse_hotwords('["magic","open"]') == ["magic", "open"]
    assert parse_hotwords("magic,open") == ["magic", "open"]
    assert parse_hotwords("magic") == ["magic"]


def test_run_infer_writes_payload(tmp_path):
    class FakeModel:
        def generate(self, **kwargs):
            return [
                {
                    "text": "hi",
                    "time_stamps": [{"text": "hi", "start": 0.0, "end": 1.0}],
                }
            ]

    def fake_loader(**kwargs):
        return FakeModel()

    output_file = tmp_path / "out.json"
    args = SimpleNamespace(
        audio_path="/tmp/demo.wav",
        output_file=str(output_file),
        model_name="paraformer-zh",
        device="cpu",
        enable_word_timestamps=True,
        vad_model=None,
        punc_model=None,
        spk_model=None,
        language="en",
        hotwords=None,
        batch_size_s=None,
        use_itn=None,
        merge_vad=None,
        merge_length_s=None,
        trust_remote_code=None,
        remote_code=None,
        model_revision=None,
        vad_model_revision=None,
        punc_model_revision=None,
        spk_model_revision=None,
        lm_model=None,
        lm_weight=None,
        beam_size=None,
    )
    payload = run_infer(args, model_loader=fake_loader)
    assert payload["text"] == "hi"
    assert output_file.exists()


def test_main_writes_output(tmp_path):
    class FakeModel:
        def generate(self, **kwargs):
            return [{"text": "ok"}]

    def fake_loader(**kwargs):
        return FakeModel()

    output_file = tmp_path / "out.json"
    payload = main(
        argv=[
            "--audio_path",
            "/tmp/demo.wav",
            "--output_file",
            str(output_file),
            "--model_name",
            "paraformer-zh",
            "--device",
            "cpu",
        ],
        model_loader=fake_loader,
    )
    assert payload["text"] == "ok"
    assert output_file.exists()


def test_run_infer_retry_with_remote_code(tmp_path, monkeypatch):
    class FakeModel:
        def generate(self, **kwargs):
            return [{"text": "ok"}]

    def fake_loader(**kwargs):
        if not kwargs.get("remote_code"):
            raise AssertionError("FunASRNano is not registered")
        return FakeModel()

    remote_code_path = tmp_path / "model.py"
    remote_code_path.write_text("# dummy")

    monkeypatch.setattr(
        funasr_infer,
        "resolve_remote_code_path",
        lambda *_args, **_kwargs: str(remote_code_path),
    )
    monkeypatch.setattr(funasr_infer, "get_audio_duration", lambda *_: 0.0)

    output_file = tmp_path / "out.json"
    args = SimpleNamespace(
        audio_path="/tmp/demo.wav",
        output_file=str(output_file),
        model_name="FunAudioLLM/Fun-ASR-Nano-2512",
        device="cpu",
        enable_word_timestamps=True,
        vad_model=None,
        punc_model=None,
        spk_model=None,
        language="auto",
        hotwords=None,
        batch_size_s=None,
        use_itn=None,
        merge_vad=None,
        merge_length_s=None,
        trust_remote_code=True,
        remote_code=None,
        model_revision=None,
        vad_model_revision=None,
        punc_model_revision=None,
        spk_model_revision=None,
        lm_model=None,
        lm_weight=None,
        beam_size=None,
    )

    payload = run_infer(args, model_loader=fake_loader)
    assert payload["text"] == "ok"
    assert output_file.exists()
