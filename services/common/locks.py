# services/common/locks.py
import os
import time
import errno

class GPULock:
    """
    一个简单的、基于文件系统的跨进程 GPU 锁。
    通过原子性地创建和删除一个锁文件来实现。
    设计为在 `with` 语句中使用。
    """
    def __init__(self, lock_dir='/tmp', lock_name='gpu.lock', timeout=300):
        """
        初始化锁。

        Args:
            lock_dir (str): 存放锁文件的目录。
            lock_name (str): 锁文件的名称。
            timeout (int): 获取锁的超时时间（秒）。
        """
        self.lock_path = os.path.join(lock_dir, lock_name)
        self.timeout = timeout
        self._lock_fd = None
        
        # 确保锁目录存在
        if not os.path.exists(lock_dir):
            try:
                os.makedirs(lock_dir)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise

    def acquire(self):
        """尝试在超时时间内获取锁。"""
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            try:
                # O_CREAT: 如果文件不存在则创建
                # O_EXCL: 如果文件已存在，则失败 (这是原子操作的关键)
                # O_WRONLY: 以只写模式打开
                self._lock_fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                # 如果成功获取锁，立即返回
                print(f"成功获取 GPU 锁: {self.lock_path}")
                return
            except OSError as e:
                if e.errno == errno.EEXIST:
                    # 文件已存在，意味着锁被其他进程持有
                    time.sleep(1)
                else:
                    # 其他类型的 OS 错误
                    raise
        # 如果循环结束仍未获取锁，则超时
        raise TimeoutError(f"获取 GPU 锁超时 ({self.timeout}s): {self.lock_path}")

    def release(self):
        """释放锁。"""
        if self._lock_fd is not None:
            try:
                os.close(self._lock_fd)
                os.remove(self.lock_path)
                self._lock_fd = None
                print(f"成功释放 GPU 锁: {self.lock_path}")
            except OSError as e:
                # 如果文件在关闭或删除时出现问题，记录警告
                print(f"警告: 释放 GPU 锁时发生错误: {e}")

    def __enter__(self):
        """上下文管理器的进入方法。"""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器的退出方法，确保锁被释放。"""
        self.release()
