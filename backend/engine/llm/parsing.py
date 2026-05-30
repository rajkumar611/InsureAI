from __future__ import annotations

import json
import logging
from typing import Callable, TypeVar

from pydantic import ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def retry_llm_with_validation(
    func: Callable[[], T],
    submission_id: str,
    agent_name: str,
    max_retries: int = 2,
) -> T:
    """
    Standardized retry logic for LLM JSON parsing across all agents.

    Args:
        func: Async function that returns parsed output
        submission_id: For logging context
        agent_name: For logging context
        max_retries: Number of retry attempts before raising

    Returns:
        Parsed output from func

    Raises:
        RuntimeError: If all retries exhausted with parse/validation errors
    """
    for attempt in range(1, max_retries + 1):
        try:
            return await func()
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning(
                f"{agent_name} (submission_id={submission_id}): "
                f"attempt {attempt}/{max_retries} failed — {exc}"
            )
            if attempt == max_retries:
                raise RuntimeError(
                    f"{agent_name} failed after {max_retries} attempts "
                    f"(submission_id={submission_id}): {exc}"
                ) from exc


def extract_first_json_object(text: str) -> str:
    """Return the first complete {...} block from text, stripping any surrounding prose."""
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers Claude sometimes adds."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    return text
