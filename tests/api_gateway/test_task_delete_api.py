from fastapi.testclient import TestClient

from services.api_gateway.app import main, single_task_api
from services.api_gateway.app.single_task_models import (
    TaskDeletionResult,
    TaskDeletionStatus,
    ResourceDeletionItem,
    DeletionResource,
    DeletionResourceStatus,
)


class _StubExecutor:
    def __init__(self, state_status: str, deletion_result: TaskDeletionResult):
        self.state_status = state_status
        self.deletion_result = deletion_result
        self.call_count = 0

    def get_task_status(self, task_id: str):
        return {
            "task_id": task_id,
            "status": self.state_status,
            "shared_storage_path": f"/share/workflows/{task_id}",
        }

    def delete_task(self, task_id: str, force: bool = False):
        self.call_count += 1
        return self.deletion_result


def test_delete_idempotent_three_times(monkeypatch):
    result = TaskDeletionResult(
        status=TaskDeletionStatus.SUCCESS,
        results=[
            ResourceDeletionItem(
                resource=DeletionResource.LOCAL_DIRECTORY,
                status=DeletionResourceStatus.DELETED,
                message="目录已删除",
            ),
            ResourceDeletionItem(
                resource=DeletionResource.REDIS,
                status=DeletionResourceStatus.SKIPPED,
                message="键不存在",
            ),
            ResourceDeletionItem(
                resource=DeletionResource.MINIO,
                status=DeletionResourceStatus.SKIPPED,
                message="无对象",
            ),
        ],
        warnings=None,
        timestamp="2025-01-01T00:00:00Z",
    )
    executor = _StubExecutor(state_status="completed", deletion_result=result)

    monkeypatch.setattr(single_task_api, "get_single_task_executor", lambda: executor)

    client = TestClient(main.app)

    for _ in range(3):
        resp = client.post("/v1/tasks/task-demo/delete", json={"force": False})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == TaskDeletionStatus.SUCCESS.value
        assert len(body["results"]) == 3

    assert executor.call_count == 3


def test_delete_partial_failed_with_retriable(monkeypatch):
    result = TaskDeletionResult(
        status=TaskDeletionStatus.PARTIAL_FAILED,
        results=[
            ResourceDeletionItem(
                resource=DeletionResource.LOCAL_DIRECTORY,
                status=DeletionResourceStatus.DELETED,
                message="目录已删除",
            ),
            ResourceDeletionItem(
                resource=DeletionResource.REDIS,
                status=DeletionResourceStatus.DELETED,
            ),
            ResourceDeletionItem(
                resource=DeletionResource.MINIO,
                status=DeletionResourceStatus.FAILED,
                message="MinIO 不可用",
                retriable=True,
            ),
        ],
        warnings=["MinIO 不可用，建议重试"],
        timestamp="2025-01-01T00:00:00Z",
    )
    executor = _StubExecutor(state_status="failed", deletion_result=result)
    monkeypatch.setattr(single_task_api, "get_single_task_executor", lambda: executor)

    client = TestClient(main.app)
    resp = client.post("/v1/tasks/task-demo/delete", json={"force": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == TaskDeletionStatus.PARTIAL_FAILED.value
    minio_item = next(
        item for item in body["results"] if item["resource"] == DeletionResource.MINIO.value
    )
    assert minio_item["status"] == DeletionResourceStatus.FAILED.value
    assert minio_item.get("retriable") is True
