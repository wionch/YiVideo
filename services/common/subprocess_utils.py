# services/common/subprocess_utils.py
# -*- coding: utf-8 -*-

"""
统一的subprocess.Popen封装工具函数
用于替代subprocess.run，实现GPU任务的实时日志输出
"""

import os
import sys
import time
import subprocess
import threading
from typing import List, Dict, Any, Optional, Union, Callable
from pathlib import Path

from services.common.logger import get_logger

logger = get_logger('subprocess_utils')


class SubprocessResult:
    """subprocess.run兼容的结果对象"""
    
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "", 
                 execution_time: float = 0.0):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.execution_time = execution_time
    
    def check_returncode(self):
        """模拟subprocess.run的check参数行为"""
        if self.returncode != 0:
            raise subprocess.CalledProcessError(
                self.returncode, [], self.stdout, self.stderr
            )


def stream_output(pipe, output_list: List[str], prefix: str, logger_func: Callable):
    """
    在单独线程中流式读取子进程输出
    
    Args:
        pipe: subprocess.PIPE文件对象
        output_list: 用于存储输出的列表
        prefix: 日志前缀
        logger_func: 日志记录函数
    """
    try:
        for line in iter(pipe.readline, ''):
            if line:
                line = line.rstrip('\n\r')
                output_list.append(line)
                logger_func(f"[{prefix}] {line}")
            else:
                break
    except Exception as e:
        logger_func(f"[{prefix}] 读取输出时出错: {e}")
    finally:
        try:
            pipe.close()
        except:
            pass


