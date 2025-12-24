"""
WService TTS 片段准备执行器。
"""

from typing import Dict, Any, List

from services.common.base_node_executor import BaseNodeExecutor
from services.common.logger import get_logger
from services.common.parameter_resolver import get_param_with_fallback
from services.common.config_loader import CONFIG

logger = get_logger(__name__)


class WServicePrepareTtsSegmentsExecutor(BaseNodeExecutor):
    """
    WService TTS 片段准备执行器。

    为 TTS 参考音准备和优化字幕片段。

    输入参数:
        - segments_data (list, 可选): 直接传入字幕片段数据
        - segments_file (str, 可选): 字幕片段数据文件路径
        - source_stage_names (list, 可选): 自定义源阶段名称列表

    输出字段:
        - prepared_segments (list): 准备好的片段列表
        - source_stage (str): 数据来源阶段
        - total_segments (int): 片段总数
        - input_summary (dict): 输入数据摘要
            - original_segments_count (int): 原始片段数量
            - prepared_segments_count (int): 准备后片段数量
            - data_source (str): 数据来源
    """

    def __init__(self, stage_name: str, context):
        super().__init__(stage_name, context)

    def validate_input(self) -> None:
        """
        验证输入参数。

        至少需要提供以下之一：
        - segments_data 或 segments_file
        - 有效的上游节点
        """
        input_data = self.get_input_data()
        workflow_id = self.context.workflow_id

        # 检查是否有直接数据或文件
        has_data = (
            get_param_with_fallback("segments_data", input_data, self.context) is not None
            or get_param_with_fallback("segments_file", input_data, self.context) is not None
        )

        if not has_data:
            # 检查默认源阶段
            default_source_stage_names = [
                'wservice.merge_with_word_timestamps',
                'wservice.merge_speaker_segments',
                'wservice.generate_subtitle_files',
                'wservice.ai_optimize_subtitles',
                'faster_whisper.transcribe_audio'
            ]

            has_valid_source = any(
                self.context.stages.get(stage_name)
                and self.context.stages[stage_name].status in ['SUCCESS', 'COMPLETED']
                for stage_name in default_source_stage_names
            )

            if not has_valid_source:
                raise ValueError(
                    "缺少必需参数: 请提供 segments_data/segments_file 参数，"
                    "或确保有有效的上游节点"
                )

        logger.info(f"[{workflow_id}] 输入参数验证通过")

    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行 TTS 片段准备核心逻辑。

        Returns:
            包含准备结果的字典
        """
        workflow_id = self.context.workflow_id
        input_data = self.get_input_data()

        logger.info(f"[{workflow_id}] 开始准备 TTS 片段")

        # 获取字幕片段数据
        segments, source_name = self._get_segments(input_data)
        if not segments:
            raise ValueError("无法获取字幕片段数据")

        logger.info(f"[{workflow_id}] 数据来源: {source_name}, 片段数量: {len(segments)}")

        # 执行 TTS 准备逻辑
        service_config = CONFIG.get('wservice', {})
        merger_config = service_config.get('tts_merger_settings', {})

        # 导入 TtsMerger（从 tasks 模块）
        from services.workers.wservice.app.tasks import TtsMerger

        merger = TtsMerger(config=merger_config)
        prepared_segments = merger.merge_segments(segments)

        logger.info(f"[{workflow_id}] TTS 片段准备完成，生成 {len(prepared_segments)} 个片段")

        return {
            'prepared_segments': prepared_segments,
            'source_stage': source_name,
            'total_segments': len(prepared_segments),
            'input_summary': {
                'original_segments_count': len(segments),
                'prepared_segments_count': len(prepared_segments),
                'data_source': source_name
            }
        }

    def _get_segments(self, input_data: Dict[str, Any]) -> tuple:
        """
        获取字幕片段数据。

        优先级:
        1. 直接传入的 segments_data
        2. segments_file 文件路径
        3. 上游节点（按优先级顺序）

        Args:
            input_data: 输入数据

        Returns:
            (segments, source_name) 元组
        """
        workflow_id = self.context.workflow_id

        # 1. 尝试直接获取片段数据
        segments = get_param_with_fallback(
            "segments_data",
            input_data,
            self.context
        )
        if segments:
            logger.info(f"[{workflow_id}] 从 segments_data 获取片段")
            return segments, 'input_data.segments_data'

        # 2. 尝试从文件加载
        segments_file = get_param_with_fallback(
            "segments_file",
            input_data,
            self.context
        )
        if segments_file:
            from services.common.file_service import get_file_service
            import os
            import json

            file_service = get_file_service()

            # 规范化路径
            if not segments_file.startswith(("http://", "https://", "minio://")):
                if not os.path.isabs(segments_file):
                    segments_file = os.path.join(
                        self.context.shared_storage_path,
                        segments_file
                    )

            # 下载文件（如果需要）
            if segments_file.startswith(("http://", "https://", "minio://")):
                try:
                    segments_file = file_service.resolve_and_download(
                        segments_file,
                        self.context.shared_storage_path
                    )
                except Exception as e:
                    logger.warning(f"[{workflow_id}] 文件下载失败: {e}")
                    segments_file = None

            # 加载文件
            if segments_file and os.path.exists(segments_file):
                try:
                    with open(segments_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    if isinstance(data, list):
                        segments = data
                    elif isinstance(data, dict) and 'segments' in data:
                        segments = data['segments']

                    if segments:
                        logger.info(
                            f"[{workflow_id}] 从文件加载片段: {segments_file}"
                        )
                        return segments, 'input_data.segments_file'
                except Exception as e:
                    logger.error(f"[{workflow_id}] 加载文件失败: {e}")

        # 3. 从上游节点获取
        source_stage_names = get_param_with_fallback(
            "source_stage_names",
            input_data,
            self.context
        )

        # 默认的源阶段列表
        if not source_stage_names:
            source_stage_names = [
                'wservice.merge_with_word_timestamps',
                'wservice.merge_speaker_segments',
                'wservice.generate_subtitle_files',
                'wservice.ai_optimize_subtitles',
                'faster_whisper.transcribe_audio'
            ]

        segments, source_name = self._get_segments_from_source_stages(source_stage_names)
        if segments:
            return segments, source_name

        return [], 'unknown'

    def _get_segments_from_source_stages(
        self,
        source_stage_names: List[str]
    ) -> tuple:
        """
        从指定的前置阶段列表中安全地获取字幕片段。

        Args:
            source_stage_names: 要搜索的阶段名称列表

        Returns:
            (segments, source_name) 元组
        """
        import os
        import json

        for stage_name in source_stage_names:
            stage = self.context.stages.get(stage_name)
            if not stage or stage.status not in ['SUCCESS', 'COMPLETED']:
                continue

            logger.info(f"找到潜在的源数据于阶段: '{stage_name}'")

            # 策略1: 尝试从 'merged_segments' 获取
            segments = stage.output.get('merged_segments')
            if segments and isinstance(segments, list):
                logger.info(
                    f"成功从 '{stage_name}' 的 'merged_segments' 字段获取 "
                    f"{len(segments)} 个片段"
                )
                return segments, stage_name

            # 策略2: 尝试从 'prepared_segments' 获取
            segments = stage.output.get('prepared_segments')
            if segments and isinstance(segments, list):
                logger.info(
                    f"成功从 '{stage_name}' 的 'prepared_segments' 字段获取 "
                    f"{len(segments)} 个片段"
                )
                return segments, stage_name

            # 策略3: 回退到从文件加载
            segments_file = (
                stage.output.get('segments_file')
                or stage.output.get('optimized_file_path')
                or stage.output.get('merged_segments_file')
            )
            if segments_file and os.path.exists(segments_file):
                try:
                    with open(segments_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    if isinstance(data, list):
                        segments = data
                    elif isinstance(data, dict) and 'segments' in data:
                        segments = data['segments']

                    if segments:
                        logger.info(
                            f"成功从文件 '{segments_file}' 加载 {len(segments)} 个片段"
                        )
                        return segments, stage_name
                except Exception as e:
                    logger.warning(f"加载文件失败: {segments_file}, 错误: {e}")

            # 策略4: 最后尝试从 'segments' 字段直接获取
            segments = stage.output.get('segments')
            if segments and isinstance(segments, list):
                logger.info(
                    f"成功从 '{stage_name}' 的 'segments' 字段获取 "
                    f"{len(segments)} 个片段"
                )
                return segments, stage_name

        return [], 'unknown'

    def get_cache_key_fields(self) -> List[str]:
        """
        返回用于生成缓存键的字段列表。

        TTS 准备结果依赖于输入片段和配置。
        """
        return ["segments_file", "source_stage_names"]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段列表。

        TTS 准备的核心输出是 prepared_segments。
        """
        return ["prepared_segments"]
