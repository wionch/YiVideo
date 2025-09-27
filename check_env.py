#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
check_env.py

一个用于检测和打印AI视频处理环境关键组件状态和版本的脚本,
包括 CUDA, cuDNN, PyTorch, PaddlePaddle, 和 FFmpeg.
"""

import os
import re
import subprocess
import sys


# 用于彩色输出的辅助函数
def green(text):
    """返回绿色文本"""
    return f"\033[92m{text}\033[0m"

def red(text):
    """返回红色文本"""
    return f"\033[91m{text}\033[0m"

def yellow(text):
    """返回黄色文本"""
    return f"\033[93m{text}\033[0m"

def print_header(title):
    """打印标准格式的标题头"""
    print("\n" + "="*60)
    print(f"--- {title} ---")
    print("="*60)

def check_cuda_version():
    """检查CUDA Toolkit版本"""
    print_header("CUDA Toolkit Version (from nvcc)")
    try:
        # 优先使用nvcc命令，这是最准确的方式
        result = subprocess.run(["nvcc", "--version"], capture_output=True, text=True, check=True, encoding='utf-8')
        match = re.search(r"release (\d+\.\d+), V(\d+\.\d+\.\d+)", result.stdout)
        if match:
            print(f"CUDA Version: {green(match.group(1))}")
            print(f"Full Version: {green(match.group(2))}")
        else:
            print(red("无法解析 nvcc 输出。"))
            print(result.stdout)
    except FileNotFoundError:
        print(red("`nvcc` 命令未找到。"))
        print(yellow("这在 runtime-only 镜像中是正常的。将尝试从PyTorch获取CUDA版本..."))
        # 如果nvcc不存在（例如在runtime镜像中），则尝试从torch获取
        try:
            import torch
            if torch.version.cuda:
                print(f"CUDA Version (由 PyTorch 报告): {green(torch.version.cuda)}")
            else:
                print(red("PyTorch 未编译CUDA支持。"))
        except ImportError:
            print(red("PyTorch 未安装。"))
    except Exception as e:
        print(red(f"发生错误: {e}"))

def check_pytorch_status():
    """检查PyTorch状态"""
    print_header("PyTorch Status")
    try:
        import torch
        print(f"PyTorch Version: {green(torch.__version__)}")
        
        cuda_available = torch.cuda.is_available()
        print(f"CUDA 可用: {green('是') if cuda_available else red('否')}")

        if cuda_available:
            print(f"cuDNN Version (由 PyTorch 报告): {green(torch.backends.cudnn.version())}")
            device_count = torch.cuda.device_count()
            print(f"检测到的GPU数量: {green(device_count)}")
            for i in range(device_count):
                print(f"  - GPU {i}: {green(torch.cuda.get_device_name(i))}")
        else:
            print(yellow("PyTorch 无法检测到GPU。请检查安装和驱动。"))

    except ImportError:
        print(red("PyTorch 未安装。"))
    except Exception as e:
        print(red(f"发生错误: {e}"))

def check_paddle_status():
    """检查PaddlePaddle状态"""
    print_header("PaddlePaddle Status")
    try:
        import paddle
        print(f"PaddlePaddle Version: {green(paddle.version.full_version)}")

        cuda_available = paddle.is_compiled_with_cuda()
        print(f"编译时支持CUDA: {green('是') if cuda_available else red('否')}")

        if cuda_available:
            cudnn_version = paddle.version.cudnn()
            print(f"cuDNN Version (由 Paddle 报告): {green(cudnn_version)}")
            
            try:
                device_count = paddle.device.cuda.device_count()
                print(f"检测到的GPU数量: {green(device_count)}")
                for i in range(device_count):
                    print(f"  - GPU {i}: {green(paddle.device.cuda.get_device_name(i))}")
            except Exception:
                 print(red("Paddle编译时支持CUDA, 但初始化GPU失败。"))
        else:
            print(yellow("PaddlePaddle 无法检测到GPU。请确保您安装了 `paddlepaddle-gpu`。"))

    except ImportError:
        print(red("PaddlePaddle 未安装。"))
    except Exception as e:
        print(red(f"发生错误: {e}"))

def check_ffmpeg_status():
    """检查FFmpeg状态"""
    print_header("FFmpeg Status")
    try:
        # 检查版本
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True, encoding='utf-8')
        version_line = result.stdout.splitlines()[0]
        print(f"FFmpeg Version: {green(version_line.strip())}")

        # 检查NVENC编码器
        encoders_result = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True, check=True, encoding='utf-8')
        nvenc_supported = "h264_nvenc" in encoders_result.stdout
        print(f"NVENC (GPU 编码) 支持: {green('是') if nvenc_supported else red('否')}")

        # 检查NVDEC/cuvid解码器
        decoders_result = subprocess.run(["ffmpeg", "-decoders"], capture_output=True, text=True, check=True, encoding='utf-8')
        nvdec_supported = "h264_cuvid" in decoders_result.stdout
        print(f"NVDEC (GPU 解码) 支持: {green('是') if nvdec_supported else red('否')}")

    except FileNotFoundError:
        print(red("`ffmpeg` 命令未找到。"))
    except Exception as e:
        print(red(f"检查FFmpeg时发生错误: {e}"))

def main():
    """主函数，运行所有检查"""
    print("="*60)
    print("开始环境检查...")
    print("="*60)
    
    check_cuda_version()
    check_pytorch_status()
    check_paddle_status()
    check_ffmpeg_status()
    
    print("\n" + "="*60)
    print("环境检查完成。")
    print("="*60)

if __name__ == "__main__":
    main()
