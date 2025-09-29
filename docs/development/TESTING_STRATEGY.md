# YiVideo 测试策略文档 (Testing Strategy)

## 1. 测试理念与原则

本项目的测试策略遵循**测试金字塔 (Testing Pyramid)** 原则，旨在通过分层、自动化的测试来确保软件的质量、稳定性和性能。我们的目标是：

*   **尽早发现缺陷**：在开发周期中尽可能早地通过自动化测试捕获Bug。
*   **保障重构安全**：为代码库提供全面的测试覆盖，使开发者可以放心地进行重构和优化。
*   **确保功能正确**：验证系统是否满足 `PRD.md` 中定义的所有功能和非功能性需求。
*   **自动化优先**：所有可自动化的测试都应纳入CI/CD流水线，减少手动回归测试的成本。

测试金字塔结构分为三层：单元测试（底部，数量最多）、集成测试（中间）、端到端测试（顶部，数量最少）。

## 2. 测试层级详解

### Level 1: 单元测试 (Unit Tests)

*   **目标**: 验证独立的、最小的功能单元（函数、类、方法）是否按预期工作。
*   **范围**:
    *   纯业务逻辑函数（例如：解析SRT文件的函数、合并字幕时间轴的算法）。
    *   工具类和辅助函数。
*   **核心原则**:
    *   **隔离性**: 测试必须在完全隔离的环境中运行，不依赖任何外部服务（如数据库、文件系统、网络API）。
    *   **Mock一切**: 所有外部依赖（如 `yt-dlp` 的调用、`PaddleOCR` 的识别引擎、`redis` 客户端）都必须使用 `unittest.mock` 进行模拟(Mock)。
*   **工具**: `pytest`, `pytest-mock`
*   **代码位置**: `tests/unit/`
*   **示例 (`tests/unit/test_subtitle_utils.py`)**:
    ```python
    from pipeline.utils import merge_overlapping_subtitles

    def test_merge_overlapping_lines():
        """测试当两个字幕条目时间重叠时，是否能被正确合并"""
        sub1 = {"start": 0.0, "end": 2.5, "text": "Hello"}
        sub2 = {"start": 2.0, "end": 4.0, "text": "World"}
        
        merged = merge_overlapping_subtitles([sub1, sub2])
        
        assert len(merged) == 1
        assert merged[0]["start"] == 0.0
        assert merged[0]["end"] == 4.0
        assert merged[0]["text"] == "Hello World"
    ```

### Level 2: 集成测试 (Integration Tests)

*   **目标**: 验证单个微服务内部，其组件之间以及与外部基础设施（如Redis、文件系统）的交互是否正确。
*   **范围**:
    *   测试一个完整的Celery任务的执行流程。
    *   测试服务与数据库、消息队列的连接和数据读写。
    *   测试服务对共享数据卷的读写操作。
*   **核心原则**:
    *   **真实依赖**: 在测试环境中启动该服务所依赖的真实基础设施（如通过`docker-compose`启动一个测试专用的Redis容器）。
    *   **服务隔离**: 一次只测试一个服务，其他微服务不启动。如果需要其他服务的产出，应通过预置数据（pre-provisioned data）的方式提供。
*   **工具**: `pytest`, `docker-compose`
*   **代码位置**: `tests/integration/`
*   **示例 (`tests/integration/test_downloader_service.py`)**:
    ```python
    from yivideo_client.tasks import download_video
    import os

    def test_download_task_success(task_id, shared_workspace):
        """
        测试下载任务能否成功下载一个视频文件到共享工作区。
        'shared_workspace' 是一个 pytest fixture，提供一个临时的、隔离的测试目录。
        """
        test_url = "https://example.com/test_video.mp4" # 使用一个已知的小型测试视频URL
        
        # 异步执行任务并等待结果
        result = download_video.apply(args=[test_url, task_id], task_id=task_id)
        
        # 验证任务成功
        assert result.successful()
        
        # 验证产出
        video_id = result.get() # e.g., "task_id/source.mp4"
        expected_file_path = os.path.join(shared_workspace, video_id)
        assert os.path.exists(expected_file_path)
        assert os.path.getsize(expected_file_path) > 0
    ```

### Level 3: 端到端测试 (End-to-End Tests)

*   **目标**: 模拟真实用户场景，验证一个完整的业务流程是否能在整个系统（包含所有微服务）中正确运行。
*   **范围**:
    *   从API网关发起请求，到最终结果产出。
    *   测试跨多个服务的复杂工作流（如：下载 -> OCR -> 翻译）。
*   **核心原则**:
    *   **黑盒测试**: 将整个系统视为一个黑盒，只通过公开的API接口进行交互和验证。
    *   **真实环境**: 使用`docker-compose`启动包含所有服务的完整应用环境。
*   **工具**: `pytest`, `requests`
*   **代码位置**: `tests/e2e/`
*   **示例 (`tests/e2e/test_full_workflow.py`)**:
    ```python
    import requests
    import time

    API_URL = "http://localhost:8000"

    def test_full_ocr_workflow():
        """测试从提交URL到获取OCR结果的完整流程"""
        # 1. 发起任务
        response = requests.post(f"{API_URL}/tasks", json={
            "url": "https://example.com/test_video.mp4",
            "actions": ["download", "ocr"]
        })
        assert response.status_code == 202
        task_id = response.json()["task_id"]

        # 2. 轮询任务状态
        final_status = {}
        for _ in range(60): # 最多等待60秒
            time.sleep(1)
            response = requests.get(f"{API_URL}/tasks/{task_id}")
            status_data = response.json()
            if status_data["state"] in ["SUCCESS", "FAILURE"]:
                final_status = status_data
                break
        
        # 3. 验证结果
        assert final_status.get("state") == "SUCCESS"
        results = final_status.get("results", {})
        assert "video" in results
        assert "subtitle" in results
        # 可选：进一步检查共享卷中的文件内容
    ```

## 3. 特殊测试策略

### 3.1. GPU 密集型任务测试

由于GPU资源昂贵且在标准CI环境中不常见，我们采用分层策略：

1.  **单元测试层**: 严格使用Mock，完全不触碰GPU。测试调用`PaddleOCR`之前的逻辑（如参数准备）和之后的逻辑（如结果处理）。
2.  **集成测试层**:
    *   **CPU模式运行**: 如果可能，在CPU模式下运行`PaddleOCR`进行基本的集成测试。
    *   **专用Runner**: 在CI/CD中配置一个带有GPU的专用执行器（Runner）。这类测试可以被标记为`@pytest.mark.gpu`，并且只在特定条件下（如夜间构建或手动触发）运行。
3.  **`gpu_lock`机制测试**: 专门编写集成测试，并发地启动两个需要GPU的任务，并验证其中一个任务会等待，直到另一个任务释放锁。

## 4. 持续集成 (CI/CD) 策略

1.  **On Pull Request (每次提交代码)**:
    *   执行所有**单元测试**。
    *   执行所有**非GPU**的**集成测试**。
    *   运行代码风格检查（`flake8`）和静态类型检查（`mypy`）。
    *   **目标**: 快速反馈，保证合入主分支的代码质量。

2.  **On Merge to `main` (合并到主分支)**:
    *   执行上述所有测试。
    *   执行所有**端到端测试**。
    *   构建所有服务的Docker镜像并推送到镜像仓库。
    *   **目标**: 确保主分支始终处于可部署状态。

3.  **Nightly Build (每日夜间构建)**:
    *   在专用的GPU Runner上，执行完整的测试套件，包括所有被标记为`@pytest.mark.gpu`的测试。
    *   **目标**: 捕获与GPU环境相关的特定问题。
