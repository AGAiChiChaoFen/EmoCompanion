"""
适配器工厂模块。

提供统一的适配器创建入口，支持通过名称动态切换不同的 LLM 提供商。
可扩展：添加新的适配器只需注册到工厂即可。
"""

from typing import Any, Optional

from .base import BaseLLMAdapter
from .config import init_config, APIConfig


# ---- 适配器注册表 ----
# 添加新提供商时，在此处注册即可。
# 格式: { "provider_name": factory_function }

_registry: dict[str, type[BaseLLMAdapter]] = {}


def register_adapter(name: str, adapter_cls: type[BaseLLMAdapter]) -> None:
    """注册一个适配器类。

    Args:
        name: 提供商名称，如 "openai"、"anthropic"。
        adapter_cls: 适配器类，必须继承 BaseLLMAdapter。
    """
    if not issubclass(adapter_cls, BaseLLMAdapter):
        raise TypeError(f"{adapter_cls} 必须继承 BaseLLMAdapter")
    _registry[name] = adapter_cls


def list_adapters() -> list[str]:
    """列出所有已注册的适配器名称。"""
    return list(_registry.keys())


def create_adapter(
    provider: str = "qwen",
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    enable_thinking: Optional[bool] = None,
    **kwargs: Any,
) -> BaseLLMAdapter:
    """创建 LLM 适配器实例。

    优先使用显式传入的参数，未提供时回退到环境变量 / .env 配置。

    Args:
        provider: 提供商名称，可选 "qwen"（默认）、"openai" 等。
        api_key: API 密钥。未提供则从环境变量读取。
        base_url: API 端点 URL。未提供则从环境变量读取。
        model: 模型名称。未提供则使用 DEFAULT_MODEL 环境变量。
        enable_thinking: 是否启用模型内置思考模式。
                         未提供则从环境变量读取，PersonaVLM 场景建议 False。
        **kwargs: 传递给适配器构造函数的额外参数。

    Returns:
        BaseLLMAdapter 实例。

    Raises:
        ValueError: 缺少必要的 API Key 或提供商不支持。

    Examples:
        # 使用默认配置
        adapter = create_adapter()

        # 切换到 OpenAI GPT-4o
        adapter = create_adapter("openai", model="gpt-4o")

        # 显式传入全部参数
        adapter = create_adapter(
            "qwen",
            api_key="sk-xxx",
            base_url="https://custom-endpoint.com/v1",
            model="qwen3.7-plus",
            enable_thinking=False,
        )
    """
    # 加载全局配置
    config = init_config()

    # 参数优先级：显式传入 > 环境变量 > 默认值
    _api_key = api_key or config.api_key
    _base_url = base_url or config.base_url
    _model = model or config.default_model
    _enable_thinking = (
        enable_thinking
        if enable_thinking is not None
        else config.enable_thinking
    )

    # 根据 provider 构建适配器配置
    if provider != "qwen" and provider.upper() != config.provider.upper():
        # 不同提供商：尝试从环境变量加载其配置
        try:
            provider_config = APIConfig.from_env(provider)
            _api_key = api_key or provider_config.api_key
            _base_url = base_url or provider_config.base_url
            _model = model or provider_config.default_model
            _enable_thinking = (
                enable_thinking
                if enable_thinking is not None
                else provider_config.enable_thinking
            )
        except ValueError:
            # 没有该提供商的专用配置，使用传入参数
            pass

    # 从注册表查找适配器类
    adapter_cls = _registry.get(provider)

    if adapter_cls is None:
        # 尝试动态导入
        if provider == "qwen":
            from .qwen_adapter import QwenAdapter
            adapter_cls = QwenAdapter
        else:
            available = list_adapters() or ["qwen"]
            raise ValueError(
                f"不支持的提供商 '{provider}'，"
                f"当前可用: {available}。"
                f"请先使用 register_adapter() 注册。"
            )

    return adapter_cls(
        api_key=_api_key,
        base_url=_base_url,
        model=_model,
        enable_thinking=_enable_thinking,
        **kwargs,
    )
