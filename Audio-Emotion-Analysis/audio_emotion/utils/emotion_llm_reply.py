# 情感分析回复处理

from __future__ import annotations

import torch
from typing import Any
from modelscope import AutoTokenizer, AutoModelForCausalLM



DEFAULT_COMPANION_SYSTEM_PROMPT = (
    "你是一位面向老年用户的专属情感陪伴助手。你的目标是提供温暖、自然、像家人一样的心灵支持。\n\n"
    "【角色设定与职责】\n"
    "- 真实自然：像日常聊天一样自然对话，绝对避免机械式的刻板回复。\n"
    "- 敏锐共情：重点关注用户的轻微情绪波动、焦虑或失落倾向，提供坚实的心理支撑。\n"
    "- 倾听为主：不要急于说教或给建议，理解陪伴往往比解决问题更重要。\n\n"
    "【沟通风格与约束】\n"
    "- 语气表达：温暖、真诚、充满尊重，使用中文并运用长辈易于接受的亲切口吻。\n"
    "- 语言习惯：多用陈述句表达理解与认同，提问时要温和自然，避免连续反问给人压迫感。\n"
    "- 安全边界：避免生硬的医疗或心理学诊断词汇。"
)

DEFAULT_MAX_CONTEXT_TOKENS = 128000
DEFAULT_MAX_OUTPUT_TOKENS = 8192
DEFAULT_MAX_HISTORY_ROUNDS = 10


def _build_user_prompt(asr_input: dict[str, str]) -> str:
    """
    根据 ASR 与情绪结果构造用户轮次提示词。

    参数：
        asr_input: 包含 asr、emotion、face_emotion 字段的字典输入。

    返回：
        返回可直接用于聊天模板的用户提示词字符串。
    """
    return (
        "请根据以下用户的语音输入和情绪状态，像家人一样生成一段贴心的回复。\n\n"
        "【输入信息】\n"
        f"- 语音转写：{asr_input['asr']}\n"
        f"- 情绪画像：{asr_input['emotion']}\n\n"
        f"- 人脸情绪：{asr_input.get('face_emotion', '未知')}\n\n"
        "【回复要求】\n"
        "1. 拒绝模板思维：严禁使用死板的“共情->建议->反问”流程，根据当前具体情境灵活回应。\n"
        "2. 情绪适配：\n"
        "   - 若情绪负面：以安抚为主。如需建议，必须极度轻量且无需思考（例如：喝口温水、看看窗外）。\n"
        "   - 若情绪正面/中性：像日常拉家常一样自然接话或顺着话题分享。\n"
        "3. 形式约束：使用口语化表达，但不要老是哎呀。"
    )


def _normalize_history_messages(conversation: list[dict[str, Any]]) -> list[dict[str, str]]:
    """
    规范化历史对话消息，仅保留 user/assistant 文本轮次。

    参数：
        conversation: 原始历史消息列表，可能包含无效字段或非字符串内容。

    返回：
        返回清洗后的消息列表，元素结构固定为：
        {
            "role": "user 或 assistant",
            "content": "文本内容"
        }
    """
    normalized: list[dict[str, str]] = []
    for item in conversation:
        role = str(item.get("role", "")).strip()
        content = item.get("content", "")
        if role not in {"user", "assistant"}:
            continue
        if not isinstance(content, str):
            continue
        content = content.strip()
        if not content:
            continue
        normalized.append({"role": role, "content": content})
    return normalized


def _trim_history_rounds(conversation: list[dict[str, str]], max_rounds: int) -> list[dict[str, str]]:
    """
    按最大轮次数限制裁剪历史消息。

    参数：
        conversation: 仅包含 user/assistant 的历史消息列表。
        max_rounds: 最大保留轮次数（1 轮 = user + assistant）。

    返回：
        返回裁剪后的消息列表，超过上限时自动丢弃最早轮次。
    """
    max_messages = max_rounds * 2
    if max_messages <= 0:
        return []
    if len(conversation) <= max_messages:
        return conversation
    return conversation[-max_messages:]


