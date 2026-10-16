import os
from dotenv import load_dotenv
from pathlib import Path
import time
from typing import Any

from fastapi import FastAPI



load_dotenv()  # 从 .env 文件加载环境变量


def normalize_session_id(session_id: str | None) -> str:
    """
    规范化会话标识符，避免空值导致状态冲突。

    参数：
        session_id: 客户端传入的会话标识符，可为空。

    返回：
        返回规范化后的会话标识符。若为空则返回 default。
    """
    if not session_id:
        return "default"
    cleaned = session_id.strip()
    return cleaned or "default"



def read_model_path(env_name: str) -> Path:
    """
    从环境变量读取模型路径并进行存在性校验。

    参数：
        env_name: 模型路径环境变量名称。

    返回：
        返回可用的模型目录 Path 对象。
        当环境变量缺失或路径不存在时，会抛出异常。
    """
    raw = os.getenv(env_name)
    if not raw:
        raise EnvironmentError(f"缺少环境变量: {env_name}")

    model_path = Path(raw)
    if not model_path.exists():
        raise FileNotFoundError(f"模型路径不存在: {model_path}")
    return model_path



def safe_getattr_state(app: FastAPI, field: str, default: Any) -> Any:
    """
    安全读取应用状态字段。

    参数：
        app: FastAPI 应用对象。
        field: 状态字段名称。
        default: 字段不存在时返回的默认值。

    返回：
        返回应用状态中的对应字段值；若不存在则返回 default。
    """
    return getattr(app.state, field, default)



def runtime_status(app: FastAPI) -> dict[str, Any]:
    """
    生成运行时状态快照。

    参数：
        app: FastAPI 应用对象。

    返回：
        返回状态字典，包含 ready、load_seconds、memory_after_load、uptime_seconds。
    """
    base_status = dict(safe_getattr_state(app, "status", {}))
    started_at = safe_getattr_state(app, "started_at", time.time())
    base_status["uptime_seconds"] = round(time.time() - started_at, 3)
    return base_status


def read_server_host() -> str:
    """
    读取 FastAPI 服务监听地址。

    参数：
        无。

    返回：
        返回监听地址字符串。默认使用 127.0.0.1 监听本地回环地址。
    """
    return os.getenv("FASTAPI_HOST", "127.0.0.1")


def read_server_port() -> int:
    """
    读取 FastAPI 服务监听端口。

    参数：
        无。

    返回：
        返回监听端口。默认使用 9010。
    """
    return int(os.getenv("FASTAPI_PORT", "9010"))


def read_server_reload() -> bool:
    """
    读取 FastAPI 热重载开关。

    参数：
        无。

    返回：
        返回是否开启热重载。默认关闭。
    """
    return os.getenv("FASTAPI_RELOAD", "false").lower() == "true"
