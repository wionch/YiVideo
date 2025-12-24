"""
IndexTTS 语音生成执行器。
"""

import os
from typing import Dict, Any, List

from services.common.base_node_executor import BaseNodeExecutor
from services.common.logger import get_logger
from services.common.file_service import get_file_service
from services.common.parameter_resolver import get_param_with_fallback

logger = get_logger(__name__)


class IndexTTSGenerateSpeechExecutor(BaseNodeExecutor):
    """
    IndexTTS 语音生成执行器。

    使用 IndexTTS2 引擎将文本转换为语音。

    输入参数:
        - text (str, 必需): 要转换的文本
        - output_path (str, 必需): 输出音频文件路径
        - spk_audio_prompt (str, 必需): 说话人参考音频路径（本地或URL）
        - emo_audio_prompt (str, 可选): 情感参考音频路径（本地或URL）
        - emotion_alpha (float, 可选): 情感强度 (默认1.0)
        - emotion_vector (Any, 可选): 情感向量
        - emotion_text (str, 可选): 情感文本
        - use_emo_text (bool, 可选): 是否使用情感文本 (默认False)
        - use_random (bool, 可选): 是否使用随机情感 (默认False)
        - max_text_tokens_per_segment (int, 可选): 每段最大文本token数 (默认120)
        - verbose (bool, 可选): 是否输出详细日志 (默认False)

    输出字段:
        - audio_path (str): 生成的音频文件路径
        - status (str): 生成状态
        - duration (float, 可选): 音频时长（秒）
        - text_length (int, 可选): 输入文本长度
    """

    def __init__(self, stage_name: str, context):
        super().__init__(stage_name, context)
        self.downloaded_reference_audio = None
        self.downloaded_emotion_audio = None

    def validate_input(self) -> None:
        """
        验证输入参数。

        text, output_path, spk_audio_prompt 是必需的。
        """
        input_data = self.get_input_data()

        # 验证 text
        text = get_param_with_fallback("text", input_data, self.context)
        if not text:
            raise ValueError("缺少必需参数: text")

        # 验证 output_path
        output_path = get_param_with_fallback("output_path", input_data, self.context)
        if not output_path:
            raise ValueError("缺少必需参数: output_path")

        # 验证 reference_audio (支持多种参数名)
        reference_audio = self._get_reference_audio(input_data)
        if not reference_audio:
            raise ValueError(
                "缺少必需参数: spk_audio_prompt (说话人参考音频)。"
                "IndexTTS2是基于参考音频的语音合成系统，必须提供说话人参考音频"
            )

    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行语音生成核心逻辑。

        Returns:
            包含音频文件信息的字典
        """
        workflow_id = self.context.workflow_id
        input_data = self.get_input_data()

        # 获取参数
        text = get_param_with_fallback("text", input_data, self.context)
        output_path = get_param_with_fallback("output_path", input_data, self.context)

        # 获取参考音频
        reference_audio = self._get_reference_audio(input_data)

        # 下载参考音频（如果是URL）
        if reference_audio and not os.path.exists(reference_audio):
            logger.info(f"[{workflow_id}] 开始下载音色参考音频: {reference_audio}")
            file_service = get_file_service()
            self.downloaded_reference_audio = file_service.resolve_and_download(
                reference_audio,
                self.context.shared_storage_path
            )
            reference_audio = self.downloaded_reference_audio
            logger.info(f"[{workflow_id}] 音色参考音频下载完成: {reference_audio}")

        # 验证参考音频文件存在
        if not os.path.exists(reference_audio):
            raise FileNotFoundError(f"参考音频文件不存在: {reference_audio}")

        # 获取情感参考音频
        emotion_reference = self._get_emotion_reference(input_data)

        # 下载情感参考音频（如果是URL）
        if emotion_reference and not os.path.exists(emotion_reference):
            logger.info(f"[{workflow_id}] 开始下载情感参考音频: {emotion_reference}")
            file_service = get_file_service()
            self.downloaded_emotion_audio = file_service.resolve_and_download(
                emotion_reference,
                self.context.shared_storage_path
            )
            emotion_reference = self.downloaded_emotion_audio
            logger.info(f"[{workflow_id}] 情感参考音频下载完成: {emotion_reference}")

        # 获取其他参数
        emotion_alpha = float(get_param_with_fallback(
            "emotion_alpha", input_data, self.context, default=1.0
        ))
        emotion_vector = get_param_with_fallback(
            "emotion_vector", input_data, self.context
        )
        emotion_text = get_param_with_fallback(
            "emotion_text", input_data, self.context
        )
        use_emo_text = bool(get_param_with_fallback(
            "use_emo_text", input_data, self.context, default=False
        ))
        use_random = bool(get_param_with_fallback(
            "use_random", input_data, self.context, default=False
        ))
        max_text_tokens_per_segment = int(get_param_with_fallback(
            "max_text_tokens_per_segment", input_data, self.context, default=120
        ))
        verbose = bool(get_param_with_fallback(
            "verbose", input_data, self.context, default=False
        ))

        logger.info(f"[{workflow_id}] 文本长度: {len(text)} 字符")
        logger.info(f"[{workflow_id}] 音色参考: {reference_audio}")
        if emotion_reference:
            logger.info(f"[{workflow_id}] 情感参考: {emotion_reference}")

        # 创建输出目录
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"[{workflow_id}] 创建输出目录: {output_dir}")

        # 调用 TTS 引擎生成语音
        result = self._generate_speech(
            text=text,
            output_path=output_path,
            reference_audio=reference_audio,
            emotion_reference=emotion_reference,
            emotion_alpha=emotion_alpha,
            emotion_vector=emotion_vector,
            emotion_text=emotion_text,
            use_random=use_random,
            max_text_tokens_per_segment=max_text_tokens_per_segment
        )

        logger.info(f"[{workflow_id}] 语音生成完成: {output_path}")

        return {
            "audio_path": output_path,
            "status": result.get("status", "success"),
            "duration": result.get("duration"),
            "text_length": len(text)
        }

    def _get_reference_audio(self, input_data: Dict[str, Any]) -> str:
        """
        获取参考音频路径。

        支持多种参数名和上游节点回退。

        优先级:
        1. 参数/input_data 中的 spk_audio_prompt
        2. 参数/input_data 中的 reference_audio
        3. 参数/input_data 中的 speaker_audio
        4. audio_separator.separate_vocals 节点的 vocal_audio
        5. ffmpeg.extract_audio 节点的 audio_path

        Args:
            input_data: 输入数据

        Returns:
            参考音频路径或 None
        """
        workflow_id = self.context.workflow_id

        # 优先从参数获取 spk_audio_prompt
        reference_audio = get_param_with_fallback(
            "spk_audio_prompt",
            input_data,
            self.context
        )
        if reference_audio:
            logger.info(
                f"[{workflow_id}] 从参数/input_data获取参考音频(spk_audio_prompt): "
                f"{reference_audio}"
            )
            return reference_audio

        # 尝试 reference_audio
        reference_audio = get_param_with_fallback(
            "reference_audio",
            input_data,
            self.context
        )
        if reference_audio:
            logger.info(
                f"[{workflow_id}] 从参数/input_data获取参考音频(reference_audio): "
                f"{reference_audio}"
            )
            return reference_audio

        # 尝试 speaker_audio
        reference_audio = get_param_with_fallback(
            "speaker_audio",
            input_data,
            self.context
        )
        if reference_audio:
            logger.info(
                f"[{workflow_id}] 从参数/input_data获取参考音频(speaker_audio): "
                f"{reference_audio}"
            )
            return reference_audio

        # 从 audio_separator.separate_vocals 获取人声
        separator_stage = self.context.stages.get('audio_separator.separate_vocals')
        if separator_stage and separator_stage.output:
            vocal_audio = separator_stage.output.get('vocal_audio')
            if vocal_audio:
                logger.info(
                    f"[{workflow_id}] 从 audio_separator.separate_vocals "
                    f"获取参考音频: {vocal_audio}"
                )
                return vocal_audio

        # 从 ffmpeg.extract_audio 获取音频
        ffmpeg_stage = self.context.stages.get('ffmpeg.extract_audio')
        if ffmpeg_stage and ffmpeg_stage.output:
            audio_path = ffmpeg_stage.output.get('audio_path')
            if audio_path:
                logger.info(
                    f"[{workflow_id}] 从 ffmpeg.extract_audio "
                    f"获取参考音频: {audio_path}"
                )
                return audio_path

        return None

    def _get_emotion_reference(self, input_data: Dict[str, Any]) -> str:
        """
        获取情感参考音频路径。

        优先级:
        1. 参数/input_data 中的 emo_audio_prompt
        2. 参数/input_data 中的 emotion_reference

        Args:
            input_data: 输入数据

        Returns:
            情感参考音频路径或 None
        """
        workflow_id = self.context.workflow_id

        # 优先从参数获取 emo_audio_prompt
        emotion_reference = get_param_with_fallback(
            "emo_audio_prompt",
            input_data,
            self.context
        )
        if emotion_reference:
            logger.info(
                f"[{workflow_id}] 从参数/input_data获取情感参考音频(emo_audio_prompt): "
                f"{emotion_reference}"
            )
            return emotion_reference

        # 尝试 emotion_reference
        emotion_reference = get_param_with_fallback(
            "emotion_reference",
            input_data,
            self.context
        )
        if emotion_reference:
            logger.info(
                f"[{workflow_id}] 从参数/input_data获取情感参考音频(emotion_reference): "
                f"{emotion_reference}"
            )
            return emotion_reference

        return None

    def _generate_speech(
        self,
        text: str,
        output_path: str,
        reference_audio: str,
        emotion_reference: str = None,
        emotion_alpha: float = 1.0,
        emotion_vector: Any = None,
        emotion_text: str = None,
        use_random: bool = False,
        max_text_tokens_per_segment: int = 120
    ) -> Dict[str, Any]:
        """
        调用 TTS 引擎生成语音。

        Args:
            text: 要转换的文本
            output_path: 输出音频文件路径
            reference_audio: 参考音频路径
            emotion_reference: 情感参考音频路径
            emotion_alpha: 情感强度
            emotion_vector: 情感向量
            emotion_text: 情感文本
            use_random: 是否使用随机情感
            max_text_tokens_per_segment: 每段最大文本token数

        Returns:
            生成结果字典
        """
        workflow_id = self.context.workflow_id

        try:
            # 导入 TTS 引擎
            from services.workers.indextts_service.app.tasks import get_tts_engine

            # 获取 TTS 引擎实例
            engine = get_tts_engine()

            # 生成语音
            result = engine.generate_speech(
                text=text,
                output_path=output_path,
                reference_audio=reference_audio,
                emotion_reference=emotion_reference,
                emotion_alpha=emotion_alpha,
                emotion_vector=emotion_vector,
                emotion_text=emotion_text,
                use_random=use_random,
                max_text_tokens_per_segment=max_text_tokens_per_segment
            )

            logger.info(f"[{workflow_id}] TTS 引擎生成完成")

            return result

        except Exception as e:
            logger.error(f"[{workflow_id}] TTS 引擎生成失败: {e}", exc_info=True)
            raise RuntimeError(f"TTS 引擎生成失败: {e}") from e

    def cleanup(self) -> None:
        """
        清理临时文件和目录。
        """
        workflow_id = self.context.workflow_id

        from services.common.config_loader import get_cleanup_temp_files_config
        import shutil

        if get_cleanup_temp_files_config():
            # 清理下载的参考音频
            if self.downloaded_reference_audio and os.path.exists(self.downloaded_reference_audio):
                try:
                    os.remove(self.downloaded_reference_audio)
                    logger.info(
                        f"[{workflow_id}] 清理下载的参考音频: {self.downloaded_reference_audio}"
                    )
                except Exception as e:
                    logger.warning(f"[{workflow_id}] 清理参考音频失败: {e}")

            # 清理下载的情感参考音频
            if self.downloaded_emotion_audio and os.path.exists(self.downloaded_emotion_audio):
                try:
                    os.remove(self.downloaded_emotion_audio)
                    logger.info(
                        f"[{workflow_id}] 清理下载的情感参考音频: {self.downloaded_emotion_audio}"
                    )
                except Exception as e:
                    logger.warning(f"[{workflow_id}] 清理情感参考音频失败: {e}")

    def get_cache_key_fields(self) -> List[str]:
        """
        返回用于生成缓存键的字段列表。

        语音生成结果依赖于文本和参考音频。
        """
        return ["text", "spk_audio_prompt"]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段列表。

        语音生成的核心输出是 audio_path。
        """
        return ["audio_path"]
