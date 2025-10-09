#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio Separator 服务测试脚本
用于测试音频分离功能是否正常工作
"""

import os
import sys
import time
import json
import requests
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API配置
API_BASE_URL = "http://localhost:8788/v1"

class AudioSeparatorTester:
    """Audio Separator 测试器"""

    def __init__(self):
        self.api_base_url = API_BASE_URL
        self.test_video_path = "/share/videos/test_video.mp4"
        self.audio_file_path = "/share/videos/test_audio.wav"

    def check_api_health(self) -> bool:
        """检查API服务健康状态"""
        try:
            response = requests.get(f"{self.api_base_url}/", timeout=10)
            if response.status_code == 200:
                logger.info("✅ API Gateway 运行正常")
                return True
            else:
                logger.error(f"❌ API Gateway 状态异常: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ 无法连接到 API Gateway: {str(e)}")
            return False

    def prepare_test_file(self) -> str:
        """准备测试文件"""
        # 检查是否有测试文件
        test_files = [
            "/share/videos/test.mp4",
            "/share/videos/example.mp4",
            "/share/videos/sample.mp4"
        ]

        for file_path in test_files:
            if Path(file_path).exists():
                logger.info(f"找到测试文件: {file_path}")
                return file_path

        # 如果没有找到，尝试创建一个简单的测试文件
        logger.warning("未找到测试文件，将使用默认路径")
        return "/share/videos/test_video.mp4"

    def create_workflow(self, video_path: str, workflow_config: Dict[str, Any]) -> Optional[str]:
        """创建工作流"""
        try:
            workflow_data = {
                "video_path": video_path,
                "workflow_config": workflow_config
            }

            logger.info("创建音频分离工作流...")
            logger.info(f"视频文件: {video_path}")
            logger.info(f"工作流配置: {json.dumps(workflow_config, indent=2, ensure_ascii=False)}")

            response = requests.post(
                f"{self.api_base_url}/workflows",
                json=workflow_data,
                timeout=30
            )

            if response.status_code == 202:
                result = response.json()
                workflow_id = result.get("workflow_id")
                logger.info(f"✅ 工作流创建成功: {workflow_id}")
                return workflow_id
            else:
                logger.error(f"❌ 创建工作流失败: {response.status_code}")
                logger.error(f"响应内容: {response.text}")
                return None

        except Exception as e:
            logger.error(f"❌ 创建工作流异常: {str(e)}")
            return None

    def check_workflow_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """检查工作流状态"""
        try:
            response = requests.get(
                f"{self.api_base_url}/workflows/status/{workflow_id}",
                timeout=10
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"❌ 获取工作流状态失败: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"❌ 获取工作流状态异常: {str(e)}")
            return None

    def wait_for_completion(self, workflow_id: str, timeout: int = 600) -> bool:
        """等待工作流完成"""
        logger.info(f"等待工作流完成 (最长等待 {timeout} 秒)...")

        start_time = time.time()
        last_stage = None

        while time.time() - start_time < timeout:
            status = self.check_workflow_status(workflow_id)
            if not status:
                return False

            # 获取当前阶段信息
            stages = status.get("stages", {})
            current_stages = []

            for stage_name, stage_info in stages.items():
                stage_status = stage_info.get("status", "UNKNOWN")
                current_stages.append(f"{stage_name}:{stage_status}")

                # 显示状态变化
                if stage_status in ["COMPLETED", "FAILED"] and stage_name != last_stage:
                    if stage_status == "COMPLETED":
                        logger.info(f"✅ 阶段完成: {stage_name}")

                        # 显示输出信息
                        output_data = stage_info.get("output_data", {})
                        if output_data:
                            logger.info(f"  输出: {json.dumps(output_data, indent=4, ensure_ascii=False)}")
                    else:
                        logger.error(f"❌ 阶段失败: {stage_name}")
                        error_info = stage_info.get("output_data", {})
                        if error_info and "error" in error_info:
                            logger.error(f"  错误: {error_info['error']}")

                    last_stage = stage_name

            # 检查是否有错误
            error = status.get("error")
            if error:
                logger.error(f"❌ 工作流失败: {error}")
                return False

            # 检查是否所有阶段都完成
            all_completed = True
            for stage_info in stages.values():
                if stage_info.get("status") not in ["COMPLETED", "FAILED"]:
                    all_completed = False
                    break

            if all_completed:
                logger.info("🎉 所有阶段已完成")
                return True

            # 显示当前状态
            if current_stages:
                logger.info(f"当前状态: {' | '.join(current_stages)}")

            time.sleep(10)  # 每10秒检查一次

        logger.error(f"⏰ 工作流超时 ({timeout} 秒)")
        return False

    def test_basic_separation(self, video_path: str) -> bool:
        """测试基础音频分离"""
        logger.info("=== 测试基础音频分离 ===")

        workflow_config = {
            "workflow_chain": [
                "audio_separator.separate_vocals"
            ],
            "audio_separator_config": {
                "quality_mode": "default",
                "use_vocal_optimization": False
            }
        }

        workflow_id = self.create_workflow(video_path, workflow_config)
        if not workflow_id:
            return False

        return self.wait_for_completion(workflow_id)

    def test_optimized_separation(self, video_path: str) -> bool:
        """测试优化音频分离"""
        logger.info("=== 测试优化音频分离 ===")

        workflow_config = {
            "workflow_chain": [
                "audio_separator.separate_vocals_optimized"
            ],
            "audio_separator_config": {
                "vocal_optimization_level": "balanced",
                "use_vocal_optimization": True
            }
        }

        workflow_id = self.create_workflow(video_path, workflow_config)
        if not workflow_id:
            return False

        return self.wait_for_completion(workflow_id)

    def test_full_workflow(self, video_path: str) -> bool:
        """测试完整工作流"""
        logger.info("=== 测试完整工作流 ===")

        workflow_config = {
            "workflow_chain": [
                "ffmpeg.extract_keyframes",
                "audio_separator.separate_vocals",
                "whisperx.transcribe_audio"
            ],
            "audio_separator_config": {
                "quality_mode": "high_quality",
                "preserve_background": True
            }
        }

        workflow_id = self.create_workflow(video_path, workflow_config)
        if not workflow_id:
            return False

        return self.wait_for_completion(workflow_id)

    def run_all_tests(self) -> bool:
        """运行所有测试"""
        logger.info("🚀 开始 Audio Separator 服务测试")

        # 检查API健康状态
        if not self.check_api_health():
            logger.error("API服务不健康，无法继续测试")
            return False

        # 准备测试文件
        video_path = self.prepare_test_file()

        # 检查文件是否存在
        if not Path(video_path).exists():
            logger.error(f"测试文件不存在: {video_path}")
            logger.info("请确保测试视频文件存在于 /share/videos/ 目录下")
            return False

        # 运行测试
        tests = [
            ("基础音频分离", self.test_basic_separation),
            ("优化音频分离", self.test_optimized_separation),
            ("完整工作流", self.test_full_workflow)
        ]

        results = {}
        for test_name, test_func in tests:
            logger.info(f"\n{'='*50}")
            logger.info(f"开始测试: {test_name}")
            logger.info(f"{'='*50}")

            try:
                start_time = time.time()
                success = test_func(video_path)
                duration = time.time() - start_time

                results[test_name] = {
                    "success": success,
                    "duration": duration
                }

                if success:
                    logger.info(f"✅ {test_name} 测试通过 (耗时: {duration:.1f}秒)")
                else:
                    logger.error(f"❌ {test_name} 测试失败")

            except Exception as e:
                logger.error(f"❌ {test_name} 测试异常: {str(e)}")
                results[test_name] = {
                    "success": False,
                    "error": str(e)
                }

        # 显示测试结果摘要
        logger.info(f"\n{'='*50}")
        logger.info("🏁 测试结果摘要")
        logger.info(f"{'='*50}")

        success_count = 0
        total_count = len(tests)

        for test_name, result in results.items():
            if result.get("success", False):
                success_count += 1
                duration = result.get("duration", 0)
                logger.info(f"✅ {test_name}: 通过 ({duration:.1f}秒)")
            else:
                error = result.get("error", "未知错误")
                logger.info(f"❌ {test_name}: 失败 ({error})")

        logger.info(f"\n总计: {success_count}/{total_count} 个测试通过")

        if success_count == total_count:
            logger.info("🎉 所有测试通过！Audio Separator 服务运行正常")
            return True
        else:
            logger.error("⚠️ 部分测试失败，请检查服务配置和日志")
            return False

    def check_service_dependencies(self) -> bool:
        """检查服务依赖"""
        logger.info("检查服务依赖...")

        # 检查Redis连接
        try:
            import redis
            r = redis.Redis(host='redis', port=6379, db=0)
            r.ping()
            logger.info("✅ Redis 连接正常")
        except Exception as e:
            logger.error(f"❌ Redis 连接失败: {str(e)}")
            return False

        # 检查模型目录
        models_dir = Path("/models/uvr_mdx")
        if models_dir.exists():
            model_files = list(models_dir.glob("*.onnx"))
            logger.info(f"✅ 模型目录存在，包含 {len(model_files)} 个模型文件")
            if len(model_files) == 0:
                logger.warning("⚠️ 模型目录为空，请运行模型下载脚本")
        else:
            logger.error("❌ 模型目录不存在")
            return False

        # 检查共享目录
        share_dir = Path("/share")
        if share_dir.exists():
            logger.info("✅ 共享目录存在")
        else:
            logger.error("❌ 共享目录不存在")
            return False

        return True


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='Audio Separator 服务测试工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 运行所有测试
  python scripts/test_audio_separator.py

  # 只运行基础测试
  python scripts/test_audio_separator.py --test basic

  # 检查服务依赖
  python scripts/test_audio_separator.py --check-deps
        """
    )

    parser.add_argument('--test', choices=['basic', 'optimized', 'full'],
                       help='运行指定测试')
    parser.add_argument('--video', help='指定测试视频文件路径')
    parser.add_argument('--check-deps', action='store_true',
                       help='只检查服务依赖')
    parser.add_argument('--api-url', default=API_BASE_URL,
                       help='API服务地址 (默认: http://localhost:8788/v1)')

    args = parser.parse_args()

    # 创建测试器
    tester = AudioSeparatorTester()
    tester.api_base_url = args.api_url

    # 设置测试文件
    if args.video:
        tester.test_video_path = args.video

    # 执行检查
    if args.check_deps:
        success = tester.check_service_dependencies()
        sys.exit(0 if success else 1)

    # 检查依赖
    if not tester.check_service_dependencies():
        logger.error("服务依赖检查失败，无法继续测试")
        sys.exit(1)

    # 运行指定测试
    if args.test:
        video_path = tester.prepare_test_file()
        if not Path(video_path).exists():
            logger.error(f"测试文件不存在: {video_path}")
            sys.exit(1)

        test_map = {
            'basic': tester.test_basic_separation,
            'optimized': tester.test_optimized_separation,
            'full': tester.test_full_workflow
        }

        test_func = test_map[args.test]
        success = test_func(video_path)
        sys.exit(0 if success else 1)

    # 运行所有测试
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()