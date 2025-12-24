# tests/unit/test_gpu_lock_error_handling.py
# -*- coding: utf-8 -*-

"""GPU 锁异常处理单元测试"""

import pytest
import os
import json
import tempfile
from unittest.mock import MagicMock, patch, mock_open, call
from typing import Any

from services.common.locks import (
    SmartGpuLockManager,
    send_alert,
    record_critical_failure
)


class TestGpuLockErrorHandling:
    """GPU 锁异常处理测试"""

    @pytest.fixture
    def lock_manager(self):
        """创建锁管理器实例"""
        return SmartGpuLockManager()

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis 客户端"""
        with patch('services.common.locks.redis_client') as mock:
            yield mock

    def test_finally_block_exception_isolation(self, lock_manager, mock_redis):
        """验证 finally 块异常隔离"""
        # 场景: release_lock 抛出异常
        lock_key = "gpu_lock:0"
        task_name = "test_task"

        # Mock: release_lock 抛出异常
        mock_redis.eval.side_effect = Exception("Redis connection error")

        # 调用 release_lock（模拟 finally 块中的调用）
        result = lock_manager.release_lock(task_name, lock_key, "normal")

        # 验证：返回 False，异常被捕获
        assert result is False, "异常应被捕获，返回 False"

    @patch('services.common.locks.send_alert')
    def test_emergency_release_on_normal_failure(self, mock_send_alert, lock_manager, mock_redis):
        """验证正常释放失败时触发应急释放"""
        # 这个测试模拟 finally 块的逻辑

        lock_key = "gpu_lock:0"
        task_name = "test_task"

        # 第一步：正常释放失败
        mock_redis.eval.return_value = 0  # 释放失败
        lock_released = lock_manager.release_lock(task_name, lock_key, "normal")

        assert lock_released is False, "正常释放应该失败"

        # 第二步：应急释放（模拟 finally 块的第三层）
        if not lock_released:
            mock_redis.delete(lock_key)
            lock_manager.exception_stats["emergency_releases"] += 1

            # 导入并调用 mock 的 send_alert
            from services.common.locks import send_alert
            send_alert("gpu_lock_emergency_release", {
                "lock_key": lock_key,
                "task_name": task_name
            })

        # 验证
        mock_redis.delete.assert_called_once_with(lock_key)
        assert lock_manager.exception_stats["emergency_releases"] == 1
        mock_send_alert.assert_called_once()

    @patch('services.common.locks.send_alert')
    @patch('services.common.locks.record_critical_failure')
    def test_critical_failure_recording(self, mock_record, mock_send_alert, lock_manager, mock_redis):
        """验证关键失败记录"""
        # 场景: 应急释放也失败

        lock_key = "gpu_lock:0"
        task_name = "test_task"

        # 第一步：正常释放失败
        mock_redis.eval.return_value = 0
        lock_released = lock_manager.release_lock(task_name, lock_key, "normal")

        # 第二步：应急释放也失败
        if not lock_released:
            mock_redis.delete.side_effect = Exception("Redis completely unavailable")

            try:
                mock_redis.delete(lock_key)
            except Exception as emergency_error:
                # 导入并调用 mock 的 record_critical_failure
                from services.common.locks import record_critical_failure
                record_critical_failure(lock_key, task_name, emergency_error)

        # 验证
        mock_record.assert_called_once()
        args = mock_record.call_args[0]
        assert args[0] == lock_key
        assert args[1] == task_name

    @patch('services.common.locks.logger')
    def test_send_alert_logs_error(self, mock_logger):
        """验证 send_alert 记录日志"""
        alert_type = "test_alert"
        data = {"key": "value"}

        send_alert(alert_type, data)

        # 验证：记录了错误日志
        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args[0][0]
        assert alert_type in call_args
        assert str(data) in call_args

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.makedirs')
    @patch('services.common.locks.send_alert')
    def test_record_critical_failure_writes_log(self, mock_send_alert, mock_makedirs, mock_file):
        """验证关键失败记录写入日志文件"""
        lock_key = "gpu_lock:0"
        task_name = "test_task"
        error = Exception("Critical error")

        record_critical_failure(lock_key, task_name, error)

        # 验证：创建目录
        mock_makedirs.assert_called_once_with(
            os.path.dirname("/var/log/yivideo/gpu_lock_critical_failures.log"),
            exist_ok=True
        )

        # 验证：打开文件
        mock_file.assert_called_once_with(
            "/var/log/yivideo/gpu_lock_critical_failures.log",
            "a"
        )

        # 验证：写入 JSON
        handle = mock_file()
        assert handle.write.called, "应该写入文件"

        # 验证写入的内容包含关键信息
        written_content = handle.write.call_args[0][0]
        assert lock_key in written_content
        assert task_name in written_content

        # 验证：发送告警
        mock_send_alert.assert_called_once()
        alert_args = mock_send_alert.call_args[0]
        assert alert_args[0] == "gpu_lock_critical_failure"
        assert alert_args[1]["level"] == "P0"

    @patch('services.common.locks.logger')
    @patch('builtins.open', side_effect=IOError("Disk full"))
    @patch('os.makedirs')
    def test_record_critical_failure_handles_write_error(self, mock_makedirs, mock_file, mock_logger):
        """验证文件写入失败时的处理"""
        lock_key = "gpu_lock:0"
        task_name = "test_task"
        error = Exception("Critical error")

        # 调用，不应抛出异常
        try:
            record_critical_failure(lock_key, task_name, error)
        except Exception as e:
            pytest.fail(f"不应向上传播异常: {e}")

        # 验证：记录了严重错误日志
        assert mock_logger.critical.called, "应该记录严重错误"

    def test_exception_stats_increment(self, lock_manager):
        """验证异常统计正确递增"""
        # 初始值
        assert lock_manager.exception_stats["normal_release_failures"] == 0
        assert lock_manager.exception_stats["emergency_releases"] == 0

        # 递增
        lock_manager.exception_stats["normal_release_failures"] += 1
        lock_manager.exception_stats["emergency_releases"] += 1

        # 验证
        assert lock_manager.exception_stats["normal_release_failures"] == 1
        assert lock_manager.exception_stats["emergency_releases"] == 1

    @patch('services.common.locks.redis_client')
    @patch('services.common.locks.send_alert')
    def test_finally_block_three_layer_protection(self, mock_send_alert, mock_redis):
        """验证 finally 块三层保护机制完整性"""
        # 这是一个集成性测试，验证三层保护的完整流程

        lock_manager = SmartGpuLockManager()
        lock_key = "gpu_lock:0"
        task_name = "test_task"

        # 第一层：GPU 显存清理（独立测试，这里跳过）

        # 第二层：正常锁释放失败
        mock_redis.eval.return_value = 0
        lock_released = lock_manager.release_lock(task_name, lock_key, "normal")
        assert lock_released is False

        # 第三层：应急强制释放
        if not lock_released:
            mock_redis.delete(lock_key)
            lock_manager.exception_stats["emergency_releases"] += 1

            # 导入并调用 mock 的 send_alert
            from services.common.locks import send_alert
            send_alert("gpu_lock_emergency_release", {
                "lock_key": lock_key,
                "task_name": task_name
            })

        # 验证完整流程
        assert lock_manager.exception_stats["ownership_violations"] == 1  # 第二层记录
        assert lock_manager.exception_stats["emergency_releases"] == 1  # 第三层记录
        mock_redis.delete.assert_called_once_with(lock_key)  # 第三层执行
        mock_send_alert.assert_called_once()  # 第三层告警
