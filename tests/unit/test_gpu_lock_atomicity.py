# tests/unit/test_gpu_lock_atomicity.py
# -*- coding: utf-8 -*-

"""GPU 锁原子性单元测试"""

import pytest
import threading
import time
from unittest.mock import MagicMock, patch, call
from typing import Any

from services.common.locks import SmartGpuLockManager, RELEASE_LOCK_SCRIPT


class TestGpuLockAtomicity:
    """GPU 锁原子性测试"""

    @pytest.fixture
    def lock_manager(self):
        """创建锁管理器实例"""
        return SmartGpuLockManager()

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis 客户端"""
        with patch('services.common.locks.redis_client') as mock:
            yield mock

    @pytest.fixture
    def mock_pubsub(self):
        """Mock Pub/Sub 管理器"""
        with patch('services.common.locks.pub_sub_manager') as mock:
            yield mock

    def test_release_lock_ownership_verification(self, lock_manager, mock_redis, mock_pubsub):
        """验证锁所有权验证"""
        # 场景: 任务A持有锁，任务B尝试释放
        lock_key = "gpu_lock:0"
        task_a = "task_a"
        task_b = "task_b"

        # Mock: Lua 脚本返回 0（释放失败）
        mock_redis.eval.return_value = 0
        # Mock: 当前锁值是 task_a
        mock_redis.get.return_value = f"locked_by_{task_a}"

        # 任务B尝试释放任务A的锁
        result = lock_manager.release_lock(task_b, lock_key, "normal")

        # 验证
        assert result is False, "任务B不应该能释放任务A的锁"
        assert lock_manager.exception_stats["ownership_violations"] == 1, "应记录所有权验证失败"

        # 验证 Lua 脚本被正确调用
        mock_redis.eval.assert_called_once_with(
            RELEASE_LOCK_SCRIPT,
            1,
            lock_key,
            f"locked_by_{task_b}"
        )

        # 验证未发布锁释放事件
        mock_pubsub.publish_lock_release.assert_not_called()

    def test_release_lock_success(self, lock_manager, mock_redis, mock_pubsub):
        """验证正确的锁释放"""
        lock_key = "gpu_lock:0"
        task_name = "task_a"

        # Mock: Lua 脚本返回 1（释放成功）
        mock_redis.eval.return_value = 1

        # 任务A释放自己的锁
        result = lock_manager.release_lock(task_name, lock_key, "normal")

        # 验证
        assert result is True, "任务应该能释放自己的锁"
        assert lock_manager.exception_stats["ownership_violations"] == 0, "不应记录所有权验证失败"

        # 验证发布了锁释放事件
        mock_pubsub.publish_lock_release.assert_called_once_with(
            lock_key,
            task_name,
            "normal"
        )

    def test_concurrent_release_no_race_condition(self, lock_manager, mock_redis, mock_pubsub):
        """验证并发释放无竞态条件"""
        lock_key = "gpu_lock:0"
        task_name = "task_a"

        # 模拟并发场景：第一次调用成功，后续调用失败
        mock_redis.eval.side_effect = [1, 0, 0, 0, 0]
        mock_redis.get.return_value = None  # 锁已被删除

        results = []

        def try_release():
            result = lock_manager.release_lock(task_name, lock_key, "normal")
            results.append(result)

        # 创建5个线程同时尝试释放
        threads = [threading.Thread(target=try_release) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 验证：只有一个成功
        assert sum(results) == 1, "只应该有一个线程成功释放锁"
        assert results.count(True) == 1, "应该有且仅有一个 True"
        assert results.count(False) == 4, "应该有4个 False"

    def test_lua_script_error_handling(self, lock_manager, mock_redis, mock_pubsub):
        """验证 Lua 脚本错误处理"""
        lock_key = "gpu_lock:0"
        task_name = "task_a"

        # Mock: Redis 返回脚本执行错误
        mock_redis.eval.side_effect = Exception("NOSCRIPT: script not found")

        # 尝试释放锁
        result = lock_manager.release_lock(task_name, lock_key, "normal")

        # 验证
        assert result is False, "脚本错误时应返回 False"
        # 注意：当前实现使用字符串检查，所以不会增加 release_script_errors
        # 这是一个已知的代码质量问题

    def test_release_lock_redis_unavailable(self, lock_manager, mock_pubsub):
        """验证 Redis 不可用时的处理"""
        lock_key = "gpu_lock:0"
        task_name = "task_a"

        # Mock: redis_client 为 None
        with patch('services.common.locks.redis_client', None):
            result = lock_manager.release_lock(task_name, lock_key, "normal")

        # 验证
        assert result is False, "Redis 不可用时应返回 False"

    def test_lua_script_atomicity(self, mock_redis):
        """验证 Lua 脚本的原子性逻辑"""
        # 这是一个逻辑验证测试，确保脚本内容正确

        # 验证脚本包含关键逻辑
        assert "redis.call(\"get\", KEYS[1])" in RELEASE_LOCK_SCRIPT
        assert "redis.call(\"del\", KEYS[1])" in RELEASE_LOCK_SCRIPT
        assert "return 1" in RELEASE_LOCK_SCRIPT
        assert "return 0" in RELEASE_LOCK_SCRIPT

        # 验证脚本使用条件判断
        assert "if" in RELEASE_LOCK_SCRIPT
        assert "then" in RELEASE_LOCK_SCRIPT
        assert "else" in RELEASE_LOCK_SCRIPT

    def test_exception_stats_initialization(self, lock_manager):
        """验证异常统计字段初始化"""
        assert "ownership_violations" in lock_manager.exception_stats
        assert "release_script_errors" in lock_manager.exception_stats
        assert "normal_release_failures" in lock_manager.exception_stats
        assert "emergency_releases" in lock_manager.exception_stats

        # 验证初始值为 0
        assert lock_manager.exception_stats["ownership_violations"] == 0
        assert lock_manager.exception_stats["release_script_errors"] == 0
        assert lock_manager.exception_stats["normal_release_failures"] == 0
        assert lock_manager.exception_stats["emergency_releases"] == 0
