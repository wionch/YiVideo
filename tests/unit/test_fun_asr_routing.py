def test_fun_asr_registered():
    from services.api_gateway.app.single_task_api import TASK_CATEGORY_MAPPING

    assert "funasr" in TASK_CATEGORY_MAPPING
    assert "funasr.transcribe_audio" in TASK_CATEGORY_MAPPING["funasr"]
