"""
Faster-Whisper 语音转录执行器。

该模块实现了音频文件的语音转录节点执行器。
"""

import os
import json
import time
from typing import Dict, Any, List
from services.common.base_node_executor import BaseNodeExecutor
from services.common.file_service import get_file_service
from services.common.logger import get_logger
from services.common.config_loader import CONFIG
from services.common.path_builder import build_node_output_path, ensure_directory

logger = get_logger(__name__)


class FasterWhisperTranscribeExecutor(BaseNodeExecutor):
    """
    Faster-Whisper 语音转录执行器。

    功能：使用 Faster-Whisper 模型对音频文件进行语音识别转录。

    输入参数：
        - audio_path: 音频文件路径(必需)

    输出字段：
        - segments_file: 转录结果文件路径
        - audio_duration: 音频时长(秒)
        - language: 识别的语言
        - model_name: 使用的模型名称
        - device: 使用的设备(cuda/cpu)
        - enable_word_timestamps: 是否启用词级时间戳
        - statistics: 统计信息(包含 transcribe_duration)
        - segments_count: 片段数量
    """

    def validate_input(self) -> None:
        """验证输入参数"""
        input_data = self.get_input_data()

        # 检查必需参数
        if "audio_path" not in input_data:
            raise ValueError("缺少必需参数: audio_path")

        # 检查参数有效性
        audio_path = input_data["audio_path"]
        if not audio_path:
            raise ValueError("参数 'audio_path' 不能为空")

    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行核心业务逻辑：对音频进行语音转录。

        Returns:
            包含转录结果的字典
        """
        input_data = self.get_input_data()
        audio_path = input_data["audio_path"]

        # 文件下载
        file_service = get_file_service()
        logger.info(f"[{self.stage_name}] 开始下载音频文件: {audio_path}")
        audio_path = file_service.resolve_and_download(
            audio_path, self.context.shared_storage_path
        )
        logger.info(f"[{self.stage_name}] 音频文件下载完成: {audio_path}")

        # 验证文件存在
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        # 加载服务配置
        service_config = CONFIG.get('faster_whisper_service', {})
        enable_word_timestamps = service_config.get('enable_word_timestamps', True)

        logger.info(f"[{self.stage_name}] 开始语音转录流程")
        logger.info(f"[{self.stage_name}] 词级时间戳: {'启用' if enable_word_timestamps else '禁用'}")

        # 执行语音转录
        logger.info(f"[{self.stage_name}] 执行语音转录...")
        transcribe_result = self._transcribe_audio_with_lock(
            audio_path, service_config
        )

        logger.info(
            f"[{self.stage_name}] 转录完成，获得 {len(transcribe_result.get('segments', []))} 个片段"
        )

        # 创建转录数据文件 - 使用 path_builder 生成标准化路径
        workflow_short_id = self.context.workflow_id[:8]
        transcribe_data_file = build_node_output_path(
            task_id=self.context.workflow_id,
            node_name=self.stage_name,
            file_type="data",
            filename=f"transcribe_data_{workflow_short_id}.json"
        )
        ensure_directory(transcribe_data_file)

        # 准备转录数据文件内容
        transcribe_data_content = {
            "metadata": {
                "task_name": self.stage_name,
                "workflow_id": self.context.workflow_id,
                "audio_file": os.path.basename(audio_path),
                "total_duration": transcribe_result.get('audio_duration', 0),
                "language": transcribe_result.get('language', 'unknown'),
                "word_timestamps_enabled": enable_word_timestamps,
                "model_name": transcribe_result.get('model_name', 'unknown'),
                "device": transcribe_result.get('device', 'unknown'),
                "transcribe_method": "gpu-lock-v3-split",
                "created_at": time.time()
            },
            "segments": transcribe_result.get('segments', []),
            "statistics": {
                "total_segments": len(transcribe_result.get('segments', [])),
                "total_words": sum(
                    len(seg.get('words', []))
                    for seg in transcribe_result.get('segments', [])
                ),
                "transcribe_duration": transcribe_result.get('transcribe_duration', 0),
                "average_segment_duration": 0
            }
        }

        # 计算平均片段时长
        if transcribe_data_content["statistics"]["total_segments"] > 0:
            total_duration = sum(
                seg.get('end', 0) - seg.get('start', 0)
                for seg in transcribe_result.get('segments', [])
            )
            transcribe_data_content["statistics"]["average_segment_duration"] = (
                total_duration / transcribe_data_content["statistics"]["total_segments"]
            )

        # 写入转录数据文件
        with open(transcribe_data_file, "w", encoding="utf-8") as f:
            json.dump(transcribe_data_content, f, ensure_ascii=False, indent=2)

        logger.info(f"[{self.stage_name}] 转录数据文件生成完成: {transcribe_data_file}")

        # 统计信息
        total_words = transcribe_data_content["statistics"]["total_words"]
        transcribe_duration = transcribe_result.get('transcribe_duration', 0)
        audio_duration = transcribe_result.get('audio_duration', 0)

        logger.info(f"[{self.stage_name}] ========== 转录统计信息 ==========")
        logger.info(f"[{self.stage_name}] 总片段数: {transcribe_data_content['statistics']['total_segments']}")
        logger.info(f"[{self.stage_name}] 总词数: {total_words}")
        logger.info(f"[{self.stage_name}] 音频时长: {audio_duration:.2f}秒")
        logger.info(f"[{self.stage_name}] 转录耗时: {transcribe_duration:.2f}秒")
        if transcribe_duration > 0:
            logger.info(f"[{self.stage_name}] 处理速度: {audio_duration/transcribe_duration:.2f}x")
        logger.info(f"[{self.stage_name}] =================================")

        # 构建输出数据
        return {
            "segments_file": transcribe_data_file,
            "audio_duration": transcribe_result.get('audio_duration', 0),
            "language": transcribe_result.get('language', 'unknown'),
            "model_name": transcribe_result.get('model_name', 'unknown'),
            "device": transcribe_result.get('device', 'unknown'),
            "enable_word_timestamps": enable_word_timestamps,
            "statistics": transcribe_data_content["statistics"],
            "segments_count": len(transcribe_result.get('segments', []))
        }

    def _transcribe_audio_with_lock(
        self,
        audio_path: str,
        service_config: dict
    ) -> dict:
        """
        使用 GPU 锁执行语音转录。

        这个方法调用原有的 _transcribe_audio_with_lock 函数。

        Args:
            audio_path: 音频文件路径
            service_config: 服务配置

        Returns:
            转录结果字典
        """
        from services.workers.faster_whisper_service.app.tasks import (
            _transcribe_audio_with_lock
        )

        return _transcribe_audio_with_lock(
            audio_path,
            service_config,
            self.stage_name,
            self.context
        )

    def get_cache_key_fields(self) -> List[str]:
        """
        返回缓存键字段。

        缓存依赖于输入音频文件,相同音频的转录结果相同。
        """
        return ["audio_path"]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段(用于缓存验证)。

        语音转录的核心输出是 segments_file。
        """
        return ["segments_file"]
