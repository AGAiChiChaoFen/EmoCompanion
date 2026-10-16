"""封装 PersonaVLM Agent 的模型加载、缓存和推理。"""

from __future__ import annotations

import logging
import os
import threading
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .config import ApiSettings, PROJECT_DIR
from .errors import ServiceNotReadyError, ValidationError
from .locks import UserLockRegistry
from .memory_service import MemoryService


LOGGER = logging.getLogger("persona_api.agent")
TIME_FORMAT = "%Y-%m-%d %H:%M"


class UserConfig:
    """适配 PersonaVLM Agent 的用户配置。"""

    def __init__(self, user_name: str, storage_path: Path) -> None:
        self.USER_NAME = user_name
        self.DATA_STORAGE_PATH = storage_path
        self.PROFILE = {
            "system context": "老年人情感陪护；仅使用中文文本进行交互",
            "requirements or expectations": "温和、尊重、不说教；必要时提醒联系家人与专业人员",
            "communication preferences": "使用清晰易读的中文回复",
        }


class AgentService:
    """共享一份大模型，为每个用户缓存独立 PersonaVLM Agent。"""

    def __init__(
        self,
        settings: ApiSettings,
        memory_service: MemoryService,
        locks: UserLockRegistry,
    ) -> None:
        self.settings = settings
        self.memory_service = memory_service
        self.locks = locks
        self._shared_model: Any = None
        self._agents: dict[str, Any] = {}
        self._registry_lock = threading.RLock()
        self._model_lock = threading.RLock()

    @property
    def model_loaded(self) -> bool:
        return self._shared_model is not None

    @property
    def cached_user_count(self) -> int:
        with self._registry_lock:
            return len(self._agents)

    def readiness(self) -> dict[str, Any]:
        model_path = self.settings.model_path
        return {
            "model_path": str(model_path),
            "model_path_exists": model_path.exists(),
            "model_config_exists": (model_path / "config.json").is_file(),
            "output_root": str(self.settings.output_root),
            "output_root_exists": self.settings.output_root.exists(),
            "model_loaded": self.model_loaded,
            "cached_user_count": self.cached_user_count,
        }

    def preload_model(self) -> dict[str, Any]:
        """在接收首次推理请求前加载共享模型，并返回最新就绪状态。"""
        self._ensure_model()
        return self.readiness()

    def _prepare_runtime(self) -> None:
        warnings.filterwarnings("ignore")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        os.chdir(PROJECT_DIR)
        for name in ("transformers", "huggingface_hub", "sentence_transformers", "faiss"):
            logging.getLogger(name).setLevel(logging.ERROR)
        try:
            from transformers.utils import logging as transformers_logging

            transformers_logging.set_verbosity_error()
            transformers_logging.disable_progress_bar()
        except (ImportError, AttributeError):
            pass

    def _ensure_model(self) -> Any:
        if self._shared_model is not None:
            return self._shared_model
        with self._model_lock:
            if self._shared_model is not None:
                return self._shared_model
            if not self.settings.model_path.exists():
                raise ServiceNotReadyError(f"模型目录不存在：{self.settings.model_path}")
            self._prepare_runtime()
            LOGGER.info("首次推理，开始加载共享模型 | 路径=%s", self.settings.model_path)
            started = time.perf_counter()
            try:
                from PersonaVLM.model import Qwenvl7B

                self._shared_model = Qwenvl7B(model_path=str(self.settings.model_path))
            except Exception as exc:
                LOGGER.exception("共享模型加载失败 | 路径=%s", self.settings.model_path)
                raise ServiceNotReadyError(f"模型加载失败：{exc}") from exc
            LOGGER.info("共享模型加载完成 | 用时=%.2f秒", time.perf_counter() - started)
            return self._shared_model

    def _get_agent(self, user_name: str) -> Any:
        with self._registry_lock:
            cached = self._agents.get(user_name)
            if cached is not None:
                LOGGER.debug("复用已缓存 Agent | 用户=%s", user_name)
                return cached

        shared_model = self._ensure_model()
        with self._registry_lock:
            cached = self._agents.get(user_name)
            if cached is not None:
                return cached
            self._prepare_runtime()
            LOGGER.info("正在初始化用户 Agent | 用户=%s", user_name)
            started = time.perf_counter()
            try:
                from PersonaVLM.PersonaVLMAgent import PersonaVLM

                storage_path = self.memory_service.user_directory(user_name)
                config = UserConfig(user_name, storage_path)
                agent = PersonaVLM(
                    config,
                    force_retrieve=self.settings.force_retrieve,
                    reasoning_mode=self.settings.reasoning_mode,
                    agent_model=shared_model,
                )
            except Exception as exc:
                LOGGER.exception("用户 Agent 初始化失败 | 用户=%s", user_name)
                raise ServiceNotReadyError(f"用户 Agent 初始化失败：{exc}") from exc
            self._agents[user_name] = agent
            LOGGER.info("用户 Agent 初始化完成 | 用户=%s | 用时=%.2f秒", user_name, time.perf_counter() - started)
            return agent

    @staticmethod
    def validate_query(query: Any) -> str:
        if not isinstance(query, str):
            raise ValidationError("query 必须是字符串。", "query")
        clean_query = query.strip()
        if not clean_query:
            raise ValidationError("query 不能为空。", "query")
        if len(clean_query) > 10_000:
            raise ValidationError("query 不能超过10000个字符。", "query")
        return clean_query

    @staticmethod
    def validate_time(value: Optional[Any]) -> str:
        if value is None or value == "":
            return datetime.now().strftime(TIME_FORMAT)
        if not isinstance(value, str):
            raise ValidationError("time 必须是 YYYY-MM-DD HH:MM 格式的字符串。", "time")
        try:
            parsed = datetime.strptime(value, TIME_FORMAT)
        except ValueError as exc:
            raise ValidationError("time 必须采用 YYYY-MM-DD HH:MM 格式。", "time") from exc
        return parsed.strftime(TIME_FORMAT)

    def _ensure_chronological_time(
        self,
        user_name: str,
        normalized_time: str,
        explicitly_supplied: bool,
    ) -> str:
        """确保新消息晚于文件中最后一次交互和画像更新时间。"""

        path = self.memory_service.memory_path(user_name)
        if not path.is_file():
            return normalized_time
        data = self.memory_service.read_memory(user_name)
        known_times: list[datetime] = []
        for session in data.get("sessions", []):
            update_time = session.get("profile", {}).get("update time")
            if update_time:
                try:
                    known_times.append(datetime.strptime(update_time, TIME_FORMAT))
                except ValueError:
                    LOGGER.warning("忽略无法解析的画像更新时间 | 用户=%s | 时间=%s", user_name, update_time)
            for interaction in session.get("interactions", []):
                interaction_time = interaction[0].get("time") if interaction else None
                if interaction_time:
                    try:
                        known_times.append(datetime.strptime(interaction_time, TIME_FORMAT))
                    except ValueError:
                        LOGGER.warning("忽略无法解析的交互时间 | 用户=%s | 时间=%s", user_name, interaction_time)
        if not known_times:
            return normalized_time
        latest_time = max(known_times)
        requested_time = datetime.strptime(normalized_time, TIME_FORMAT)
        if requested_time > latest_time:
            return normalized_time
        if explicitly_supplied:
            raise ValidationError(
                f"time 必须晚于现有记忆的最后时间 {latest_time.strftime(TIME_FORMAT)}。",
                "time",
            )
        adjusted = latest_time + timedelta(minutes=1)
        LOGGER.warning(
            "服务器当前时间不晚于现有记忆，已自动顺延 | 用户=%s | 原时间=%s | 调整后=%s",
            user_name,
            normalized_time,
            adjusted.strftime(TIME_FORMAT),
        )
        return adjusted.strftime(TIME_FORMAT)

    @staticmethod
    def validate_personality(value: Any) -> Optional[dict[str, float]]:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValidationError("personality 必须是对象。", "personality")
        allowed = {"openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"}
        result: dict[str, float] = {}
        for key, raw_score in value.items():
            if key not in allowed:
                raise ValidationError(f"不支持的人格字段：{key}", f"personality.{key}")
            if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
                raise ValidationError("人格分数必须是数字。", f"personality.{key}")
            score = float(raw_score)
            if score < 1 or score > 5:
                raise ValidationError("人格分数必须在1到5之间。", f"personality.{key}")
            result[key] = score
        return result

    @staticmethod
    def validate_external_knowledge(value: Any) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValidationError("external_knowledge 必须是字符串。", "external_knowledge")
        return value.strip()

    def infer(
        self,
        user_name: str,
        query: Any,
        request_time: Optional[Any] = None,
        personality: Any = None,
        external_knowledge: Any = None,
        memory_update: bool = True,
    ) -> dict[str, Any]:
        if not isinstance(memory_update, bool):
            raise ValidationError("memory_update 必须是布尔值。", "memory_update")
        clean_name = self.memory_service.validate_user_name(user_name)
        clean_query = self.validate_query(query)
        clean_external_knowledge = self.validate_external_knowledge(external_knowledge)
        normalized_time = self.validate_time(request_time)
        normalized_personality = self.validate_personality(personality)
        started = time.perf_counter()
        with self.locks.get(clean_name):
            if memory_update:
                normalized_time = self._ensure_chronological_time(
                    clean_name,
                    normalized_time,
                    explicitly_supplied=request_time not in {None, ""},
                )
            LOGGER.info(
                "准备执行推理 | 用户=%s | 时间=%s | 输入长度=%d | 输入预览=%s",
                clean_name,
                normalized_time,
                len(clean_query),
                clean_query[:80].replace("\n", " "),
            )
            agent = self._get_agent(clean_name)
            with self._model_lock:
                try:
                    response, personality_info, reasoning_chain = agent.send_message(
                        {
                            "query": clean_query,
                            "time": normalized_time,
                            "imgs": [],
                        },
                        personality_input=normalized_personality,
                        return_response_only=False,
                        update=memory_update,
                        external_knowledge=clean_external_knowledge,
                    )
                except Exception:
                    LOGGER.exception("推理执行失败 | 用户=%s | 时间=%s", clean_name, normalized_time)
                    try:
                        self._shared_model.clear_conversation_history()
                    except Exception:
                        LOGGER.debug("异常后清理模型对话上下文失败", exc_info=True)
                    raise

        elapsed = time.perf_counter() - started
        LOGGER.info(
            "推理执行完成 | 用户=%s | 用时=%.2f秒 | 回复长度=%d | 推理步骤=%d",
            clean_name,
            elapsed,
            len(response or ""),
            len(reasoning_chain or []),
        )
        return {
            "user_name": clean_name,
            "time": normalized_time,
            "query": clean_query,
            "response": response,
            "personality": personality_info,
            "reasoning_chain": reasoning_chain,
            "memory_updated": memory_update,
            "duration_seconds": round(elapsed, 3),
        }

    def invalidate_agent(self, user_name: str) -> bool:
        clean_name = self.memory_service.validate_user_name(user_name)
        with self.locks.get(clean_name), self._registry_lock:
            removed = self._agents.pop(clean_name, None) is not None
        LOGGER.info("用户 Agent 缓存已清除 | 用户=%s | 原缓存存在=%s", clean_name, removed)
        return removed
