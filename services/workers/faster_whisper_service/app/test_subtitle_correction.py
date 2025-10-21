#!/usr/bin/env python3
"""
字幕校正功能测试脚本 - 容器内版本

用于在Docker容器内测试字幕校正系统的各个组件，包括：
1. 环境检测和路径验证
2. SRT解析器功能
3. AI服务提供商接口
4. 字幕校正器整体功能
5. 配置管理功能

使用方法:
python test_subtitle_correction.py [--provider deepseek] [--test-file /path/to/subtitle.srt]
"""

import os
import sys
import asyncio
import argparse
from pathlib import Path

# 容器内Python路径配置
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/services')

# 容器内默认路径配置
DEFAULT_TEST_SUBTITLE = "/share/workflows/45fa11be-3727-4d3b-87ce-08c09618183f/subtitles/666_with_speakers.srt"
DEFAULT_SYSTEM_PROMPT = "/app/config/system_prompt/subtitle_optimization.md"
DEFAULT_CONFIG_PATH = "/app/config.yml"


def check_container_environment():
    """检测容器内环境"""
    print("🔍 检测容器内环境...")

    env_checks = {
        "工作目录": os.getcwd(),
        "Python路径": sys.executable,
        "Python版本": sys.version,
        "环境变量": {
            "PYTHONPATH": os.getenv("PYTHONPATH", "未设置"),
            "HOME": os.getenv("HOME", "未设置"),
            "PWD": os.getenv("PWD", "未设置")
        }
    }

    for key, value in env_checks.items():
        if isinstance(value, dict):
            print(f"✅ {key}:")
            for k, v in value.items():
                print(f"   {k}: {v}")
        else:
            print(f"✅ {key}: {value}")

    # 检查关键目录
    critical_dirs = [
        "/app",
        "/app/services",
        "/app/config",
        "/share"
    ]

    print("\n📁 关键目录检查:")
    for dir_path in critical_dirs:
        if os.path.exists(dir_path):
            print(f"✅ {dir_path} - 存在")
        else:
            print(f"❌ {dir_path} - 不存在")

    # 检查关键文件
    critical_files = [
        DEFAULT_CONFIG_PATH,
        DEFAULT_SYSTEM_PROMPT
    ]

    print("\n📄 关键文件检查:")
    for file_path in critical_files:
        if os.path.exists(file_path):
            size = os.path.getsize(file_path)
            print(f"✅ {file_path} - 存在 ({size} bytes)")
        else:
            print(f"❌ {file_path} - 不存在")

    print()


