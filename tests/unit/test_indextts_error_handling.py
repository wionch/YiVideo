# tests/unit/test_indextts_error_handling.py
# -*- coding: utf-8 -*-

"""IndexTTS 错误处理单元测试"""

import pytest
from unittest.mock import MagicMock, patch, Mock

from services.workers.indextts_service.app.tasks import IndexTTSTask


class TestIndexTTSErrorHandling:
    """IndexTTS 错误处理测试"""

    @pytest.fixture
    def mock_gpu_lock_manager(self):
        """Mock GPU 锁管理器"""
        mock_manager = MagicMock()
        mock_manager.release_lock.return_value = True
        return mock_manager

    @pytest.fixture
    def indextts_task(self, mock_gpu_lock_manager):
        """创建 IndexTTS 任务实例"""
        task = IndexTTSTask()
        task.gpu_lock_manager = mock_gpu_lock_manager
        return task

    def test_indextts_on_failure_releases_lock(self, indextts_task, mock_gpu_lock_manager):
        """验证任务失败时释放锁"""
        # 准备测试数据
        exc = Exception("Test failure")
        task_id = "test_task_123"
        args = ()
        kwargs = {'gpu_id': 0}
        einfo = None

        # 调用 on_failure
        indextts_task.on_failure(exc, task_id, args, kwargs, einfo)

        # 验证：release_lock 被调用
        mock_gpu_lock_manager.release_lock.assert_called_once_with(
            task_id,
            "gpu_lock:0",
            "task_failure"
        )

    def test_indextts_on_failure_default_gpu_id(self, indextts_task, mock_gpu_lock_manager):
        """验证默认 GPU ID 为 0"""
        exc = Exception("Test failure")
        task_id = "test_task_456"
        args = ()
        kwargs = {}  # 没有 gpu_id
        einfo = None

        # 调用 on_failure
        indextts_task.on_failure(exc, task_id, args, kwargs, einfo)

        # 验证：使用默认 gpu_id=0
        mock_gpu_lock_manager.release_lock.assert_called_once_with(
            task_id,
            "gpu_lock:0",
            "task_failure"
        )

    def test_indextts_on_failure_custom_gpu_id(self, indextts_task, mock_gpu_lock_manager):
        """验证自定义 GPU ID"""
        exc = Exception("Test failure")
        task_id = "test_task_789"
        args = ()
        kwargs = {'gpu_id': 1}  # 自定义 GPU ID
        einfo = None

        # 调用 on_failure
        indextts_task.on_failure(exc, task_id, args, kwargs, einfo)

        # 验证：使用自定义 gpu_id=1
        mock_gpu_lock_manager.release_lock.assert_called_once_with(
            task_id,
            "gpu_lock:1",
            "task_failure"
        )

    def test_indextts_no_attribute_error(self, indextts_task):
        """验证不再抛出 AttributeError"""
        # 这是对旧 bug 的回归测试
        # 旧代码调用 force_release_lock() 会抛出 AttributeError

        exc = Exception("Test failure")
        task_id = "test_task_regression"
        args = ()
        kwargs = {'gpu_id': 0}
        einfo = None

        # 调用 on_failure，不应抛出 AttributeError
        try:
            indextts_task.on_failure(exc, task_id, args, kwargs, einfo)
        except AttributeError as e:
            pytest.fail(f"不应抛出 AttributeError: {e}")

    def test_indextts_on_failure_handles_release_exception(self, indextts_task, mock_gpu_lock_manager):
        """验证释放锁异常被正确处理"""
        # Mock: release_lock 抛出异常
        mock_gpu_lock_manager.release_lock.side_effect = Exception("Redis connection error")

        exc = Exception("Test failure")
        task_id = "test_task_exception"
        args = ()
        kwargs = {'gpu_id': 0}
        einfo = None

        # 调用 on_failure，不应向上传播异常
        try:
            indextts_task.on_failure(exc, task_id, args, kwargs, einfo)
        except Exception as e:
            pytest.fail(f"on_failure 不应向上传播异常: {e}")

        # 验证：release_lock 被调用
        mock_gpu_lock_manager.release_lock.assert_called_once()

    def test_indextts_on_failure_no_gpu_lock_manager(self):
        """验证没有 GPU 锁管理器时的处理"""
        task = IndexTTSTask()
        task.gpu_lock_manager = None  # 没有锁管理器

        exc = Exception("Test failure")
        task_id = "test_task_no_manager"
        args = ()
        kwargs = {'gpu_id': 0}
        einfo = None

        # 调用 on_failure，不应抛出异常
        try:
            task.on_failure(exc, task_id, args, kwargs, einfo)
        except Exception as e:
            pytest.fail(f"没有锁管理器时不应抛出异常: {e}")

    @patch('services.workers.indextts_service.app.tasks.logger')
    def test_indextts_on_failure_logs_error(self, mock_logger, indextts_task):
        """验证错误日志记录"""
        exc = Exception("Test failure")
        task_id = "test_task_logging"
        args = ()
        kwargs = {'gpu_id': 0}
        einfo = None

        # 调用 on_failure
        indextts_task.on_failure(exc, task_id, args, kwargs, einfo)

        # 验证：记录了错误日志
        assert mock_logger.error.call_count >= 1, "应该记录错误日志"

    def test_indextts_on_success(self, indextts_task):
        """验证成功回调正常工作"""
        retval = {"status": "success"}
        task_id = "test_task_success"
        args = ()
        kwargs = {}

        # 调用 on_success，不应抛出异常
        try:
            indextts_task.on_success(retval, task_id, args, kwargs)
        except Exception as e:
            pytest.fail(f"on_success 不应抛出异常: {e}")
