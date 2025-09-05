# pipeline/pipeline.py
import yaml
import os
import av

from .modules.decoder import GPUDecoder
from .modules.area_detector import SubtitleAreaDetector
from .modules.change_detector import ChangeDetector
from .modules.ocr import BatchOCREngine
from .modules.postprocessor import SubtitlePostprocessor

class VideoSubtitleExtractorPipeline:
    """
    流水线总调度器，负责整合并执行所有处理阶段。
    """
    def __init__(self, config_path=None):
        """
        初始化所有处理模块。
        """
        print("初始化流水线...")
        if config_path and os.path.exists(config_path):
            self.config = self._load_config(config_path)
        else:
            self.config = self._load_default_config()
        
        self.decoder = GPUDecoder(self.config.get('decoder', {}))
        self.area_detector = SubtitleAreaDetector(self.config.get('area_detector', {}))
        self.change_detector = ChangeDetector(self.config.get('change_detector', {}))
        self.ocr_engine = BatchOCREngine(self.config.get('ocr', {}))
        self.postprocessor = SubtitlePostprocessor(self.config.get('postprocessor', {}))
        print("流水线所有模块已成功加载。")

    def _load_config(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _load_default_config(self):
        """加载默认配置, 这里我们直接定义一个字典"""
        return {
            'decoder': {'batch_size': 32},
            'area_detector': {'sample_count': 300}, # 修正: 提高默认采样数量
            'change_detector': {'dhash_size': 8, 'hamming_threshold': 3},
            'ocr': {'lang': 'en'},
            'postprocessor': {'min_duration_seconds': 0.2}
        }

    def _get_video_metadata(self, video_path: str):
        """获取视频的帧率和总帧数"""
        try:
            with av.open(video_path) as container:
                stream = container.streams.video[0]
                fps = stream.average_rate
                total_frames = stream.frames
                if total_frames == 0: # 如果元数据中没有总帧数，则估算
                    total_frames = int(stream.duration * stream.time_base * fps)
                return float(fps), total_frames
        except (av.AVError, IndexError) as e:
            print(f"警告: 无法准确获取视频元数据: {e}. 将使用估算值。")
            return 25.0, 99999 # 返回一个通用估算值

    def run(self, video_path: str):
        """
        执行完整的字幕提取流水线。
        """
        print(f"开始处理视频: {video_path}")
        
        # 0. 获取视频元数据
        fps, total_frames = self._get_video_metadata(video_path)
        print(f"视频信息: 帧率={fps:.2f}, 总帧数={total_frames}")

        # --- 第1步: 智能字幕区域检测 ---
        subtitle_area = self.area_detector.detect(video_path, self.decoder)

        # --- 第2步: 变化点检测 ---
        key_frame_indices = self.change_detector.find_key_frames(video_path, self.decoder, subtitle_area)

        # --- 第3步: 批量OCR识别 ---
        ocr_results = self.ocr_engine.recognize(video_path, self.decoder, key_frame_indices, subtitle_area)

        # --- 第4步: 后处理与格式化 ---
        final_subtitles = self.postprocessor.format(ocr_results, fps, total_frames)
        print(f"流水线执行完毕，生成 {len(final_subtitles)} 条最终字幕。")

        return final_subtitles