"""PersonaVLM 对话请求模型。"""

from pydantic import BaseModel, Field

from src.api.services.persona_agent import USER_ID_PATTERN


class PersonaChatRequest(BaseModel):
    """PersonaVLM 对话请求（JSON 方式）。

    注意：persona 的会话是 sessions[] 的整数索引，与 /emollm 的字符串
    会话 id 语义不同，此处使用 session_index 字段名避免混淆。
    """

    user_id: str = Field(
        ...,
        description="用户标识，将作为记忆与人格的持久化主键",
        pattern=USER_ID_PATTERN.pattern,
    )
    asr: str = Field(
        default="",
        description="音频转写文本",
    )
    emotion: str = Field(
        default="",
        description="音频情绪标签，如 悲伤、孤独",
    )
    face_emotion: str = Field(
        default="中性/平静",
        description="人脸情绪标签",
    )
    new_session: bool = Field(
        default=False,
        description="为 True 时先归纳当前会话并开新会话，本条消息落在新会话",
    )
    session_index: int | None = Field(
        default=None,
        description="继续指定会话（sessions[] 索引，-1 表示最新）。不传则用当前默认会话",
    )
    timestamp: str | None = Field(
        default=None,
        description="消息时间戳，格式 YYYY-MM-DD HH:MM。不传则用服务端当前时间",
    )
