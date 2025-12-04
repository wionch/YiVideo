"""
临时文件路径工具函数
基于工作流ID生成安全的临时文件路径，替代系统级 /tmp 目录使用
"""

import os
import time
import uuid


def get_temp_path(workflow_id: str, suffix: str = "") -> str:
    """生成基于工作流ID的临时文件路径
    
    Args:
        workflow_id: 工作流ID，用于创建基于任务的隔离目录
        suffix: 文件后缀，如 '.zip', '.json'
        
    Returns:
        临时文件路径，格式为: /share/workflows/{workflow_id}/tmp/temp_{timestamp}_{uuid8}{suffix}
    """
    temp_dir = f"/share/workflows/{workflow_id}/tmp"
    os.makedirs(temp_dir, exist_ok=True)
    
    timestamp = int(time.time() * 1000)
    unique_id = str(uuid.uuid4())[:8]
    filename = f"temp_{timestamp}_{unique_id}{suffix}"
    
    return os.path.join(temp_dir, filename)