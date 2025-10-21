#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
clean.py

一个用于清理项目中所有__pycache__目录的简单脚本
"""

import os
import shutil
import sys


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


def find_pycache_dirs(root_dir="."):
    """
    递归搜索所有__pycache__目录
    
    Args:
        root_dir (str): 搜索的根目录，默认为当前目录
        
    Returns:
        list: 找到的所有__pycache__目录路径列表
    """
    pycache_dirs = []
    
    for dirpath, dirnames, _ in os.walk(root_dir):
        # 检查当前目录是否为__pycache__
        if os.path.basename(dirpath) == "__pycache__":
            pycache_dirs.append(dirpath)
    
    return pycache_dirs


def delete_pycache_dirs(pycache_dirs):
    """
    删除指定的__pycache__目录列表
    
    Args:
        pycache_dirs (list): 要删除的__pycache__目录路径列表
        
    Returns:
        tuple: (成功删除数量, 失败删除数量, 失败的目录列表)
    """
    success_count = 0
    failure_count = 0
    failed_dirs = []
    total_count = len(pycache_dirs)
    
    for i, pycache_dir in enumerate(pycache_dirs, 1):
        try:
            # 显示删除进度
            print(f"删除中 {i}/{total_count}: {pycache_dir}")
            
            # 删除目录及其内容
            shutil.rmtree(pycache_dir)
            success_count += 1
            
        except Exception as e:
            print(f"{red('删除失败')}: {pycache_dir} - {e}")
            failure_count += 1
            failed_dirs.append(pycache_dir)
    
    return success_count, failure_count, failed_dirs


def main():
    """主函数，搜索并删除所有__pycache__目录"""
    print_header("Python 缓存清理工具")
    
    # 搜索所有__pycache__目录
    print("搜索__pycache__目录...")
    pycache_dirs = find_pycache_dirs()
    
    if not pycache_dirs:
        print(green("未找到任何__pycache__目录，项目已经很干净！"))
        return
    
    print(f"找到 {yellow(str(len(pycache_dirs)))} 个__pycache__目录")
    
    # 删除找到的目录
    print("\n开始删除...")
    success_count, failure_count, failed_dirs = delete_pycache_dirs(pycache_dirs)
    
    # 显示结果统计
    print_header("清理完成")
    print(f"成功删除: {green(str(success_count))} 个目录")
    
    if failure_count > 0:
        print(f"删除失败: {red(str(failure_count))} 个目录")
        print("\n失败的目录:")
        for failed_dir in failed_dirs:
            print(f"  - {red(failed_dir)}")
    
    print(f"\n总计处理: {len(pycache_dirs)} 个__pycache__目录")
    
    if failure_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()