"""
LLM 适配器抽象基类。

定义所有第三方 API 适配器必须实现的接口。
子类需同时提供同步和异步两套 API。
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional


class BaseLLMAdapter(ABC):
    """LLM 适配器抽象基类。

    每个具体的适配器（如 QwenAdapter、OpenAIAdapter）必须实现此类。
    设计原则：
        - 同步方法用于兼容 PersonaVLM 现有代码
        - 异步方法用于现代异步应用
        - prepare_input 是纯 CPU 操作，同步即可
    """

    # ---- 元信息 ----

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """提供商名称，如 'qwen'、'openai'。"""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """当前使用的模型名称，如 'qwen3.7-plus'。"""
        ...

    # ---- 同步 API（PersonaVLM 框架调用） ----

    @abstractmethod
    def prepare_input(self, prompt: str, imgs: Optional[list[str]] = None) -> Any:
        """将 PersonaVLM 的 prompt 和图片路径转换为 API 所需的消息格式。

        PersonaVLM 的 prompt 中使用 <img_fill> 作为图片占位符，
        适配器需要将其转换为对应 API 支持的格式（如 base64 data URI 或 URL）。

        Args:
            prompt: 包含 <img_fill> 占位符的文本 prompt。
            imgs: 图片文件路径列表，数量应与 <img_fill> 数量一致。

        Returns:
            API 可接受的消息格式（具体类型由适配器决定）。
        """
        ...

    @abstractmethod
    def send_message(self, message: Any, clear: bool = True) -> str:
        """同步发送消息并获取回复。

        Args:
            message: prepare_input 返回的消息格式。
            clear: 是否在获取回复后清空对话历史。

        Returns:
            模型的文本回复。
        """
        ...

    def send_message_stream(
        self, message: Any, clear: bool = True,
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> str:
        """同步流式发送消息。

        默认实现回退到非流式 send_message（单块回调）；支持流式的
        子类应覆写为逐 token 回调。返回完整文本（与非流式同契约）。

        Args:
            message: prepare_input 返回的消息格式。
            clear: 是否在获取回复后清空对话历史。
            on_chunk: 每收到一段文本就回调一次（可为 None）。

        Returns:
            模型的完整文本回复。
        """
        text = self.send_message(message, clear=clear)
        if on_chunk is not None:
            on_chunk(text)
        return text

    @abstractmethod
    def clear_conversation_history(self) -> None:
        """清空当前对话历史。"""
        ...

    # ---- 异步 API（现代应用使用） ----

    async def asend_message(self, message: Any, clear: bool = True) -> str:
        """异步发送消息并获取回复。

        默认实现回退到同步方法，子类应覆写为真正的异步实现。

        Args:
            message: prepare_input 返回的消息格式。
            clear: 是否在获取回复后清空对话历史。

        Returns:
            模型的文本回复。
        """
        return self.send_message(message, clear=clear)

    async def aclear_conversation_history(self) -> None:
        """异步清空当前对话历史。

        默认实现回退到同步方法。
        """
        self.clear_conversation_history()
