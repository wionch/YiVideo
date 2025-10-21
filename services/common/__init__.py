"""YiVideo Common Utilities and Shared Infrastructure"""

# Logger
from .logger import get_logger

# Configuration
from .config_loader import (
    get_config,
    get_cleanup_temp_files_config,
    get_gpu_lock_config,
    get_gpu_lock_monitor_config,
    CONFIG,
)

# Workflow Context
from .context import WorkflowContext, StageExecution

# GPU Lock
from .locks import (
    gpu_lock,
    get_gpu_lock_status,
    get_gpu_lock_health_summary,
    release_gpu_lock,
    SmartGpuLockManager,
)

# State Manager
from .state_manager import (
    create_workflow_state,
    update_workflow_state,
    get_workflow_state,
)

# GPU Memory Manager
from .gpu_memory_manager import (
    GPUMemoryManager,
    initialize_worker_gpu_memory,
    cleanup_worker_gpu_memory,
    cleanup_paddleocr_processes,
)

__all__ = [
    # Logger
    'get_logger',
    # Configuration
    'get_config',
    'get_cleanup_temp_files_config',
    'get_gpu_lock_config',
    'get_gpu_lock_monitor_config',
    'CONFIG',
    # Context
    'WorkflowContext',
    'StageExecution',
    # GPU Lock
    'gpu_lock',
    'get_gpu_lock_status',
    'get_gpu_lock_health_summary',
    'release_gpu_lock',
    'SmartGpuLockManager',
    # State
    'create_workflow_state',
    'update_workflow_state',
    'get_workflow_state',
    # GPU Memory
    'GPUMemoryManager',
    'initialize_worker_gpu_memory',
    'cleanup_worker_gpu_memory',
    'cleanup_paddleocr_processes',
]
