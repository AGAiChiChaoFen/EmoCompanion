# 音频 ASR 转写与情感分析

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

import torch
import librosa
from modelscope import AutoProcessor
from transformers import Qwen2AudioForConditionalGeneration



DEFAULT_ANALYSIS_PROMPT = (
    "请先给出音频中的完整中文转写，再判断整体情绪。"
    "仅输出 JSON 的回答，且格式必须严格为: "
    '{"asr":"...","emotion":"..."}'
)



def _parse_analysis_response(response_text: str) -> dict[str, str]:
    """
    将模型原始文本解析为包含 asr 与 emotion 的标准字典。

    参数：
        response_text: 模型原始输出文本。可能是标准 JSON、Python 字典字符串，
            或被代码块包裹、夹杂前后缀文本的非纯净内容。

    返回：
        返回结构化结果字典，固定包含以下字段：
        {
            "asr": "音频转写文本，解析失败时可能为空字符串",
            "emotion": "情绪标签，解析失败时默认返回'未知'",
        }
    """
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]

    parsed: dict[str, Any]
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(cleaned)
        except (ValueError, SyntaxError):
            asr_match = re.search(r'"asr"\s*:\s*"(.*?)"', cleaned)
            emotion_match = re.search(r'"emotion"\s*:\s*"(.*?)"', cleaned)
            return {
                "asr": (asr_match.group(1) if asr_match else "").strip(),
                "emotion": (emotion_match.group(1) if emotion_match else "未知").strip(),
            }

    return {
        "asr": str(parsed.get("asr", "")).strip(),
        "emotion": str(parsed.get("emotion", "未知")).strip(),
    }



def _resolve_input_device(model: Qwen2AudioForConditionalGeneration) -> torch.device:
    """
    根据模型的 device_map 自动推断输入数据应该放在哪个设备上。
    优先使用模型的 hf_device_map 中的设备（如果存在且有效），否则根据当前环境自动选择 CUDA 或 CPU。
    """
    if hasattr(model, "hf_device_map"):
        for mapped_device in model.hf_device_map.values():
            if isinstance(mapped_device, str) and mapped_device not in {"cpu", "disk", "meta"}:
                return torch.device(mapped_device)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")



async def analysis_audio_with_path(
    audio_path: Path, 
    *args,
    audio_model: torch.nn.Module, 
    audio_processor: AutoProcessor,
    **kwargs,
) -> dict[str, str]:
    """
    对输入的音频文件进行 ASR 转写和情感分析。

    参数:
        audio_path: 输入音频文件的路径
        *args: 其他位置参数，传递给模型分析函数
        audio_model: 已加载的音频分析模型
        audio_processor: 已加载的音频处理器
        **kwargs: 其他关键字参数，传递给模型分析函数

    返回:
        包含转写文本和情感分析结果的字典
    """
    # 验证音频文件存在
    if not audio_path.exists():
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")
    
    model, processor = audio_model, audio_processor

    audio_input, _ = librosa.load(audio_path, sr=processor.feature_extractor.sampling_rate)

    conversation: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": "你是一名专业的音频内容与情绪分析助手。请始终使用中文回答。",
        },
        {
            "role": "user",
            "content": [
                {"type": "audio", "audio_url": str(audio_path)},
                {
                    "type": "text",
                    "text": DEFAULT_ANALYSIS_PROMPT,
                },
            ],
        },
    ]

    text = processor.apply_chat_template(
        conversation,
        add_generation_prompt=True,
        tokenize=False,
    )

    inputs = processor(
        text=text,
        audio=audio_input,
        sampling_rate=processor.feature_extractor.sampling_rate,
        return_tensors="pt",
        padding=True,
    )

    
    input_device = _resolve_input_device(model)
    model_inputs = {
        key: value.to(input_device) if hasattr(value, "to") else value
        for key, value in inputs.items()
    }

    with torch.inference_mode():
        generated = model.generate(**model_inputs, max_new_tokens=256)

    prompt_len = model_inputs["input_ids"].shape[1]
    generated = generated[:, prompt_len:]

    raw_response = processor.batch_decode(
        generated,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0].strip()

    return _parse_analysis_response(raw_response)