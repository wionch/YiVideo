# test_sampling_optimization.py
"""
字幕区域检测抽帧优化效果验证脚本
"""
import time
import os
import sys

# 设置路径以便导入模块
SERVICE_ROOT = os.path.dirname(__file__)
APP_ROOT = os.path.join(SERVICE_ROOT, 'app')
sys.path.insert(0, APP_ROOT)

from app.modules.decoder import GPUDecoder
from app.modules.area_detector import SubtitleAreaDetector

def test_sampling_performance(video_path: str, config: dict):
    """
    对比传统采样和精准采样的性能差异
    """
    print("=" * 60)
    print("字幕区域检测抽帧性能对比测试")
    print("=" * 60)
    
    if not os.path.exists(video_path):
        print(f"错误: 视频文件不存在: {video_path}")
        return
    
    # 初始化模块
    decoder = GPUDecoder(config.get('decoder', {}))
    area_detector = SubtitleAreaDetector(config.get('area_detector', {}))
    
    print(f"测试视频: {video_path}")
    print(f"采样目标: {area_detector.sample_count} 帧")
    print()
    
    # 测试1: 传统采样方法
    print("🔍 测试1: 传统采样方法")
    start_time = time.time()
    try:
        traditional_frames = area_detector._sample_frames_traditional(video_path, decoder)
        traditional_time = time.time() - start_time
        traditional_count = len(traditional_frames)
        print(f"  ✅ 传统采样完成")
        print(f"  ⏱️  耗时: {traditional_time:.2f} 秒")
        print(f"  📊 获得帧数: {traditional_count}")
    except Exception as e:
        print(f"  ❌ 传统采样失败: {e}")
        traditional_time = float('inf')
        traditional_count = 0
    
    print()
    
    # 获取视频时长信息
    duration = 0
    try:
        import av
        container = av.open(video_path)
        stream = container.streams.video[0]
        duration = float(stream.duration * stream.time_base)
        container.close()
    except:
        duration = 300  # 默认值
    
    # 测试2: 精准采样方法
    print("🎯 测试2: 精准采样方法")
    start_time = time.time()
    try:
        precise_frames = area_detector._sample_frames_precise(video_path, decoder, duration)
        precise_time = time.time() - start_time
        precise_count = len(precise_frames)
        print(f"  ✅ 精准采样完成")
        print(f"  ⏱️  耗时: {precise_time:.2f} 秒")
        print(f"  📊 获得帧数: {precise_count}")
    except Exception as e:
        print(f"  ❌ 精准采样失败: {e}")
        precise_time = float('inf')
        precise_count = 0
    
    print()
    
    # 性能对比分析
    print("📈 性能对比分析")
    print("-" * 40)
    
    if traditional_time < float('inf') and precise_time < float('inf'):
        speedup = traditional_time / precise_time if precise_time > 0 else 0
        print(f"⚡ 加速比: {speedup:.2f}x")
        print(f"⏱️  时间节省: {traditional_time - precise_time:.2f} 秒")
        
        if speedup > 1:
            print("🎉 精准采样方法性能更优！")
        elif speedup > 0.8:
            print("🤔 两种方法性能相近")
        else:
            print("⚠️  传统方法在此视频上性能更好")
    
    print(f"📊 帧数对比: 传统={traditional_count}, 精准={precise_count}")
    
    # 质量评估
    if traditional_count > 0 and precise_count > 0:
        quality_ratio = precise_count / traditional_count
        print(f"🎯 采样质量比: {quality_ratio:.2f}")
        
        if quality_ratio >= 0.9:
            print("✅ 精准采样质量优秀")
        elif quality_ratio >= 0.7:
            print("⚠️  精准采样质量可接受")
        else:
            print("❌ 精准采样质量不足，建议使用传统方法")

def main():
    """测试主函数"""
    import argparse
    import yaml
    
    parser = argparse.ArgumentParser(description="字幕区域检测抽帧性能测试")
    parser.add_argument('-i', '--input', required=True, help="测试视频路径")
    parser.add_argument('--config', default='/app/config.yml', help="配置文件路径")
    
    args = parser.parse_args()
    
    # 加载配置
    try:
        with open(args.config, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"配置加载失败: {e}")
        config = {}
    
    # 执行性能测试
    test_sampling_performance(args.input, config)

if __name__ == '__main__':
    main()