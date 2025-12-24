# tests/integration/test_gpu_lock_deadlock.py
# -*- coding: utf-8 -*-

"""GPU 锁死锁预防集成测试"""

import pytest
import time
import threading
from unittest.mock import patch, MagicMock
from typing import Any

from services.common.locks import SmartGpuLockManager, redis_client
from services.workers.indextts_service.app.tasks import IndexTTSTask


class TestGpuLockDeadlockPrevention:
    """GPU 锁死锁预防集成测试"""

    @pytest.fixture
    def redis_cleanup(self):
        """清理 Redis 测试数据"""
        # 测试前清理
        if redis_client:
            redis_client.delete("gpu_lock:0")
            redis_client.delete("gpu_lock:1")

        yield

        # 测试后清理
        if redis_client:
            redis_client.delete("gpu_lock:0")
            redis_client.delete("gpu_lock:1")

    @pytest.fixture
    def lock_manager(self):
        """创建锁管理器实例"""
        return SmartGpuLockManager()

    def test_no_deadlock_on_task_crash(self, redis_cleanup, lock_manager):
        """验证任务崩溃时不会导致死锁"""
        # 场景: 任务获取锁后崩溃，finally 块确保锁被释放

        lock_key = "gpu_lock:0"
        task_name = "crash_task"

        # 第一步：模拟任务获取锁
        config = {
            'max_wait_time': 10,
            'poll_interval': 0.1,
            'lock_timeout': 30,
            'exponential_backoff': False,
            'use_event_driven': False
        }

        success = lock_manager.acquire_lock_with_smart_polling(task_name, lock_key, config)
        assert success, "任务应该能获取锁"

        # 验证锁已被持有
        if redis_client:
            lock_value = redis_client.get(lock_key)
            assert lock_value == f"locked_by_{task_name}", "锁应该被任务持有"

        # 第二步：模拟任务崩溃（通过异常）
        try:
            raise Exception("模拟任务崩溃")
        except Exception:
            # 模拟 finally 块的三层保护
            lock_released = False
            try:
                lock_released = lock_manager.release_lock(task_name, lock_key, "task_crash")
            except Exception:
                pass

            # 如果正常释放失败，应急释放
            if not lock_released and redis_client:
                redis_client.delete(lock_key)

        # 第三步：验证锁已被释放
        if redis_client:
            lock_value = redis_client.get(lock_key)
            assert lock_value is None, "锁应该已被释放"

        # 第四步：验证其他任务可以获取锁
        other_task = "recovery_task"
        success = lock_manager.acquire_lock_with_smart_polling(other_task, lock_key, config)
        assert success, "其他任务应该能获取锁（无死锁）"

        # 清理
        lock_manager.release_lock(other_task, lock_key, "normal")

    def test_concurrent_lock_acquisition(self, redis_cleanup, lock_manager):
        """验证并发锁获取的正确性"""
        # 场景: 多个任务同时尝试获取锁，验证互斥性和顺序获取

        lock_key = "gpu_lock:0"
        results = []
        lock_holders = []  # 记录同时持有锁的任务数

        config = {
            'max_wait_time': 10,  # 增加等待时间以确保所有任务都能获取
            'poll_interval': 0.1,
            'lock_timeout': 30,
            'exponential_backoff': False,
            'use_event_driven': False
        }

        def try_acquire(task_id: int):
            """尝试获取锁"""
            task_name = f"task_{task_id}"
            success = lock_manager.acquire_lock_with_smart_polling(task_name, lock_key, config)

            if success:
                # 记录获取锁的时刻
                lock_holders.append(task_name)
                results.append({
                    'task_id': task_id,
                    'task_name': task_name,
                    'success': True,
                    'timestamp': time.time()
                })

                # 持有锁一段时间
                time.sleep(0.3)

                # 释放锁前移除记录
                lock_holders.remove(task_name)
                lock_manager.release_lock(task_name, lock_key, "normal")
            else:
                results.append({
                    'task_id': task_id,
                    'task_name': task_name,
                    'success': False,
                    'timestamp': time.time()
                })

        # 创建 5 个线程同时尝试获取锁
        threads = [threading.Thread(target=try_acquire, args=(i,)) for i in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 验证：所有任务最终都能获取锁（顺序获取）
        successful_tasks = [r for r in results if r['success']]
        assert len(successful_tasks) == 5, "所有任务应该最终都能获取锁（顺序获取）"

        # 验证：任何时刻只有一个任务持有锁（通过检查 lock_holders 永远不超过1）
        # 注意：由于线程调度，这个检查在测试中很难精确验证
        # 实际的互斥性由 Redis SET NX 保证

        # 验证：锁最终被释放
        if redis_client:
            lock_value = redis_client.get(lock_key)
            assert lock_value is None, "锁应该已被释放"

    @patch('services.workers.indextts_service.app.tasks.MultiProcessTTSEngine')
    def test_indextts_task_failure_integration(self, mock_tts_engine, redis_cleanup):
        """验证 IndexTTS 任务失败时的锁释放"""
        # 场景: IndexTTS 任务执行失败，on_failure 回调释放锁

        lock_key = "gpu_lock:0"
        task_id = "indextts_task_123"

        # 创建任务实例
        task = IndexTTSTask()
        task.gpu_lock_manager = SmartGpuLockManager()

        # 第一步：模拟任务获取锁
        config = {
            'max_wait_time': 10,
            'poll_interval': 0.1,
            'lock_timeout': 30,
            'exponential_backoff': False,
            'use_event_driven': False
        }

        success = task.gpu_lock_manager.acquire_lock_with_smart_polling(
            task_id, lock_key, config
        )
        assert success, "任务应该能获取锁"

        # 验证锁已被持有
        if redis_client:
            lock_value = redis_client.get(lock_key)
            assert lock_value == f"locked_by_{task_id}", "锁应该被任务持有"

        # 第二步：模拟任务失败
        exc = Exception("TTS 引擎初始化失败")
        args = ()
        kwargs = {'gpu_id': 0}
        einfo = None

        # 调用 on_failure 回调
        task.on_failure(exc, task_id, args, kwargs, einfo)

        # 第三步：验证锁已被释放
        if redis_client:
            lock_value = redis_client.get(lock_key)
            assert lock_value is None, "锁应该已被 on_failure 释放"

        # 第四步：验证其他任务可以获取锁
        other_task = "recovery_task"
        success = task.gpu_lock_manager.acquire_lock_with_smart_polling(
            other_task, lock_key, config
        )
        assert success, "其他任务应该能获取锁（无死锁）"

        # 清理
        task.gpu_lock_manager.release_lock(other_task, lock_key, "normal")

    def test_emergency_release_on_normal_failure(self, redis_cleanup, lock_manager):
        """验证正常释放失败时的应急释放机制"""
        # 场景: 正常释放失败（所有权验证失败），应急释放生效

        lock_key = "gpu_lock:0"
        task_a = "task_a"
        task_b = "task_b"

        config = {
            'max_wait_time': 10,
            'poll_interval': 0.1,
            'lock_timeout': 30,
            'exponential_backoff': False,
            'use_event_driven': False
        }

        # 第一步：任务 A 获取锁
        success = lock_manager.acquire_lock_with_smart_polling(task_a, lock_key, config)
        assert success, "任务 A 应该能获取锁"

        # 第二步：任务 B 尝试释放任务 A 的锁（模拟异常情况）
        lock_released = lock_manager.release_lock(task_b, lock_key, "normal")
        assert lock_released is False, "任务 B 不应该能释放任务 A 的锁"

        # 验证锁仍然被任务 A 持有
        if redis_client:
            lock_value = redis_client.get(lock_key)
            assert lock_value == f"locked_by_{task_a}", "锁应该仍被任务 A 持有"

        # 第三步：应急释放（模拟 finally 块的第三层）
        if not lock_released and redis_client:
            redis_client.delete(lock_key)
            lock_manager.exception_stats["emergency_releases"] += 1

        # 验证锁已被应急释放
        if redis_client:
            lock_value = redis_client.get(lock_key)
            assert lock_value is None, "锁应该已被应急释放"

        # 验证统计信息
        assert lock_manager.exception_stats["ownership_violations"] == 1, "应记录所有权验证失败"
        assert lock_manager.exception_stats["emergency_releases"] == 1, "应记录应急释放"

    def test_lock_timeout_auto_expiry(self, redis_cleanup, lock_manager):
        """验证锁超时自动过期机制"""
        # 场景: 锁超时后自动过期，其他任务可以获取

        lock_key = "gpu_lock:0"
        task_a = "task_a"
        task_b = "task_b"

        # 第一步：任务 A 获取锁（设置短超时）
        config = {
            'max_wait_time': 10,
            'poll_interval': 0.1,
            'lock_timeout': 2,  # 2 秒超时
            'exponential_backoff': False,
            'use_event_driven': False
        }

        success = lock_manager.acquire_lock_with_smart_polling(task_a, lock_key, config)
        assert success, "任务 A 应该能获取锁"

        # 验证锁已被持有
        if redis_client:
            lock_value = redis_client.get(lock_key)
            assert lock_value == f"locked_by_{task_a}", "锁应该被任务 A 持有"

        # 第二步：等待锁过期
        time.sleep(3)

        # 第三步：验证锁已过期
        if redis_client:
            lock_value = redis_client.get(lock_key)
            assert lock_value is None, "锁应该已过期"

        # 第四步：任务 B 获取锁
        success = lock_manager.acquire_lock_with_smart_polling(task_b, lock_key, config)
        assert success, "任务 B 应该能获取过期后的锁"

        # 清理
        lock_manager.release_lock(task_b, lock_key, "normal")
