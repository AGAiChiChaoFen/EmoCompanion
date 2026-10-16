"""PersonaVLM Agent 生命周期管理（本项目集成层）。

按 user_id 缓存 PersonaVLM Agent 实例，保证同一用户的多次请求复用
同一实例，保持记忆和人格的连续性；不同用户之间完全隔离。
数据持久化到项目根 output/{user_id}/user_data.json。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from src import create_adapter
from src.streaming import StreamEmitter
from PersonaVLM import PersonaVLMAgent


# 用户数据根目录（绝对路径，与进程 CWD 无关）
_OUTPUT_ROOT = Path(__file__).resolve().parents[3] / "output"

# 用户标识格式：字母数字下划线连字符，长度 1-64。
# 用于防止 user_id 直接拼进 output/{user_id} 路径（目录穿越）。
USER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class UserConfig:
    """PersonaVLM Agent 的用户配置适配器。"""

    def __init__(self, user_id: str, name: str, profile: dict[str, str]):
        self.USER_NAME = name
        self.DATA_STORAGE_PATH = _OUTPUT_ROOT / user_id
        self.PROFILE = profile


def compose_persona_query(asr: str, emotion: str, face_emotion: str) -> str:
    """
    将音频转写与情绪画像组装为 PersonaVLM 的 query 文本。

    参数：
        asr: 音频转写文本，为空时兜底为"（未识别到清晰语音内容）"。
        emotion: 音频情绪标签，为空时兜底为"未知"。
        face_emotion: 人脸情绪标签，为空时兜底为"未知"。

    返回：
        组装后的 query 字符串，结构为：
        "用户语音转写：{asr}
         情绪画像：{emotion}
         人脸情绪：{face_emotion}
         请以家人身份用简体中文温暖回应。"
    """
    asr_text = str(asr or "").strip() or "（未识别到清晰语音内容）"
    emotion_text = str(emotion or "").strip() or "未知"
    face_emotion_text = str(face_emotion or "").strip() or "未知"
    return (
        f"用户语音转写：{asr_text}\n"
        f"情绪画像：{emotion_text}\n"
        f"人脸情绪：{face_emotion_text}\n"
        "请以家人身份用简体中文温暖回应。"
    )


class PersonaAgentManager:
    """管理 PersonaVLM Agent 实例的生命周期。

    按 user_id 缓存 Agent 实例并维护每用户 asyncio.Lock，保证同一用户的
    请求串行处理（状态读写与 user_data.json 落盘互斥）；不同用户并行。
    Agent 的推理为同步阻塞（每轮 3-5 次 LLM 往返），调用方必须经
    asyncio.to_thread 执行，避免阻塞事件循环。
    """

    def __init__(self, adapter=None):
        self._agents: dict[str, PersonaVLMAgent.PersonaVLM] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._adapter = adapter  # 可注入（测试用 FakeAdapter）；None 时懒加载 create_adapter()

    def _get_lock(self, user_id: str) -> asyncio.Lock:
        """获取或创建用户级别的锁，保证同一用户串行处理。"""
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]

    def _get_or_create_agent(
        self, user_id: str, name: str = "", profile: dict[str, str] | None = None
    ) -> PersonaVLMAgent.PersonaVLM:
        """从缓存获取或新建 Agent 实例。

        参数：
            user_id: 用户标识。
            name: 新建用户时的名称。
            profile: 新建用户时的初始画像。

        返回：
            PersonaVLM Agent 实例。优先复用缓存；磁盘已有 user_data.json
            时从该文件恢复用户信息，否则新建并立即落盘。
        """
        if user_id in self._agents:
            return self._agents[user_id]

        data_path = _OUTPUT_ROOT / user_id / "user_data.json"
        if data_path.exists():
            with open(data_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            init_profile = saved.get("init_profile", {})
            name = init_profile.get("name", user_id)
            profile = {k: v for k, v in init_profile.items() if k != "name"}
        else:
            name = name or user_id
            profile = profile or {}

        config = UserConfig(user_id, name, profile)
        # 注意：源项目此处无条件 create_adapter() 导致注入的 adapter 失效，
        # 本项目修复为优先使用注入的适配器（测试与自定义后端依赖此行为）。
        adapter = self._adapter or create_adapter()

        agent = PersonaVLMAgent.PersonaVLM(
            config,
            agent_model=adapter,
            force_retrieve=False,
            reasoning_mode=True,
        )
        self._agents[user_id] = agent
        # 新建用户立即落盘，保证只读接口在首轮对话前就能读到用户数据
        agent.update()
        return agent

    async def send_message(
        self,
        user_id: str,
        query: str,
        timestamp: str | None = None,
        new_session: bool = False,
        session_index: int | None = None,
    ) -> dict[str, Any]:
        """发送消息给指定用户的 Agent。

        参数：
            user_id: 用户标识。
            query: 已组装好情绪画像的用户消息文本。
            timestamp: 消息时间戳，格式 "YYYY-MM-DD HH:MM"，为空用服务端当前时间。
            new_session: 为 True 时先归纳当前会话并开新会话，本条消息落在新会话。
            session_index: 继续指定会话（sessions[] 索引，-1 表示最新），不传用默认会话。

        返回：
            返回结果字典，结构为：
            {
                "response": 回复文本,
                "remembering": 记忆信息字典或 None,
                "reasoning": 推理链步骤列表,
                "alignment": 大五人格分数字典,
            }
        """
        lock = self._get_lock(user_id)
        async with lock:
            agent = await asyncio.to_thread(self._get_or_create_agent, user_id)

            ts = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M")
            payload = {"query": query, "time": ts}

            # Agent 推理为同步阻塞（3-5 次 LLM 往返），必须在线程池执行
            response, personality_info, reasoning_chain = await asyncio.to_thread(
                agent.send_message,
                payload,
                personality_input=None,
                return_response_only=False,
                new_session=new_session,
                session_id=session_index,
            )
            return self._compose_result(agent, response, personality_info, reasoning_chain)

    async def stream_chat(
        self,
        user_id: str,
        query: str,
        timestamp: str | None = None,
        new_session: bool = False,
        session_index: int | None = None,
    ):
        """流式对话：产出 {type, ...} 事件序列。

        事件类型：think_chunk（推理增量）/ step（推理链单步）/ answer_chunk
        （回复增量）/ done（完成，data 与 send_message 返回结构一致）/
        error（失败）。Agent 同步逻辑跑在线程中，chunk 经
        call_soon_threadsafe 投递到 asyncio.Queue 后由本生成器按序 yield。

        参数：
            user_id: 用户标识。
            query: 已组装好情绪画像的用户消息文本。
            timestamp: 消息时间戳，格式 "YYYY-MM-DD HH:MM"，为空用服务端当前时间。
            new_session: 为 True 时先归纳当前会话并开新会话。
            session_index: 继续指定会话（sessions[] 索引，-1 表示最新）。

        返回：
            异步生成器，逐条产出事件字典（含 type 字段）。
        """
        lock = self._get_lock(user_id)
        async with lock:
            agent = await asyncio.to_thread(self._get_or_create_agent, user_id)

            ts = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M")
            payload = {"query": query, "time": ts}

            loop = asyncio.get_running_loop()
            queue: asyncio.Queue = asyncio.Queue()

            def emit_think(step: int, delta: str) -> None:
                loop.call_soon_threadsafe(queue.put_nowait,
                                          {"type": "think_chunk", "step": step, "delta": delta})

            def emit_answer(delta: str) -> None:
                loop.call_soon_threadsafe(queue.put_nowait,
                                          {"type": "answer_chunk", "delta": delta})

            def emit_step(step: dict) -> None:
                loop.call_soon_threadsafe(queue.put_nowait, {"type": "step", **step})

            emitter = StreamEmitter(emit_think=emit_think, emit_answer=emit_answer,
                                    emit_step=emit_step)

            def run() -> None:
                try:
                    response, personality_info, reasoning_chain = agent.send_message(
                        payload,
                        personality_input=None,
                        return_response_only=False,
                        new_session=new_session,
                        session_id=session_index,
                        stream_emitter=emitter,
                    )
                    loop.call_soon_threadsafe(queue.put_nowait, {
                        "type": "done",
                        **self._compose_result(agent, response, personality_info,
                                               reasoning_chain),
                    })
                except Exception as e:
                    loop.call_soon_threadsafe(queue.put_nowait,
                                              {"type": "error", "message": str(e)})

            thread_task = asyncio.create_task(asyncio.to_thread(run))
            try:
                while True:
                    event = await queue.get()
                    yield event
                    if event["type"] in ("done", "error"):
                        break
            finally:
                # 客户端断开也等 Agent 跑完（user_data.json 落盘不依赖连接）
                await thread_task

    @staticmethod
    def _compose_result(agent, response, personality_info, reasoning_chain) -> dict[str, Any]:
        """response + 记忆/推理链/人格 → 与 send_message 一致的返回结构。

        参数：
            agent: PersonaVLM Agent 实例（用于读取当前会话记忆与人格）。
            response: 回复文本。
            personality_info: 本轮人格推断原始输出。
            reasoning_chain: 推理链步骤列表。

        返回：
            结构化结果字典，字段：response / remembering / reasoning / alignment。
        """
        remembering = None
        sessions = agent.data.get("sessions", [{}])
        if sessions:
            sem_mems = agent.active_session().get("semantic_memory", [])
            if sem_mems:
                latest = sem_mems[-1]
                remembering = {
                    "reason": latest.get("reason", ""),
                    "decision": latest.get("decision", False),
                    "content": latest.get("content", ""),
                    "keywords": latest.get("keywords", ""),
                }

        reasoning = []
        for step in reasoning_chain:
            reasoning.append({
                "think": step.get("think", ""),
                "action": step.get("action", ""),
                "response": step.get("response", ""),
                "retrieve_info": step.get("retrieve_info", None),
            })

        alignment = {
            "openness": float(str(agent.big_five_personality.get("openness", 3.0))[:3]),
            "conscientiousness": float(str(agent.big_five_personality.get("conscientiousness", 3.0))[:3]),
            "extraversion": float(str(agent.big_five_personality.get("extraversion", 3.0))[:3]),
            "agreeableness": float(str(agent.big_five_personality.get("agreeableness", 3.0))[:3]),
            "neuroticism": float(str(agent.big_five_personality.get("neuroticism", 3.0))[:3]),
        }

        return {
            "response": response,
            "remembering": remembering,
            "reasoning": reasoning,
            "alignment": alignment,
        }

    @property
    def active_count(self) -> int:
        """当前缓存的 Agent 数量。"""
        return len(self._agents)


def persona_configured() -> bool:
    """判断 PersonaVLM 云端后端是否已配置（存在 DASHSCOPE_API_KEY）。"""
    return bool(os.getenv("DASHSCOPE_API_KEY"))


# 模块级单例：构造仅初始化空 dict，无启动成本
manager = PersonaAgentManager()
