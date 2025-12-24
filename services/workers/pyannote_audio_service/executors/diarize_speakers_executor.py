"""
Pyannote Audio 说话人分离执行器。
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, List

from services.common.base_node_executor import BaseNodeExecutor
from services.common.config_loader import get_config
from services.common.logger import get_logger
from services.common.file_service import get_file_service
from services.common.parameter_resolver import get_param_with_fallback

logger = get_logger(__name__)
config = get_config()


class PyannoteAudioDiarizeSpeakersExecutor(BaseNodeExecutor):
    """
    Pyannote Audio 说话人分离执行器。

    使用 subprocess 调用独立的推理脚本进行说话人分离，
    支持付费和免费两种 API 模式。

    输入参数:
        - audio_path (str, 可选): 音频文件路径，如果不提供则从前置节点获取

    输出字段:
        - diarization_file (str): 说话人分离结果文件路径
        - detected_speakers (list): 检测到的说话人列表
        - speaker_statistics (dict): 说话人统计信息
        - total_speakers (int): 说话人总数
        - total_segments (int): 说话片段总数
        - summary (str): 分离结果摘要
        - execution_method (str): 执行方法 (subprocess)
        - audio_source (str): 音频来源
        - api_type (str): API 类型 (paid/free)
        - model_name (str): 使用的模型名称
        - use_paid_api (bool): 是否使用付费 API
    """

    def validate_input(self) -> None:
        """
        验证输入参数。

        音频路径可以从参数获取，也可以从前置节点获取，
        因此这里不强制要求 audio_path 参数。
        """
        # 不强制要求 audio_path，因为可以从前置节点获取
        pass

    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行说话人分离核心逻辑。

        Returns:
            包含说话人分离结果的字典
        """
        workflow_id = self.context.workflow_id
        input_data = self.get_input_data()
        file_service = get_file_service()

        # 获取音频文件路径 - 智能源选择
        audio_path, audio_source = self._get_audio_path(input_data)

        if not audio_path:
            raise ValueError(
                "无法获取音频文件路径：请确保 ffmpeg.extract_audio 或 "
                "audio_separator.separate_vocals 任务已成功完成，"
                "或在 input_params 中提供 audio_path"
            )

        logger.info(f"[{workflow_id}] 音频源: {audio_source}, 路径: {audio_path}")

        # 下载音频文件（如果需要）
        if not os.path.exists(audio_path):
            logger.info(f"[{workflow_id}] 开始下载音频文件: {audio_path}")
            audio_path = file_service.resolve_and_download(
                audio_path,
                self.context.shared_storage_path
            )
            logger.info(f"[{workflow_id}] 音频文件下载完成: {audio_path}")

        # 检查音频文件是否存在
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        # 创建输出目录
        workflow_output_dir = Path(self.context.shared_storage_path) / "diarization"
        workflow_output_dir.mkdir(parents=True, exist_ok=True)

        # 准备输出文件路径
        output_file = workflow_output_dir / "diarization_result.json"

        # 调用 subprocess 执行推理
        result_data, execution_time = self._run_diarization_subprocess(
            audio_path,
            output_file
        )

        # 解析结果
        speaker_segments = result_data.get('segments', [])
        total_speakers = result_data.get('total_speakers', 0)
        metadata = result_data.get('metadata', {})
        api_type = metadata.get('api_type', 'free')
        model_name = metadata.get('model', 'unknown')

        # 生成说话人列表
        detected_speakers = [f"SPEAKER_{i:02d}" for i in range(total_speakers)]

        # 计算说话人统计信息
        speaker_statistics = self._calculate_speaker_statistics(
            detected_speakers,
            speaker_segments
        )

        # 获取配置
        service_config = config.get('pyannote_audio_service', {})
        use_paid_api = service_config.get('use_paid_api', False)

        # 构建输出数据
        output_data = {
            "diarization_file": str(output_file),
            "detected_speakers": detected_speakers,
            "speaker_statistics": speaker_statistics,
            "total_speakers": total_speakers,
            "total_segments": len(speaker_segments),
            "summary": (
                f"检测到 {total_speakers} 个说话人，"
                f"共 {len(speaker_segments)} 个说话片段 "
                f"(使用{'付费' if api_type == 'paid' else '免费'}接口: {model_name})"
            ),
            "execution_method": "subprocess",
            "audio_source": audio_source,
            "api_type": api_type,
            "model_name": model_name,
            "use_paid_api": use_paid_api,
            "statistics": {
                "execution_time": execution_time
            }
        }

        return output_data

    def _get_audio_path(self, input_data: Dict[str, Any]) -> tuple:
        """
        获取音频文件路径 - 智能源选择。

        优先级:
        1. 参数/input_data 中的 audio_path
        2. ffmpeg.extract_audio 节点的输出
        3. audio_separator.separate_vocals 节点的输出

        Args:
            input_data: 输入数据

        Returns:
            (audio_path, audio_source) 元组
        """
        workflow_id = self.context.workflow_id

        # 优先从参数获取
        audio_path = get_param_with_fallback("audio_path", input_data, self.context)
        if audio_path:
            logger.info(f"[{workflow_id}] 从参数/input_data获取音频: {audio_path}")
            return audio_path, "parameter/input_data"

        # 从 ffmpeg.extract_audio 获取
        ffmpeg_stage = self.context.stages.get('ffmpeg.extract_audio')
        if ffmpeg_stage and ffmpeg_stage.output:
            audio_path = ffmpeg_stage.output.get('audio_path')
            if audio_path and os.path.exists(audio_path):
                logger.info(f"[{workflow_id}] 从 ffmpeg.extract_audio 获取音频: {audio_path}")
                return audio_path, "ffmpeg.extract_audio"

        # 从 audio_separator.separate_vocals 获取
        separator_stage = self.context.stages.get('audio_separator.separate_vocals')
        if separator_stage and separator_stage.output:
            # 优先使用 vocal_audio
            audio_path = separator_stage.output.get('vocal_audio')
            if audio_path:
                logger.info(f"[{workflow_id}] 从 audio_separator 获取人声音频: {audio_path}")
                return audio_path, "audio_separator.separate_vocals"

            # 其次使用 all_audio_files 列表的第一个
            all_tracks = separator_stage.output.get('all_audio_files') or []
            if isinstance(all_tracks, list) and all_tracks:
                audio_path = all_tracks[0]
                logger.info(f"[{workflow_id}] 从 audio_separator 获取音频: {audio_path}")
                return audio_path, "audio_separator.separate_vocals"

        return None, ""

    def _run_diarization_subprocess(
        self,
        audio_path: str,
        output_file: Path
    ) -> tuple:
        """
        通过 subprocess 调用推理脚本执行说话人分离。

        Args:
            audio_path: 音频文件路径
            output_file: 输出文件路径

        Returns:
            (result_data, execution_time) 元组
        """
        workflow_id = self.context.workflow_id

        # 获取推理脚本路径
        current_dir = Path(__file__).parent.parent / "app"
        infer_script = current_dir / "pyannote_infer.py"

        if not infer_script.exists():
            raise FileNotFoundError(f"推理脚本不存在: {infer_script}")

        # 获取配置
        service_config = config.get('pyannote_audio_service', {})
        use_paid_api = service_config.get('use_paid_api', False)
        hf_token = os.environ.get('HF_TOKEN', service_config.get('hf_token', ''))
        pyannoteai_api_key = os.environ.get(
            'PYANNOTEAI_API_KEY',
            service_config.get('pyannoteai_api_key', '')
        )

        # 准备命令
        cmd = [
            sys.executable,
            str(infer_script),
            "--audio_path", str(audio_path),
            "--output_file", str(output_file)
        ]

        if use_paid_api:
            cmd.extend(["--use_paid_api"])
            if pyannoteai_api_key:
                cmd.extend(["--pyannoteai_api_key", pyannoteai_api_key])
        else:
            if hf_token:
                cmd.extend(["--hf_token", hf_token])

        logger.info(f"[{workflow_id}] 执行命令: {' '.join(cmd)}")

        # 执行 subprocess
        start_time = time.time()

        try:
            from services.common.subprocess_utils import run_with_popen

            result = run_with_popen(
                cmd,
                stage_name="pyannote_audio_subprocess",
                timeout=1800,  # 30分钟超时
                cwd=str(current_dir),
                env=os.environ.copy()
            )

            execution_time = time.time() - start_time
            logger.info(f"[{workflow_id}] subprocess 执行完成，耗时: {execution_time:.3f}s")

            # 检查执行结果
            if result.returncode != 0:
                error_msg = f"subprocess 执行失败，返回码: {result.returncode}"
                logger.error(f"[{workflow_id}] {error_msg}")
                logger.error(f"[{workflow_id}] stdout: {result.stdout}")
                logger.error(f"[{workflow_id}] stderr: {result.stderr}")
                raise RuntimeError(f"{error_msg}\nstderr: {result.stderr}")

            logger.info(f"[{workflow_id}] subprocess 执行成功")

        except subprocess.TimeoutExpired:
            raise RuntimeError("subprocess 执行超时（30分钟）")
        except Exception as e:
            raise RuntimeError(f"subprocess 执行异常: {str(e)}")

        # 读取结果文件
        if not output_file.exists():
            raise RuntimeError(f"推理结果文件不存在: {output_file}")

        logger.info(f"[{workflow_id}] 读取推理结果文件: {output_file}")

        with open(output_file, 'r', encoding='utf-8') as f:
            result_data = json.load(f)

        if not result_data.get('success', False):
            error_info = result_data.get('error', {})
            raise RuntimeError(
                f"推理失败: {error_info.get('message', '未知错误')} "
                f"(类型: {error_info.get('type', '未知')})"
            )

        return result_data, execution_time

    def _calculate_speaker_statistics(
        self,
        detected_speakers: List[str],
        speaker_segments: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        计算说话人统计信息。

        Args:
            detected_speakers: 检测到的说话人列表
            speaker_segments: 说话人片段列表

        Returns:
            说话人统计信息字典
        """
        speaker_statistics = {}

        for speaker in detected_speakers:
            speaker_segments_for_speaker = [
                seg for seg in speaker_segments
                if seg.get('speaker') == speaker
            ]
            total_duration = sum(
                seg.get('duration', 0)
                for seg in speaker_segments_for_speaker
            )
            speaker_statistics[speaker] = {
                'segments': len(speaker_segments_for_speaker),
                'duration': total_duration,
                'words': 0  # 将在后续处理中填充
            }

        return speaker_statistics

    def get_cache_key_fields(self) -> List[str]:
        """
        返回用于生成缓存键的字段列表。

        说话人分离结果仅依赖于音频文件，
        因此缓存键只需要 audio_path。
        """
        return ["audio_path"]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段列表。

        说话人分离的核心输出是 diarization_file。
        """
        return ["diarization_file"]
