"""
PaddleOCR 后处理和生成最终字幕执行器。
"""

import os
import json
import time
from typing import Dict, Any, List

from services.common.base_node_executor import BaseNodeExecutor
from services.common.logger import get_logger
from services.common.file_service import get_file_service
from services.common.parameter_resolver import get_param_with_fallback
from services.common.subtitle.subtitle_parser import SubtitleEntry, write_srt_file
from services.common.path_builder import build_node_output_path, ensure_directory

logger = get_logger(__name__)


class PaddleOCRPostprocessAndFinalizeExecutor(BaseNodeExecutor):
    """
    PaddleOCR 后处理和生成最终字幕执行器。

    对 OCR 结果进行后处理，生成最终的 SRT 和 JSON 字幕文件。

    输入参数:
        - ocr_results_path (str, 可选): OCR结果JSON文件路径（本地或MinIO URL）
        - ocr_results_file (str, 可选): OCR结果文件URL（用于单步任务）
        - video_path (str, 必需): 视频文件路径（用于获取FPS和生成文件名）

    输出字段:
        - srt_file (str): 最终SRT字幕文件路径
        - json_file (str): 最终JSON字幕文件路径
        - subtitles_count (int, 可选): 字幕条目数量
    """

    def __init__(self, stage_name: str, context):
        super().__init__(stage_name, context)
        self.ocr_download_dir = None

    def validate_input(self) -> None:
        """
        验证输入参数。

        ocr_results_path 可以从前置节点获取，
        但 video_path 是必需的。
        """
        # video_path 在 execute_core_logic 中验证
        pass

    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行后处理和生成最终字幕核心逻辑。

        Returns:
            包含字幕文件信息的字典
        """
        workflow_id = self.context.workflow_id
        input_data = self.get_input_data()

        # 获取 OCR 结果路径
        ocr_results_path = self._get_ocr_results_path(input_data)

        if not ocr_results_path:
            raise ValueError(
                "无法获取OCR结果文件：请提供 ocr_results_path 或 ocr_results_file 参数，"
                "或确保 paddleocr.perform_ocr 任务已成功完成"
            )

        # 如果是 URL，下载文件
        if self._is_url(ocr_results_path):
            ocr_results_path = self._download_ocr_results_from_url(ocr_results_path)

        # 验证文件存在
        if not os.path.exists(ocr_results_path):
            raise FileNotFoundError(f"OCR结果文件不存在: {ocr_results_path}")

        logger.info(f"[{workflow_id}] OCR结果文件路径: {ocr_results_path}")

        # 加载 OCR 结果
        with open(ocr_results_path, 'r', encoding='utf-8') as f:
            ocr_results = json.load(f)

        logger.info(f"[{workflow_id}] 加载了 {len(ocr_results)} 条OCR结果")

        # 获取视频路径（必需）
        video_path = get_param_with_fallback(
            "video_path",
            input_data,
            self.context
        )

        if not video_path:
            raise ValueError("缺少 'video_path' 参数，无法获取FPS和生成文件名")

        logger.info(f"[{workflow_id}] 视频文件路径: {video_path}")

        # 获取视频 FPS
        fps = self._get_video_fps(video_path)
        logger.info(f"[{workflow_id}] 视频FPS: {fps}")

        # 后处理 OCR 结果
        final_subtitles = self._postprocess_ocr_results(ocr_results, fps)

        if not final_subtitles:
            logger.warning(
                f"[{workflow_id}] 后处理完成，但未生成任何有效字幕"
            )
            return {
                "srt_file": None,
                "json_file": None,
                "subtitles_count": 0
            }

        # 生成字幕文件
        video_basename = os.path.basename(video_path)
        video_name, _ = os.path.splitext(video_basename)

        final_srt_path = build_node_output_path(
            task_id=workflow_id,
            node_name=self.stage_name,
            file_type="subtitle",
            filename=f"{video_name}.srt"
        )
        final_json_path = build_node_output_path(
            task_id=workflow_id,
            node_name=self.stage_name,
            file_type="data",
            filename=f"{video_name}.json"
        )
        ensure_directory(final_srt_path)
        ensure_directory(final_json_path)

        # 转换为 SubtitleEntry 对象
        entries = []
        for i, sub in enumerate(final_subtitles, 1):
            entry = SubtitleEntry(
                index=i,
                start_time=sub['startTime'],
                end_time=sub['endTime'],
                text=sub['text']
            )
            entries.append(entry)

        # 写入 SRT 文件
        write_srt_file(entries, final_srt_path)

        # 写入 JSON 文件
        with open(final_json_path, 'w', encoding='utf-8') as f:
            json.dump(final_subtitles, f, ensure_ascii=False, indent=4)

        logger.info(
            f"[{workflow_id}] 后处理完成，生成 {len(final_subtitles)} 条字幕"
        )
        logger.info(f"[{workflow_id}] SRT文件: {final_srt_path}")
        logger.info(f"[{workflow_id}] JSON文件: {final_json_path}")

        return {
            "srt_file": final_srt_path,
            "json_file": final_json_path,
            "subtitles_count": len(final_subtitles)
        }

    def _get_ocr_results_path(self, input_data: Dict[str, Any]) -> str:
        """
        获取 OCR 结果文件路径。

        优先级:
        1. 参数/input_data 中的 ocr_results_path
        2. 参数/input_data 中的 ocr_results_file（URL）
        3. paddleocr.perform_ocr 节点的 ocr_results_path
        4. paddleocr.perform_ocr 节点的 ocr_results_minio_url

        Args:
            input_data: 输入数据

        Returns:
            ocr_results_path 路径或 URL
        """
        workflow_id = self.context.workflow_id

        # 优先从参数获取 ocr_results_path
        ocr_results_path = get_param_with_fallback(
            "ocr_results_path",
            input_data,
            self.context
        )
        if ocr_results_path:
            logger.info(
                f"[{workflow_id}] 从参数/input_data获取OCR结果路径: "
                f"{ocr_results_path}"
            )
            return ocr_results_path

        # 尝试从参数获取 ocr_results_file（URL）
        ocr_results_file = get_param_with_fallback(
            "ocr_results_file",
            input_data,
            self.context
        )
        if ocr_results_file:
            logger.info(
                f"[{workflow_id}] 从参数/input_data获取OCR结果文件URL: "
                f"{ocr_results_file}"
            )
            return ocr_results_file

        # 从 paddleocr.perform_ocr 获取
        ocr_stage = self.context.stages.get('paddleocr.perform_ocr')
        if ocr_stage and ocr_stage.output:
            ocr_results_path = ocr_stage.output.get('ocr_results_path')
            if not ocr_results_path:
                # 尝试从 MinIO URL 获取
                ocr_results_path = ocr_stage.output.get('ocr_results_minio_url')

            if ocr_results_path:
                logger.info(
                    f"[{workflow_id}] 从 paddleocr.perform_ocr "
                    f"获取OCR结果路径: {ocr_results_path}"
                )
                return ocr_results_path

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

    def _download_ocr_results_from_url(self, url: str) -> str:
        """
        从URL下载OCR结果文件。

        Args:
            url: MinIO或HTTP URL

        Returns:
            本地OCR结果文件路径
        """
        workflow_id = self.context.workflow_id
        from services.common.minio_url_utils import normalize_minio_url

        logger.info(
            f"[{workflow_id}] 检测到OCR结果文件为URL，尝试从远程下载: {url}"
        )

        # 创建临时目录
        self.ocr_download_dir = build_node_output_path(
            task_id=workflow_id,
            node_name=self.stage_name,
            file_type="temp",
            filename=f"download_ocr_{int(time.time())}"
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
            os.makedirs(self.ocr_download_dir, exist_ok=True)

            local_ocr_results_path = file_service.resolve_and_download(
                download_url,
                self.ocr_download_dir
            )

            logger.info(
                f"[{workflow_id}] OCR结果文件下载成功: {local_ocr_results_path}"
            )

            return local_ocr_results_path

        except Exception as e:
            logger.error(f"[{workflow_id}] OCR结果文件下载过程出错: {e}")
            raise RuntimeError(f"无法从URL下载OCR结果文件: {e}") from e

    def _get_video_fps(self, video_path: str) -> float:
        """
        获取视频的帧率（FPS）。

        Args:
            video_path: 视频文件路径

        Returns:
            视频帧率
        """
        workflow_id = self.context.workflow_id

        try:
            import av
            with av.open(video_path) as container:
                fps = float(container.streams.video[0].average_rate)
                return fps
        except Exception as e:
            logger.warning(
                f"[{workflow_id}] 无法从视频元数据获取FPS: {e}。使用默认值 30.0"
            )
            return 30.0

    def _postprocess_ocr_results(
        self,
        ocr_results: List[Dict[str, Any]],
        fps: float
    ) -> List[Dict[str, Any]]:
        """
        后处理 OCR 结果，生成最终字幕。

        Args:
            ocr_results: OCR识别结果列表
            fps: 视频帧率

        Returns:
            最终字幕列表
        """
        workflow_id = self.context.workflow_id

        try:
            # 使用 SubtitlePostprocessor 进行后处理
            from services.workers.paddleocr_service.app.modules.postprocessor import SubtitlePostprocessor
            from services.common.config_loader import CONFIG

            postprocessor = SubtitlePostprocessor(CONFIG.get('postprocessor', {}))
            final_subtitles = postprocessor.format_from_full_frames(
                ocr_results,
                fps
            )

            logger.info(
                f"[{workflow_id}] 后处理完成，生成 {len(final_subtitles)} 条字幕"
            )

            return final_subtitles

        except Exception as e:
            logger.error(f"[{workflow_id}] 后处理OCR结果失败: {e}", exc_info=True)
            raise RuntimeError(f"后处理OCR结果失败: {e}") from e

    def cleanup(self) -> None:
        """
        清理临时文件和目录。
        """
        workflow_id = self.context.workflow_id

        from services.common.config_loader import get_cleanup_temp_files_config
        import shutil

        if get_cleanup_temp_files_config():
            # 清理OCR下载目录
            if self.ocr_download_dir and os.path.exists(self.ocr_download_dir):
                try:
                    shutil.rmtree(self.ocr_download_dir)
                    logger.info(
                        f"[{workflow_id}] 清理OCR下载目录: {self.ocr_download_dir}"
                    )
                except Exception as e:
                    logger.warning(f"[{workflow_id}] 清理OCR下载目录失败: {e}")

    def get_cache_key_fields(self) -> List[str]:
        """
        返回用于生成缓存键的字段列表。

        后处理结果依赖于 OCR 结果和视频路径。
        """
        return ["ocr_results_path", "video_path"]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段列表。

        后处理的核心输出是 srt_file 和 json_file。
        """
        return ["srt_file", "json_file"]
