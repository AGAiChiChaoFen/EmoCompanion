from pydantic import BaseModel, Field
from typing import Optional

class TTSInputRequest(BaseModel):
    """
    文本转语音请求模型。
    """
    text: str = Field(..., description="待转换的文本内容")