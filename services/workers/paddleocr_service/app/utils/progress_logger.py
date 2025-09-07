# services/workers/paddleocr_service/app/utils/progress_logger.py
import sys
import time
from typing import Optional, Dict, Any
from threading import Lock

class ProgressBar:
    """
    简洁的进度条日志系统，用于替代大量重复的单帧处理日志。
    支持多种进度显示模式和实时更新。
    """
    
    def __init__(self, total: int, task_name: str = "处理中", 
                 show_rate: bool = True, show_eta: bool = True,
                 update_interval: float = 0.5):
        """
        初始化进度条
        
        Args:
            total: 总任务数量
            task_name: 任务名称
            show_rate: 是否显示处理速率
            show_eta: 是否显示预估剩余时间
            update_interval: 更新间隔（秒），避免频繁更新
        """
        self.total = total
        self.current = 0
        self.task_name = task_name
        self.show_rate = show_rate
        self.show_eta = show_eta
        self.update_interval = update_interval
        
        self.start_time = time.time()
        self.last_update_time = 0
        self.lock = Lock()  # 多进程安全
        
        # 额外统计信息
        self.extras = {}
        
    def update(self, increment: int = 1, **kwargs):
        """
        更新进度
        
        Args:
            increment: 增加的进度量
            **kwargs: 额外的统计信息，如 success_count=5, error_count=1
        """
        with self.lock:
            self.current += increment
            
            # 更新额外统计
            for key, value in kwargs.items():
                if key in self.extras:
                    self.extras[key] += value
                else:
                    self.extras[key] = value
            
            # 控制更新频率
            current_time = time.time()
            if (current_time - self.last_update_time >= self.update_interval or 
                self.current >= self.total):
                self._display()
                self.last_update_time = current_time
    
    def _display(self):
        """显示进度条"""
        if self.total <= 0:
            return
            
        # 计算百分比
        percent = min(100, (self.current * 100) // self.total)
        
        # 构建进度条
        bar_length = 30
        filled_length = (self.current * bar_length) // self.total
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        
        # 基础信息
        progress_info = f"\r[{self.task_name}] [{bar}] {self.current}/{self.total} ({percent}%)"
        
        # 处理速率
        if self.show_rate and self.current > 0:
            elapsed = time.time() - self.start_time
            rate = self.current / elapsed if elapsed > 0 else 0
            progress_info += f" | 速率: {rate:.1f}/s"
        
        # 预估剩余时间
        if self.show_eta and self.current > 0 and self.current < self.total:
            elapsed = time.time() - self.start_time
            rate = self.current / elapsed if elapsed > 0 else 0
            if rate > 0:
                remaining = (self.total - self.current) / rate
                eta_str = self._format_time(remaining)
                progress_info += f" | 预计剩余: {eta_str}"
        
        # 额外统计信息
        if self.extras:
            extra_parts = []
            for key, value in self.extras.items():
                extra_parts.append(f"{key}:{value}")
            if extra_parts:
                progress_info += f" | {' '.join(extra_parts)}"
        
        # 输出进度条（会覆盖上一行）
        print(progress_info, end='', flush=True)
        
        # 如果完成，换行
        if self.current >= self.total:
            elapsed = time.time() - self.start_time
            final_rate = self.current / elapsed if elapsed > 0 else 0
            print(f"\n✅ {self.task_name}完成: {self.current}项，耗时: {self._format_time(elapsed)}, 平均速率: {final_rate:.1f}/s")
    
    def _format_time(self, seconds: float) -> str:
        """格式化时间显示"""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m{secs:02d}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h{minutes:02d}m"
    
    def finish(self, message: str = ""):
        """手动结束进度条"""
        with self.lock:
            if self.current < self.total:
                self.current = self.total
            self._display()
            if message:
                print(f"\n{message}")

class MultiStageProgressLogger:
    """
    多阶段进度日志管理器
    用于管理整个视频处理流程中的不同阶段
    """
    
    def __init__(self):
        self.stages = {}
        self.current_stage = None
        
    def create_stage(self, stage_name: str, total: int, **kwargs) -> ProgressBar:
        """创建新的处理阶段"""
        progress_bar = ProgressBar(total, stage_name, **kwargs)
        self.stages[stage_name] = progress_bar
        self.current_stage = stage_name
        print(f"\n🚀 开始阶段: {stage_name} (总计: {total}项)")
        return progress_bar
    
    def get_stage(self, stage_name: str) -> Optional[ProgressBar]:
        """获取指定阶段的进度条"""
        return self.stages.get(stage_name)
    
    def finish_stage(self, stage_name: str, message: str = ""):
        """结束指定阶段"""
        if stage_name in self.stages:
            self.stages[stage_name].finish(message)
    
    def summary(self):
        """显示所有阶段的总结"""
        print("\n📊 处理总结:")
        for stage_name, progress_bar in self.stages.items():
            elapsed = time.time() - progress_bar.start_time
            rate = progress_bar.current / elapsed if elapsed > 0 else 0
            print(f"  - {stage_name}: {progress_bar.current}/{progress_bar.total} "
                  f"(耗时: {progress_bar._format_time(elapsed)}, 速率: {rate:.1f}/s)")

# 全局多阶段日志管理器实例
global_progress_logger = MultiStageProgressLogger()

def get_progress_logger() -> MultiStageProgressLogger:
    """获取全局进度日志管理器"""
    return global_progress_logger

# 便捷函数
def create_progress_bar(total: int, task_name: str = "处理中", **kwargs) -> ProgressBar:
    """创建独立的进度条"""
    return ProgressBar(total, task_name, **kwargs)

def create_stage_progress(stage_name: str, total: int, **kwargs) -> ProgressBar:
    """创建阶段进度条"""
    return global_progress_logger.create_stage(stage_name, total, **kwargs)