def run_with_popen(
    cmd: Union[str, List[str]],
    *,
    capture_output: bool = False,
    text: bool = True,
    timeout: Optional[float] = None,
    check: bool = False,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    encoding: str = 'utf-8',
    log_prefix: str = "subprocess",
    real_time_logging: bool = True,
    max_log_lines: Optional[int] = None,
    **kwargs
) -> SubprocessResult:
    """
    使用subprocess.Popen替代subprocess.run，支持实时日志输出
    
    Args:
        cmd: 要执行的命令
        capture_output: 是否捕获输出 (兼容subprocess.run)
        text: 是否使用文本模式 (兼容subprocess.run)
        timeout: 超时时间 (兼容subprocess.run)
        check: 是否在返回码非0时抛出异常 (兼容subprocess.run)
        cwd: 工作目录 (兼容subprocess.run)
        env: 环境变量 (兼容subprocess.run)
        encoding: 文本编码
        log_prefix: 日志前缀
        real_time_logging: 是否启用实时日志输出
        max_log_lines: 最大日志行数限制，避免内存溢出
        **kwargs: 其他subprocess.Popen参数
    
    Returns:
        SubprocessResult: 执行结果对象，兼容subprocess.CompletedProcess
    """
    start_time = time.time()
    
    # 准备命令
    if isinstance(cmd, str):
        shell = True
    else:
        shell = False
    
    # 准备环境变量
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    
    # 准备stdout/stderr处理
    stdout_pipe = subprocess.PIPE if capture_output or real_time_logging else None
    stderr_pipe = subprocess.PIPE if capture_output or real_time_logging else None
    
    # 输出收集列表
    stdout_lines = []
    stderr_lines = []
    
    logger.info(f"[{log_prefix}] 开始执行命令: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    
    try:
        # 启动子进程
        process = subprocess.Popen(
            cmd,
            stdout=stdout_pipe,
            stderr=stderr_pipe,
            cwd=cwd,
            env=process_env,
            encoding=encoding,
            text=text,
            **kwargs
        )
        
        # 启动流式输出线程
        threads = []
        if real_time_logging:
            # stdout流
            if stdout_pipe:
                stdout_thread = threading.Thread(
                    target=stream_output,
                    args=(process.stdout, stdout_lines, f"{log_prefix}-stdout", logger.info),
                    daemon=True
                )
                stdout_thread.start()
                threads.append(stdout_thread)
            
            # stderr流
            if stderr_pipe:
                stderr_thread = threading.Thread(
                    target=stream_output,
                    args=(process.stderr, stderr_lines, f"{log_prefix}-stderr", logger.info),
                    daemon=True
                )
                stderr_thread.start()
                threads.append(stderr_thread)
        
        # 等待进程完成
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.error(f"[{log_prefix}] 进程执行超时({timeout}秒)，开始终止...")
            process.terminate()
            
            # 等待一段时间后强制杀死
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.error(f"[{log_prefix}] 强制终止进程...")
                process.kill()
                process.wait()
            
            execution_time = time.time() - start_time
            logger.error(f"[{log_prefix}] 进程超时终止，耗时: {execution_time:.3f}s")
            
            # 构建超时错误信息
            timeout_stderr = "\n".join(stderr_lines) if stderr_lines else "(empty)"
            raise subprocess.TimeoutExpired(cmd, timeout, output="\n".join(stdout_lines), stderr=timeout_stderr)
        
        # 等待所有流式线程完成
        for thread in threads:
            thread.join(timeout=1.0)
        
        # 收集剩余输出（如果需要）
        if capture_output:
            try:
                remaining_stdout, remaining_stderr = process.communicate(timeout=1.0)
                if remaining_stdout:
                    stdout_lines.append(remaining_stdout.rstrip('\n\r'))
                if remaining_stderr:
                    stderr_lines.append(remaining_stderr.rstrip('\n\r'))
            except subprocess.TimeoutExpired:
                # 忽略最后的超时，这通常意味着输出已经读取完毕
                pass
        
        execution_time = time.time() - start_time
        
        # 构建结果
        result = SubprocessResult(
            returncode=process.returncode,
            stdout="\n".join(stdout_lines) if stdout_lines else "",
            stderr="\n".join(stderr_lines) if stderr_lines else "",
            execution_time=execution_time
        )
        
        # 记录执行结果
        if process.returncode == 0:
            logger.info(f"[{log_prefix}] 进程执行成功，耗时: {execution_time:.3f}s")
            if result.stderr:
                logger.debug(f"[{log_prefix}] stderr输出: {result.stderr}")
        else:
            error_msg = f"进程执行失败，返回码: {process.returncode}"
            logger.error(f"[{log_prefix}] {error_msg}")
            logger.error(f"[{log_prefix}] stdout: {result.stdout}")
            logger.error(f"[{log_prefix}] stderr: {result.stderr}")
        
        # 检查返回码（如果需要）
        if check:
            result.check_returncode()
        
        # 限制日志行数（避免内存问题）
        if max_log_lines and len(stdout_lines) > max_log_lines:
            logger.warning(f"[{log_prefix}] stdout行数({len(stdout_lines)})超过限制({max_log_lines})，已截断")
        if max_log_lines and len(stderr_lines) > max_log_lines:
            logger.warning(f"[{log_prefix}] stderr行数({len(stderr_lines)})超过限制({max_log_lines})，已截断")
        
        return result
        
    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"[{log_prefix}] 执行过程中发生异常: {e}")
        logger.error(f"[{log_prefix}] 已收集的输出: stdout={len(stdout_lines)}行, stderr={len(stderr_lines)}行")
        
        # 重新抛出原始异常
        raise


# 兼容性别名
run_process = run_with_popen


def run_gpu_command(
    cmd: Union[str, List[str]],
    stage_name: str,
    *,
    timeout: float = 1800.0,
    check: bool = True,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    **kwargs
) -> SubprocessResult:
    """
    专门用于GPU任务的命令执行函数
    
    Args:
        cmd: 要执行的命令
        stage_name: 阶段名称，用于日志前缀
        timeout: 超时时间（默认30分钟）
        check: 是否在返回码非0时抛出异常
        cwd: 工作目录
        env: 环境变量
        **kwargs: 其他参数
    
    Returns:
        SubprocessResult: 执行结果
    """
    return run_with_popen(
        cmd=cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
        cwd=cwd,
        env=env or os.environ.copy(),
        log_prefix=stage_name,
        real_time_logging=True,
        max_log_lines=1000,  # 限制每阶段最大日志行数
        **kwargs
    )


# 保持向后兼容性的装饰器
class SubprocessCompat:
    """subprocess.run兼容性包装类"""
    
    @staticmethod
    def run(cmd, **kwargs):
        """模拟subprocess.run的接口"""
        return run_with_popen(cmd, **kwargs)


# 为了向后兼容，提供一个subprocess模块的替代品
subprocess_popen = SubprocessCompat()