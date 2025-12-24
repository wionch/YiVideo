# tests/unit/common/test_base_node_executor.py
# -*- coding: utf-8 -*-

"""BaseNodeExecutor 单元测试"""

import pytest
from typing import Dict, Any, List
from unittest.mock import MagicMock

from services.common.base_node_executor import BaseNodeExecutor
from services.common.context import WorkflowContext, StageExecution


class ConcreteNodeExecutor(BaseNodeExecutor):
    """用于测试的具体节点执行器"""

    def __init__(self, task_name: str, context: WorkflowContext, should_fail: bool = False):
        super().__init__(task_name, context)
        self.should_fail = should_fail
        self.validate_called = False
        self.execute_called = False

    def validate_input(self) -> None:
        """验证输入参数"""
        self.validate_called = True
        if self.should_fail:
            raise ValueError("Validation failed")

    def execute_core_logic(self) -> Dict[str, Any]:
        """执行核心逻辑"""
        self.execute_called = True
        if self.should_fail:
            raise RuntimeError("Execution failed")
        return {"output_path": "/share/output.txt"}

    def get_cache_key_fields(self) -> List[str]:
        """返回缓存键字段"""
        return ["input_path"]

    def get_required_output_fields(self) -> List[str]:
        """返回必需输出字段"""
        return ["output_path"]


class TestBaseNodeExecutor:
    """BaseNodeExecutor 测试"""

    def test_successful_execution(self):
        """测试成功执行流程"""
        context = WorkflowContext(
            workflow_id="task-001",
            shared_storage_path="/share/workflows/task-001",
            input_params={
                "input_data": {"input_path": "/share/input.txt"},
                "core": {"auto_upload_to_minio": False}
            }
        )

        executor = ConcreteNodeExecutor("test.node", context)
        result_context = executor.execute()

        # 验证调用顺序
        assert executor.validate_called
        assert executor.execute_called

        # 验证结果
        assert "test.node" in result_context.stages
        stage = result_context.stages["test.node"]
        assert stage.status == "SUCCESS"
        assert stage.output["output_path"] == "/share/output.txt"
        assert stage.error is None
        assert stage.duration >= 0  # 允许为0（执行太快）

    def test_validation_failure(self):
        """测试验证失败场景"""
        context = WorkflowContext(
            workflow_id="task-002",
            shared_storage_path="/share/workflows/task-002",
            input_params={"input_data": {}}
        )

        executor = ConcreteNodeExecutor("test.node", context, should_fail=True)
        result_context = executor.execute()

        # 验证失败处理
        assert executor.validate_called
        assert not executor.execute_called  # 验证失败后不应执行

        stage = result_context.stages["test.node"]
        assert stage.status == "FAILED"
        assert "Validation failed" in stage.error
        assert stage.output == {}

    def test_execution_failure(self):
        """测试执行失败场景"""
        context = WorkflowContext(
            workflow_id="task-003",
            shared_storage_path="/share/workflows/task-003",
            input_params={"input_data": {"input_path": "/share/input.txt"}}
        )

        # 创建一个验证通过但执行失败的执行器
        class FailingExecutor(ConcreteNodeExecutor):
            def validate_input(self):
                self.validate_called = True  # 验证通过

            def execute_core_logic(self):
                self.execute_called = True
                raise RuntimeError("Execution failed")

        executor = FailingExecutor("test.node", context)
        result_context = executor.execute()

        # 验证失败处理
        assert executor.validate_called
        assert executor.execute_called

        stage = result_context.stages["test.node"]
        assert stage.status == "FAILED"
        assert "Execution failed" in stage.error

    def test_minio_url_generation_enabled(self):
        """测试启用 MinIO URL 生成"""
        context = WorkflowContext(
            workflow_id="task-004",
            shared_storage_path="/share/workflows/task-004",
            input_params={
                "input_data": {"input_path": "/share/input.txt"},
                "core": {"auto_upload_to_minio": True}
            }
        )

        executor = ConcreteNodeExecutor("test.node", context)
        result_context = executor.execute()

        stage = result_context.stages["test.node"]
        assert "output_path" in stage.output
        assert "output_path_minio_url" in stage.output

    def test_minio_url_generation_disabled(self):
        """测试禁用 MinIO URL 生成"""
        context = WorkflowContext(
            workflow_id="task-005",
            shared_storage_path="/share/workflows/task-005",
            input_params={
                "input_data": {"input_path": "/share/input.txt"},
                "core": {"auto_upload_to_minio": False}
            }
        )

        executor = ConcreteNodeExecutor("test.node", context)
        result_context = executor.execute()

        stage = result_context.stages["test.node"]
        assert "output_path" in stage.output
        assert "output_path_minio_url" not in stage.output

    def test_get_input_data(self):
        """测试获取输入数据"""
        context = WorkflowContext(
            workflow_id="task-006",
            shared_storage_path="/share/workflows/task-006",
            input_params={
                "input_data": {"key1": "value1", "key2": "value2"}
            }
        )

        executor = ConcreteNodeExecutor("test.node", context)
        input_data = executor.get_input_data()

        assert input_data["key1"] == "value1"
        assert input_data["key2"] == "value2"

    def test_abstract_methods_enforcement(self):
        """测试抽象方法强制实现"""
        # 尝试实例化未实现抽象方法的类应该失败
        with pytest.raises(TypeError):
            class IncompleteExecutor(BaseNodeExecutor):
                pass

            IncompleteExecutor("test.node", MagicMock())

    def test_duration_measurement(self):
        """测试执行时长测量"""
        context = WorkflowContext(
            workflow_id="task-009",
            shared_storage_path="/share/workflows/task-009",
            input_params={"input_data": {}}
        )

        executor = ConcreteNodeExecutor("test.node", context)
        result_context = executor.execute()

        stage = result_context.stages["test.node"]
        assert stage.duration >= 0
        assert isinstance(stage.duration, float)
