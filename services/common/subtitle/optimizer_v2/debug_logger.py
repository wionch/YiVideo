"""调试日志记录器 - 用于记录LLM请求/响应和错误

用于字幕优化器v2的调试日志记录，支持记录请求、响应和错误信息到文件。
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class DebugLogger:
    """调试日志记录器

    用于记录LLM请求、响应和错误信息，便于调试和问题排查。
    文件命名格式: {task_id}_seg{idx}_request.txt
                  {task_id}_seg{idx}_response.txt
                  {task_id}_seg{idx}_error.txt
    """

    def __init__(self, log_dir: str = "tmp/subtitle_optimizer_logs", enabled: bool = True):
        """初始化调试日志记录器

        Args:
            log_dir: 日志文件存储目录
            enabled: 是否启用日志记录
        """
        self.log_dir = Path(log_dir)
        self.enabled = enabled

        if self.enabled:
            self.log_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, task_id: str, segment_idx: int, suffix: str) -> Path:
        """获取日志文件路径

        Args:
            task_id: 任务ID
            segment_idx: 段索引
            suffix: 文件后缀 (request/response/error)

        Returns:
            日志文件路径
        """
        filename = f"{task_id}_seg{segment_idx}_{suffix}.txt"
        return self.log_dir / filename

    def _format_content(self, title: str, content: Dict[str, Any]) -> str:
        """格式化日志内容

        Args:
            title: 标题
            content: 内容字典

        Returns:
            格式化后的字符串
        """
        lines = [
            f"{'=' * 60}",
            f"{title}",
            f"时间: {datetime.now().isoformat()}",
            f"{'=' * 60}",
            "",
        ]

        for key, value in content.items():
            lines.append(f"{key}:")
            if isinstance(value, str):
                lines.append(value)
            else:
                lines.append(str(value))
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)

    def log_request(
        self,
        task_id: str,
        segment_idx: int,
        prompt: str,
        model: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录LLM请求

        Args:
            task_id: 任务ID
            segment_idx: 段索引
            prompt: 提示词内容
            model: 模型名称
            extra: 额外信息
        """
        if not self.enabled:
            return

        content: Dict[str, Any] = {"prompt": prompt}
        if model:
            content["model"] = model
        if extra:
            content.update(extra)

        file_path = self._get_file_path(task_id, segment_idx, "request")
        formatted = self._format_content("LLM 请求", content)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(formatted)

    def log_response(
        self,
        task_id: str,
        segment_idx: int,
        response: str,
        latency_ms: Optional[float] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录LLM响应

        Args:
            task_id: 任务ID
            segment_idx: 段索引
            response: 响应内容
            latency_ms: 延迟时间(毫秒)
            extra: 额外信息
        """
        if not self.enabled:
            return

        content: Dict[str, Any] = {"response": response}
        if latency_ms is not None:
            content["latency_ms"] = latency_ms
        if extra:
            content.update(extra)

        file_path = self._get_file_path(task_id, segment_idx, "response")
        formatted = self._format_content("LLM 响应", content)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(formatted)

    def log_error(
        self,
        task_id: str,
        segment_idx: int,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录错误

        Args:
            task_id: 任务ID
            segment_idx: 段索引
            error: 异常对象
            context: 错误上下文信息
        """
        if not self.enabled:
            return

        content: Dict[str, Any] = {
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
        if context:
            content["context"] = context

        file_path = self._get_file_path(task_id, segment_idx, "error")
        formatted = self._format_content("错误日志", content)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(formatted)

    def is_enabled(self) -> bool:
        """检查日志记录是否启用

        Returns:
            是否启用
        """
        return self.enabled
