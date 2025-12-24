"""
Audio Separator 人声分离执行器。

该模块实现了音频文件的人声/背景音分离节点执行器。
"""

import os
from pathlib import Path
from typing import Dict, Any, List
from services.common.base_node_executor import BaseNodeExecutor
from services.common.file_service import get_file_service
from services.common.logger import get_logger
from services.common.config_loader import CONFIG

logger = get_logger(__name__)


class AudioSeparatorSeparateVocalsExecutor(BaseNodeExecutor):
    """
    Audio Separator 人声分离执行器。

    功能：使用 UVR-MDX 模型将音频分离为人声和背景音。

    输入参数：
        - audio_path: 音频文件路径(必需)
        - quality_mode: 质量模式(可选: default/high_quality/fast)
        - model_type: 模型类型(可选: mdx/demucs)
        - use_vocal_optimization: 是否使用人声优化(可选)
        - vocal_optimization_level: 人声优化级别(可选)

    输出字段：
        - vocal_audio: 人声音频文件路径
        - vocal_audio_minio_url: 人声音频 MinIO URL
        - all_audio_files: 所有分离音轨文件路径列表
        - all_audio_minio_urls: 所有音轨 MinIO URL 列表
        - model_used: 使用的模型名称
        - quality_mode: 使用的质量模式
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

        # 验证可选参数
        if "quality_mode" in input_data:
            valid_modes = ["default", "high_quality", "fast"]
            if input_data["quality_mode"] not in valid_modes:
                raise ValueError(
                    f"参数 'quality_mode' 必须是以下之一: {valid_modes}"
                )

        if "model_type" in input_data:
            valid_types = ["mdx", "demucs"]
            if input_data["model_type"].lower() not in valid_types:
                raise ValueError(
                    f"参数 'model_type' 必须是以下之一: {valid_types}"
                )

    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行核心业务逻辑：音频人声分离。

        Returns:
            包含分离结果的字典
        """
        input_data = self.get_input_data()
        audio_path = input_data["audio_path"]

        # 文件下载
        file_service = get_file_service()
        if not os.path.exists(audio_path):
            logger.info(f"[{self.stage_name}] 开始下载音频文件: {audio_path}")
            audio_path = file_service.resolve_and_download(
                audio_path, self.context.shared_storage_path
            )
            logger.info(f"[{self.stage_name}] 音频文件下载完成: {audio_path}")

        # 验证文件存在
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        logger.info(f"[{self.stage_name}] 开始音频分离任务")

        # 加载配置
        config = CONFIG.get('audio_separator_service', {})
        quality_mode = input_data.get("quality_mode", "default")
        use_vocal_optimization = input_data.get("use_vocal_optimization", False)
        vocal_optimization_level = input_data.get(
            "vocal_optimization_level",
            config.get('vocal_optimization_level')
        )
        model_type = input_data.get("model_type", config.get('model_type', "mdx"))

        logger.info(f"[{self.stage_name}] 质量模式: {quality_mode}")
        logger.info(f"[{self.stage_name}] 使用人声优化: {use_vocal_optimization}")
        logger.info(f"[{self.stage_name}] 模型类型: {model_type}")

        # 确定使用的模型
        model_name = self._determine_model_name(
            model_type, quality_mode, config, input_data
        )
        logger.info(f"[{self.stage_name}] 使用模型: {model_name}")

        # 创建输出目录
        task_output_dir = Path(
            f"{self.context.shared_storage_path}/audio/audio_separated"
        )
        task_output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[{self.stage_name}] 输出目录: {task_output_dir}")

        # 执行音频分离
        logger.info(f"[{self.stage_name}] 开始执行分离 (subprocess模式)...")
        result = self._separate_audio(
            audio_path,
            model_name,
            str(task_output_dir),
            model_type,
            use_vocal_optimization,
            vocal_optimization_level
        )

        logger.info(f"[{self.stage_name}] 分离完成")
        logger.info(f"[{self.stage_name}] 人声文件: {result.get('vocals')}")
        logger.info(f"[{self.stage_name}] 背景音文件: {result.get('instrumental')}")

        # 准备输出数据
        all_audio_files = list(result.get('all_tracks', {}).values())
        vocal_audio = result.get('vocals')
        instrumental_audio = result.get('instrumental')

        # 确保路径是完整的
        vocal_audio = self._ensure_absolute_path(vocal_audio, task_output_dir)
        instrumental_audio = self._ensure_absolute_path(
            instrumental_audio, task_output_dir
        )
        all_audio_files = [
            self._ensure_absolute_path(f, task_output_dir) for f in all_audio_files
        ]

        if not vocal_audio:
            raise ValueError("无法确定人声音频文件")

        if not instrumental_audio:
            logger.warning(
                f"[{self.stage_name}] 未能确定背景声音频文件，将回退到音频列表"
            )
            if all_audio_files:
                instrumental_audio = (
                    all_audio_files[0] if all_audio_files[0] != vocal_audio
                    else (all_audio_files[1] if len(all_audio_files) > 1 else vocal_audio)
                )

        # 构建输出数据
        return {
            "vocal_audio": vocal_audio,
            "all_audio_files": all_audio_files,
            "model_used": model_name,
            "quality_mode": quality_mode
        }

    def _determine_model_name(
        self,
        model_type: str,
        quality_mode: str,
        config: dict,
        input_data: dict
    ) -> str:
        """
        确定使用的模型名称。

        Args:
            model_type: 模型类型
            quality_mode: 质量模式
            config: 服务配置
            input_data: 输入数据

        Returns:
            模型名称
        """
        # 如果直接指定了模型名称，优先使用
        if "model_name" in input_data:
            return input_data["model_name"]

        if model_type.lower() == "demucs":
            if quality_mode == 'high_quality':
                return config.get('demucs_high_quality_model', 'htdemucs_6s')
            elif quality_mode == 'fast':
                return config.get('demucs_fast_model', 'htdemucs')
            else:
                return config.get('demucs_balanced_model', 'htdemucs')
        else:  # mdx
            if quality_mode == 'high_quality':
                return config.get('high_quality_model', 'UVR-MDX-NET-Inst_HQ_3')
            elif quality_mode == 'fast':
                return config.get('fast_model', 'UVR_MDXNET_KARA_2')
            else:
                return config.get('default_model', 'UVR-MDX-NET-Inst_3')

    def _separate_audio(
        self,
        audio_path: str,
        model_name: str,
        output_dir: str,
        model_type: str,
        use_vocal_optimization: bool,
        vocal_optimization_level: str
    ) -> dict:
        """
        执行音频分离。

        Args:
            audio_path: 音频文件路径
            model_name: 模型名称
            output_dir: 输出目录
            model_type: 模型类型
            use_vocal_optimization: 是否使用人声优化
            vocal_optimization_level: 人声优化级别

        Returns:
            分离结果字典
        """
        from services.workers.audio_separator_service.app.model_manager import (
            get_model_manager
        )

        model_manager = get_model_manager()
        return model_manager.separate_audio_subprocess(
            audio_path=audio_path,
            model_name=model_name,
            output_dir=output_dir,
            model_type=model_type,
            use_vocal_optimization=use_vocal_optimization,
            vocal_optimization_level=vocal_optimization_level
        )

    def _ensure_absolute_path(self, file_path: str, base_dir: Path) -> str:
        """
        确保文件路径是绝对路径。

        Args:
            file_path: 文件路径
            base_dir: 基础目录

        Returns:
            绝对路径
        """
        if not file_path:
            return file_path

        if not os.path.isabs(file_path):
            return str(base_dir / file_path)

        return file_path

    def get_cache_key_fields(self) -> List[str]:
        """
        返回缓存键字段。

        缓存依赖于输入音频、质量模式和模型类型。
        """
        return ["audio_path", "quality_mode", "model_type"]

    def get_custom_path_fields(self) -> List[str]:
        """
        返回自定义路径字段列表。

        vocal_audio 和 all_audio_files 不符合标准后缀规则，需要声明为自定义字段。
        """
        return ["vocal_audio", "all_audio_files"]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段(用于缓存验证)。

        音频分离的核心输出是 vocal_audio。
        """
        return ["vocal_audio"]
