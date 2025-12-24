"""
PaddleOCR 创建拼接图像执行器。
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
from services.common.config_loader import CONFIG, get_cleanup_temp_files_config

logger = get_logger(__name__)


class PaddleOCRCreateStitchedImagesExecutor(BaseNodeExecutor):
    """
    PaddleOCR 创建拼接图像执行器。

    通过调用外部脚本将裁剪后的字幕条图像并发拼接成大图。

    输入参数:
        - cropped_images_path (str, 可选): 裁剪图像目录路径（本地或MinIO URL）
        - subtitle_area (dict, 可选): 字幕区域坐标
        - upload_stitched_images_to_minio (bool, 可选): 是否上传到MinIO（默认True）
        - delete_local_stitched_images_after_upload (bool, 可选): 上传后删除本地文件（默认False）
        - auto_decompress (bool, 可选): 是否自动解压缩（默认True）

    输出字段:
        - multi_frames_path (str): 拼接图像目录路径
        - manifest_path (str): 清单文件路径
        - multi_frames_minio_url (str, 可选): 拼接图像MinIO URL
        - manifest_minio_url (str, 可选): 清单文件MinIO URL
        - stitched_images_count (int, 可选): 拼接图像数量
        - compression_info (dict, 可选): 压缩信息
    """

    def __init__(self, stage_name: str, context):
        super().__init__(stage_name, context)
        self.local_download_dir = None
        self.input_dir_str = None

    def validate_input(self) -> None:
        """
        验证输入参数。

        cropped_images_path 和 subtitle_area 可以从前置节点获取，
        因此这里不强制要求。
        """
        # 不强制要求，因为可以从前置节点获取
        pass

    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行创建拼接图像核心逻辑。

        Returns:
            包含拼接图像信息的字典
        """
        workflow_id = self.context.workflow_id
        input_data = self.get_input_data()

        # 获取输入路径和字幕区域
        self.input_dir_str = self._get_cropped_images_path(input_data)
        subtitle_area = self._get_subtitle_area(input_data)

        if not self.input_dir_str:
            raise ValueError(
                "无法获取裁剪图像目录：请提供 cropped_images_path 参数，"
                "或确保 ffmpeg.crop_subtitle_images 任务已成功完成"
            )

        if not subtitle_area:
            raise ValueError(
                "无法获取字幕区域：请提供 subtitle_area 参数，"
                "或确保 paddleocr.detect_subtitle_area 任务已成功完成"
            )

        logger.info(f"[{workflow_id}] 裁剪图像目录: {self.input_dir_str}")
        logger.info(f"[{workflow_id}] 字幕区域: {subtitle_area}")

        # 处理URL下载
        auto_decompress = get_param_with_fallback(
            "auto_decompress",
            input_data,
            self.context,
            default=True
        )

        if self._is_url(self.input_dir_str):
            self.input_dir_str = self._download_from_url(
                self.input_dir_str,
                auto_decompress
            )

        # 验证输入目录
        if not Path(self.input_dir_str).is_dir():
            raise FileNotFoundError(f"输入目录不存在或无效: {self.input_dir_str}")

        # 输出根目录是输入目录的父目录
        output_root_dir = Path(self.input_dir_str).parent

        # 获取配置
        pipeline_config = CONFIG.get('pipeline', {})
        batch_size = pipeline_config.get('concat_batch_size', 50)
        max_workers = pipeline_config.get('stitching_workers', 10)

        logger.info(f"[{workflow_id}] 准备拼接图像...")
        logger.info(f"[{workflow_id}]   - 批次大小: {batch_size}")
        logger.info(f"[{workflow_id}]   - 工作线程: {max_workers}")

        # 调用外部脚本执行拼接
        self._run_stitching_subprocess(
            self.input_dir_str,
            output_root_dir,
            batch_size,
            max_workers,
            subtitle_area
        )

        # 构造输出
        output_data = {
            "multi_frames_path": str(output_root_dir / "multi_frames"),
            "manifest_path": str(output_root_dir / "multi_frames.json")
        }

        # MinIO上传
        upload_to_minio = get_param_with_fallback(
            "upload_stitched_images_to_minio",
            input_data,
            self.context,
            default=True
        )

        delete_local_images = get_param_with_fallback(
            "delete_local_stitched_images_after_upload",
            input_data,
            self.context,
            default=False
        )

        if upload_to_minio:
            upload_result = self._upload_to_minio(
                output_data,
                delete_local_images
            )
            output_data.update(upload_result)

        return output_data

    def _get_cropped_images_path(self, input_data: Dict[str, Any]) -> str:
        """
        获取裁剪图像目录路径。

        优先级:
        1. 参数/input_data 中的 cropped_images_path
        2. ffmpeg.crop_subtitle_images 节点的输出

        Args:
            input_data: 输入数据

        Returns:
            cropped_images_path 路径
        """
        workflow_id = self.context.workflow_id

        # 优先从参数获取
        cropped_images_path = get_param_with_fallback(
            "cropped_images_path",
            input_data,
            self.context
        )
        if cropped_images_path:
            logger.info(
                f"[{workflow_id}] 从参数/input_data获取裁剪图像目录: "
                f"{cropped_images_path}"
            )
            return cropped_images_path

        # 从 ffmpeg.crop_subtitle_images 获取
        crop_stage = self.context.stages.get('ffmpeg.crop_subtitle_images')
        if crop_stage and crop_stage.output:
            cropped_images_path = crop_stage.output.get('cropped_images_path')
            if cropped_images_path:
                logger.info(
                    f"[{workflow_id}] 从 ffmpeg.crop_subtitle_images "
                    f"获取裁剪图像目录: {cropped_images_path}"
                )
                return cropped_images_path

        return None

    def _get_subtitle_area(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取字幕区域。

        优先级:
        1. 参数/input_data 中的 subtitle_area
        2. paddleocr.detect_subtitle_area 节点的输出

        Args:
            input_data: 输入数据

        Returns:
            subtitle_area 字典
        """
        workflow_id = self.context.workflow_id

        # 优先从参数获取
        subtitle_area = get_param_with_fallback(
            "subtitle_area",
            input_data,
            self.context
        )
        if subtitle_area:
            logger.info(f"[{workflow_id}] 从参数/input_data获取字幕区域: {subtitle_area}")
            return subtitle_area

        # 从 paddleocr.detect_subtitle_area 获取
        detect_stage = self.context.stages.get('paddleocr.detect_subtitle_area')
        if detect_stage and detect_stage.output:
            subtitle_area = detect_stage.output.get('subtitle_area')
            if subtitle_area:
                logger.info(
                    f"[{workflow_id}] 从 paddleocr.detect_subtitle_area "
                    f"获取字幕区域: {subtitle_area}"
                )
                return subtitle_area

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

    def _download_from_url(self, url: str, auto_decompress: bool) -> str:
        """
        从URL下载裁剪图像目录。

        Args:
            url: MinIO或HTTP URL
            auto_decompress: 是否自动解压缩

        Returns:
            本地下载目录路径
        """
        workflow_id = self.context.workflow_id
        from services.common.minio_url_utils import normalize_minio_url
        from services.common.minio_directory_download import (
            download_directory_from_minio,
            is_archive_url
        )

        logger.info(f"[{workflow_id}] 检测到输入路径为URL，尝试从远程下载目录: {url}")

        # 检查原始URL是否为压缩包
        is_original_archive = is_archive_url(url)
        logger.info(f"[{workflow_id}] 原始URL是否为压缩包: {is_original_archive}")

        # 创建临时目录
        self.local_download_dir = os.path.join(
            self.context.shared_storage_path,
            f"downloaded_cropped_{int(time.time())}"
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
                local_dir=self.local_download_dir,
                create_structure=True,
                auto_decompress=auto_decompress,
                workflow_id=workflow_id
            )

            if not download_result["success"]:
                raise RuntimeError(
                    f"从URL下载目录失败: {download_result.get('error')}"
                )

            logger.info(
                f"[{workflow_id}] URL目录下载成功，使用本地路径: "
                f"{self.local_download_dir}"
            )
            logger.info(
                f"[{workflow_id}] 下载结果: "
                f"{download_result.get('total_files', 0)} 个文件"
            )

            return self.local_download_dir

        except Exception as e:
            logger.error(f"[{workflow_id}] URL目录下载过程出错: {e}")
            raise RuntimeError(f"无法从URL下载裁剪图像目录: {e}") from e

    def _run_stitching_subprocess(
        self,
        input_dir: str,
        output_root_dir: Path,
        batch_size: int,
        max_workers: int,
        subtitle_area: Dict[str, Any]
    ) -> None:
        """
        调用外部脚本进行图像拼接。

        Args:
            input_dir: 输入目录
            output_root_dir: 输出根目录
            batch_size: 批次大小
            max_workers: 最大工作线程数
            subtitle_area: 字幕区域
        """
        workflow_id = self.context.workflow_id

        try:
            executor_script_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "app",
                "executor_stitch_images.py"
            )

            subtitle_area_json = json.dumps(subtitle_area)

            command = [
                sys.executable,
                executor_script_path,
                "--input-dir", str(input_dir),
                "--output-root", str(output_root_dir),
                "--batch-size", str(batch_size),
                "--workers", str(max_workers),
                "--subtitle-area-json", subtitle_area_json
            ]

            # 使用GPU命令执行
            from services.common.subprocess_utils import run_gpu_command
            result = run_gpu_command(
                command,
                stage_name=self.stage_name,
                check=True,
                timeout=1800
            )

            if result.stderr:
                logger.debug(
                    f"[{workflow_id}] 图像拼接子进程有 stderr 输出:\n"
                    f"{result.stderr.strip()}"
                )

            logger.info(f"[{workflow_id}] 外部脚本成功完成图像拼接")

        except subprocess.TimeoutExpired as e:
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logger.error(
                f"[{workflow_id}] 图像拼接子进程执行超时({e.timeout}秒)。"
                f"Stderr:\n---\n{stderr_output}\n---"
            )
            raise RuntimeError(
                f"Image stitching subprocess timed out after {e.timeout} seconds."
            ) from e
        except subprocess.CalledProcessError as e:
            stdout_output = e.stdout.strip() if e.stdout else "(empty)"
            stderr_output = e.stderr.strip() if e.stderr else "(empty)"
            logger.error(
                f"[{workflow_id}] 图像拼接子进程执行失败，返回码: {e.returncode}。\n"
                f"Stdout:\n---\n{stdout_output}\n---\n"
                f"Stderr:\n---\n{stderr_output}\n---"
            )
            raise RuntimeError(
                f"Image stitching subprocess failed with exit code {e.returncode}."
            ) from e

    def _upload_to_minio(
        self,
        output_data: Dict[str, Any],
        delete_local_images: bool
    ) -> Dict[str, Any]:
        """
        上传拼接图像和清单文件到MinIO。

        Args:
            output_data: 输出数据
            delete_local_images: 是否删除本地图像

        Returns:
            上传结果字典
        """
        workflow_id = self.context.workflow_id
        upload_result = {}

        # 上传拼接图像目录（压缩上传）
        if os.path.exists(output_data["multi_frames_path"]):
            try:
                logger.info(f"[{workflow_id}] 开始上传拼接图片目录到MinIO（压缩优化）...")
                minio_base_path = f"{workflow_id}/stitched_images"

                from services.common.minio_directory_upload import upload_directory_compressed

                result = upload_directory_compressed(
                    local_dir=output_data["multi_frames_path"],
                    minio_base_path=minio_base_path,
                    file_pattern="*.jpg",
                    compression_format="zip",
                    compression_level="default",
                    delete_local=delete_local_images,
                    workflow_id=workflow_id
                )

                if result["success"]:
                    upload_result["multi_frames_minio_url"] = result["archive_url"]
                    upload_result["compression_info"] = result.get("compression_info", {})
                    upload_result["stitched_images_count"] = result.get("total_files", 0)

                    compression_info = result.get("compression_info", {})
                    if compression_info:
                        compression_ratio = compression_info.get("compression_ratio", 0)
                        logger.info(
                            f"[{workflow_id}] 拼接图片压缩上传成功: "
                            f"{result['archive_url']}"
                        )
                        logger.info(
                            f"[{workflow_id}] 压缩统计: "
                            f"{compression_info.get('files_count', 0)} 个文件, "
                            f"压缩率 {compression_ratio:.1%}, "
                            f"原始大小 {compression_info.get('original_size', 0)/1024/1024:.1f}MB, "
                            f"压缩后 {compression_info.get('compressed_size', 0)/1024/1024:.1f}MB"
                        )
                else:
                    upload_result["multi_frames_upload_error"] = result.get("error")
                    logger.warning(
                        f"[{workflow_id}] 拼接图片上传失败: {result.get('error')}"
                    )

            except Exception as e:
                logger.warning(f"[{workflow_id}] 上传过程异常: {e}", exc_info=True)
                upload_result["multi_frames_upload_error"] = str(e)

        # 上传manifest文件
        if os.path.exists(output_data["manifest_path"]):
            try:
                logger.info(f"[{workflow_id}] 开始上传manifest文件到MinIO...")
                file_service = get_file_service()

                minio_manifest_path = f"{workflow_id}/manifest/multi_frames.json"

                manifest_minio_url = file_service.upload_to_minio(
                    local_file_path=output_data["manifest_path"],
                    object_name=minio_manifest_path
                )

                upload_result["manifest_minio_url"] = manifest_minio_url
                logger.info(
                    f"[{workflow_id}] manifest文件上传成功: {manifest_minio_url}"
                )

            except Exception as e:
                logger.warning(f"[{workflow_id}] manifest文件上传失败: {e}", exc_info=True)
                upload_result["manifest_upload_error"] = str(e)

        return upload_result

    def cleanup(self) -> None:
        """
        清理临时文件和目录。
        """
        workflow_id = self.context.workflow_id

        if get_cleanup_temp_files_config():
            # 清理下载的临时目录
            if self.local_download_dir and os.path.exists(self.local_download_dir):
                try:
                    shutil.rmtree(self.local_download_dir)
                    logger.info(
                        f"[{workflow_id}] 清理下载的临时目录: {self.local_download_dir}"
                    )
                except Exception as e:
                    logger.warning(f"[{workflow_id}] 清理下载目录失败: {e}")

            # 清理输入目录（如果不是下载的临时目录）
            elif self.input_dir_str and Path(self.input_dir_str).exists():
                try:
                    shutil.rmtree(self.input_dir_str)
                    logger.info(
                        f"[{workflow_id}] 清理临时裁剪图像帧目录: {self.input_dir_str}"
                    )
                except Exception as e:
                    logger.warning(f"[{workflow_id}] 清理裁剪图像帧目录失败: {e}")

    def get_cache_key_fields(self) -> List[str]:
        """
        返回用于生成缓存键的字段列表。

        拼接结果依赖于裁剪图像目录和字幕区域。
        """
        return ["cropped_images_path", "subtitle_area"]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段列表。

        拼接的核心输出是 multi_frames_path 和 manifest_path。
        """
        return ["multi_frames_path", "manifest_path"]
