#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio Separator Service - 模型管理器
功能：通过 subprocess 调用独立脚本执行模型推理
"""

import os
import time
import threading
import logging
from typing import Optional, Dict
from pathlib import Path
import subprocess
import sys
import json

from services.common.temp_path_utils import get_temp_path
from .config import get_config, AudioSeparatorConfig

# 配置日志
logger = logging.getLogger(__name__)


class ModelManager:
    """
    模型管理器 (Subprocess 模式)

    功能：
    1. 构造并执行对独立推理脚本的 subprocess 调用。
    2. 解析子进程返回的结果。
    3. 提供服务健康检查。
    """

    def __init__(self):
        """初始化模型管理器"""
        self.config: AudioSeparatorConfig = get_config()
        logger.info("ModelManager (subprocess mode) 初始化完成")

    def separate_audio_subprocess(
        self,
        audio_path: str,
        model_name: str,
        output_dir: str,
        model_type: str,
        workflow_id: Optional[str] = None,
        use_vocal_optimization: bool = False,
        vocal_optimization_level: Optional[str] = None
    ) -> Dict[str, str]:
        """
        使用 subprocess 调用独立脚本执行音频分离。
        """
        logger.info(f"开始处理音频 (subprocess模式): {audio_path}")

        if not Path(audio_path).exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        # 准备输出路径
        # 使用基于工作流ID的临时文件来接收子进程的JSON输出
        output_file = get_temp_path(workflow_id or "audio_separator", '.json')
        
        logger.info(f"子进程结果临时文件: {output_file}")

        # 准备推理脚本路径
        current_dir = Path(__file__).parent
        infer_script = current_dir / "audio_separator_infer.py"
        if not infer_script.exists():
            raise FileNotFoundError(f"推理脚本不存在: {infer_script}")

        # 构建命令
        cmd = [
            sys.executable,
            str(infer_script),
            "--audio_path", str(audio_path),
            "--output_file", str(output_file),
            "--model_name", model_name,
            "--model_type", model_type,
            "--output_dir", output_dir,
        ]
        
        if use_vocal_optimization and vocal_optimization_level:
            cmd.extend(["--optimization_level", vocal_optimization_level])

        logger.info(f"执行命令: {' '.join(cmd)}")

        # 执行 subprocess (升级为实时日志版本)
        try:
            from services.common.subprocess_utils import run_with_popen
            
            result = run_with_popen(
                cmd,
                stage_name="audio_separator_subprocess",
                timeout=1800,  # 30分钟超时
                cwd=str(current_dir),
                env=os.environ.copy(),
                encoding='utf-8',
                text=True
            )

            if result.returncode != 0:
                error_msg = f"Subprocess 执行失败，返回码: {result.returncode}"
                logger.error(f"{error_msg}\nstdout: {result.stdout}\nstderr: {result.stderr}")
                raise RuntimeError(f"{error_msg}\nstderr: {result.stderr}")

            logger.info("Subprocess 执行成功")
            if result.stderr:
                logger.debug(f"Subprocess stderr:\n{result.stderr}")

        except subprocess.TimeoutExpired as e:
            raise RuntimeError("Subprocess 执行超时 (30分钟)") from e
        except Exception as e:
            raise RuntimeError(f"Subprocess 执行异常: {e}") from e

        # 读取结果文件
        if not Path(output_file).exists():
            raise RuntimeError(f"推理结果文件不存在: {output_file}")

        with open(output_file, 'r', encoding='utf-8') as f:
            result_data = json.load(f)

        # 清理临时文件
        try:
            Path(output_file).unlink()
        except Exception as e:
            logger.warning(f"清理临时文件失败: {e}")

        if not result_data.get('success', False):
            error_info = result_data.get('error', {})
            raise RuntimeError(f"推理失败: {error_info.get('message', '未知错误')}")

        # 解析输出文件
        output_files = result_data.get('output_files', [])
        return self._parse_output_files(output_files, output_dir)

    def _parse_output_files(self, output_files: list, output_dir: str) -> Dict[str, str]:
        """
        解析输出文件列表，识别 vocals 和 instrumental。
        """
        result = {'vocals': None, 'instrumental': None, 'all_tracks': {}}
        
        # audio_separator 返回的是完整路径
        absolute_files = output_files

        for file_path in absolute_files:
            file_name = Path(file_path).name.lower()
            track_name = Path(file_path).stem.lower()
            result['all_tracks'][track_name] = file_path

            if 'vocals' in file_name:
                result['vocals'] = file_path
            elif 'instrumental' in file_name or 'inst' in file_name or 'no_vocal' in file_name:
                result['instrumental'] = file_path
            elif 'drums' in file_name:
                if not result.get('drums'): result['drums'] = file_path
            elif 'bass' in file_name:
                if not result.get('bass'): result['bass'] = file_path
            elif 'other' in file_name:
                if not result.get('other'): result['other'] = file_path

        # 如果标准解析失败，使用备用逻辑
        if not result['vocals'] or not result['instrumental']:
            logger.warning(f"无法通过标准名称匹配识别人声和伴奏: {output_files}")
            if not result['vocals'] and 'vocals' in result['all_tracks']:
                 result['vocals'] = result['all_tracks']['vocals']

            # 伴奏的备用逻辑
            if not result['instrumental']:
                if 'instrumental' in result['all_tracks']:
                    result['instrumental'] = result['all_tracks']['instrumental']
                elif 'no_vocals' in result['all_tracks']:
                    result['instrumental'] = result['all_tracks']['no_vocals']
                elif 'other' in result['all_tracks']:
                     result['instrumental'] = result['all_tracks']['other']
                elif len(absolute_files) >= 2:
                    # 选择第一个不是人声的文件
                    for f in absolute_files:
                        if f != result['vocals']:
                            result['instrumental'] = f
                            break
        
        if not result['vocals'] and len(absolute_files) > 0:
            result['vocals'] = absolute_files[0]
            logger.warning(f"最终备用：选择第一个文件作为人声: {result['vocals']}")

        if not result['instrumental'] and len(absolute_files) > 1:
            # 确保不与人声文件重复
            for f in absolute_files:
                if f != result['vocals']:
                    result['instrumental'] = f
                    break
            if not result['instrumental']: # 如果只有一个文件
                 result['instrumental'] = result['vocals']
            logger.warning(f"最终备用：选择另一个文件作为伴奏: {result['instrumental']}")

        return result

    def list_available_models(self) -> list:
        """
        列出所有可用的模型
        """
        models_dir = Path(self.config.models_dir)

        if not models_dir.exists():
            logger.warning(f"模型目录不存在: {models_dir}")
            return []

        # 查找所有 .onnx 和 .pth 文件
        model_files = []
        for ext in ['*.onnx', '*.pth', '*.ckpt', '*.yaml']:
            model_files.extend(models_dir.glob(ext))

        return [f.name for f in model_files]

    def health_check(self) -> Dict[str, any]:
        """
        简化的健康检查 (Subprocess 模式)
        """
        import psutil
        import datetime

        health_status = {
            'status': 'healthy',
            'timestamp': datetime.datetime.now().isoformat(),
            'mode': 'subprocess',
            'available_models': self.list_available_models(),
            'config': {
                'models_dir': self.config.models_dir,
                'output_format': self.config.output_format,
            },
            'system_info': {},
            'checks': {}
        }

        # 检查模型目录
        models_dir = Path(self.config.models_dir)
        models_dir_check = {
            'exists': models_dir.exists(),
            'readable': os.access(models_dir, os.R_OK) if models_dir.exists() else False,
        }
        health_status['checks']['models_directory'] = models_dir_check

        # 检查系统资源
        try:
            memory = psutil.virtual_memory()
            health_status['system_info'] = {
                'memory_usage_percent': memory.percent,
                'memory_available_gb': round(memory.available / (1024**3), 2),
                'cpu_count': psutil.cpu_count()
            }
        except Exception as e:
            health_status['system_info'] = {'error': str(e)}

        # 检查GPU状态
        try:
            import torch
            gpu_info = {'available': torch.cuda.is_available()}
            if gpu_info['available']:
                gpu_info['device_count'] = torch.cuda.device_count()
            health_status['system_info']['gpu'] = gpu_info
        except ImportError:
            health_status['system_info']['gpu'] = {'available': False, 'error': 'PyTorch not installed'}
        except Exception as e:
            health_status['system_info']['gpu'] = {'available': False, 'error': str(e)}

        # 确定整体健康状态
        if not models_dir_check['exists'] or not models_dir_check['readable']:
            health_status['status'] = 'unhealthy'
            health_status['issues'] = ['models_directory_issue']

        return health_status

# ========================================
# 全局模型管理器实例
# ========================================

def get_model_manager() -> ModelManager:
    """
    获取全局模型管理器实例
    """
    # 在subprocess模式下，ModelManager是无状态的，每次都创建新实例是安全的
    return ModelManager()


if __name__ == "__main__":
    # 测试模型管理器
    logging.basicConfig(level=logging.INFO)
    manager = get_model_manager()
    print("健康检查:", manager.health_check())
