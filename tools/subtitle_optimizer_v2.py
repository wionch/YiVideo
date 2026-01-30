#!/usr/bin/env python3
"""
字幕优化器 V2 CLI 工具

命令行工具，用于执行字幕优化任务。

用法:
    python subtitle_optimizer_v2.py -i input.json -o output.json
    python subtitle_optimizer_v2.py -i input.json -o output.json -t my_task -d "视频描述"
    python subtitle_optimizer_v2.py -i input.json -o output.json -c config.yml

示例:
    # 基本用法
    python tools/subtitle_optimizer_v2.py -i data/subtitles.json -o data/optimized.json

    # 指定任务ID和描述
    python tools/subtitle_optimizer_v2.py -i data/subtitles.json -o data/optimized.json \\
        -t task_001 -d "这是一个测试视频"

    # 使用自定义配置
    python tools/subtitle_optimizer_v2.py -i data/subtitles.json -o data/optimized.json \\
        -c config/custom.yml
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from services.common.subtitle.optimizer_v2 import (
    OptimizerConfigLoader,
    SubtitleOptimizerConfig,
    SubtitleOptimizerV2,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    """
    解析命令行参数

    Returns:
        解析后的参数命名空间
    """
    parser = argparse.ArgumentParser(
        prog="subtitle_optimizer_v2",
        description="字幕优化器 V2 - 基于 LLM 的字幕分段优化工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s -i input.json -o output.json
  %(prog)s -i input.json -o output.json -t my_task -d "视频描述"
  %(prog)s -i input.json -o output.json -c config.yml
        """,
    )

    parser.add_argument(
        "--input",
        "-i",
        type=str,
        required=True,
        help="输入 JSON 文件路径 (必需)",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        required=True,
        help="输出 JSON 文件路径 (必需)",
    )

    parser.add_argument(
        "--task-id",
        "-t",
        type=str,
        default="cli_task",
        help="任务 ID (默认: cli_task)",
    )

    parser.add_argument(
        "--description",
        "-d",
        type=str,
        default=None,
        help="视频描述 (可选)",
    )

    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=None,
        help="配置文件路径 (可选，默认使用项目根目录的 config.yml)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="启用详细日志输出",
    )

    return parser.parse_args()


def validate_input_file(input_path: str) -> None:
    """
    验证输入文件是否存在且有效

    Args:
        input_path: 输入文件路径

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 文件格式无效
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"输入文件不存在: {input_path}")

    if not os.path.isfile(input_path):
        raise ValueError(f"输入路径不是文件: {input_path}")

    # 验证 JSON 格式
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"输入文件不是有效的 JSON: {e}")
    except Exception as e:
        raise ValueError(f"读取输入文件失败: {e}")

    # 验证必要的字段
    if "segments" not in data and not isinstance(data.get("segments"), list):
        logger.warning("输入文件缺少 'segments' 字段，或 'segments' 不是数组")

    logger.info(f"输入文件验证通过: {input_path}")


def load_config(config_path: Optional[str] = None) -> SubtitleOptimizerConfig:
    """
    加载优化器配置

    Args:
        config_path: 配置文件路径，如果为 None 则使用默认配置

    Returns:
        优化器配置对象
    """
    if config_path and os.path.exists(config_path):
        logger.info(f"从配置文件加载配置: {config_path}")
        return OptimizerConfigLoader.load(config_path)
    else:
        if config_path:
            logger.warning(f"配置文件不存在，使用默认配置: {config_path}")
        else:
            logger.info("使用默认配置")
        return OptimizerConfigLoader.get_default_config()


def print_results(result: Dict[str, Any], output_path: str) -> None:
    """
    打印优化结果

    Args:
        result: 优化结果字典
        output_path: 输出文件路径
    """
    metadata = result.get("metadata", {})
    segments = result.get("segments", [])

    print("\n" + "=" * 60)
    print("字幕优化完成")
    print("=" * 60)

    print(f"\n📊 统计信息:")
    print(f"  - 总行数: {metadata.get('total_lines', len(segments))}")
    print(f"  - 修改行数: {metadata.get('modified_lines', 'N/A')}")
    print(f"  - 分段数: {metadata.get('segment_count', 'N/A')}")

    config = metadata.get("config", {})
    if config:
        print(f"\n⚙️  配置信息:")
        print(f"  - 分段大小: {config.get('segment_size', 'N/A')}")
        print(f"  - 重叠行数: {config.get('overlap_lines', 'N/A')}")
        print(f"  - 最大并发: {config.get('max_concurrent', 'N/A')}")

        llm_config = config.get("llm", {})
        if llm_config:
            print(f"  - LLM 模型: {llm_config.get('model', 'N/A')}")

    print(f"\n💾 输出文件: {output_path}")
    print("=" * 60 + "\n")


async def main() -> int:
    """
    主函数

    Returns:
        退出码 (0 表示成功，1 表示失败)
    """
    try:
        # 1. 解析参数
        args = parse_arguments()

        # 设置日志级别
        if args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)
            logger.debug("启用详细日志模式")

        logger.info(f"任务 ID: {args.task_id}")
        if args.description:
            logger.info(f"视频描述: {args.description}")

        # 2. 验证输入文件
        validate_input_file(args.input)

        # 3. 加载配置
        config = load_config(args.config)
        logger.debug(f"配置: {config.to_dict()}")

        # 4. 创建优化器
        optimizer = SubtitleOptimizerV2(config)
        logger.info("字幕优化器创建成功")

        # 5. 加载输入文件
        optimizer.load_from_file(args.input)
        logger.info(f"已加载字幕数据")

        # 6. 执行优化
        logger.info("开始执行优化...")
        result = await optimizer.optimize(output_path=args.output)

        # 7. 打印结果
        print_results(result, args.output)

        return 0

    except FileNotFoundError as e:
        logger.error(f"文件错误: {e}")
        return 1
    except ValueError as e:
        logger.error(f"数据错误: {e}")
        return 1
    except KeyboardInterrupt:
        logger.info("用户中断操作")
        return 130
    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=True)
        return 1


def cli_main() -> None:
    """CLI 入口点"""
    exit_code = asyncio.run(main())
    sys.exit(exit_code)


if __name__ == "__main__":
    cli_main()
