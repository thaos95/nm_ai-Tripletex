"""Knowledge base loader for Tripletex task types.

Provides structured API specs, forbidden fields, and gotchas per task type.
The KB is loaded once from task_registry.json and cached in memory.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

_KB_PATH = Path(__file__).parent / "task_registry.json"
_kb_cache: Optional[Dict[str, Any]] = None


def load_kb() -> Dict[str, Any]:
    """Load and cache the task registry KB."""
    global _kb_cache
    if _kb_cache is not None:
        return _kb_cache
    try:
        with open(_KB_PATH, "r", encoding="utf-8") as f:
            _kb_cache = json.load(f)
        logger.info("kb_loaded tasks=%d", len(_kb_cache))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning("kb_load_failed path=%s error=%s", _KB_PATH, exc)
        _kb_cache = {}
    return _kb_cache


def get_task_spec(task_type: str) -> Optional[Dict[str, Any]]:
    """Get the KB spec for a given task type, or None if not registered."""
    kb = load_kb()
    return kb.get(task_type)


def get_forbidden_fields(task_type: str) -> Set[str]:
    """Get fields that must NOT appear in the API payload for this task type."""
    spec = get_task_spec(task_type)
    if spec is None:
        return set()
    return set(spec.get("forbidden_fields", []))


def get_gotchas(task_type: str) -> List[str]:
    """Get known gotchas/warnings for this task type (useful for LLM prompts)."""
    spec = get_task_spec(task_type)
    if spec is None:
        return []
    return list(spec.get("gotchas", []))


def get_allowed_fields(task_type: str) -> Optional[Set[str]]:
    """Get the set of allowed parsed fields for this task type, or None if not in KB."""
    spec = get_task_spec(task_type)
    if spec is None:
        return None
    return set(spec.get("allowed_parsed_fields", []))
