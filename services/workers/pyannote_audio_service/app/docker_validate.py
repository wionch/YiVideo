# services/workers/pyannote_audio_service/app/docker_validate.py
# -*- coding: utf-8 -*-

"""
Docker 环境验证脚本

用于验证 pyannote.audio 服务在 Docker 环境中的正确配置和功能
"""

import os
import sys
import logging
from pathlib import Path

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def validate_pyannote_audio_import():
    """验证 pyannote.audio 模块导入"""
    try:
        from pyannote.audio import Pipeline
        logger.info("✅ pyannote.audio 模块导入成功")
        return True
    except ImportError as e:
        logger.error(f"❌ pyannote.audio 模块导入失败: {e}")
        return False

def validate_torch_cuda():
    """验证 PyTorch 和 CUDA 支持"""
    try:
        import torch
        logger.info(f"✅ PyTorch 版本: {torch.__version__}")

        if torch.cuda.is_available():
            logger.info(f"✅ CUDA 可用, 版本: {torch.version.cuda}")
            logger.info(f"✅ GPU 数量: {torch.cuda.device_count()}")
            for i in range(torch.cuda.device_count()):
                logger.info(f"✅ GPU {i}: {torch.cuda.get_device_name(i)}")
        else:
            logger.info("⚠️  CUDA 不可用，将使用 CPU 模式")

        return True
    except ImportError as e:
        logger.error(f"❌ PyTorch 导入失败: {e}")
        return False

def validate_dependencies():
    """验证其他依赖"""
    dependencies = [
        ('celery', 'Celery 消息队列'),
        ('redis', 'Redis 客户端'),
        ('librosa', '音频处理库'),
        ('numpy', '数值计算库'),
        ('yaml', 'YAML 解析库'),
        ('json', 'JSON 处理')
    ]

    all_valid = True
    for module_name, description in dependencies:
        try:
            __import__(module_name)
            logger.info(f"✅ {description} - 可用")
        except ImportError:
            logger.error(f"❌ {description} - 不可用")
            all_valid = False

    return all_valid

def validate_audio_file_access():
    """验证音频文件访问能力"""
    try:
        import librosa

        # 创建测试音频文件
        test_audio_path = "/tmp/test_audio.wav"
        if os.path.exists(test_audio_path):
            os.remove(test_audio_path)

        # 生成测试音频
        import numpy as np
        sample_rate = 16000
        duration = 1.0
        t = np.linspace(0., duration, int(sample_rate * duration))
        frequency = 440
        audio_data = np.sin(2. * np.pi * frequency * t)

        # 保存为 WAV 文件
        import soundfile as sf
        sf.write(test_audio_path, audio_data, sample_rate)

        # 验证读取
        data, sr = librosa.load(test_audio_path, sr=None)
        logger.info(f"✅ 音频文件访问测试成功: 采样率 {sr}, 长度 {len(data)}")

        # 清理
        os.remove(test_audio_path)

        return True
    except Exception as e:
        logger.error(f"❌ 音频文件访问测试失败: {e}")
        return False

def validate_huggingface_access():
    """验证 Hugging Face 模型访问"""
    try:
        from pyannote.audio import Pipeline
        import os

        # 检查是否配置了 Hugging Face token
        hf_token = os.environ.get('HF_TOKEN')
        if hf_token:
            logger.info("✅ HF_TOKEN 环境变量已配置")

            # 尝试访问模型
            try:
                # 这里不实际加载模型，只验证访问权限
                from huggingface_hub import HfApi
                api = HfApi()
                user_info = api.whoami(token=hf_token)
                logger.info(f"✅ Hugging Face 访问成功，用户: {user_info.get('name', 'unknown')}")
            except Exception as e:
                logger.warning(f"⚠️  Hugging Face 模型访问可能受限: {e}")

        else:
            logger.warning("⚠️  未配置 HF_TOKEN，可能无法访问某些模型")

        return True
    except Exception as e:
        logger.error(f"❌ Hugging Face 访问验证失败: {e}")
        return False

def validate_pyannoteai_access():
    """验证 pyannoteAI API 访问"""
    try:
        import os

        api_key = os.environ.get('PYANNOTEAI_API_KEY')
        if api_key:
            logger.info("✅ PYANNOTEAI_API_KEY 环境变量已配置")
        else:
            logger.warning("⚠️  未配置 PYANNOTEAI_API_KEY，将使用本地模式")

        return True
    except Exception as e:
        logger.error(f"❌ pyannoteAI API 验证失败: {e}")
        return False

