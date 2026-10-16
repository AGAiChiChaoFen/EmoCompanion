# 音频TTS合成

from __future__ import annotations
from pathlib import Path

import torch
import soundfile as sf

from .output_path import unique_output_path



async def audio_tts(
    text_input: str,
    *args,
    qwen_tts_model: torch.nn.Module,
    **kwargs,
) -> Path:
    """
    使用 Qwen TTS 模型将文本合成为音频数据。

    参数:
        text_input: 输入文本字符串
        *args: 其他位置参数，传递给模型生成函数
        qwen_tts_model: 已加载的 Qwen TTS 模型
        **kwargs: 其他关键字参数，传递给模型生成函数
    返回:
        合成的音频数据，保存到 audio_emotion/output 目录内并返回文件路径
    """
    # 验证输入格式
    if not isinstance(text_input, str):
        raise ValueError("text_input必须是字符串类型")
    
    model = qwen_tts_model
    
    wavs, sr = model.generate_custom_voice(
        text=text_input,
        language="Chinese",
        speaker="Vivian",
        instruct="用温柔的语气说", 
    )

    # 生成唯一输出文件路径
    output_path = unique_output_path(prefix="tts_output_", ext=".wav")

    # 保存音频数据到文件
    sf.write(output_path, wavs[0], sr)

    return Path(output_path)

    