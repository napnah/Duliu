"""M10 LangGraph checkpointer: memory or Postgres."""

from __future__ import annotations

from typing import Any

from duliu.config import settings

_saver: Any = None
_setup_done = False


def _postgres_conn_string() -> str:
    url = settings.database_url
    if "+asyncpg" in url:
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


async def get_checkpointer():
    """Return shared checkpointer (setup once)."""
    global _saver, _setup_done
    if _saver is not None:
        return _saver

    mode = (settings.langgraph_checkpoint or "memory").lower()
    if mode == "postgres":
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            _saver = AsyncPostgresSaver.from_conn_string(_postgres_conn_string())
            await _saver.setup()
            _setup_done = True
            return _saver
        except Exception as e:
            import logging

            logging.getLogger("duliu.pipeline").warning(
                "Postgres checkpointer failed (%s), falling back to memory", e
            )

    from langgraph.checkpoint.memory import MemorySaver

    _saver = MemorySaver()
    _setup_done = True
    return _saver


def checkpointer_mode() -> str:
    if _saver is None:
        return settings.langgraph_checkpoint or "memory"
    cls = type(_saver).__name__
    if "Postgres" in cls:
        return "postgres"
    return "memory"
