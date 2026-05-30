"""
In-process pipeline progress store.

Each workflow node calls set_step() when it starts.
The polling endpoint reads from here so the UI can show which agent is running.
Keyed by submission_id (same as LangGraph thread_id).
"""
from __future__ import annotations

_store: dict[str, str] = {}


def set_step(submission_id: str, step: str) -> None:
    _store[submission_id] = step


def get_step(submission_id: str) -> str | None:
    return _store.get(submission_id)


def clear(submission_id: str) -> None:
    _store.pop(submission_id, None)
