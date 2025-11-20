# -*- coding: utf-8 -*-

"""
paddleocr.detect_subtitle_area 节点测试

测试新增的自定义参数输入和远程目录下载功能。
"""

import unittest
import json
import os
from unittest.mock import patch, MagicMock
from services.workers.paddleocr_service.app.tasks import detect_subtitle_area
from services.common.context import WorkflowContext, StageExecution


class TestDetectSubtitleArea(unittest.TestCase):
    """测试 detect_subtitle_area 函数的新功能"""
    
    def setUp(self):
        """测试准备"""
        self.workflow_id = "test_workflow_123"
        self.shared_storage_path = "/tmp/test_storage"
        os.makedirs(self.shared_storage_path, exist_ok=True)
        
        # 创建模拟的关键帧目录和文件
        self.keyframe_dir = os.path.join(self.shared_storage_path, "keyframes")
        os.makedirs(self.keyframe_dir, exist_ok=True)
        for i in range(3):
            with open(os.path.join(self.keyframe_dir, f"frame_{i}.jpg"), 'w') as f:
                f.write("fake image content")
    
    def tearDown(self):
        """清理测试文件"""
        import shutil
        if os.path.exists(self.shared_storage_path):
            shutil.rmtree(self.shared_storage_path)
    
    def _create_mock_context(self, input_params=None):
        """创建模拟的工作流上下文"""
        if input_params is None:
            input_params = {}
        
        context = {
            "workflow_id": self.workflow_id,
            "shared_storage_path": self.shared_storage_path,
            "input_params": input_params,
            "stages": {}
        }
        return context
    
    @patch('subprocess.run')
    def test_parameter_local_keyframe_dir(self, mock_subprocess):
        """测试通过参数传入本地关键帧目录"""
        # 模拟外部脚本返回
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"subtitle_area": {"x": 0, "y": 100, "width": 1920, "height": 200}})
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result
        
        # 创建测试上下文，传入关键帧目录参数
        input_params = {
            "node_params": {
                "paddleocr.detect_subtitle_area": {
                    "keyframe_dir": self.keyframe_dir
                }
            }
        }
        context = self._create_mock_context(input_params)
        
        # 执行任务
        result = detect_subtitle_area(context=context)
        
        # 验证结果
        self.assertEqual(result["stages"]["paddleocr.detect_subtitle_area"]["status"], "SUCCESS")
        self.assertIn("subtitle_area", result["stages"]["paddleocr.detect_subtitle_area"]["output"])
        
        # 验证参数解析正确
        recorded_params = result["stages"]["paddleocr.detect_subtitle_area"]["input_params"]
        self.assertEqual(recorded_params["input_source"], "parameter_local")
        self.assertEqual(recorded_params["keyframe_dir"], self.keyframe_dir)
    
    @patch('services.common.minio_directory_download.download_keyframes_directory')
    @patch('subprocess.run')
    def test_parameter_minio_keyframe_dir(self, mock_subprocess, mock_download):
        """测试通过参数传入MinIO关键帧目录URL"""
        # 模拟外部脚本返回
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"subtitle_area": {"x": 0, "y": 100, "width": 1920, "height": 200}})
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result
        
        # 模拟MinIO下载结果
        mock_download.return_value = {
            "success": True,
            "total_files": 3,
            "downloaded_files": ["frame_0.jpg", "frame_1.jpg", "frame_2.jpg"]
        }
        
        # 创建测试上下文，传入MinIO关键帧目录参数
        input_params = {
            "node_params": {
                "paddleocr.detect_subtitle_area": {
                    "keyframe_dir": "minio://yivideo/workflow_123/keyframes",
                    "download_from_minio": True
                }
            }
        }
        context = self._create_mock_context(input_params)
        
        # 执行任务
        result = detect_subtitle_area(context=context)
        
        # 验证结果
        self.assertEqual(result["stages"]["paddleocr.detect_subtitle_area"]["status"], "SUCCESS")
        self.assertIn("subtitle_area", result["stages"]["paddleocr.detect_subtitle_area"]["output"])
        
        # 验证下载功能被调用
        mock_download.assert_called_once()
        
        # 验证参数解析正确
        recorded_params = result["stages"]["paddleocr.detect_subtitle_area"]["input_params"]
        self.assertEqual(recorded_params["input_source"], "parameter_minio")
        self.assertIn("minio_download_result", recorded_params)
        self.assertEqual(recorded_params["minio_download_result"]["total_files"], 3)
    
    def test_workflow_mode_backward_compatibility(self):
        """测试工作流模式的向后兼容性"""
        # 创建测试上下文，模拟工作流前置阶段
        context = self._create_mock_context()
        context["stages"] = {
            "ffmpeg.extract_keyframes": {
                "status": "SUCCESS",
                "output": {
                    "keyframe_dir": self.keyframe_dir
                }
            }
        }
        
        # 执行任务
        with patch('subprocess.run') as mock_subprocess:
            mock_result = MagicMock()
            mock_result.stdout = json.dumps({"subtitle_area": {"x": 0, "y": 100, "width": 1920, "height": 200}})
            mock_result.stderr = ""
            mock_subprocess.return_value = mock_result
            
            result = detect_subtitle_area(context=context)
        
        # 验证结果
        self.assertEqual(result["stages"]["paddleocr.detect_subtitle_area"]["status"], "SUCCESS")
        
        # 验证参数解析正确
        recorded_params = result["stages"]["paddleocr.detect_subtitle_area"]["input_params"]
        self.assertEqual(recorded_params["input_source"], "workflow_ffmpeg")
        self.assertEqual(recorded_params["keyframe_dir"], self.keyframe_dir)
    
    def test_invalid_keyframe_dir_error(self):
        """测试无效关键帧目录的错误处理"""
        # 创建测试上下文，传入无效的关键帧目录
        input_params = {
            "node_params": {
                "paddleocr.detect_subtitle_area": {
                    "keyframe_dir": "/nonexistent/directory"
                }
            }
        }
        context = self._create_mock_context(input_params)
        
        # 执行任务，应该抛出异常
        with self.assertRaises(ValueError):
            detect_subtitle_area(context=context)


if __name__ == '__main__':
    unittest.main()