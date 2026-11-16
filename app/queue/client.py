"""Redis connection and RQ queue accessors. Tests swap the connection with `set_connection`."""

from __future__ import annotations

from redis import Redis
from rq import Queue

from app.core.config import get_settings

_connection: Redis | None = None


def get_connection() -> Redis:
    global _connection
    if _connection is None:
        _connection = Redis.from_url(get_settings().redis_url)
    return _connection


def set_connection(connection: Redis | None) -> None:
    global _connection
    _connection = connection


def get_queue() -> Queue:
    return Queue(get_settings().queue_name, connection=get_connection())
