import pytest

from services.api_gateway.app.single_task_api import get_supported_tasks


@pytest.mark.anyio
async def test_supported_tasks_includes_translate_subtitles():
    payload = await get_supported_tasks()
    supported = payload["supported_tasks"]
    assert "wservice.translate_subtitles" in supported.get("wservice", [])
