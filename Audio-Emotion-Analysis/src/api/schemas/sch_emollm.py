"""陪护回复请求模型（EmoLLM 本地后端 / PersonaVLM 云端后端）。

注意：EmoLLM 已暂停使用（对话服务统一走 PersonaVLM），本文件不再被
main.py 引用，保留供恢复时使用。
"""

from typing import Literal

from pydantic import BaseModel, Field

from src.api.services.persona_agent import USER_ID_PATTERN


class EmoLLMInputRequest(BaseModel):
    asr: str = Field(..., description="音频转写文本")
    emotion: str = Field(..., description="音频情绪标签")
    face_emotion: str = Field("中性/平静", description="人脸情绪标签")
    session_id: str = Field("default", description="会话标识符（仅本地 EmoLLM 后端使用）")
    provider: Literal["persona", "emollm", "auto"] = Field(
        "auto",
        description="回复后端：persona 走 PersonaVLM 云端，emollm 走本地模型，auto 优先 persona 失败回退 emollm",
    )
    user_id: str = Field(
        "default",
        description="PersonaVLM 用户标识（provider 为 persona/auto 时使用）",
        pattern=USER_ID_PATTERN.pattern,
    )
