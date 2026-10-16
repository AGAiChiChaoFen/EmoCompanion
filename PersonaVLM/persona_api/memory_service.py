"""读取和整理 PersonaVLM 用户记忆。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable

from .errors import MemoryFileError, UserNotFoundError, ValidationError
from .locks import UserLockRegistry


LOGGER = logging.getLogger("persona_api.memory")


class MemoryService:
    """以 user_data.json 为唯一数据源提供只读查询。"""

    def __init__(self, output_root: Path, locks: UserLockRegistry) -> None:
        self.output_root = output_root.resolve(strict=False)
        self.locks = locks

    @staticmethod
    def validate_user_name(user_name: str) -> str:
        clean_name = str(user_name or "").strip()
        if not clean_name:
            raise ValidationError("用户名不能为空。", "user_name")
        if clean_name in {".", ".."} or "/" in clean_name or "\\" in clean_name or "\x00" in clean_name:
            raise ValidationError("用户名包含非法路径字符。", "user_name")
        if len(clean_name) > 100:
            raise ValidationError("用户名不能超过100个字符。", "user_name")
        return clean_name

    def user_directory(self, user_name: str) -> Path:
        clean_name = self.validate_user_name(user_name)
        target = (self.output_root / clean_name).resolve(strict=False)
        if target == self.output_root or target.parent != self.output_root:
            raise ValidationError("用户目录超出允许的记忆根目录。", "user_name")
        return target

    def memory_path(self, user_name: str) -> Path:
        return self.user_directory(user_name) / "user_data.json"

    def list_users(self) -> list[dict[str, Any]]:
        if not self.output_root.exists():
            LOGGER.info("记忆根目录尚不存在 | 路径=%s", self.output_root)
            return []
        users: list[dict[str, Any]] = []
        for child in sorted(self.output_root.iterdir(), key=lambda item: item.name):
            memory_file = child / "user_data.json"
            if not child.is_dir() or not memory_file.is_file():
                continue
            try:
                data = self.read_memory(child.name)
                summary = self.build_summary(data)
                users.append({"user_name": child.name, **summary})
            except (MemoryFileError, UserNotFoundError) as exc:
                LOGGER.warning("跳过不可读取的用户记忆 | 用户=%s | 原因=%s", child.name, exc.detail)
        return users

    def read_memory(self, user_name: str) -> dict[str, Any]:
        clean_name = self.validate_user_name(user_name)
        path = self.memory_path(clean_name)
        if not path.is_file():
            raise UserNotFoundError(clean_name)
        with self.locks.get(clean_name):
            try:
                with path.open("r", encoding="utf-8") as file:
                    data = json.load(file)
            except json.JSONDecodeError as exc:
                raise MemoryFileError(
                    f"用户“{clean_name}”的 user_data.json 不是有效 JSON（第{exc.lineno}行）。"
                ) from exc
            except OSError as exc:
                raise MemoryFileError(f"无法读取用户“{clean_name}”的记忆文件：{exc}") from exc
        if not isinstance(data, dict):
            raise MemoryFileError(f"用户“{clean_name}”的记忆文件顶层必须是对象。")
        return data

    def build_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        sessions = data.get("sessions", [])
        valid_sessions = [session for session in sessions if session.get("interactions")]
        semantic_records = [
            memory
            for session in sessions
            for memory in session.get("semantic_memory", [])
        ]
        episodic_records = [
            memory
            for session in sessions
            for memory in session.get("EpisodicMemory", [])
        ]
        procedural_versions = [
            session
            for session in sessions
            if session.get("ProceduralMemory")
        ]
        latest_profile = sessions[-1].get("profile", {}) if sessions else data.get("init_profile", {})
        personality_history = data.get("personality_history", [])
        if not isinstance(personality_history, list):
            personality_history = []
        interaction_count = len(self.flatten_interactions(data))
        return {
            "current_interactions": data.get("current_interactions", interaction_count),
            "session_count": len(valid_sessions),
            "profile_version_count": sum(1 for session in sessions if session.get("profile")),
            "semantic_record_count": len(semantic_records),
            "retained_semantic_count": sum(bool(item.get("decision")) for item in semantic_records),
            "episodic_topic_count": len(episodic_records),
            "procedural_version_count": len(procedural_versions),
            "image_count": len(data.get("imgs", [])),
            "latest_profile": latest_profile,
            "big_five_personality": data.get("big_five_personality", {}),
            "personality_history_schema_version": data.get("personality_history_schema_version"),
            "personality_history_count": len(personality_history),
            "personality_history_complete": (
                data.get("personality_history_schema_version") == 1
                and len(personality_history) == interaction_count
            ),
            "latest_personality_history": personality_history[-1] if personality_history else None,
            "last_update_time": latest_profile.get("update time"),
        }

    @staticmethod
    def flatten_profiles(data: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "session_index": session_index,
                "profile": session.get("profile", {}),
            }
            for session_index, session in enumerate(data.get("sessions", []))
            if session.get("profile")
        ]

    @staticmethod
    def flatten_personality_history(data: dict[str, Any]) -> list[dict[str, Any]]:
        history = data.get("personality_history", [])
        if not isinstance(history, list):
            return []
        return [
            {"history_index": index, **record}
            for index, record in enumerate(history)
            if isinstance(record, dict)
        ]

    @staticmethod
    def flatten_semantic_memories(data: dict[str, Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for session_index, session in enumerate(data.get("sessions", [])):
            interactions = session.get("interactions", [])
            for memory_index, memory in enumerate(session.get("semantic_memory", [])):
                interaction = interactions[memory_index] if memory_index < len(interactions) else []
                query = interaction[0] if interaction else {}
                result.append({
                    "session_index": session_index,
                    "memory_index": memory_index,
                    "time": query.get("time"),
                    "user_query": query.get("query"),
                    **memory,
                })
        return result

    @staticmethod
    def flatten_episodic_memories(data: dict[str, Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for session_index, session in enumerate(data.get("sessions", [])):
            interactions = session.get("interactions", [])
            for memory_index, memory in enumerate(session.get("EpisodicMemory", [])):
                source_indices = memory.get("source_dialog_indices", [])
                first_index = source_indices[0] if source_indices else None
                last_index = source_indices[-1] if source_indices else None
                start_time = (
                    interactions[first_index][0].get("time")
                    if isinstance(first_index, int) and 0 <= first_index < len(interactions)
                    else None
                )
                end_time = (
                    interactions[last_index][0].get("time")
                    if isinstance(last_index, int) and 0 <= last_index < len(interactions)
                    else None
                )
                result.append({
                    "session_index": session_index,
                    "memory_index": memory_index,
                    "start_time": start_time,
                    "end_time": end_time,
                    **memory,
                })
        return result

    @staticmethod
    def flatten_procedural_memories(data: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "session_index": session_index,
                "update_time": session.get("profile", {}).get("update time"),
                "memory": session["ProceduralMemory"],
            }
            for session_index, session in enumerate(data.get("sessions", []))
            if session.get("ProceduralMemory")
        ]

    @staticmethod
    def flatten_interactions(data: dict[str, Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for session_index, session in enumerate(data.get("sessions", [])):
            for turn_index, interaction in enumerate(session.get("interactions", [])):
                query = interaction[0] if len(interaction) > 0 else {}
                response = interaction[1] if len(interaction) > 1 else {}
                reasoning_chain = interaction[2] if len(interaction) > 2 else []
                images = interaction[3] if len(interaction) > 3 else []
                result.append({
                    "session_index": session_index,
                    "turn_index": turn_index,
                    "time": query.get("time"),
                    "query": query.get("query"),
                    "response": response.get("response") if isinstance(response, dict) else response,
                    "reasoning_chain": reasoning_chain,
                    "images": images,
                })
        return result

    @staticmethod
    def paginate(items: Iterable[Any], page: int, per_page: int) -> dict[str, Any]:
        records = list(items)
        total = len(records)
        total_pages = max(1, (total + per_page - 1) // per_page)
        if page > total_pages and total > 0:
            raise ValidationError(f"页码超出范围，最大页码为 {total_pages}。", "page")
        start = (page - 1) * per_page
        return {
            "items": records[start:start + per_page],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
            },
        }
