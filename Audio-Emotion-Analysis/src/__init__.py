"""
PersonaVLM 第三方 API 适配器包。

提供统一的 LLM 适配器接口，支持：
    - Qwen3.7-Plus（阿里云百炼）
    - 可扩展至 OpenAI、Anthropic 等任意提供商

核心组件:
    - BaseLLMAdapter:  抽象基类，定义适配器接口
    - QwenAdapter:     Qwen3.7-Plus 具体实现
    - create_adapter:  工厂函数，按名称创建适配器
    - init_config:     配置加载（.env + CSV）

基本用法:
    from src import create_adapter

    # 使用默认 Qwen 配置
    adapter = create_adapter()

    # 接入 PersonaVLM Agent
    from PersonaVLM import PersonaVLMAgent
    agent = PersonaVLMAgent.PersonaVLM(user_config, agent_model=adapter)

    # 异步使用
    response = await adapter.asend_message(
        adapter.prepare_input("你好！")
    )
"""

from .base import BaseLLMAdapter
from .qwen_adapter import QwenAdapter
from .factory import create_adapter, register_adapter, list_adapters
from .config import init_config, APIConfig, load_dotenv, load_csv_config

__all__ = [
    # 核心接口
    "BaseLLMAdapter",
    "QwenAdapter",
    # 工厂
    "create_adapter",
    "register_adapter",
    "list_adapters",
    # 配置
    "init_config",
    "APIConfig",
    "load_dotenv",
    "load_csv_config",
]
