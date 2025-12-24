"""
PaddleOCR 执行 OCR 识别执行器。
"""

import os
import sys
import json
import shutil
import subprocess
import time
from typing import Dict, Any, List
from pathlib import Path

from services.common.base_node_executor import BaseNodeExecutor
from services.common.logger import get_logger
from services.common.file_service import get_file_service
from services.common.parameter_resolver import get_param_with_fallback
from services.common.config_loader import get_cleanup_temp_files_config

logger = get_logger(__name__)


class PaddleOCRPerformOCRExecutor(BaseNodeExecutor):
    """
    PaddleOCR 执行 OCR 识别执行器。

    通过调用外部脚本对拼接好的图片执行 OCR 识别。

    输入参数:
        - manifest_path (str, 可选): 拼接图像的清单文件路径（本地或MinIO URL）
        - multi_frames_path (str, 可选): 拼接图像的目录路径（本地或MinIO URL）
        - upload_ocr_results_to_minio (bool, 可选): 是否上传OCR结果到MinIO（默认True）
        - delete_local_ocr_results_after_upload (bool, 可选): 上传后删除本地OCR结果（默认False）
        - auto_decompress (bool, 可选): 是否自动解压缩（默认True）

    输出字段:
        - ocr_results_path (str): OCR结果JSON文件路径
        - ocr_results_minio_url (str, 可选): OCR结果MinIO URL
        - ocr_results_count (int, 可选): OCR识别的帧数
    """

    def __init__(self, stage_name: str, context):
        super().__init__(stage_name, context)
        self.manifest_download_dir = None
        self.multi_frames_download_dir = None
        self.local_manifest_path = None
        self.local_multi_frames_path = None

    def validate_input(self) -> None:
        """
        验证输入参数。

        manifest_path 和 multi_frames_path 可以从前置节点获取，
        因此这里不强制要求。
        """
        # 不强制要求，因为可以从前置节点获取
        pass

    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行 OCR 识别核心逻辑。

        Returns:
            包含 OCR 结果信息的字典
        """
        workflow_id = self.context.workflow_id
        input_data = self.get_input_data()

        # 获取输入路径
        manifest_path = self._get_manifest_path(input_data)
        multi_frames_path = self._get_multi_frames_path(input_data)

        if not manifest_path:
            raise ValueError(
                "无法获取清单文件路径：请提供 manifest_path 参数，"
                "或确保 paddleocr.create_stitched_images 任务已成功完成"
            )

        if not multi_frames_path:
            raise ValueError(
                "无法获取拼接图像目录：请提供 multi_frames_path 参数，"
                "或确保 paddleocr.create_stitched_images 任务已成功完成"
            )

        logger.info(f"[{workflow_id}] 清单文件路径: {manifest_path}")
        logger.info(f"[{workflow_id}] 拼接图像目录: {multi_frames_path}")

        # 处理URL下载
        auto_decompress = get_param_with_fallback(
            "auto_decompress",
            input_data,
            self.context,
            default=True
        )

        # 下载 manifest_path
        if self._is_url(manifest_path):
            self.local_manifest_path = self._download_manifest_from_url(
                manifest_path
            )
        else:
            self.local_manifest_path = manifest_path

        # 下载 multi_frames_path
        if self._is_url(multi_frames_path):
            self.local_multi_frames_path = self._download_multi_frames_from_url(
                multi_frames_path,
                auto_decompress
            )
        else:
            self.local_multi_frames_path = multi_frames_path

        # 验证本地路径
        if not os.path.exists(self.local_manifest_path):
            raise FileNotFoundError(
                f"清单文件不存在: {self.local_manifest_path}"
            )

        if not Path(self.local_multi_frames_path).is_dir():
            raise FileNotFoundError(
                f"拼接图像目录不存在或无效: {self.local_multi_frames_path}"
            )

        # 记录GPU设备信息
        self._log_gpu_info()

        # 调用外部脚本执行OCR
        ocr_results = self._run_ocr_subprocess(
            self.local_manifest_path,
            self.local_multi_frames_path
        )

        # 保存OCR结果到本地文件
        ocr_results_path = os.path.join(
            self.context.shared_storage_path,
            "ocr_results.json"
        )
        with open(ocr_results_path, 'w', encoding='utf-8') as f:
            json.dump(ocr_results, f, ensure_ascii=False)

        logger.info(f"[{workflow_id}] OCR结果已保存到: {ocr_results_path}")

        # 构造输出
        output_data = {
            "ocr_results_path": ocr_results_path,
            "ocr_results_count": len(ocr_results)
        }

        # MinIO上传
        upload_to_minio = get_param_with_fallback(
            "upload_ocr_results_to_minio",
            input_data,
            self.context,
            default=True
        )

        delete_local_results = get_param_with_fallback(
            "delete_local_ocr_results_after_upload",
            input_data,
            self.context,
            default=False
        )

        if upload_to_minio:
            upload_result = self._upload_to_minio(
                ocr_results_path,
                delete_local_results
            )
            output_data.update(upload_result)

        return output_data

    def _get_manifest_path(self, input_data: Dict[str, Any]) -> str:
        """
        获取清单文件路径。

        优先级:
        1. 参数/input_data 中的 manifest_path
        2. paddleocr.create_stitched_images 节点的输出

        Args:
            input_data: 输入数据

        Returns:
            manifest_path 路径
        """
        workflow_id = self.context.workflow_id

        # 优先从参数获取
        manifest_path = get_param_with_fallback(
            "manifest_path",
            input_data,
            self.context
        )
        if manifest_path:
            logger.info(
                f"[{workflow_id}] 从参数/input_data获取清单文件路径: "
                f"{manifest_path}"
            )
            return manifest_path

        # 从 paddleocr.create_stitched_images 获取
        stitch_stage = self.context.stages.get('paddleocr.create_stitched_images')
        if stitch_stage and stitch_stage.output:
            manifest_path = stitch_stage.output.get('manifest_path')
            if not manifest_path:
                # 尝试从 MinIO URL 获取
                manifest_path = stitch_stage.output.get('manifest_minio_url')

            if manifest_path:
                logger.info(
                    f"[{workflow_id}] 从 paddleocr.create_stitched_images "
                    f"获取清单文件路径: {manifest_path}"
                )
                return manifest_path

        return None

    def _get_multi_frames_path(self, input_data: Dict[str, Any]) -> str:
        """
        获取拼接图像目录路径。

        优先级:
        1. 参数/input_data 中的 multi_frames_path
        2. paddleocr.create_stitched_images 节点的输出

        Args:
            input_data: 输入数据

        Returns:
            multi_frames_path 路径
        """
        workflow_id = self.context.workflow_id

        # 优先从参数获取
        multi_frames_path = get_param_with_fallback(
            "multi_frames_path",
            input_data,
            self.context
        )
        if multi_frames_path:
            logger.info(
                f"[{workflow_id}] 从参数/input_data获取拼接图像目录: "
                f"{multi_frames_path}"
            )
            return multi_frames_path

        # 从 paddleocr.create_stitched_images 获取
        stitch_stage = self.context.stages.get('paddleocr.create_stitched_images')
        if stitch_stage and stitch_stage.output:
            multi_frames_path = stitch_stage.output.get('multi_frames_path')
            if not multi_frames_path:
                # 尝试从 MinIO URL 获取
                multi_frames_path = stitch_stage.output.get('multi_frames_minio_url')

            if multi_frames_path:
                logger.info(
                    f"[{workflow_id}] 从 paddleocr.create_stitched_images "
                    f"获取拼接图像目录: {multi_frames_path}"
                )
                return multi_frames_path

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

    def _download_manifest_from_url(self, url: str) -> str:
        """
        从URL下载清单文件。

        Args:
            url: MinIO或HTTP URL

        Returns:
            本地清单文件路径
        """
        workflow_id = self.context.workflow_id
        from services.common.minio_url_utils import normalize_minio_url

        logger.info(f"[{workflow_id}] 检测到清单文件为URL，尝试从远程下载: {url}")

        # 创建临时目录
        self.manifest_download_dir = os.path.join(
            self.context.shared_storage_path,
            f"download_manifest_{int(time.time())}"
        )

        # 规范化URL
        try:
            download_url = normalize_minio_url(url)
            logger.info(f"[{workflow_id}] 规范化URL为MinIO格式: {download_url}")
        except ValueError:
            # 如果规范化失败，保持原始URL
            download_url = url
            logger.info(f"[{workflow_id}] 保持原始URL格式: {download_url}")

        try:
            file_service = get_file_service()
            os.makedirs(self.manifest_download_dir, exist_ok=True)

            local_manifest_path = file_service.resolve_and_download(
                download_url,
                self.manifest_download_dir
            )

            logger.info(
                f"[{workflow_id}] 清单文件下载成功: {local_manifest_path}"
            )

            return local_manifest_path

        except Exception as e:
            logger.error(f"[{workflow_id}] 清单文件下载过程出错: {e}")
            raise RuntimeError(f"无法从URL下载清单文件: {e}") from e

    def _download_multi_frames_from_url(
        self,
        url: str,
        auto_decompress: bool
    ) -> str:
        """
        从URL下载拼接图像目录。

        Args:
            url: MinIO或HTTP URL
            auto_decompress: 是否自动解压缩

        Returns:
            本地拼接图像目录路径
        """
        workflow_id = self.context.workflow_id
        from services.common.minio_url_utils import normalize_minio_url
        from services.common.minio_directory_download import (
            download_directory_from_minio,
            is_archive_url
        )

        logger.info(
            f"[{workflow_id}] 检测到拼接图像目录为URL，尝试从远程下载: {url}"
        )

        # 检查原始URL是否为压缩包
        is_original_archive = is_archive_url(url)
        logger.info(f"[{workflow_id}] 原始URL是否为压缩包: {is_original_archive}")

        # 创建临时目录
        self.multi_frames_download_dir = os.path.join(
            self.context.shared_storage_path,
            f"download_multi_frames_{int(time.time())}"
        )

        # 如果是压缩包且启用自动解压，使用原始URL
        if is_original_archive and auto_decompress:
            download_url = url
            logger.info(
                f"[{workflow_id}] 检测到压缩包URL，使用原始URL避免文件名丢失: "
                f"{download_url}"
            )
        else:
            # 对于普通目录URL，进行规范化处理
            try:
                download_url = normalize_minio_url(url)
                logger.info(f"[{workflow_id}] 规范化URL为MinIO格式: {download_url}")
            except ValueError:
                # 如果规范化失败，保持原始URL
                download_url = url
                logger.info(f"[{workflow_id}] 保持原始URL格式: {download_url}")

        try:
            download_result = download_directory_from_minio(
                minio_url=download_url,
                local_dir=self.multi_frames_download_dir,
                create_structure=True,
                auto_decompress=auto_decompress,
                workflow_id=workflow_id
            )

            if not download_result["success"]:
                raise RuntimeError(
                    f"从URL下载目录失败: {download_result.get('error')}"
                )

            logger.info(
                f"[{workflow_id}] 拼接图像目录下载成功，使用本地路径: "
                f"{self.multi_frames_download_dir}"
            )
            logger.info(
                f"[{workflow_id}] 下载结果: "
                f"{download_result.get('total_files', 0)} 个文件"
            )

            return self.multi_frames_download_dir

        except Exception as e:
            logger.error(f"[{workflow_id}] 拼接图像目录下载过程出错: {e}")
            raise RuntimeError(f"无法从URL下载拼接图像目录: {e}") from e

    def _log_gpu_info(self) -> None:
        """
        记录GPU设备信息。
        """
        workflow_id = self.context.workflow_id

        logger.info(f"[{workflow_id}] ========== OCR任务设备信息 ==========")
        try:
            import torch
            if torch.cuda.is_available():
                gpu_count = torch.cuda.device_count()
                gpu_name = torch.cuda.get_device_name(0) if gpu_count > 0 else "N/A"
                logger.info(f"[{workflow_id}] 当前GPU数量: {gpu_count}")
                logger.info(f"[{workflow_id}] GPU设备: {gpu_name}")
                logger.info(f"[{workflow_id}] ✅ 已获取GPU锁，OCR任务将使用GPU加速")
            else:
                logger.info(f"[{workflow_id}] ℹ️ 当前设备为CPU，OCR任务将使用CPU模式")
        except Exception as e:
            logger.warning(f"[{workflow_id}] 设备检测失败: {e}")
        logger.info(f"[{workflow_id}] ================================")

    def _run_ocr_subprocess(
        self,
        manifest_path: str,
        multi_frames_path: str
    ) -> List[Dict[str, Any]]:
        """
        调用外部脚本进行OCR识别。

        Args:
            manifest_path: 清单文件路径
            multi_frames_path: 拼接图像目录路径

        Returns:
            OCR识别结果列表
        """
        workflow_id = self.context.workflow_id

        try:
            executor_script_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "app",
                "executor_ocr.py"
            )

            command = [
                sys.executable,
                executor_script_path,
                "--manifest-path", manifest_path,
                "--multi-frames-path", multi_frames_path
            ]

            # 使用GPU命令执行
            from services.common.subprocess_utils import run_gpu_command
            result = run_gpu_command(
                command,
                stage_name=self.stage_name,
                check=True,
                timeout=3600
            )

            if result.stderr:
                logger.debug(
                    f"[{workflow_id}] OCR子进程有 stderr 输出:\n"
                    f"{result.stderr.strip()}"
                )

            ocr_results_str = result.stdout.strip()
            if not ocr_results_str:
                raise RuntimeError("OCR执行脚本没有返回任何输出")

            ocr_results = json.loads(ocr_results_str)
            logger.info(
                f"[{workflow_id}] 外部脚本OCR完成，识别出 {len(ocr_results)} 帧的文本"
            )

            return ocr_results

        except subprocess.TimeoutExpired as e:
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logger.error(
                f"[{workflow_id}] OCR子进程执行超时({e.timeout}秒)。"
                f"Stderr:\n---\n{stderr_output}\n---"
            )
            raise RuntimeError(
                f"OCR subprocess timed out after {e.timeout} seconds."
            ) from e
        except subprocess.CalledProcessError as e:
            stdout_output = e.stdout.strip() if e.stdout else "(empty)"
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logger.error(
                f"[{workflow_id}] OCR子进程执行失败，返回码: {e.returncode}。\n"
                f"Stdout:\n---\n{stdout_output}\n---\n"
                f"Stderr:\n---\n{stderr_output}\n---"
            )
            raise RuntimeError(
                f"OCR subprocess failed with exit code {e.returncode}."
            ) from e

    def _upload_to_minio(
        self,
        ocr_results_path: str,
        delete_local_results: bool
    ) -> Dict[str, Any]:
        """
        上传OCR结果到MinIO。

        Args:
            ocr_results_path: OCR结果文件路径
            delete_local_results: 是否删除本地结果

        Returns:
            上传结果字典
        """
        workflow_id = self.context.workflow_id
        upload_result = {}

        if os.path.exists(ocr_results_path):
            try:
                logger.info(f"[{workflow_id}] 开始上传OCR结果JSON文件到MinIO...")
                file_service = get_file_service()

                # 构建OCR结果文件在MinIO中的路径
                minio_ocr_path = f"{workflow_id}/ocr_results/ocr_results.json"

                ocr_minio_url = file_service.upload_to_minio(
                    local_file_path=ocr_results_path,
                    object_name=minio_ocr_path
                )

                upload_result["ocr_results_minio_url"] = ocr_minio_url
                logger.info(
                    f"[{workflow_id}] OCR结果文件上传成功: {ocr_minio_url}"
                )

                # 如果需要删除本地文件
                if delete_local_results:
                    os.remove(ocr_results_path)
                    logger.info(
                        f"[{workflow_id}] 已删除本地OCR结果文件: {ocr_results_path}"
                    )

            except Exception as e:
                logger.warning(
                    f"[{workflow_id}] OCR结果文件上传失败: {e}",
                    exc_info=True
                )
                upload_result["ocr_results_upload_error"] = str(e)

        return upload_result

    def cleanup(self) -> None:
        """
        清理临时文件和目录。
        """
        workflow_id = self.context.workflow_id

        if get_cleanup_temp_files_config():
            # 清理manifest下载目录
            if self.manifest_download_dir and os.path.exists(self.manifest_download_dir):
                try:
                    shutil.rmtree(self.manifest_download_dir)
                    logger.info(
                        f"[{workflow_id}] 清理manifest下载目录: "
                        f"{self.manifest_download_dir}"
                    )
                except Exception as e:
                    logger.warning(f"[{workflow_id}] 清理manifest下载目录失败: {e}")

            # 清理multi_frames下载目录
            if self.multi_frames_download_dir and os.path.exists(self.multi_frames_download_dir):
                try:
                    shutil.rmtree(self.multi_frames_download_dir)
                    logger.info(
                        f"[{workflow_id}] 清理multi_frames下载目录: "
                        f"{self.multi_frames_download_dir}"
                    )
                except Exception as e:
                    logger.warning(f"[{workflow_id}] 清理multi_frames下载目录失败: {e}")

        # 强制清理PaddleOCR相关进程和GPU显存
        try:
            from services.common.gpu_memory_manager import (
                cleanup_paddleocr_processes,
                log_gpu_memory_state
            )

            logger.info(f"[{workflow_id}] 开始清理OCR相关进程和GPU资源...")
            log_gpu_memory_state("OCR任务完成前")

            # 清理残留的OCR进程
            cleanup_paddleocr_processes()

            # 记录清理后的状态
            log_gpu_memory_state("OCR任务清理后")

        except Exception as cleanup_e:
            logger.warning(
                f"[{workflow_id}] OCR资源清理过程中出现问题: {cleanup_e}"
            )

    def get_cache_key_fields(self) -> List[str]:
        """
        返回用于生成缓存键的字段列表。

        OCR结果依赖于拼接图像目录和清单文件。
        """
        return ["manifest_path", "multi_frames_path"]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段列表。

        OCR的核心输出是 ocr_results_path。
        """
        return ["ocr_results_path"]
