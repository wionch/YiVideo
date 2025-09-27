# services/workers/llm_service/app/tasks.py
import os

from services.common.logger import get_logger

logger = get_logger('tasks')
import json
import logging
from typing import Any
from typing import Dict
from typing import Optional

import requests
import yaml
from celery import Celery
from celery import Task

from services.common import state_manager

# 导入标准上下文
from services.common.context import StageExecution
from services.common.context import WorkflowContext

# --- 日志配置 ---
# 日志已统一管理，使用 services.common.logger

# --- 配置加载 ---
CONFIG = {}

def load_config():
    """在worker启动时加载主配置文件。"""
    global CONFIG
    config_path = os.path.join(os.path.dirname(__file__), '..\/..\/..\/config.yml')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            CONFIG = yaml.safe_load(f)
        logger.info("LLM Service: 主配置文件加载成功。")
    except Exception as e:
        logger.error(f"LLM Service: 加载配置文件时出错: {e}")

# --- LLM API 客户端 ---

class LLMClient:
    """一个用于调用不同LLM Provider API的通用客户端。"""
    def __init__(self, provider_name: str, config: Dict[str, Any]):
        self.provider_name = provider_name
        self.api_key = config.get('api_key')
        self.api_base_url = config.get('api_base_url')
        if not self.api_key or not self.api_base_url:
            raise ValueError(f"LLM提供商 '{provider_name}' 的配置不完整 (缺少api_key或api_base_url)。")

    def generate(self, prompt: str) -> str:
        """根据不同的提供商，调用相应的API生成内容。"""
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }
        
        if self.provider_name == 'gemini':
            url = f"{self.api_base_url}?key={self.api_key}"
            headers.pop('Authorization')
            payload = {'contents': [{'parts': [{'text': prompt}]}]}
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            return response.json()['candidates'][0]['content']['parts'][0]['text']

        elif self.provider_name == 'deepseek':
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ]
            }
            response = requests.post(self.api_base_url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            return response.json()['choices'][0]['message']['content']
        
        else:
            raise NotImplementedError(f"LLM提供商 '{self.provider_name}' 的实现未找到。")

# --- Celery App & 任务定义 ---

celery_app = Celery(
    'llm_tasks',
    broker=os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0'),
    backend=os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/1'),
    include=['app.tasks']
)
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

LLM_CLIENTS: Dict[str, LLMClient] = {}

@celery_app.on_after_configure.connect
def setup_llm_clients(sender, **kwargs):
    """Celery worker启动后执行，初始化所有LLM客户端。"""
    load_config()
    llm_config = CONFIG.get('llm_service', {})
    providers = llm_config.get('providers', {})
    for name, provider_config in providers.items():
        try:
            if provider_config.get('api_key'): # 只初始化配置了API Key的客户端
                LLM_CLIENTS[name] = LLMClient(name, provider_config)
                logger.info(f"成功初始化LLM客户端: {name}")
        except ValueError as e:
            logger.warning(f"初始化LLM客户端 '{name}' 失败: {e}")

def _find_input_file_from_previous_stage(self: Task, context: WorkflowContext) -> Optional[str]:
    """在工作流中动态查找上一个阶段的输出文件作为本阶段的输入。"""
    try:
        workflow_chain = context.input_params['workflow_chain']
        current_index = workflow_chain.index(self.name)
        if current_index == 0:
            return None

        previous_stage_name = workflow_chain[current_index - 1]
        previous_stage_output = context.stages[previous_stage_name]['output']

        for key, value in previous_stage_output.items():
            if isinstance(value, str) and ('_file' in key or '_path' in key):
                if os.path.exists(value):
                    logger.info(f"从上一阶段 '{previous_stage_name}' 找到输入文件: {value}")
                    return value
    except (KeyError, ValueError, IndexError) as e:
        logger.warning(f"无法从上一阶段动态确定输入文件: {e}")
    return None

@celery_app.task(bind=True, name='llm.process_text')
def process_text(self: Task, context: dict) -> dict:
    """通用文本处理任务，可用于校对、翻译等。"""
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        params = workflow_context.input_params.get('llm_params', {})
        
        # 动态地从上一个阶段寻找输入文件
        input_file = _find_input_file_from_previous_stage(self, workflow_context)
        if not input_file:
            # 如果动态查找失败，则回退到从参数中直接指定
            input_file = params.get('input_file')

        if not input_file or not os.path.exists(input_file):
            raise FileNotFoundError(f"输入文件未提供或不存在: {input_file}")

        action = params.get('action', 'proofread')
        provider = params.get('provider', CONFIG.get('llm_service', {}).get('default_provider'))
        prompt_template = params.get('prompt')

        if not provider or provider not in LLM_CLIENTS:
            raise ValueError(f"指定的LLM提供商 '{provider}' 不可用或未配置API Key。")
        if not prompt_template:
            raise ValueError("必须在llm_params中提供 'prompt' 模板。")

        with open(input_file, 'r', encoding='utf-8') as f:
            text_content = f.read()

        prompt = prompt_template.format(text=text_content)

        logger.info(f"[{stage_name}] 开始使用 '{provider}' 执行 '{action}' 操作...")
        client = LLM_CLIENTS[provider]
        processed_text = client.generate(prompt)

        output_filename = f"{os.path.splitext(os.path.basename(input_file))[0]}_{action}.txt"
        output_file = os.path.join(workflow_context.shared_storage_path, output_filename)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(processed_text)
        logger.info(f"[{stage_name}] 操作完成，结果已保存至: {output_file}")

        output_data = {"output_file": output_file, "provider": provider}
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data
        
    except Exception as e:
        logger.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)
        workflow_context.error = f"在阶段 {stage_name} 发生错误: {e}"

    state_manager.update_workflow_state(workflow_context)
    return workflow_context.dict()
