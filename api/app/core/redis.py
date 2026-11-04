from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

import redis

from app.core.config import get_settings


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_app_url, decode_responses=True)


class LockNotAcquired(RuntimeError):
    pass


@contextmanager
def redis_lock(key: str, timeout: int = 30, blocking_timeout: float = 10) -> Iterator[None]:
    """Lock distribuído para operações de baixa (ex.: por `e2e_id` ou por título)."""
    lock = get_redis().lock(f"lock:{key}", timeout=timeout, blocking_timeout=blocking_timeout)
    if not lock.acquire():
        raise LockNotAcquired(key)
    try:
        yield
    finally:
        lock.release()