def _count_prompt_tokens(tokenizer: AutoTokenizer, messages: list[dict[str, str]]) -> int:
    """
    统计当前聊天消息在模型输入端的 token 数量。

    参数：
        tokenizer: EmoLLM 分词器。
        messages: 聊天消息列表，包含 system/user/assistant 轮次。

    返回：
        返回输入 token 数量整数。
    """
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    model_inputs = tokenizer(text, return_tensors="pt")
    return int(model_inputs["input_ids"].shape[1])


def _drop_oldest_round(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """
    从历史消息中移除最早轮次，优先按 user+assistant 配对移除。

    参数：
        messages: 历史消息列表，不含 system 提示。

    返回：
        返回移除最早轮次后的新列表。
    """
    if not messages:
        return messages
    if len(messages) >= 2 and messages[0]["role"] == "user" and messages[1]["role"] == "assistant":
        return messages[2:]
    return messages[1:]


def _fit_history_with_token_budget(
    tokenizer: AutoTokenizer,
    conversation: list[dict[str, str]],
    user_prompt: str,
    max_context_tokens: int,
    max_output_tokens: int,
    max_rounds: int,
) -> tuple[list[dict[str, str]], int]:
    """
    在最大上下文与输出预算下裁剪历史消息，避免上下文溢出。

    参数：
        tokenizer: EmoLLM 分词器。
        conversation: 历史消息列表，仅含 user/assistant。
        user_prompt: 当前轮用户提示词。
        max_context_tokens: 模型最大上下文长度。
        max_output_tokens: 预留最大输出 token 数。
        max_rounds: 最大历史轮次数。

    返回：
        返回二元组：
        {
            "第一个元素": 可用历史消息列表（已按轮次和 token 预算裁剪）, 
            "第二个元素": 当前构造消息的输入 token 数
        }
    """
    budget = max(1024, max_context_tokens - max_output_tokens)
    history = _trim_history_rounds(conversation, max_rounds)

    while True:
        candidate_messages = [
            {"role": "system", "content": DEFAULT_COMPANION_SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": user_prompt},
        ]
        prompt_tokens = _count_prompt_tokens(tokenizer, candidate_messages)
        if prompt_tokens <= budget:
            return history, prompt_tokens
        if not history:
            return [], prompt_tokens
        history = _drop_oldest_round(history)



def _resolve_input_device(model: AutoModelForCausalLM) -> torch.device:
    """
    根据模型的 device_map 自动推断输入数据应该放在哪个设备上。
    优先使用模型的 hf_device_map 中的设备（如果存在且有效），否则根据当前环境自动选择 CUDA 或 CPU。
    """
    if hasattr(model, "hf_device_map"):
        for mapped_device in model.hf_device_map.values():
            if isinstance(mapped_device, str) and mapped_device not in {"cpu", "disk", "meta"}:
                return torch.device(mapped_device)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")



async def emollm_reply(
    asr_input: dict[str, str],
    *args,
    emollm_model: torch.nn.Module,
    emollm_tokenizer: AutoTokenizer,
    **kwargs,
) -> str:
    """
    使用情感分析模型生成回复文本。

    参数:
        asr_input: 包含ASR结果的字典，
        *args: 其他位置参数，传递给模型生成函数
        emollm_model: 已加载的情感分析模型
        emollm_tokenizer: 已加载的情感分析分词器
        **kwargs: 其他关键字参数，传递给模型生成函数

    返回:
        模型生成的回复文本
    """
    # 验证输入格式
    if "asr" not in asr_input or "emotion" not in asr_input:
        raise ValueError("asr_input必须包含'asr'和'emotion'键")
    

    user_prompt = _build_user_prompt(asr_input)

    messages = [
        {"role": "system", "content": DEFAULT_COMPANION_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    
    model, tokenizer = emollm_model, emollm_tokenizer

    text = tokenizer.apply_chat_template(
        messages, tokenize=False,
        add_generation_prompt=True
    )
    
    model_inputs = tokenizer(
        text,
        return_tensors="pt"
    )

    input_device = _resolve_input_device(model)
    model_inputs = {
        key: value.to(input_device) if hasattr(value, "to") else value
        for key, value in model_inputs.items()
    }

    with torch.inference_mode():
        output_ids = model.generate(**model_inputs, max_new_tokens=256)

    prompt_len = model_inputs["input_ids"].shape[1]
    output_ids = output_ids[:, prompt_len:]
    reply = tokenizer.batch_decode(output_ids, skip_special_tokens=True)[0].strip()

    return reply or "我在这儿陪着您，愿意和我再慢慢说说刚刚让您在意的事吗？"


async def emollm_reply_with_memory(
    asr_input: dict[str, str],
    conversation: list[dict[str, Any]],
    *args,
    emollm_model: torch.nn.Module,
    emollm_tokenizer: AutoTokenizer,
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    max_rounds: int = DEFAULT_MAX_HISTORY_ROUNDS,
    **kwargs,
) -> dict[str, Any]:
    """
    使用带上下文记忆的方式生成陪护回复，并返回更新后的历史消息。

    参数：
        asr_input: 包含 asr ，emotion，face_emotion 字段的输入字典。
        conversation: 历史对话消息列表，仅记录 user/assistant 内容。
        *args: 其他位置参数，保留兼容扩展。
        emollm_model: 已加载的 EmoLLM 模型。
        emollm_tokenizer: 已加载的 EmoLLM 分词器。
        max_context_tokens: 上下文最大 token 限制，默认 128000。
        max_output_tokens: 预留最大输出 token 数，默认 8192。
        max_rounds: 最大保留历史轮次数，默认 10。
        **kwargs: 其他关键字参数，保留兼容扩展。

    返回：
        返回结果字典，结构为：
        {
            "reply": "当前轮生成回复",
            "conversation": [
                {"role": "user", "content": "语音转写+情绪画像+人脸情绪"},
                {"role": "assistant", "content": "..."}
            ],
            "prompt_tokens": "本轮输入 token 数",
            "token_budget": "本轮可用输入预算"
        }
    """
    if "asr" not in asr_input or "emotion" not in asr_input:
        raise ValueError("asr_input必须包含'asr'和'emotion'键")

    model, tokenizer = emollm_model, emollm_tokenizer
    # user_prompt = _build_user_prompt(asr_input)

    asr_text = str(asr_input.get("asr", "")).strip()
    emotion_text = str(asr_input.get("emotion", "")).strip()
    face_emotion_text = str(asr_input.get("face_emotion", "未知")).strip()
    if not asr_text:
        asr_text = "（未识别到清晰语音内容）"
    if not emotion_text:
        emotion_text = "未知"
    if not face_emotion_text:
        face_emotion_text = "未知"
    user_memory_content = (
        f"用户输入：{asr_text}\n"
        f"情绪画像：{emotion_text}\n"
        f"人脸情绪：{face_emotion_text}"
    )

    user_input = asr_text

    normalized_history = _normalize_history_messages(conversation)
    fitted_history, prompt_tokens = _fit_history_with_token_budget(
        tokenizer=tokenizer,
        conversation=normalized_history,
        user_prompt=user_input,
        max_context_tokens=max_context_tokens,
        max_output_tokens=max_output_tokens,
        max_rounds=max_rounds,
    )

    messages = [
        {"role": "system", "content": DEFAULT_COMPANION_SYSTEM_PROMPT},
        *fitted_history,
        {"role": "user", "content": user_input},
    ]
    print("构造的消息列表：", messages)
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    model_inputs = tokenizer(text, return_tensors="pt")
    input_device = _resolve_input_device(model)
    model_inputs = {
        key: value.to(input_device) if hasattr(value, "to") else value
        for key, value in model_inputs.items()
    }

    with torch.inference_mode():
        output_ids = model.generate(**model_inputs, max_new_tokens=max_output_tokens)

    prompt_len = model_inputs["input_ids"].shape[1]
    output_ids = output_ids[:, prompt_len:]
    reply = tokenizer.batch_decode(output_ids, skip_special_tokens=True)[0].strip()
    if not reply:
        reply = "我在这儿陪着您，愿意和我再慢慢说说刚刚让您在意的事吗？"

    updated_conversation = [
        *fitted_history,
        {"role": "user", "content": user_memory_content},
        {"role": "assistant", "content": reply},
    ]
    updated_conversation = _trim_history_rounds(updated_conversation, max_rounds=max_rounds)

    return {
        "reply": reply,
        "conversation": updated_conversation,
        "prompt_tokens": prompt_tokens,
        "token_budget": max(1024, max_context_tokens - max_output_tokens),
    }


        