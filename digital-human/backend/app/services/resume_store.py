"""简历文本的会话级内存存储"""
import asyncio
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class ResumeEntry:
    text: str
    expires_at: float


class ResumeStore:
    """内存简历存储（带 TTL）"""

    def __init__(self, default_ttl_seconds: int = 2 * 60 * 60) -> None:
        self._default_ttl_seconds = default_ttl_seconds
        self._data: dict[str, ResumeEntry] = {}
        self._lock = asyncio.Lock()

    async def put(self, resume_id: str, text: str, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds
        expires_at = time.time() + ttl
        async with self._lock:
            self._cleanup_expired_locked(time.time())
            self._data[resume_id] = ResumeEntry(text=text, expires_at=expires_at)

    async def get(self, resume_id: str) -> Optional[str]:
        now = time.time()
        async with self._lock:
            self._cleanup_expired_locked(now)
            entry = self._data.get(resume_id)
            if not entry:
                return None
            if entry.expires_at <= now:
                self._data.pop(resume_id, None)
                return None
            return entry.text

    def _cleanup_expired_locked(self, now: float) -> None:
        expired_keys = [key for key, entry in self._data.items() if entry.expires_at <= now]
        for key in expired_keys:
            self._data.pop(key, None)


resume_store = ResumeStore()
