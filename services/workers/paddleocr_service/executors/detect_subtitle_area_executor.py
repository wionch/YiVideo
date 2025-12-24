"""
PaddleOCR 检测字幕区域执行器。
"""

import os
import sys
import json
import shutil
import subprocess
import urllib.parse
from typing import Dict, Any, List
from pathlib import Path

from services.common.base_node_executor import BaseNodeExecutor
from services.common.logger import get_logger
from services.common.file_service import get_file_service
from services.common.parameter_resolver import get_param_with_fallback
from services.common.temp_path_utils import get_temp_path
from services.common.config_loader import get_cleanup_temp_files_config

logger = get_logger(__name__)


class PaddleOCRDetectSubtitleAreaExecutor(BaseNodeExecutor):
    """
    PaddleOCR 检测字幕区域执行器。

    通过调用外部脚本检测视频关键帧中的字幕区域。

    输入参数:
        - keyframe_dir (str, 可选): 关键帧目录路径（本地或MinIO URL）
        - download_from_minio (bool, 可选): 是否从MinIO下载关键帧（默认False）
        - local_keyframe_dir (str, 可选): 本地保存下载关键帧的目录
        - auto_decompress (bool, 可选): 是否自动解压缩（默认True）

    输出字段:
        - subtitle_area (dict): 检测到的字幕区域坐标 {x, y, width, height}
        - input_source (str): 输入来源类型
        - downloaded_keyframes_dir (str, 可选): 下载后的本地目录
    """

    def __init__(self, stage_name: str, context):
        super().__init__(stage_name, context)
        self.local_download_dir = None
        self.paths_file_path = None
        self.keyframe_dir = None
        self.execution_metadata = {}

    def validate_input(self) -> None:
        """
        验证输入参数。

        keyframe_dir 可以从参数获取，也可以从前置节点获取，
        因此这里不强制要求。
        """
        # 不强制要求 keyframe_dir，因为可以从前置节点获取
        pass

    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行检测字幕区域核心逻辑。

        Returns:
            包含字幕区域信息的字典
        """
        workflow_id = self.context.workflow_id
        input_data = self.get_input_data()
        file_service = get_file_service()

        # 记录GPU设备信息
        self._log_gpu_info()

        # 获取关键帧目录
        self.keyframe_dir = self._get_keyframe_dir(input_data)

        if not self.keyframe_dir:
            raise ValueError(
                "无法获取关键帧目录：请提供 keyframe_dir 参数，"
                "或确保 ffmpeg.extract_keyframes 任务已成功完成"
            )

        logger.info(f"[{workflow_id}] 关键帧目录: {self.keyframe_dir}")

        # 处理URL下载
        download_from_minio = get_param_with_fallback(
            "download_from_minio",
            input_data,
            self.context,
            default=False
        )

        auto_decompress = get_param_with_fallback(
            "auto_decompress",
            input_data,
            self.context,
            default=True
        )

        if self._is_url(self.keyframe_dir):
            if download_from_minio:
                self.keyframe_dir = self._download_from_url(
                    self.keyframe_dir,
                    input_data,
                    auto_decompress
                )
            else:
                logger.warning(
                    f"[{workflow_id}] 检测到URL但未启用下载，将尝试验证URL有效性"
                )

        # 验证关键帧目录
        if not os.path.isdir(self.keyframe_dir):
            raise ValueError(f"无效的关键帧目录: {self.keyframe_dir}")

        # 获取关键帧文件列表
        try:
            keyframe_files = sorted(os.listdir(self.keyframe_dir))
            keyframe_paths = [
                os.path.join(self.keyframe_dir, f) for f in keyframe_files
            ]
        except OSError as e:
            raise RuntimeError(f"无法读取关键帧目录 {self.keyframe_dir}: {e}") from e

        if not keyframe_paths:
            raise ValueError("关键帧目录为空，无法进行字幕区域检测")

        logger.info(
            f"[{workflow_id}] 准备从 {len(keyframe_paths)} 个关键帧检测字幕区域"
        )

        # 调用外部脚本进行检测
        output_data = self._run_detection_subprocess(keyframe_paths)

        # 添加执行元数据
        output_data.update(self.execution_metadata)

        # 如果进行了下载，记录本地路径
        if self.local_download_dir and os.path.isdir(self.local_download_dir):
            output_data['downloaded_keyframes_dir'] = self.local_download_dir

        return output_data

    def _log_gpu_info(self) -> None:
        """记录GPU设备信息"""
        workflow_id = self.context.workflow_id
        logger.info(f"[{workflow_id}] ========== 字幕区域检测设备信息 ==========")
        try:
            import torch
            if torch.cuda.is_available():
                gpu_count = torch.cuda.device_count()
                gpu_name = torch.cuda.get_device_name(0) if gpu_count > 0 else "N/A"
                logger.info(f"[{workflow_id}] 当前GPU数量: {gpu_count}")
                logger.info(f"[{workflow_id}] GPU设备: {gpu_name}")
                logger.info(f"[{workflow_id}] ✅ 已获取GPU锁，字幕区域检测将使用GPU加速")
            else:
                logger.info(f"[{workflow_id}] ℹ️ 当前设备为CPU，字幕区域检测将使用CPU模式")
        except Exception as e:
            logger.warning(f"[{workflow_id}] 设备检测失败: {e}")
        logger.info(f"[{workflow_id}] ======================================")

    def _get_keyframe_dir(self, input_data: Dict[str, Any]) -> str:
        """
        获取关键帧目录路径。

        优先级:
        1. 参数/input_data 中的 keyframe_dir
        2. ffmpeg.extract_keyframes 节点的输出

        Args:
            input_data: 输入数据

        Returns:
            keyframe_dir 路径
        """
        workflow_id = self.context.workflow_id

        # 优先从参数获取
        keyframe_dir = get_param_with_fallback(
            "keyframe_dir",
            input_data,
            self.context
        )
        if keyframe_dir:
            logger.info(f"[{workflow_id}] 从参数/input_data获取关键帧目录: {keyframe_dir}")
            self.execution_metadata['input_source'] = 'parameter'
            return keyframe_dir

        # 从 ffmpeg.extract_keyframes 获取
        ffmpeg_stage = self.context.stages.get('ffmpeg.extract_keyframes')
        if ffmpeg_stage and ffmpeg_stage.output:
            # 优先使用 keyframe_minio_url
            keyframe_dir = ffmpeg_stage.output.get('keyframe_minio_url')
            if not keyframe_dir:
                # 回退到 keyframe_dir
                keyframe_dir = ffmpeg_stage.output.get('keyframe_dir')

            if keyframe_dir:
                logger.info(
                    f"[{workflow_id}] 从 ffmpeg.extract_keyframes "
                    f"获取关键帧目录: {keyframe_dir}"
                )
                self.execution_metadata['input_source'] = 'workflow_ffmpeg'
                return keyframe_dir

        return None

    def _is_url(self, path: str) -> bool:
        """
        判断路径是否为URL。

        Args:
            path: 路径字符串

        Returns:
            是否为URL
        """
        from services.common.minio_url_utils import is_minio_url

        # 检查是否为HTTP/HTTPS URL或MinIO URL
        is_http_url = path.startswith(('http://', 'https://'))
        is_minio_format = path.startswith('minio://') or is_minio_url(path)

        return is_http_url or is_minio_format

    def _download_from_url(
        self,
        url: str,
        input_data: Dict[str, Any],
        auto_decompress: bool
    ) -> str:
        """
        从URL下载关键帧目录。

        Args:
            url: MinIO或HTTP URL
            input_data: 输入数据
            auto_decompress: 是否自动解压缩

        Returns:
            本地下载目录路径
        """
        workflow_id = self.context.workflow_id
        from services.common.minio_url_utils import normalize_minio_url
        from services.common.minio_directory_download import download_keyframes_directory

        # 尝试规范化为minio://格式
        try:
            minio_url = normalize_minio_url(url)
            logger.info(f"[{workflow_id}] 规范化URL为MinIO格式: {minio_url}")
        except ValueError:
            # 如果规范化失败，保持原始URL
            minio_url = url
            logger.info(f"[{workflow_id}] 保持原始URL格式: {minio_url}")

        # 获取本地下载目录
        self.local_download_dir = get_param_with_fallback(
            "local_keyframe_dir",
            input_data,
            self.context
        )

        if not self.local_download_dir:
            self.local_download_dir = os.path.join(
                self.context.shared_storage_path,
                "downloaded_keyframes"
            )

        logger.info(f"[{workflow_id}] 开始从URL下载关键帧目录: {minio_url}")
        logger.info(f"[{workflow_id}] 本地保存目录: {self.local_download_dir}")

        try:
            download_result = download_keyframes_directory(
                minio_url=minio_url,
                workflow_id=workflow_id,
                local_dir=self.local_download_dir,
                auto_decompress=auto_decompress
            )

            if download_result["success"]:
                logger.info(
                    f"[{workflow_id}] URL目录下载成功: "
                    f"{download_result['total_files']} 个文件"
                )
                self.execution_metadata['input_source'] = 'url_download'
                self.execution_metadata['url_download_result'] = {
                    'total_files': download_result['total_files'],
                    'downloaded_files_count': len(download_result['downloaded_files']),
                    'downloaded_local_dir': self.local_download_dir,
                    'original_url': url
                }
                return self.local_download_dir
            else:
                raise RuntimeError(
                    f"URL目录下载失败: {download_result.get('error', '未知错误')}"
                )

        except Exception as e:
            logger.error(f"[{workflow_id}] URL目录下载过程出错: {e}")
            raise RuntimeError(f"无法从URL下载关键帧目录: {e}") from e

    def _run_detection_subprocess(self, keyframe_paths: List[str]) -> Dict[str, Any]:
        """
        调用外部脚本进行字幕区域检测。

        Args:
            keyframe_paths: 关键帧文件路径列表

        Returns:
            检测结果字典
        """
        workflow_id = self.context.workflow_id

        try:
            executor_script_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "app",
                "executor_area_detection.py"
            )

            # 使用临时文件传递路径列表，避免参数过长
            self.paths_file_path = get_temp_path(workflow_id, '.json')
            with open(self.paths_file_path, 'w', encoding='utf-8') as f:
                json.dump(keyframe_paths, f)

            command = [
                sys.executable,
                executor_script_path,
                "--keyframe-paths-file",
                self.paths_file_path
            ]

            # 使用GPU命令执行
            from services.common.subprocess_utils import run_gpu_command
            result = run_gpu_command(
                command,
                stage_name=self.stage_name,
                check=True,
                timeout=1800
            )

            result_str = result.stdout.strip()

            if not result_str:
                raise RuntimeError(
                    "字幕区域检测脚本执行成功，但没有返回任何输出 (stdout is empty)"
                )

            output_data = json.loads(result_str)
            return output_data

        except json.JSONDecodeError as e:
            logger.error(
                f"[{workflow_id}] JSON解码失败。接收到的原始 stdout 是:\n---\n"
                f"{result_str}\n---"
            )
            raise RuntimeError("Failed to decode JSON from subprocess.") from e
        except subprocess.TimeoutExpired as e:
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logger.error(
                f"[{workflow_id}] 字幕区域检测子进程执行超时({e.timeout}秒)。"
                f"Stderr:\n---\n{stderr_output}\n---"
            )
            raise RuntimeError(
                f"Area detection subprocess timed out after {e.timeout} seconds."
            ) from e
        except subprocess.CalledProcessError as e:
            stdout_output = e.stdout.strip() if e.stdout else "(empty)"
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logger.error(
                f"[{workflow_id}] 字幕区域检测子进程执行失败，返回码: {e.returncode}。\n"
                f"Stdout:\n---\n{stdout_output}\n---\n"
                f"Stderr:\n---\n{stderr_output}\n---"
            )
            raise RuntimeError(
                f"Area detection subprocess failed with exit code {e.returncode}."
            ) from e

    def cleanup(self) -> None:
        """
        清理临时文件和目录。
        """
        workflow_id = self.context.workflow_id

        # 清理参数临时文件
        if self.paths_file_path and os.path.exists(self.paths_file_path):
            try:
                os.remove(self.paths_file_path)
                logger.debug(f"[{workflow_id}] 清理参数临时文件: {self.paths_file_path}")
            except Exception as e:
                logger.warning(f"[{workflow_id}] 清理参数临时文件失败: {e}")

        # 如果启用了临时文件清理
        if get_cleanup_temp_files_config():
            # 清理下载的目录
            if self.local_download_dir and os.path.isdir(self.local_download_dir):
                try:
                    shutil.rmtree(self.local_download_dir)
                    logger.info(f"[{workflow_id}] 清理下载的关键帧目录: {self.local_download_dir}")
                except Exception as e:
                    logger.warning(f"[{workflow_id}] 清理下载关键帧目录失败: {e}")

            # 清理原始keyframes目录（如果是从工作流获取的）
            if (self.execution_metadata.get('input_source') == 'workflow_ffmpeg' and
                self.keyframe_dir and os.path.isdir(self.keyframe_dir)):
                try:
                    shutil.rmtree(self.keyframe_dir)
                    logger.info(f"[{workflow_id}] 清理原始关键帧目录: {self.keyframe_dir}")
                except Exception as e:
                    logger.warning(f"[{workflow_id}] 清理原始关键帧目录失败: {e}")

    def get_cache_key_fields(self) -> List[str]:
        """
        返回用于生成缓存键的字段列表。

        检测结果仅依赖于关键帧目录。
        """
        return ["keyframe_dir"]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段列表。

        检测的核心输出是 subtitle_area。
        """
        return ["subtitle_area"]
