#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立音频分离工具 - 类似 UVR5 功能
基于 audio-separator 库，支持 Demucs v4 和 MDX-Net 模型
使用示例:
    python audio_separator_standalone.py -i input.mp3 -m demucs -q high
    python audio_separator_standalone.py -i input.wav --model mdx --output_dir ./output
"""

import os
import sys
import time
import argparse
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import json

try:
    from audio_separator.separator import Separator
except ImportError:
    print("错误: 请先安装 audio-separator 库")
    print("安装命令: pip install audio-separator[gpu]")
    sys.exit(1)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('audio_separator.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class AudioSeparatorStandalone:
    """独立音频分离器"""

    def __init__(self):
        """初始化分离器"""
        self.logger = logger
        self._setup_model_configs()

    def _setup_model_configs(self):
        """设置模型配置"""
        self.model_configs = {
            # Demucs 模型配置 - 使用官方文档确认的模型名称
            'demucs': {
                'model_name': 'htdemucs.yaml',  # Demucs v4 Hybrid模型 (官方格式)
                'description': 'Demucs v4 Hybrid - 高质量通用分离',
                'params': {
                    'segment_size': None,  # 使用默认值
                    'batch_size': 1,
                    'normalization_threshold': 0.9,
                    'overlap': 0.25,
                }
            },

            # Demucs v4 快速模型
            'demucs_fast': {
                'model_name': 'htdemucs_ft.yaml',  # 快速Demucs模型 (官方格式)
                'description': 'Demucs v4 Fast - 快速分离',
                'params': {
                    'segment_size': None,
                    'batch_size': 4,  # 更大的批次提高速度
                    'normalization_threshold': 0.9,
                    'overlap': 0.25,
                }
            },

            # Demucs v4 高质量模型
            'demucs_hd': {
                'model_name': 'htdemucs_6s.yaml',  # 6-stem高保真模型 (官方格式)
                'description': 'Demucs v4 6-Stem - 最高质量分离（鼓、贝斯、人声、钢琴、其他、吉他）',
                'params': {
                    'segment_size': None,
                    'batch_size': 1,
                    'normalization_threshold': 0.9,
                    'overlap': 0.25,
                }
            },

            # MDX-Net 模型配置 (与 UVR-MDX-NET Inst HQ5 配置一致)
            'mdx_net': {
                'model_name': 'UVR-MDX-NET-Inst_HQ_5.onnx',
                'description': 'UVR MDX-Net Inst HQ 5 - 高质量乐器分离（与UVR5配置一致）',
                'params': {
                    'hop_length': 1024,
                    'segment_size': 256,
                    'batch_size': 1,
                    'overlap': 8/256,  # UVR5默认重叠设置，约0.031
                    'chunk_size': 261120,  # UVR5配置的音频块大小
                    'dim_f': 6144,  # UVR5配置的频率维度
                    'n_fft': 12288,  # UVR5配置的FFT窗口大小
                    'enable_denoise': True,  # 官方支持的参数
                    'enable_tta': False,     # 不启用TTA以保持速度
                    'enable_post_process': True,  # 启用后处理
                    'post_process_threshold': 0.2,
                }
            },

            # MDX-Net 人声专用模型 - 推荐用于人声分离
            'mdx_vocal': {
                'model_name': 'UVR-MDX-NET-Voc_FT.onnx',
                'description': 'UVR MDX-Net Vocal FT - 人声专用优化（推荐）',
                'params': {
                    'hop_length': 1024,
                    'segment_size': 256,
                    'batch_size': 1,
                    'normalization_threshold': 0.9,
                    'overlap': 8/256,  # 调整为UVR5默认设置
                    'enable_denoise': True,  # 启用降噪提升人声质量
                    'enable_tta': False,     # 测试时增强，提高质量但增加处理时间
                    'enable_post_process': True,  # 启用后处理减少伪影
                    'post_process_threshold': 0.2,  # 后处理阈值
                }
            },

            # MDX-Net Karaoke 专用模型 - 另一个优秀的人声分离选择
            'mdx_karaoke': {
                'model_name': 'UVR_MDXNET_KARA_2.onnx',
                'description': 'UVR MDX-Net Karaoke 2 - Karaoke专用人声分离',
                'params': {
                    'hop_length': 1024,
                    'segment_size': 256,
                    'batch_size': 1,
                    'normalization_threshold': 0.9,
                    'overlap': 8/256,  # 调整为UVR5默认设置
                    'enable_denoise': True,
                    'enable_tta': False,     # Karaoke模型通常不需要TTA
                    'enable_post_process': True,
                    'post_process_threshold': 0.15,  # Karaoke模型使用更低的阈值
                }
            }
        }

        # 质量模式预设
        self.quality_presets = {
            'fast': {
                'description': '快速模式 - 优先处理速度',
                'models': ['demucs_fast'],
                'batch_size': 4,
            },
            'balanced': {
                'description': '平衡模式 - 速度与质量均衡',
                'models': ['demucs', 'mdx_net'],
                'batch_size': 1,
            },
            'high': {
                'description': '高质量模式 - 最佳分离效果',
                'models': ['demucs_hd', 'mdx_vocal'],
                'batch_size': 1,
            }
        }

    def list_models(self):
        """列出所有可用模型"""
        print("\n=== 可用模型列表 ===")
        for key, config in self.model_configs.items():
            print(f"  {key}: {config['description']}")
        print("\n=== 质量预设 ===")
        for key, preset in self.quality_presets.items():
            print(f"  {key}: {preset['description']}")
            print(f"    推荐模型: {', '.join(preset['models'])}")

    def _validate_input_file(self, audio_path: str) -> Path:
        """验证输入文件"""
        input_file = Path(audio_path)

        if not input_file.exists():
            raise FileNotFoundError(f"输入文件不存在: {audio_path}")

        if not input_file.is_file():
            raise ValueError(f"输入路径不是文件: {audio_path}")

        # 检查文件扩展名
        supported_formats = ['.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac', '.mp4', '.avi', '.mov']
        if input_file.suffix.lower() not in supported_formats:
            self.logger.warning(f"文件格式可能不受支持: {input_file.suffix}")

        return input_file

    def _create_separator(self, model_name: str, output_dir: str, custom_params: Optional[Dict] = None) -> Separator:
        """创建音频分离器实例"""
        # 获取模型配置
        if model_name not in self.model_configs:
            available = ', '.join(self.model_configs.keys())
            raise ValueError(f"未知模型: {model_name}. 可用模型: {available}")

        model_config = self.model_configs[model_name]
        actual_model_name = model_config['model_name']

        # 合并参数
        params = model_config['params'].copy()
        if custom_params:
            params.update(custom_params)
        print(params)

        self.logger.info(f"创建分离器实例...")
        self.logger.info(f"模型: {actual_model_name} ({model_config['description']})")
        self.logger.info(f"输出目录: {output_dir}")

        # 创建分离器
        separator = Separator(
            log_level=logging.INFO,
            model_file_dir='D:\\Program Files\\Ultimate Vocal Remover\\models\\MDX_Net_Models',  # UVR5模型目录
            output_dir=output_dir,
            output_format='wav',  # 高质量输出格式
            normalization_threshold=params.get('normalization_threshold', 0.9),
            mdx_params={
                'hop_length': params.get('hop_length', 1024),
                'segment_size': params.get('segment_size', 256),
                'batch_size': params.get('batch_size', 1),
                'overlap': params.get('overlap', 8/256),  # 使用UVR5默认重叠设置
                'chunk_size': params.get('chunk_size', 261120),  # 添加UVR5音频块大小
                'dim_f': params.get('dim_f', 6144),  # 添加UVR5频率维度
                'n_fft': params.get('n_fft', 12288),  # 添加UVR5 FFT窗口大小
            }
        )

        return separator, actual_model_name

    def separate_audio(
        self,
        audio_path: str,
        model_name: str = 'demucs',
        output_dir: str = './output',
        quality_mode: str = 'balanced',
        custom_params: Optional[Dict] = None
    ) -> Dict[str, str]:
        """
        执行音频分离

        Args:
            audio_path: 输入音频文件路径
            model_name: 使用的模型名称
            output_dir: 输出目录
            quality_mode: 质量模式 (fast/balanced/high)
            custom_params: 自定义参数

        Returns:
            Dict[str, str]: 分离结果文件路径
        """
        start_time = time.time()

        # 验证输入
        input_file = self._validate_input_file(audio_path)

        # 创建输出目录
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"开始音频分离任务...")
        self.logger.info(f"输入文件: {input_file}")
        self.logger.info(f"质量模式: {quality_mode}")

        try:
            # 创建分离器实例
            separator, actual_model_name = self._create_separator(
                model_name, output_dir, custom_params
            )

            # 加载模型
            self.logger.info("正在加载模型...")
            separator.load_model(actual_model_name)

            # 执行分离
            self.logger.info("开始执行分离...")
            output_files = separator.separate(str(input_file))

            # 计算处理时间
            processing_time = time.time() - start_time
            self.logger.info(f"分离完成，总耗时: {processing_time:.2f} 秒")

            # 解析输出文件
            result = self._parse_output_files(output_files, output_dir, actual_model_name)

            # 显示结果
            print(f"\n=== 分离结果 ===")
            print(f"🎵 人声文件: {result['vocals']}")
            print(f"🎸 背景音文件: {result['instrumental'] if 'instrumental' in result else '无独立背景音轨'}")
            if 'drums' in result:
                print(f"🥁 鼓声文件: {result['drums']}")
            if 'bass' in result:
                print(f"🎺 贝斯文件: {result['bass']}")
            if 'other' in result:
                print(f"🎹 其他乐器: {result['other']}")
            if 'piano' in result:
                print(f"🎹 钢琴文件: {result['piano']}")
            if 'guitar' in result:
                print(f"🎸 吉他文件: {result['guitar']}")

            # 显示所有生成的文件
            print(f"\n📁 生成的所有文件:")
            for stem, file_path in result.items():
                print(f"   {stem}: {file_path}")
            print(f"⏱️  处理时间: {processing_time:.2f} 秒")

            return result

        except Exception as e:
            self.logger.error(f"音频分离失败: {str(e)}", exc_info=True)
            raise

    def _parse_output_files(self, output_files: list, output_dir: str, model_name: str = None) -> Dict[str, str]:
        """解析输出文件列表"""
        result = {}

        for file_path in output_files:
            # 确保是绝对路径
            if not Path(file_path).is_absolute():
                file_path = str(Path(output_dir) / file_path)

            file_name = Path(file_path).name.lower()

            # 根据文件名识别类型
            if 'vocal' in file_name or 'voice' in file_name:
                result['vocals'] = file_path
            elif 'instrumental' in file_name or 'inst' in file_name or 'no_vocal' in file_name:
                result['instrumental'] = file_path
            elif 'drums' in file_name or 'drum' in file_name:
                result['drums'] = file_path
            elif 'bass' in file_name:
                result['bass'] = file_path
            elif 'other' in file_name:
                result['other'] = file_path
            elif 'piano' in file_name:
                result['piano'] = file_path
            elif 'guitar' in file_name:
                result['guitar'] = file_path

        # 对Demucs模型进行特殊处理 - 合并非人声音轨为伴奏
        if model_name and 'demucs' in model_name.lower() and 'instrumental' not in result:
            instrumental_tracks = []
            if 'drums' in result:
                instrumental_tracks.append(result['drums'])
            if 'bass' in result:
                instrumental_tracks.append(result['bass'])
            if 'other' in result:
                instrumental_tracks.append(result['other'])
            if 'piano' in result:
                instrumental_tracks.append(result['piano'])
            if 'guitar' in result:
                instrumental_tracks.append(result['guitar'])
            
            # 如果有多个伴奏音轨，标记需要合并
            if len(instrumental_tracks) > 0:
                result['instrumental_tracks'] = instrumental_tracks
                result['instrumental'] = f"[需要合并] {', '.join([Path(t).name for t in instrumental_tracks])}"

        # 如果无法识别，使用默认逻辑
        if len(output_files) >= 2 and 'vocals' not in result:
            file1 = output_files[0] if Path(output_files[0]).is_absolute() else str(Path(output_dir) / output_files[0])
            file2 = output_files[1] if Path(output_files[1]).is_absolute() else str(Path(output_dir) / output_files[1])
            result['vocals'] = file1
            result['instrumental'] = file2

        return result

    def benchmark_models(self, audio_path: str, output_dir: str = './benchmark_output'):
        """
        对不同模型进行基准测试

        Args:
            audio_path: 测试音频文件路径
            output_dir: 基准测试输出目录
        """
        print("\n=== 开始模型基准测试 ===")

        # 验证输入文件
        self._validate_input_file(audio_path)

        # 测试所有模型
        benchmark_results = {}

        for model_key in ['demucs_fast', 'demucs', 'demucs_hd', 'mdx_net', 'mdx_vocal']:
            print(f"\n🔄 测试模型: {model_key}")
            print("-" * 50)

            try:
                model_output_dir = Path(output_dir) / model_key
                start_time = time.time()

                result = self.separate_audio(
                    audio_path=audio_path,
                    model_name=model_key,
                    output_dir=str(model_output_dir)
                )

                processing_time = time.time() - start_time

                # 获取文件大小
                vocals_size = Path(result['vocals']).stat().st_size / (1024 * 1024)  # MB
                instrumental_size = Path(result['instrumental']).stat().st_size / (1024 * 1024)  # MB

                benchmark_results[model_key] = {
                    'processing_time': processing_time,
                    'vocals_size_mb': vocals_size,
                    'instrumental_size_mb': instrumental_size,
                    'total_size_mb': vocals_size + instrumental_size,
                    'status': 'success'
                }

                print(f"✅ 成功 - 耗时: {processing_time:.2f}s, 输出大小: {benchmark_results[model_key]['total_size_mb']:.2f}MB")

            except Exception as e:
                print(f"❌ 失败 - {str(e)}")
                benchmark_results[model_key] = {
                    'status': 'failed',
                    'error': str(e)
                }

        # 输出基准测试报告
        print("\n" + "="*60)
        print("📊 基准测试报告")
        print("="*60)

        for model_key, result in benchmark_results.items():
            if result['status'] == 'success':
                print(f"{model_key:20} | {result['processing_time']:8.2f}s | {result['total_size_mb']:8.2f}MB | ✅")
            else:
                print(f"{model_key:20} | {'N/A':8} | {'N/A':8} | ❌ {result['error']}")

        # 保存基准测试结果
        benchmark_file = Path(output_dir) / 'benchmark_results.json'
        with open(benchmark_file, 'w', encoding='utf-8') as f:
            json.dump(benchmark_results, f, indent=2, ensure_ascii=False)

        print(f"\n📄 详细结果已保存到: {benchmark_file}")


def check_environment():
    """检查运行环境和依赖"""
    print("=== 环境检查 ===")

    # 检查 audio-separator 是否可用
    try:
        from audio_separator.separator import Separator
        print("✅ audio-separator 库已安装")

        # 检查常用模型是否可用（通过检查模型缓存目录）
        separator = Separator()
        print("检查常用模型可用性...")

        common_models = ['htdemucs.yaml', 'htdemucs_6s.yaml', 'htdemucs_ft.yaml']
        for model in common_models:
            try:
                # 检查模型是否已缓存
                model_dir = Path("/app/.cache/audio_separator")
                model_path = model_dir / model
                if model_path.exists():
                    print(f"  ✓ {model} (已缓存)")
                else:
                    print(f"  ○ {model} (首次使用时会自动下载)")
            except Exception as e:
                print(f"  ✗ {model} (检查失败: {e})")

        # 检查MDX-Net模型
        mdx_models = ['UVR-MDX-NET-Inst_HQ_5.onnx', 'UVR-MDX-NET-Voc_FT.onnx']
        print("检查MDX-Net模型...")
        for model in mdx_models:
            model_dir = Path("/app/.cache/audio_separator")
            model_path = model_dir / model
            if model_path.exists():
                print(f"  ✓ {model} (已缓存)")
            else:
                print(f"  ○ {model} (需要手动下载)")

        print("提示: 模型会在首次使用时自动下载")

    except ImportError as e:
        print(f"❌ audio-separator 库未安装: {e}")
        print("请安装: pip install audio-separator[gpu]")
        return False

    # 检查GPU可用性
    try:
        import torch
        if torch.cuda.is_available():
            print(f"✅ CUDA 可用: {torch.cuda.device_count()} 个GPU设备")
            print(f"  当前设备: {torch.cuda.get_device_name(0)}")
        else:
            print("⚠️  CUDA 不可用，将使用CPU")
    except:
        print("⚠️  无法检查CUDA状态")

    # 检查FFmpeg
    try:
        import subprocess
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ FFmpeg 可用")
        else:
            print("⚠️  FFmpeg 可能有问题")
    except:
        print("⚠️  FFmpeg 未安装或不在PATH中")

    print("=" * 50)
    return True

def main():
    """主函数"""

    # 设置环境变量以解决GPU问题
    os.environ['CUDA_VISIBLE_DEVICES'] = '0'  # 强制使用第一个GPU

    parser = argparse.ArgumentParser(
        description='独立音频分离工具 - 支持 Demucs v4 和 MDX-Net 模型',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 基本使用
  python audio_separator_standalone.py -i input.mp3

  # 使用高质量Demucs模型
  python audio_separator_standalone.py -i input.wav -m demucs_hd -q high

  # 使用MDX-Net模型
  python audio_separator_standalone.py -i input.mp3 -m mdx_net --output_dir ./output

  # 批量基准测试
  python audio_separator_standalone.py -i test.mp3 --benchmark

  # 列出所有可用模型
  python audio_separator_standalone.py --list-models

  # 检查运行环境
  python audio_separator_standalone.py --check-env
        """
    )

    parser.add_argument('-i', '--input', required=False,
                       help='输入音频文件路径')
    parser.add_argument('-m', '--model', default='demucs',
                       choices=['demucs', 'demucs_fast', 'demucs_hd', 'mdx_net', 'mdx_vocal', 'mdx_karaoke'],
                       help='选择分离模型 (默认: demucs)')
    parser.add_argument('-q', '--quality', default='balanced',
                       choices=['fast', 'balanced', 'high'],
                       help='质量模式 (默认: balanced)')
    parser.add_argument('-o', '--output_dir', default='./output',
                       help='输出目录 (默认: ./output)')
    parser.add_argument('--benchmark', action='store_true',
                       help='对所有模型进行基准测试')
    parser.add_argument('--list-models', action='store_true',
                       help='列出所有可用模型')
    parser.add_argument('--check-env', action='store_true',
                       help='检查运行环境和依赖')
    parser.add_argument('--custom_params', type=str,
                       help='自定义JSON格式参数')

    args = parser.parse_args()

    # 处理环境检查
    if args.check_env:
        check_environment()
        return

    # 创建分离器实例
    separator = AudioSeparatorStandalone()

    # 处理命令
    if args.list_models:
        separator.list_models()
        return

    if args.benchmark:
        if not args.input:
            print("错误: 基准测试需要指定输入文件 (-i/--input)")
            sys.exit(1)
        separator.benchmark_models(args.input, args.output_dir)
        return

    if not args.input:
        # 设置默认音频文件路径
        args.input = '/app/videos/666.wav'
        print(f"使用默认音频文件: {args.input}")

    try:
        # 解析自定义参数
        custom_params = None
        if args.custom_params:
            custom_params = json.loads(args.custom_params)

        # 执行分离
        result = separator.separate_audio(
            audio_path=args.input,
            model_name=args.model,
            output_dir=args.output_dir,
            quality_mode=args.quality,
            custom_params=custom_params
        )

        print(f"\n🎉 分离完成！输出文件位于: {args.output_dir}")

    except KeyboardInterrupt:
        print("\n\n⏹️  用户中断操作")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 错误: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()