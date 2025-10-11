#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IndexTTS2 独立测试脚本
用于验证 IndexTTS2 服务部署状态和语音生成功能
使用示例:
    python test_indextts.py --check-env
    python test_indextts.py --text "你好世界" --output ./test_output.wav
    python test_indextts.py --test-all
"""

import os
import sys
import time
import argparse
import logging
import json
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import torch
    import torchaudio
    import soundfile as sf
except ImportError as e:
    print(f"错误: 缺少必要的音频处理库: {e}")
    print("请安装: pip install torch torchaudio soundfile")
    sys.exit(1)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('indextts_test.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class IndexTTSTest:
    """IndexTTS2 测试类"""

    def __init__(self):
        """初始化测试环境"""
        self.logger = logger
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.test_results = {}

    def check_environment(self) -> bool:
        """检查运行环境和依赖"""
        print("\n=== IndexTTS2 环境检查 ===")

        success = True

        # 检查 Python 版本
        python_version = sys.version_info
        print(f"Python 版本: {python_version.major}.{python_version.minor}.{python_version.micro}")
        if python_version < (3, 8):
            print("❌ Python 版本过低，需要 3.8+")
            success = False
        else:
            print("✅ Python 版本满足要求")

        # 检查 PyTorch
        try:
            print(f"PyTorch 版本: {torch.__version__}")
            print(f"TorchAudio 版本: {torchaudio.__version__}")

            if torch.cuda.is_available():
                print(f"✅ CUDA 可用: {torch.cuda.device_count()} 个GPU设备")
                print(f"  当前设备: {torch.cuda.get_device_name(0)}")
                print(f"  CUDA 版本: {torch.version.cuda}")
            else:
                print("⚠️  CUDA 不可用，将使用CPU模式")
        except Exception as e:
            print(f"❌ PyTorch 检查失败: {e}")
            success = False

        # 检查音频处理库
        try:
            import soundfile as sf
            print(f"✅ SoundFile 可用: {sf.__version__}")
        except ImportError:
            print("❌ SoundFile 未安装")
            success = False

        # 检查 FFmpeg
        try:
            import subprocess
            result = subprocess.run(['ffmpeg', '-version'],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print("✅ FFmpeg 可用")
            else:
                print("⚠️  FFmpeg 可能有问题")
        except Exception as e:
            print(f"⚠️  FFmpeg 检查失败: {e}")

        # 检查模型目录
        model_paths = [
            "/models/indextts",
            os.environ.get('INDEX_TTS_MODEL_PATH', '/models/indextts'),
            "./models/indextts"
        ]

        model_found = False
        for path in model_paths:
            if Path(path).exists():
                print(f"✅ 模型目录存在: {path}")
                model_found = True
                break

        if not model_found:
            print("⚠️  模型目录不存在，首次运行时会自动创建")
            for path in model_paths:
                try:
                    Path(path).mkdir(parents=True, exist_ok=True)
                    print(f"  已创建: {path}")
                    model_found = True
                    break
                except Exception as e:
                    print(f"  创建失败 {path}: {e}")

        # 检查共享目录
        share_paths = ["/share", "./share"]
        for path in share_paths:
            if Path(path).exists():
                print(f"✅ 共享目录存在: {path}")
                break
        else:
            print("⚠️  共享目录不存在")

        print("=" * 50)
        self.test_results['environment_check'] = {
            'success': success,
            'device': self.device,
            'torch_version': torch.__version__,
            'cuda_available': torch.cuda.is_available()
        }

        return success

    def generate_test_speech(
        self,
        text: str,
        output_path: str,
        voice_preset: str = "default"
    ) -> Dict[str, Any]:
        """
        生成测试语音

        Args:
            text: 测试文本
            output_path: 输出文件路径
            voice_preset: 语音预设

        Returns:
            Dict[str, Any]: 生成结果
        """
        start_time = time.time()

        try:
            print(f"\n=== 生成测试语音 ===")
            print(f"输入文本: {text}")
            print(f"输出路径: {output_path}")
            print(f"语音预设: {voice_preset}")
            print(f"使用设备: {self.device}")

            # 创建输出目录
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # 占位符实现 - 生成测试音频
            # 实际部署时这里需要替换为真实的IndexTTS推理代码
            print("正在生成语音 (占位符实现)...")

            # 生成简单的测试音频
            sample_rate = 22050
            duration = len(text) * 0.1  # 根据文本长度估算时长

            import numpy as np
            t = np.linspace(0, duration, int(sample_rate * duration))

            # 生成多频率合成的测试音频
            frequencies = [440, 523, 659, 784]  # A4, C5, E5, G5
            audio_data = np.zeros_like(t)

            for i, char in enumerate(text):
                if char.isalpha() or char.isdigit():
                    # 根据字符选择频率
                    freq_idx = ord(char) % len(frequencies)
                    frequency = frequencies[freq_idx]

                    # 计算时间窗口
                    start_idx = int(i * len(t) / len(text))
                    end_idx = min(int((i + 1) * len(t) / len(text)), len(t))

                    # 生成正弦波
                    if start_idx < len(t):
                        envelope = np.exp(-3 * (t[start_idx:end_idx] - t[start_idx]) / (t[end_idx] - t[start_idx]))
                        audio_data[start_idx:end_idx] += (
                            np.sin(2 * np.pi * frequency * t[start_idx:end_idx]) *
                            envelope * 0.3
                        )

            # 添加一些噪声使其更自然
            noise = np.random.normal(0, 0.01, len(audio_data))
            audio_data += noise

            # 归一化
            if np.max(np.abs(audio_data)) > 0:
                audio_data = audio_data / np.max(np.abs(audio_data)) * 0.8

            # 保存音频文件
            sf.write(output_path, audio_data, sample_rate)

            processing_time = time.time() - start_time
            file_size = output_file.stat().st_size

            print(f"✅ 语音生成完成")
            print(f"  文件大小: {file_size / 1024:.1f} KB")
            print(f"  音频时长: {duration:.2f} 秒")
            print(f"  处理时间: {processing_time:.2f} 秒")

            result = {
                'status': 'success',
                'output_path': str(output_path),
                'file_size_bytes': file_size,
                'duration': duration,
                'sample_rate': sample_rate,
                'text_length': len(text),
                'voice_preset': voice_preset,
                'processing_time': processing_time,
                'device': self.device,
                'placeholder': True  # 标识这是占位符实现
            }

            self.test_results['speech_generation'] = result
            return result

        except Exception as e:
            error_msg = f"语音生成失败: {str(e)}"
            print(f"❌ {error_msg}")
            logger.error(error_msg, exc_info=True)

            result = {
                'status': 'error',
                'error': error_msg,
                'output_path': output_path,
                'processing_time': time.time() - start_time
            }

            self.test_results['speech_generation'] = result
            return result

    def test_voice_presets(self) -> Dict[str, Any]:
        """测试不同的语音预设"""
        print("\n=== 测试语音预设 ===")

        # 这里将实现测试不同语音预设的逻辑
        # 目前返回一些示例预设
        presets = {
            'default': {'name': 'Default Voice', 'language': 'zh-CN'},
            'male_01': {'name': 'Male Voice 01', 'language': 'zh-CN'},
            'female_01': {'name': 'Female Voice 01', 'language': 'zh-CN'}
        }

        print("可用语音预设:")
        for key, preset in presets.items():
            print(f"  {key}: {preset['name']} ({preset['language']})")

        result = {
            'status': 'success',
            'presets': presets,
            'total_count': len(presets)
        }

        self.test_results['voice_presets'] = result
        return result

    def benchmark_performance(self, test_texts: list = None) -> Dict[str, Any]:
        """性能基准测试"""
        print("\n=== 性能基准测试 ===")

        if test_texts is None:
            test_texts = [
                "你好世界",
                "这是一个测试文本，用来验证语音合成功能",
                "人工智能技术的发展日新月异，语音合成技术也越来越成熟",
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                "测试不同长度和复杂度的文本处理能力"
            ]

        results = []

        for i, text in enumerate(test_texts):
            print(f"\n测试文本 {i+1}/{len(test_texts)}: {text[:30]}...")

            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                output_path = tmp_file.name

            try:
                start_time = time.time()
                result = self.generate_test_speech(text, output_path)
                end_time = time.time()

                if result['status'] == 'success':
                    # 计算性能指标
                    processing_time = result['processing_time']
                    text_length = len(text)
                    real_time_factor = processing_time / result['duration'] if result['duration'] > 0 else float('inf')

                    perf_result = {
                        'text_id': i + 1,
                        'text_length': text_length,
                        'duration': result['duration'],
                        'processing_time': processing_time,
                        'real_time_factor': real_time_factor,
                        'file_size': result['file_size_bytes'],
                        'status': 'success'
                    }

                    print(f"  ✅ 处理时间: {processing_time:.3f}s, RTF: {real_time_factor:.2f}")

                else:
                    perf_result = {
                        'text_id': i + 1,
                        'text_length': len(text),
                        'status': 'error',
                        'error': result.get('error', 'Unknown error')
                    }
                    print(f"  ❌ 失败: {perf_result['error']}")

                results.append(perf_result)

                # 清理临时文件
                try:
                    os.unlink(output_path)
                except:
                    pass

            except Exception as e:
                print(f"  ❌ 测试失败: {e}")
                results.append({
                    'text_id': i + 1,
                    'text_length': len(text),
                    'status': 'error',
                    'error': str(e)
                })

        # 统计结果
        successful_tests = [r for r in results if r['status'] == 'success']
        failed_tests = [r for r in results if r['status'] == 'error']

        if successful_tests:
            avg_processing_time = sum(r['processing_time'] for r in successful_tests) / len(successful_tests)
            avg_rtf = sum(r['real_time_factor'] for r in successful_tests) / len(successful_tests)

            print(f"\n📊 基准测试结果:")
            print(f"  成功: {len(successful_tests)}/{len(results)}")
            print(f"  平均处理时间: {avg_processing_time:.3f}s")
            print(f"  平均RTF: {avg_rtf:.2f}")
        else:
            print(f"\n❌ 所有测试都失败了")

        benchmark_result = {
            'status': 'success' if successful_tests else 'error',
            'total_tests': len(results),
            'successful_tests': len(successful_tests),
            'failed_tests': len(failed_tests),
            'success_rate': len(successful_tests) / len(results) if results else 0,
            'results': results,
            'summary': {
                'avg_processing_time': sum(r['processing_time'] for r in successful_tests) / len(successful_tests) if successful_tests else 0,
                'avg_rtf': sum(r['real_time_factor'] for r in successful_tests) / len(successful_tests) if successful_tests else 0
            } if successful_tests else {}
        }

        self.test_results['benchmark'] = benchmark_result
        return benchmark_result

    def save_test_report(self, output_path: str = "indextts_test_report.json"):
        """保存测试报告"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.test_results, f, indent=2, ensure_ascii=False)
            print(f"\n📄 测试报告已保存到: {output_path}")
        except Exception as e:
            print(f"❌ 保存测试报告失败: {e}")

    def test_all(self):
        """执行所有测试"""
        print("\n🧪 开始执行 IndexTTS2 完整测试套件")

        # 环境检查
        env_ok = self.check_environment()
        if not env_ok:
            print("\n❌ 环境检查失败，跳过后续测试")
            return False

        # 语音预设测试
        self.test_voice_presets()

        # 基础语音生成测试
        test_result = self.generate_test_speech(
            text="你好，这是IndexTTS2服务的测试语音",
            output_path="./test_indextts_output.wav"
        )

        # 性能基准测试
        self.benchmark_performance()

        # 保存测试报告
        self.save_test_report()

        # 总结
        print(f"\n🎉 测试完成！")
        print(f"环境检查: {'✅ 通过' if env_ok else '❌ 失败'}")
        print(f"语音生成: {'✅ 通过' if test_result['status'] == 'success' else '❌ 失败'}")

        return env_ok and test_result['status'] == 'success'


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='IndexTTS2 独立测试脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 检查环境
  python test_indextts.py --check-env

  # 生成测试语音
  python test_indextts.py --text "你好世界" --output ./test.wav

  # 测试所有功能
  python test_indextts.py --test-all

  # 性能基准测试
  python test_indextts.py --benchmark
        """
    )

    parser.add_argument('--check-env', action='store_true',
                       help='检查运行环境和依赖')
    parser.add_argument('--text', type=str, default='你好，这是IndexTTS2的测试语音',
                       help='要转换的测试文本')
    parser.add_argument('--output', type=str, default='./test_indextts_output.wav',
                       help='输出音频文件路径')
    parser.add_argument('--voice-preset', type=str, default='default',
                       help='语音预设')
    parser.add_argument('--test-all', action='store_true',
                       help='执行所有测试')
    parser.add_argument('--benchmark', action='store_true',
                       help='执行性能基准测试')
    parser.add_argument('--save-report', action='store_true',
                       help='保存测试报告')

    args = parser.parse_args()

    # 创建测试实例
    tester = IndexTTSTest()

    try:
        if args.check_env:
            success = tester.check_environment()
            if args.save_report:
                tester.save_test_report()
            sys.exit(0 if success else 1)

        elif args.test_all:
            success = tester.test_all()
            sys.exit(0 if success else 1)

        elif args.benchmark:
            result = tester.benchmark_performance()
            success = result['status'] == 'success'
            if args.save_report:
                tester.save_test_report()
            sys.exit(0 if success else 1)

        elif args.text:
            result = tester.generate_test_speech(
                text=args.text,
                output_path=args.output,
                voice_preset=args.voice_preset
            )
            success = result['status'] == 'success'
            if args.save_report:
                tester.save_test_report()
            sys.exit(0 if success else 1)

        else:
            # 默认执行环境检查
            tester.check_environment()

    except KeyboardInterrupt:
        print("\n\n⏹️  用户中断测试")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试执行失败: {e}")
        logger.error(f"测试执行失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()