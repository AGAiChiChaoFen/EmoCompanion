"""
Qwen3.7-Plus 适配器。

通过阿里云百炼平台的 OpenAI 兼容接口调用 Qwen3.7-Plus 多模态模型。
同时提供同步（供 PersonaVLM 使用）和异步 API。
"""

import logging
from typing import Any, Callable, Optional

from .base import BaseLLMAdapter
from .utils import encode_image_to_base64, count_img_fill, strip_img_fill

logger = logging.getLogger(__name__)


class QwenAdapter(BaseLLMAdapter):
    """Qwen3.7-Plus 适配器，通过 OpenAI 兼容接口访问。

    使用方法:
        # 方式一：直接创建
        adapter = QwenAdapter(
            api_key="sk-xxx",
            base_url="https://ws-xxx.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
            model="qwen3.7-plus",
        )

        # 方式二：通过工厂创建
        adapter = create_adapter("qwen")
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model: str = "qwen3.7-plus",
        enable_thinking: bool = False,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        timeout: float = 120.0,
    ):
        """初始化 Qwen 适配器。

        Args:
            api_key: 阿里云百炼 API Key。
            base_url: OpenAI 兼容端点 URL。
            model: 模型名称，默认 qwen3.7-plus。
            enable_thinking: 是否启用模型内置思考模式。
                            PersonaVLM 场景下应保持 False。
            max_tokens: 最大生成 token 数。
            temperature: 采样温度。
            timeout: API 请求超时时间（秒）。
        """
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._enable_thinking = enable_thinking
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout = timeout

        self._conversation_history: list[dict] = []

        # 延迟初始化客户端
        self._sync_client: Any = None
        self._async_client: Any = None

    # ---- 元信息 ----

    @property
    def provider_name(self) -> str:
        return "qwen"

    @property
    def model_name(self) -> str:
        return self._model

    # ---- 客户端懒加载 ----

    def _get_sync_client(self):
        """获取同步 OpenAI 客户端（懒加载）。"""
        if self._sync_client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError(
                    "使用 QwenAdapter 需要安装 openai 库。"
                    "请运行: uv pip install openai"
                )
            self._sync_client = OpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._sync_client

    def _get_async_client(self):
        """获取异步 OpenAI 客户端（懒加载）。"""
        if self._async_client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError(
                    "使用 QwenAdapter 异步 API 需要安装 openai 库。"
                    "请运行: uv pip install openai"
                )
            self._async_client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._async_client

    # ---- 同步 API ----

    def prepare_input(self, prompt: str, imgs: Optional[list[str]] = None) -> list[dict]:
        """将 PersonaVLM prompt 转换为 OpenAI 多模态消息格式。

        将 <img_fill> 占位符替换为 base64 编码的图片，
        构建 OpenAI chat completions 可接受的 content 数组。

        Args:
            prompt: 包含 <img_fill> 的 prompt 文本。
            imgs: 图片文件路径列表。

        Returns:
            OpenAI 格式的 content 列表，可直接作为 message['content']。
        """
        imgs = imgs or []
        n_fill = count_img_fill(prompt)
        n_imgs = len(imgs)

        if n_fill != n_imgs:
            logger.warning(
                f"<img_fill> 数量 ({n_fill}) 与图片数量 ({n_imgs}) 不一致，"
                f"将以图片数量为准"
            )

        content: list[dict] = []

        # 图片放在前面（与 PersonaVLM 原有行为一致）
        for img_path in imgs:
            data_uri = encode_image_to_base64(img_path)
            content.append({
                "type": "image_url",
                "image_url": {"url": data_uri},
            })

        # 文本内容（移除 <img_fill> 占位符）
        text = strip_img_fill(prompt)
        content.append({"type": "text", "text": text})

        return content

    def send_message(self, message: list[dict], clear: bool = True) -> str:
        """同步发送消息。

        Args:
            message: prepare_input 返回的 content 列表。
            clear: 调用后是否清空对话历史。

        Returns:
            模型的文本回复。
        """
        client = self._get_sync_client()

        # 构建请求
        self._conversation_history.append({
            "role": "user",
            "content": message,
        })

        extra_body = {"enable_thinking": self._enable_thinking}

        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=self._conversation_history,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                extra_body=extra_body,
            )
            text = response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"API 调用失败: {e}")
            raise

        if clear:
            self.clear_conversation_history()
        else:
            # 将助手回复加入历史（仅在不清除时）
            self._conversation_history.append({
                "role": "assistant",
                "content": text,
            })

        return text

    def send_message_stream(
        self, message: list[dict], clear: bool = True,
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> str:
        """同步流式发送：stream=True，逐 token 回调 on_chunk。

        Args:
            message: prepare_input 返回的 content 列表。
            clear: 调用后是否清空对话历史。
            on_chunk: 每收到一段增量文本就回调一次（delta.content 为空时跳过）。

        Returns:
            模型的完整文本回复。
        """
        client = self._get_sync_client()

        self._conversation_history.append({
            "role": "user",
            "content": message,
        })

        extra_body = {"enable_thinking": self._enable_thinking}

        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=self._conversation_history,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                extra_body=extra_body,
                stream=True,
            )
            parts: list[str] = []
            for chunk in response:
                if not chunk.choices:  # usage 等元信息块无 choices
                    continue
                delta = chunk.choices[0].delta
                text = getattr(delta, "content", None) or ""
                if text:
                    parts.append(text)
                    if on_chunk is not None:
                        on_chunk(text)
            text = "".join(parts)
        except Exception as e:
            logger.error(f"API 调用失败: {e}")
            raise

        if clear:
            self.clear_conversation_history()
        else:
            self._conversation_history.append({
                "role": "assistant",
                "content": text,
            })

        return text

    def clear_conversation_history(self) -> None:
        """清空对话历史。"""
        self._conversation_history.clear()

    # ---- 异步 API ----

    async def asend_message(self, message: list[dict], clear: bool = True) -> str:
        """异步发送消息。

        Args:
            message: prepare_input 返回的 content 列表。
            clear: 调用后是否清空对话历史。

        Returns:
            模型的文本回复。
        """
        client = self._get_async_client()

        self._conversation_history.append({
            "role": "user",
            "content": message,
        })

        extra_body = {"enable_thinking": self._enable_thinking}

        try:
            response = await client.chat.completions.create(
                model=self._model,
                messages=self._conversation_history,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                extra_body=extra_body,
            )
            text = response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"异步 API 调用失败: {e}")
            raise

        if clear:
            await self.aclear_conversation_history()
        else:
            self._conversation_history.append({
                "role": "assistant",
                "content": text,
            })

        return text

    async def aclear_conversation_history(self) -> None:
        """异步清空对话历史。"""
        self._conversation_history.clear()

    # ---- 便捷方法 ----

    def __repr__(self) -> str:
        return (
            f"QwenAdapter(model={self._model!r}, "
            f"base_url={self._base_url!r}, "
            f"thinking={self._enable_thinking})"
        )