def validate_gpu_lock():
    """验证 GPU 锁功能"""
    try:
        # 验证 Redis 连接
        import redis
        r = redis.Redis(host='redis', port=6379, db=2)
        r.ping()
        logger.info("✅ GPU 锁 Redis 连接正常")

        # 尝试导入 GPU 锁模块（如果可用）
        try:
            from services.common.locks import SmartGpuLockManager
            logger.info("✅ GPU 锁模块导入成功")
        except ImportError:
            logger.warning("⚠️  GPU 锁模块不可用，将在运行时动态导入")

        return True
    except Exception as e:
        logger.error(f"❌ GPU 锁功能验证失败: {e}")
        return False

def validate_redis_connection():
    """验证 Redis 连接"""
    try:
        import redis

        # 测试不同的 Redis 数据库
        databases = {
            'broker': 0,
            'backend': 1,
            'locks': 2,
            'state': 3
        }

        for name, db in databases.items():
            try:
                r = redis.Redis(host='redis', port=6379, db=db)
                r.ping()
                logger.info(f"✅ Redis {name} 连接正常 (db={db})")
            except Exception as e:
                logger.warning(f"⚠️  Redis {name} 连接失败 (db={db}): {e}")

        return True
    except Exception as e:
        logger.error(f"❌ Redis 连接验证失败: {e}")
        return False

def validate_filesystem():
    """验证文件系统访问"""
    try:
        # 测试临时目录
        temp_dir = Path("/tmp")
        test_file = temp_dir / "test_write.txt"

        with open(test_file, 'w') as f:
            f.write("test")

        with open(test_file, 'r') as f:
            content = f.read()

        if content == "test":
            logger.info("✅ 临时目录写入测试成功")
            os.remove(test_file)
        else:
            logger.error("❌ 临时目录写入测试失败")
            return False

        # 测试共享目录
        share_dir = Path("/share")
        if share_dir.exists():
            logger.info("✅ 共享目录访问正常")
        else:
            logger.warning("⚠️  共享目录不存在")

        return True
    except Exception as e:
        logger.error(f"❌ 文件系统验证失败: {e}")
        return False

def main():
    """主验证函数"""
    logger.info("🚀 开始 pyannote.audio 服务环境验证...")

    validation_results = []

    # 1. 验证核心依赖
    logger.info("📦 验证核心依赖...")
    validation_results.append(("核心依赖", validate_dependencies()))

    # 2. 验证 PyTorch 和 CUDA
    logger.info("🔥 验证 PyTorch 和 CUDA...")
    validation_results.append(("PyTorch/CUDA", validate_torch_cuda()))

    # 3. 验证 pyannote.audio
    logger.info("🎤 验证 pyannote.audio...")
    validation_results.append(("pyannote.audio", validate_pyannote_audio_import()))

    # 4. 验证音频文件访问
    logger.info("🎵 验证音频文件访问...")
    validation_results.append(("音频文件访问", validate_audio_file_access()))

    # 5. 验证 Hugging Face 访问
    logger.info("🤗 验证 Hugging Face 访问...")
    validation_results.append(("Hugging Face 访问", validate_huggingface_access()))

    # 6. 验证 pyannoteAI API
    logger.info("🎙️ 验证 pyannoteAI API...")
    validation_results.append(("pyannoteAI API", validate_pyannoteai_access()))

    # 7. 验证 GPU 锁
    logger.info("🔒 验证 GPU 锁...")
    validation_results.append(("GPU 锁", validate_gpu_lock()))

    # 8. 验证 Redis 连接
    logger.info("🔗 验证 Redis 连接...")
    validation_results.append(("Redis 连接", validate_redis_connection()))

    # 9. 验证文件系统
    logger.info("📁 验证文件系统...")
    validation_results.append(("文件系统", validate_filesystem()))

    # 汇总结果
    logger.info("\n" + "="*50)
    logger.info("🎯 验证结果汇总:")
    logger.info("="*50)

    all_passed = True
    for test_name, result in validation_results:
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"  {test_name}: {status}")
        if not result:
            all_passed = False

    logger.info("="*50)
    if all_passed:
        logger.info("🎉 所有验证通过！pyannote.audio 服务环境配置正确。")
        logger.info("🚀 可以开始处理说话人分离任务。")
    else:
        logger.error("❌ 部分验证失败，请检查配置。")

    return all_passed

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("验证被用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"验证过程中发生未预期的错误: {e}")
        sys.exit(1)