#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio Separator 模型下载脚本
自动下载和配置音频分离所需的 UVR-MDX 模型
"""

import os
import sys
import argparse
import logging
from pathlib import Path
import json
import time
from typing import List, Dict

# 添加项目根目录到Python路径
sys.path.append(str(Path(__file__).parent.parent))

try:
    from audio_separator.separator import Separator
except ImportError:
    print("错误: 请先安装 audio-separator 库")
    print("安装命令: pip install audio-separator[gpu]")
    sys.exit(1)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 推荐的模型配置
RECOMMENDED_MODELS = {
    "UVR-MDX-NET-Inst_HQ_5.onnx": {
        "description": "高质量通用分离模型（推荐）",
        "type": "general",
        "quality": "high",
        "size_mb": 312
    },
    "UVR-MDX-NET-Voc_FT.onnx": {
        "description": "人声专用优化模型",
        "type": "vocal",
        "quality": "high",
        "size_mb": 318
    },
    "UVR-MDX-NET-Inst_3.onnx": {
        "description": "快速分离模型",
        "type": "general",
        "quality": "medium",
        "size_mb": 184
    },
    "MDX23C-InstVoc HQ.onnx": {
        "description": "最高质量模型",
        "type": "general",
        "quality": "highest",
        "size_mb": 389
    },
    "UVR_MDXNET_KARA_2.onnx": {
        "description": "Karaoke专用模型",
        "type": "karaoke",
        "quality": "high",
        "size_mb": 318
    }
}

class ModelDownloader:
    """模型下载器"""

    def __init__(self, models_dir: str = "/models/uvr_mdx"):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.models_dir / "download_info.json"

    def load_download_info(self) -> Dict:
        """加载下载信息"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"无法加载下载信息: {e}")
        return {}

    def save_download_info(self, info: Dict):
        """保存下载信息"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(info, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存下载信息失败: {e}")

    def list_downloaded_models(self) -> List[str]:
        """列出已下载的模型"""
        models = []
        for ext in ['*.onnx', '*.pth', '*.ckpt']:
            models.extend(self.models_dir.glob(ext))
        return [f.name for f in models]

    def download_model(self, model_name: str, force_download: bool = False) -> bool:
        """
        下载指定模型

        Args:
            model_name: 模型名称
            force_download: 是否强制重新下载

        Returns:
            bool: 下载是否成功
        """
        model_path = self.models_dir / model_name

        # 检查模型是否已存在
        if model_path.exists() and not force_download:
            logger.info(f"模型 {model_name} 已存在，跳过下载")
            return True

        logger.info(f"开始下载模型: {model_name}")

        try:
            # 创建临时Separator实例来下载模型
            temp_separator = Separator(
                model_file_dir=str(self.models_dir),
                log_level=logging.INFO
            )

            start_time = time.time()
            temp_separator.load_model(model_name)
            download_time = time.time() - start_time

            # 验证文件是否下载成功
            if not model_path.exists():
                logger.error(f"模型下载失败: {model_name}")
                return False

            file_size_mb = model_path.stat().st_size / (1024 * 1024)

            logger.info(f"模型 {model_name} 下载成功")
            logger.info(f"  文件大小: {file_size_mb:.1f} MB")
            logger.info(f"  下载时间: {download_time:.1f} 秒")
            logger.info(f"  下载速度: {file_size_mb / download_time:.1f} MB/s")

            # 更新下载信息
            download_info = self.load_download_info()
            download_info[model_name] = {
                "download_time": time.time(),
                "file_size_mb": file_size_mb,
                "download_duration": download_time
            }
            self.save_download_info(download_info)

            return True

        except Exception as e:
            logger.error(f"下载模型 {model_name} 失败: {str(e)}")
            return False

    def download_recommended_models(self, force_download: bool = False) -> Dict[str, bool]:
        """
        下载所有推荐模型

        Args:
            force_download: 是否强制重新下载

        Returns:
            Dict[str, bool]: 各模型下载结果
        """
        results = {}

        logger.info("开始下载推荐的音频分离模型...")
        logger.info(f"目标目录: {self.models_dir}")

        for model_name, model_info in RECOMMENDED_MODELS.items():
            logger.info(f"\n下载模型: {model_name}")
            logger.info(f"描述: {model_info['description']}")
            logger.info(f"类型: {model_info['type']}, 质量: {model_info['quality']}")

            success = self.download_model(model_name, force_download)
            results[model_name] = success

            if success:
                logger.info(f"✅ {model_name} 下载成功")
            else:
                logger.error(f"❌ {model_name} 下载失败")

        return results

    def verify_models(self) -> Dict[str, Dict]:
        """验证已下载的模型"""
        downloaded_models = self.list_downloaded_models()
        verification_results = {}

        logger.info("验证已下载的模型...")

        for model_name in downloaded_models:
            model_path = self.models_dir / model_name
            file_size_mb = model_path.stat().st_size / (1024 * 1024)

            # 检查是否在推荐列表中
            is_recommended = model_name in RECOMMENDED_MODELS
            expected_size = RECOMMENDED_MODELS.get(model_name, {}).get("size_mb")

            # 文件大小验证
            size_ok = True
            if expected_size:
                size_diff = abs(file_size_mb - expected_size) / expected_size
                if size_diff > 0.1:  # 允许10%的大小差异
                    size_ok = False

            verification_results[model_name] = {
                "file_path": str(model_path),
                "file_size_mb": file_size_mb,
                "is_recommended": is_recommended,
                "size_ok": size_ok,
                "expected_size_mb": expected_size,
                "status": "ok" if size_ok else "size_mismatch"
            }

            status_icon = "✅" if size_ok else "⚠️"
            rec_icon = "⭐" if is_recommended else "📦"

            logger.info(f"{status_icon} {rec_icon} {model_name}")
            logger.info(f"   大小: {file_size_mb:.1f} MB" +
                       (f" (预期: {expected_size} MB)" if expected_size else ""))

            if not size_ok:
                logger.warning(f"   文件大小可能不正确")

        return verification_results

    def cleanup_incomplete_downloads(self):
        """清理不完整的下载"""
        logger.info("清理不完整的下载...")

        incomplete_files = []
        for pattern in ['*.tmp', '*.part', '*.download']:
            incomplete_files.extend(self.models_dir.glob(pattern))

        for file_path in incomplete_files:
            try:
                file_path.unlink()
                logger.info(f"删除不完整文件: {file_path}")
            except Exception as e:
                logger.warning(f"删除文件失败 {file_path}: {e}")

    def show_status(self):
        """显示模型状态"""
        logger.info("=== Audio Separator 模型状态 ===")
        logger.info(f"模型目录: {self.models_dir}")

        downloaded_models = self.list_downloaded_models()
        download_info = self.load_download_info()

        if not downloaded_models:
            logger.info("未找到已下载的模型")
            logger.info("运行 'python scripts/download_audio_models.py --download-recommended' 来下载推荐模型")
            return

        logger.info(f"已下载模型数量: {len(downloaded_models)}")
        logger.info("")

        total_size_mb = 0
        for model_name in sorted(downloaded_models):
            model_path = self.models_dir / model_name
            file_size_mb = model_path.stat().st_size / (1024 * 1024)
            total_size_mb += file_size_mb

            # 获取模型信息
            model_info = RECOMMENDED_MODELS.get(model_name, {})
            dl_info = download_info.get(model_name, {})

            # 显示模型信息
            rec_icon = "⭐" if model_info else "📦"
            quality = model_info.get('quality', 'unknown')
            type_name = model_info.get('type', 'unknown')

            logger.info(f"{rec_icon} {model_name}")
            logger.info(f"   类型: {type_name}, 质量: {quality}")
            logger.info(f"   大小: {file_size_mb:.1f} MB")

            if dl_info:
                dl_time = dl_info.get('download_duration', 0)
                if dl_time > 0:
                    logger.info(f"   下载时间: {dl_time:.1f} 秒")

            logger.info("")

        logger.info(f"总大小: {total_size_mb:.1f} MB")
        logger.info(f"磁盘空间: {self.models_dir.stat().f_frsize * self.models_dir.stat().f_bavail / (1024*1024):.1f} MB 可用")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='Audio Separator 模型下载和管理工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 下载所有推荐模型
  python scripts/download_audio_models.py --download-recommended

  # 下载特定模型
  python scripts/download_audio_models.py --download-model UVR-MDX-NET-Inst_HQ_5.onnx

  # 显示模型状态
  python scripts/download_audio_models.py --status

  # 验证已下载的模型
  python scripts/download_audio_models.py --verify

  # 清理不完整的下载
  python scripts/download_audio_models.py --cleanup
        """
    )

    parser.add_argument('--models-dir', default='/models/uvr_mdx',
                       help='模型存储目录 (默认: /models/uvr_mdx)')
    parser.add_argument('--download-recommended', action='store_true',
                       help='下载所有推荐模型')
    parser.add_argument('--download-model', metavar='MODEL_NAME',
                       help='下载指定模型')
    parser.add_argument('--force-download', action='store_true',
                       help='强制重新下载已存在的模型')
    parser.add_argument('--status', action='store_true',
                       help='显示模型状态')
    parser.add_argument('--verify', action='store_true',
                       help='验证已下载的模型')
    parser.add_argument('--cleanup', action='store_true',
                       help='清理不完整的下载')
    parser.add_argument('--list-models', action='store_true',
                       help='列出所有可用的模型名称')

    args = parser.parse_args()

    # 创建下载器
    downloader = ModelDownloader(args.models_dir)

    # 处理命令
    if args.list_models:
        print("=== 可用模型列表 ===")
        for name, info in RECOMMENDED_MODELS.items():
            print(f"{name}")
            print(f"  描述: {info['description']}")
            print(f"  类型: {info['type']}, 质量: {info['quality']}")
            print(f"  大小: ~{info['size_mb']} MB")
            print()
        return

    if args.status:
        downloader.show_status()
        return

    if args.cleanup:
        downloader.cleanup_incomplete_downloads()
        return

    if args.verify:
        downloader.verify_models()
        return

    if args.download_recommended:
        results = downloader.download_recommended_models(args.force_download)

        print("\n=== 下载结果摘要 ===")
        success_count = sum(1 for success in results.values() if success)
        total_count = len(results)

        for model_name, success in results.items():
            status = "✅ 成功" if success else "❌ 失败"
            print(f"{model_name}: {status}")

        print(f"\n总计: {success_count}/{total_count} 个模型下载成功")

        if success_count == total_count:
            print("🎉 所有推荐模型下载完成！")
        else:
            print("⚠️ 部分模型下载失败，请检查日志")

        return

    if args.download_model:
        success = downloader.download_model(args.download_model, args.force_download)
        if success:
            print(f"✅ 模型 {args.download_model} 下载成功")
        else:
            print(f"❌ 模型 {args.download_model} 下载失败")
            sys.exit(1)
        return

    # 如果没有指定操作，显示状态
    parser.print_help()


if __name__ == "__main__":
    main()