def check_test_subtitle_file(test_file: str):
    """检查测试字幕文件"""
    print(f"📽️ 检查测试字幕文件: {test_file}")

    if os.path.exists(test_file):
        size = os.path.getsize(test_file)
        print(f"✅ 字幕文件存在 ({size} bytes)")

        # 尝试读取前几行内容
        try:
            with open(test_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()[:10]
            print(f"✅ 文件可读，前10行内容预览:")
            for i, line in enumerate(lines, 1):
                print(f"   {i:2d}: {line.rstrip()}")
            if len(lines) == 10:
                print("   ...")
        except Exception as e:
            print(f"❌ 文件读取失败: {e}")
            return False
    else:
        print(f"❌ 字幕文件不存在")
        return False

    return True


try:
    from services.common.subtitle.subtitle_parser import SRTParser, SubtitleEntry, parse_srt_file, write_srt_file
    from services.common.subtitle.ai_providers import AIProviderFactory
    from services.common.subtitle.subtitle_correction_config import SubtitleCorrectionConfig
    from services.common.subtitle import SubtitleCorrector
    from services.common.config_loader import CONFIG

    print("✅ 所有模块导入成功")

except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    print("请确保在容器内运行此脚本，并且所有依赖模块都已正确安装")
    print("当前Python路径:", sys.path)
    print("当前工作目录:", os.getcwd())
    sys.exit(1)


def create_test_srt_file(file_path: str):
    """创建测试用的SRT字幕文件"""
    test_content = """1
00:00:01,000 --> 00:00:03,500
大家好，欢迎来到今天的视频

2
00:00:04,000 --> 00:00:06,200
今天我们要讨论的话题是
人工智能技术的发展

3
00:00:06,800 --> 00:00:09,100
AI技术正在改变我们的
生活方式和工作方式

4
00:00:10,000 --> 00:00:12,500
它不仅在医疗领域有广泛应用
还在教育、金融等多个领域

5
00:00:13,000 --> 00:00:15,800
发挥着越来越重要的作用
"""

    # 确保目录存在
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(test_content)

    print(f"✅ 测试SRT文件已创建: {file_path}")


def test_srt_parser(test_file: str):
    """测试SRT解析器功能"""
    print("\n🔧 测试SRT解析器...")

    try:
        # 测试文件解析
        entries = parse_srt_file(test_file)
        print(f"✅ 解析成功，共 {len(entries)} 条字幕")

        # 测试统计信息
        parser = SRTParser()
        stats = parser.get_statistics(entries)
        print(f"✅ 统计信息: {stats}")

        # 测试字幕条目操作
        if len(entries) > 1:
            # 测试时间戳检查
            overlap = entries[0].overlaps_with(entries[1])
            print(f"✅ 重叠检查: 前2条字幕是否重叠 = {overlap}")

        # 测试文本转换
        text = parser.entries_to_text(entries)
        print(f"✅ 文本转换成功，长度: {len(text)} 字符")

        return True

    except Exception as e:
        print(f"❌ SRT解析器测试失败: {e}")
        return False


def test_config_management():
    """测试配置管理功能"""
    print("\n⚙️ 测试配置管理...")

    try:
        # 测试从全局配置加载
        print("📋 步骤1: 读取全局配置")
        subtitle_config = CONFIG.get('subtitle_correction', {})
        if not subtitle_config:
            print("⚠️ 配置文件中未找到subtitle_correction配置，使用默认配置")
            subtitle_config = {}
        else:
            print(f"✅ 从配置文件读取到subtitle_correction配置: {list(subtitle_config.keys())}")
            if 'providers' in subtitle_config:
                print(f"✅ 找到providers配置: {list(subtitle_config['providers'].keys())}")
            else:
                print("⚠️ 配置中未找到providers字段")

        print("📋 步骤2: 创建SubtitleCorrectionConfig实例")
        config = SubtitleCorrectionConfig(subtitle_config)
        print(f"✅ 配置加载成功，默认提供商: {config.default_provider}")

        print("📋 步骤3: 检查providers字段")
        if hasattr(config, 'providers') and config.providers:
            print(f"✅ providers字段存在，包含 {len(config.providers)} 个提供商:")
            for name, provider in config.providers.items():
                status = "启用" if provider.enabled else "禁用"
                print(f"   - {name}: {provider.model} ({status})")
        else:
            print("❌ providers字段不存在或为空")
            print(f"   - hasattr(config, 'providers'): {hasattr(config, 'providers')}")
            if hasattr(config, 'providers'):
                print(f"   - config.providers值: {config.providers}")
            return False

        # 测试提供商配置获取
        print("📋 步骤4: 获取启用的提供商")
        enabled_providers = config.get_enabled_providers()
        print(f"✅ 启用的提供商: {enabled_providers}")

        # 测试系统提示词路径
        print("📋 步骤5: 检查系统提示词文件")
        if os.path.exists(config.system_prompt_path):
            size = os.path.getsize(config.system_prompt_path)
            print(f"✅ 系统提示词文件存在: {config.system_prompt_path} ({size} bytes)")
        else:
            print(f"❌ 系统提示词文件不存在: {config.system_prompt_path}")

        return True

    except Exception as e:
        print(f"❌ 配置管理测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_api_keys():
    """检查API密钥配置"""
    print("\n🔑 检查API密钥配置...")

    api_keys = {
        "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY"),
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
        "ZHIPU_API_KEY": os.getenv("ZHIPU_API_KEY"),
        "VOLCENGINE_API_KEY": os.getenv("VOLCENGINE_API_KEY")
    }

    configured_count = 0
    for key, value in api_keys.items():
        if value:
            masked_value = value[:8] + "***" if len(value) > 8 else "***"
            print(f"✅ {key}: {masked_value}")
            configured_count += 1
        else:
            print(f"❌ {key}: 未配置")

    print(f"\n📊 API密钥配置状态: {configured_count}/{len(api_keys)} 个已配置")
    return configured_count > 0


async def test_ai_providers():
    """测试AI服务提供商"""
    print("\n🤖 测试AI服务提供商...")

    try:
        factory = AIProviderFactory()
        supported_providers = factory.get_supported_providers()
        print(f"✅ 支持的AI提供商: {supported_providers}")

        success_count = 0

        for provider_name in supported_providers:
            try:
                # 获取提供商信息
                provider_info = factory.get_provider_info(provider_name)
                print(f"✅ {provider_name}: {provider_info.get('name', 'Unknown')} - {provider_info.get('model', 'Unknown')}")

                # 尝试创建提供商实例（不进行实际API调用）
                provider_config = {
                    'api_key': 'test_key',
                    'api_key_env': 'TEST_API_KEY'
                }
                provider = factory.create_provider(provider_name, provider_config)
                print(f"✅ {provider_name} 实例创建成功")

                success_count += 1

            except Exception as e:
                print(f"❌ {provider_name} 测试失败: {e}")

        print(f"✅ AI提供商测试完成: {success_count}/{len(supported_providers)} 成功")
        return success_count > 0

    except Exception as e:
        print(f"❌ AI提供商测试失败: {e}")
        return False


async def test_subtitle_corrector(test_file: str, provider_name: str = None):
    """测试字幕校正器功能（不进行实际API调用）"""
    print(f"\n✨ 测试字幕校正器 (提供商: {provider_name or '默认'})...")

    try:
        print("📋 步骤1: 创建字幕校正器")
        corrector = SubtitleCorrector(provider=provider_name)
        print(f"✅ 字幕校正器创建成功，使用提供商: {corrector.provider_name}")

        print("📋 步骤2: 检查校正器配置")
        print(f"   - 默认提供商: {corrector.config.default_provider}")
        print(f"   - 系统提示词路径: {corrector.config.system_prompt_path}")
        print(f"   - 最大字符数: {corrector.config.max_subtitle_length}")
        print(f"   - 可用提供商: {list(corrector.config.providers.keys())}")

        print("📋 步骤3: 测试系统提示词加载")
        system_prompt = corrector._load_system_prompt()
        print(f"✅ 系统提示词加载成功，长度: {len(system_prompt)} 字符")

        print("📋 步骤4: 测试字幕文件解析")
        entries = corrector.parser.parse_file(test_file)
        print(f"✅ 字幕解析成功，共 {len(entries)} 条")

        print("📋 步骤5: 测试文本转换")
        subtitle_text = corrector.parser.entries_to_text(entries)
        print(f"✅ 字幕文本转换成功，长度: {len(subtitle_text)} 字符")

        print("📋 步骤6: 检查分批处理需求")
        needs_batch = len(subtitle_text) > corrector.config.max_subtitle_length
        print(f"✅ 分批处理检查: {'需要' if needs_batch else '不需要'}")
        print(f"   - 当前文本长度: {len(subtitle_text)}")
        print(f"   - 最大允许长度: {corrector.config.max_subtitle_length}")

        print("✅ 字幕校正器基础功能测试完成（未进行实际API调用）")
        return True

    except Exception as e:
        print(f"❌ 字幕校正器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def full_correction_test(test_file: str, provider_name: str = None):
    """完整的字幕校正测试（包括实际API调用）"""
    print(f"\n🚀 完整字幕校正测试 (提供商: {provider_name or '默认'})...")
    print("⚠️ 此测试将进行实际的API调用，请确保已配置有效的API密钥")

    # 检查API密钥
    if not check_api_keys():
        print("❌ 未配置有效的API密钥，跳过完整API测试")
        return False

    # 在容器内跳过用户交互，直接进行测试
    print("🔄 自动开始完整API测试...")

    try:
        # 创建校正器
        corrector = SubtitleCorrector(provider=provider_name)

        # 执行校正
        result = await corrector.correct_subtitle_file(test_file)

        if result.success:
            print(f"✅ 字幕校正成功!")
            print(f"   原始文件: {result.original_subtitle_path}")
            print(f"   校正文件: {result.corrected_subtitle_path}")
            print(f"   使用提供商: {result.provider_used}")
            print(f"   处理时间: {result.processing_time:.2f}秒")
            print(f"   统计信息: {result.statistics}")

            # 显示校正前后对比
            try:
                with open(result.original_subtitle_path, 'r', encoding='utf-8') as f:
                    original_content = f.read()
                with open(result.corrected_subtitle_path, 'r', encoding='utf-8') as f:
                    corrected_content = f.read()

                print(f"   原始内容长度: {len(original_content)} 字符")
                print(f"   校正内容长度: {len(corrected_content)} 字符")
                print(f"   内容变化: {'有变化' if original_content != corrected_content else '无变化'}")
            except Exception as e:
                print(f"   内容对比失败: {e}")

            return True
        else:
            print(f"❌ 字幕校正失败: {result.error_message}")
            return False

    except Exception as e:
        print(f"❌ 完整校正测试失败: {e}")
        return False


async def main():
    """主测试函数"""
    parser = argparse.ArgumentParser(description="字幕校正功能测试脚本 - 容器内版本")
    parser.add_argument("--provider", help="指定AI服务提供商", choices=["deepseek", "gemini", "zhipu", "volcengine"])
    parser.add_argument("--test-file", help="测试字幕文件路径", default=DEFAULT_TEST_SUBTITLE)
    parser.add_argument("--full-test", help="执行完整API测试", action="store_true")
    parser.add_argument("--skip-env-check", help="跳过环境检查", action="store_true")
    args = parser.parse_args()

    print("🎬 YiVideo 字幕校正功能测试 - 容器内版本")
    print("=" * 60)

    # 环境检测
    if not args.skip_env_check:
        check_container_environment()

    # 检查测试文件
    if not check_test_subtitle_file(args.test_file):
        print(f"⚠️ 指定的测试文件不存在，将创建临时测试文件")
        # 在容器内创建临时测试文件
        temp_test_file = "/tmp/test_subtitle.srt"
        create_test_srt_file(temp_test_file)
        args.test_file = temp_test_file

    # 运行测试
    test_results = []

    # 1. 测试SRT解析器
    test_results.append(("SRT解析器", test_srt_parser(args.test_file)))

    # 2. 测试配置管理
    test_results.append(("配置管理", test_config_management()))

    # 3. 检查API密钥配置
    test_results.append(("API密钥配置", check_api_keys()))

    # 4. 测试AI提供商
    test_results.append(("AI提供商", await test_ai_providers()))

    # 5. 测试字幕校正器基础功能
    test_results.append(("字幕校正器基础", await test_subtitle_corrector(args.test_file, args.provider)))

    # 6. 完整API测试（可选）
    if args.full_test:
        test_results.append(("完整字幕校正", await full_correction_test(args.test_file, args.provider)))

    # 输出测试结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)

    success_count = 0
    for test_name, success in test_results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{test_name:20} : {status}")
        if success:
            success_count += 1

    print(f"\n总计: {success_count}/{len(test_results)} 测试通过")

    if success_count == len(test_results):
        print("🎉 所有测试通过！字幕校正功能在容器内运行正常。")
        return 0
    else:
        print("⚠️ 部分测试失败，请检查配置和依赖。")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 测试过程中发生未预期的错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)