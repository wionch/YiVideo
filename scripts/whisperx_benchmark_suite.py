#!/usr/bin/env python3
"""
WhisperX 性能基准测试套件
对比原生后端和 Faster-Whisper 后端的性能差异
"""

import sys
import os
import time
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Tuple
import statistics

# 添加项目路径
sys.path.append('/app/services')

class WhisperXBenchmarkSuite:
    def __init__(self):
        self.test_audio = "videos/223.mp4"
        self.results_file = "logs/whisperx_benchmark_results.json"
        self.report_file = "logs/whisperx_benchmark_report.html"

        # 测试配置
        self.test_configs = [
            {"name": "Native Backend", "use_faster_whisper": False, "threads": 1},
            {"name": "Faster-Whisper (2 threads)", "use_faster_whisper": True, "threads": 2},
            {"name": "Faster-Whisper (4 threads)", "use_faster_whisper": True, "threads": 4},
            {"name": "Faster-Whisper (8 threads)", "use_faster_whisper": True, "threads": 8},
        ]

        self.setup_logging()

    def setup_logging(self):
        """设置日志"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def load_whisperx_models(self, config: Dict[str, Any]) -> Tuple[Any, float]:
        """加载 WhisperX 模型"""
        try:
            from services.workers.whisperx_service.app.tasks import get_whisperx_models
            import whisperx

            # 临时修改配置
            from services.common.config_loader import CONFIG
            original_config = CONFIG.get('whisperx_service', {}).copy()

            # 应用测试配置
            CONFIG['whisperx_service'].update(config)

            # 测量加载时间
            start_time = time.time()
            get_whisperx_models()
            load_time = time.time() - start_time

            # 恢复原始配置
            CONFIG['whisperx_service'].update(original_config)

            return whisperx, load_time

        except Exception as e:
            self.logger.error(f"模型加载失败: {e}")
            return None, 0

    def benchmark_transcription(self, whisperx, config: Dict[str, Any]) -> Dict[str, Any]:
        """基准测试转录性能"""
        result = {
            "config_name": config["name"],
            "use_faster_whisper": config["use_faster_whisper"],
            "threads": config["threads"],
            "load_time": 0,
            "inference_time": 0,
            "total_time": 0,
            "segments_count": 0,
            "memory_usage": 0,
            "success": False,
            "error": None
        }

        try:
            # 加载模型
            start_time = time.time()
            whisperx, load_time = self.load_whisperx_models(config)
            result["load_time"] = load_time

            if not whisperx:
                result["error"] = "模型加载失败"
                return result

            # 加载音频
            audio = whisperx.load_audio(self.test_audio)

            # 获取模型
            from services.workers.whisperx_service.app.tasks import ASR_MODEL
            if ASR_MODEL is None:
                result["error"] = "模型未正确加载"
                return result

            # 测量推理时间
            start_time = time.time()
            transcription = ASR_MODEL.transcribe(
                audio,
                batch_size=config.get("batch_size", 4),
                language=config.get("language", "zh")
            )
            inference_time = time.time() - start_time

            result["inference_time"] = inference_time
            result["total_time"] = result["load_time"] + inference_time
            result["segments_count"] = len(transcription.get("segments", []))
            result["success"] = True

            # 获取内存使用情况
            try:
                import psutil
                process = psutil.Process()
                result["memory_usage"] = process.memory_info().rss / 1024 / 1024  # MB
            except:
                pass

        except Exception as e:
            result["error"] = str(e)

        return result

    def run_comprehensive_benchmark(self) -> List[Dict[str, Any]]:
        """运行完整的基准测试"""
        print("开始 WhisperX 性能基准测试...")
        print(f"测试文件: {self.test_audio}")
        print(f"测试时间: {datetime.now()}")
        print("=" * 60)

        results = []

        for config in self.test_configs:
            print(f"\n测试配置: {config['name']}")
            print("-" * 40)

            try:
                # 运行多次测试取平均值
                test_runs = []
                for run in range(3):  # 每个配置运行3次
                    print(f"  运行 {run + 1}/3...")
                    result = self.benchmark_transcription(None, config)
                    test_runs.append(result)

                    if result["success"]:
                        print(f"  ✅ 完成 - 加载: {result['load_time']:.2f}s, 推理: {result['inference_time']:.2f}s")
                    else:
                        print(f"  ❌ 失败 - {result.get('error', '未知错误')}")

                    # 等待一下让系统冷却
                    time.sleep(5)

                # 计算平均值
                successful_runs = [r for r in test_runs if r["success"]]
                if successful_runs:
                    avg_result = self._calculate_average(successful_runs, config)
                    results.append(avg_result)
                    print(f"  📊 平均结果 - 总时间: {avg_result['total_time']:.2f}s")
                else:
                    # 所有运行都失败了
                    failed_result = {
                        "config_name": config["name"],
                        "use_faster_whisper": config["use_faster_whisper"],
                        "threads": config["threads"],
                        "success": False,
                        "error": "所有测试运行都失败了"
                    }
                    results.append(failed_result)
                    print(f"  ❌ 所有测试运行都失败了")

            except Exception as e:
                error_result = {
                    "config_name": config["name"],
                    "use_faster_whisper": config["use_faster_whisper"],
                    "threads": config["threads"],
                    "success": False,
                    "error": str(e)
                }
                results.append(error_result)
                print(f"  ❌ 测试异常: {e}")

        return results

    def _calculate_average(self, results: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
        """计算平均值"""
        avg_result = {
            "config_name": config["name"],
            "use_faster_whisper": config["use_faster_whisper"],
            "threads": config["threads"],
            "load_time": statistics.mean([r["load_time"] for r in results]),
            "inference_time": statistics.mean([r["inference_time"] for r in results]),
            "total_time": statistics.mean([r["total_time"] for r in results]),
            "segments_count": statistics.mean([r["segments_count"] for r in results]),
            "memory_usage": statistics.mean([r["memory_usage"] for r in results]),
            "success": True,
            "error": None,
            "runs_count": len(results),
            "load_time_std": statistics.stdev([r["load_time"] for r in results]),
            "inference_time_std": statistics.stdev([r["inference_time"] for r in results]),
        }

        return avg_result

    def analyze_results(self, results: List[Dict[str, Any]]):
        """分析测试结果"""
        print("\n" + "=" * 60)
        print("性能分析结果")
        print("=" * 60)

        # 找到基准（原生后端）
        baseline = next((r for r in results if r["config_name"] == "Native Backend" and r["success"]), None)
        if not baseline:
            print("❌ 未找到基准测试结果，无法进行性能分析")
            return

        print(f"基准 (Native Backend): {baseline['total_time']:.2f}s")
        print("-" * 50)

        # 分析每个 Faster-Whisper 配置
        for result in results:
            if result["config_name"] != "Native Backend" and result["success"]:
                speedup = baseline["total_time"] / result["total_time"]
                memory_saving = (baseline["memory_usage"] - result["memory_usage"]) / baseline["memory_usage"] * 100

                print(f"{result['config_name']}:")
                print(f"  - 速度提升: {speedup:.2f}x")
                print(f"  - 内存节省: {memory_saving:.1f}%")
                print(f"  - 总时间: {result['total_time']:.2f}s (基准: {baseline['total_time']:.2f}s)")
                print(f"  - 推理时间: {result['inference_time']:.2f}s")
                print(f"  - 内存使用: {result['memory_usage']:.1f}MB")
                print()

    def save_results(self, results: List[Dict[str, Any]]):
        """保存测试结果"""
        os.makedirs(os.path.dirname(self.results_file), exist_ok=True)

        data = {
            "timestamp": datetime.now().isoformat(),
            "test_file": self.test_audio,
            "results": results
        }

        with open(self.results_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"测试结果已保存到: {self.results_file}")

    def generate_html_report(self, results: List[Dict[str, Any]]):
        """生成 HTML 报告"""
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>WhisperX 性能基准测试报告</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; }}
        .section {{ margin: 30px 0; padding: 20px; border: 1px solid #ddd; border-radius: 10px; }}
        .success {{ background: #d4edda; }}
        .warning {{ background: #fff3cd; }}
        .error {{ background: #f8d7da; }}
        .performance-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        .performance-table th, .performance-table td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        .performance-table th {{ background: #f2f2f2; font-weight: bold; }}
        .improvement {{ color: #28a745; font-weight: bold; }}
        .benchmark {{ font-size: 1.2em; font-weight: bold; color: #007bff; }}
        .chart-container {{ margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 WhisperX 性能基准测试报告</h1>
        <p>测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>测试文件: {self.test_audio}</p>
    </div>

    <div class="section">
        <h2>📊 性能测试结果</h2>
        <table class="performance-table">
            <thead>
                <tr>
                    <th>配置</th>
                    <th>加载时间</th>
                    <th>推理时间</th>
                    <th>总时间</th>
                    <th>内存使用</th>
                    <th>片段数量</th>
                    <th>状态</th>
                </tr>
            </thead>
            <tbody>
"""

        # 添加测试结果行
        for result in results:
            status_class = "success" if result["success"] else "error"
            status_text = "✅ 成功" if result["success"] else "❌ 失败"

            if result["success"]:
                load_time = f"{result['load_time']:.2f}s"
                inference_time = f"{result['inference_time']:.2f}s"
                total_time = f"<span class='benchmark'>{result['total_time']:.2f}s</span>"
                memory_usage = f"{result['memory_usage']:.1f}MB"
                segments_count = f"{result['segments_count']:.0f}"
            else:
                load_time = "N/A"
                inference_time = "N/A"
                total_time = "N/A"
                memory_usage = "N/A"
                segments_count = "N/A"

            html_content += f"""
                <tr class="{status_class}">
                    <td>{result['config_name']}</td>
                    <td>{load_time}</td>
                    <td>{inference_time}</td>
                    <td>{total_time}</td>
                    <td>{memory_usage}</td>
                    <td>{segments_count}</td>
                    <td>{status_text}</td>
                </tr>
"""

        html_content += """
            </tbody>
        </table>
    </div>

    <div class="section">
        <h2>📈 性能提升分析</h2>
"""

        # 添加性能分析
        baseline = next((r for r in results if r["config_name"] == "Native Backend" and r["success"]), None)
        if baseline:
            html_content += f"""
        <p><strong>基准配置 (Native Backend):</strong> {baseline['total_time']:.2f}s</p>
        <table class="performance-table">
            <thead>
                <tr>
                    <th>配置</th>
                    <th>速度提升</th>
                    <th>内存节省</th>
                    <th>时间节省</th>
                </tr>
            </thead>
            <tbody>
"""

            for result in results:
                if result["config_name"] != "Native Backend" and result["success"]:
                    speedup = baseline["total_time"] / result["total_time"]
                    memory_saving = (baseline["memory_usage"] - result["memory_usage"]) / baseline["memory_usage"] * 100
                    time_saving = (baseline["total_time"] - result["total_time"]) / baseline["total_time"] * 100

                    html_content += f"""
                <tr>
                    <td>{result['config_name']}</td>
                    <td><span class="improvement">{speedup:.2f}x</span></td>
                    <td><span class="improvement">{memory_saving:.1f}%</span></td>
                    <td><span class="improvement">{time_saving:.1f}%</span></td>
                </tr>
"""

            html_content += """
            </tbody>
        </table>
"""

        html_content += f"""
    </div>

    <div class="section">
        <h2>📝 测试结论</h2>
        <ul>
"""

        # 添加测试结论
        successful_configs = [r for r in results if r["success"]]
        if successful_configs:
            fastest = min(successful_configs, key=lambda x: x["total_time"])
            lowest_memory = min(successful_configs, key=lambda x: x["memory_usage"])

            html_content += f"""
            <li>🏆 最快配置: <strong>{fastest['config_name']}</strong> ({fastest['total_time']:.2f}s)</li>
            <li>💾 最省内存配置: <strong>{lowest_memory['config_name']}</strong> ({lowest_memory['memory_usage']:.1f}MB)</li>
"""

        # 检查是否达到预期目标
        if baseline and any(r["success"] for r in results if r["config_name"] != "Native Backend"):
            fastest_fw = min([r for r in results if r["success"] and r["config_name"] != "Native Backend"], key=lambda x: x["total_time"])
            speedup = baseline["total_time"] / fastest_fw["total_time"]

            if speedup >= 4:
                html_content += f'<li>🎯 <span class="improvement">达到预期目标: 4x 速度提升 (实际: {speedup:.2f}x)</span></li>\n'
            else:
                html_content += f'<li>⚠️ 未达到预期目标: 预期 4x 速度提升 (实际: {speedup:.2f}x)</li>\n'

        html_content += f"""
        </ul>
    </div>

    <div class="section">
        <h2>🔧 技术细节</h2>
        <p>测试环境:</p>
        <ul>
            <li>基础镜像: PaddlePaddle 3.1.1 + CUDA 11.8</li>
            <li>WhisperX 版本: 3.4.2</li>
            <li>Faster-Whisper 版本: 1.1.1+</li>
            <li>测试方法: 每个配置运行3次取平均值</li>
        </ul>
    </div>
</body>
</html>
        """

        os.makedirs(os.path.dirname(self.report_file), exist_ok=True)
        with open(self.report_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"HTML 报告已生成: {self.report_file}")

    def run_full_benchmark(self):
        """运行完整的基准测试"""
        try:
            # 运行测试
            results = self.run_comprehensive_benchmark()

            # 分析结果
            self.analyze_results(results)

            # 保存结果
            self.save_results(results)

            # 生成报告
            self.generate_html_report(results)

            # 输出摘要
            successful_tests = [r for r in results if r["success"]]
            print(f"\n=== 测试摘要 ===")
            print(f"总测试数: {len(results)}")
            print(f"成功测试: {len(successful_tests)}")
            print(f"失败测试: {len(results) - len(successful_tests)}")

            if successful_tests:
                fastest = min(successful_tests, key=lambda x: x["total_time"])
                print(f"最快配置: {fastest['config_name']} ({fastest['total_time']:.2f}s)")

            return results

        except Exception as e:
            self.logger.error(f"基准测试执行失败: {e}")
            return []

if __name__ == "__main__":
    # 检查测试文件是否存在
    test_file = "videos/223.mp4"
    if not os.path.exists(test_file):
        print(f"❌ 测试文件不存在: {test_file}")
        exit(1)

    benchmark = WhisperXBenchmarkSuite()
    results = benchmark.run_full_benchmark()
    exit(0 if results and any(r["success"] for r in results) else 1)