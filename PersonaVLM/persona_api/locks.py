"""用户级锁注册表。"""

from __future__ import annotations

import threading


class UserLockRegistry:
    """为每个用户提供稳定的可重入锁，保护 JSON 读写。"""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.RLock] = {}

    def get(self, user_name: str) -> threading.RLock:
        with self._guard:
            if user_name not in self._locks:
                self._locks[user_name] = threading.RLock()
            return self._locks[user_name]
