"""Lightweight ReAct agent loop for Tripletex API error recovery.

Architecture:
  1. Programmatic fix (no LLM) — fastest, handles field removal
  2. Agent loop (1-3 LLM calls) — handles complex recovery with tools
  3. Falls back to existing retry flow if agent can't fix it

The agent is only activated when the programmatic fix fails.
"""
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.agent.prompts import AGENT_SYSTEM_PROMPT
from app.agent.tools import (
    call_api,
    extract_rejected_fields,
    fix_payload_from_error,
    get_endpoint_schema,
    search_api_docs,
)
from app.clients.tripletex import TripletexClient, TripletexClientError
from app.config import settings
from app.error_handling import extract_validation_messages

logger = logging.getLogger(__name__)

MAX_AGENT_STEPS = 5


def _call_llm(messages: List[Dict[str, str]], thinking_level: str = "low") -> Optional[str]:
    """Call the LLM with a message list. Returns raw text output."""
    if not settings.replicate_api_token:
        return None

    # Build a single prompt from messages
    parts = []
    system_msg = ""
    for msg in messages:
        if msg["role"] == "system":
            system_msg = msg["content"]
        elif msg["role"] == "user":
            parts.append("User: {0}".format(msg["content"]))
        elif msg["role"] == "assistant":
            parts.append("Assistant: {0}".format(msg["content"]))
        elif msg["role"] == "tool":
            parts.append("Tool result: {0}".format(msg["content"]))

    prompt = "\n\n".join(parts)
    prompt += "\n\nAssistant: "

    payload = {
        "input": {
            "system_instruction": system_msg,
            "prompt": prompt,
            "temperature": 0.1,
            "top_p": 0.95,
            "thinking_level": thinking_level,
            "max_output_tokens": 2048,
        },
    }

    headers = {
        "Authorization": "Bearer {0}".format(settings.replicate_api_token),
        "Content-Type": "application/json",
        "Prefer": "wait",
    }

    url = "https://api.replicate.com/v1/models/{0}/predictions".format(settings.replicate_model)

    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=45.0, trust_env=False)
        if response.is_error:
            logger.warning("agent_llm_error status=%s", response.status_code)
            return None
        data = response.json()
        output = data.get("output")
        if isinstance(output, list):
            return "".join(str(chunk) for chunk in output)
        if isinstance(output, str):
            return output
        return None
    except Exception:
        logger.exception("agent_llm_exception")
        return None


def _parse_tool_call(text: str) -> Optional[Dict[str, Any]]:
    """Extract a JSON tool call from LLM output."""
    text = text.strip()
    # Find JSON object in the text
    start = text.find("{")
    if start == -1:
        return None

    # Try progressively larger substrings
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    continue
    return None


def _execute_tool(
    tool_call: Dict[str, Any],
    client: TripletexClient,
) -> Tuple[str, bool]:
    """Execute a tool call. Returns (result_string, is_done)."""
    tool_name = tool_call.get("tool", "")
    args = tool_call.get("args", {})

    if tool_name == "search_api_docs":
        result = search_api_docs(args.get("query", ""))
        return result, False

    if tool_name == "get_endpoint_schema":
        result = get_endpoint_schema(args.get("endpoint", ""))
        return result, False

    if tool_name == "call_api":
        result = call_api(
            client,
            method=args.get("method", "GET"),
            path=args.get("path", "/"),
            payload=args.get("payload"),
            params=args.get("params"),
        )
        return result, False

    if tool_name == "done":
        success = args.get("success", False)
        result = args.get("result", {})
        return json.dumps({"done": True, "success": success, "result": result}, default=str), True

    return "Unknown tool: {0}".format(tool_name), False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def programmatic_retry(
    client: TripletexClient,
    method: str,
    path: str,
    payload: Dict[str, Any],
    exc: TripletexClientError,
    max_retries: int = 2,
) -> Optional[Dict[str, Any]]:
    """Try to fix a payload programmatically (no LLM) and retry the API call.

    Returns the successful response, or None if it can't be fixed.
    """
    current_payload = dict(payload)
    current_exc = exc

    for attempt in range(max_retries):
        fixed = fix_payload_from_error(current_payload, current_exc)
        if fixed is None:
            logger.info("programmatic_retry no_fix attempt=%d", attempt + 1)
            return None

        logger.info(
            "programmatic_retry attempt=%d path=%s removed=%s",
            attempt + 1, path, set(current_payload.keys()) - set(fixed.keys()),
        )
        try:
            return client._request(method, path, json=fixed)
        except TripletexClientError as new_exc:
            if new_exc.status_code != 422:
                raise
            current_payload = fixed
            current_exc = new_exc

    return None


def agent_recover(
    client: TripletexClient,
    task_type: str,
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]],
    error: TripletexClientError,
) -> Optional[Dict[str, Any]]:
    """Run the lightweight agent to recover from an API error.

    Returns the successful API response, or None if recovery failed.
    Uses 1-3 LLM calls with tool use.
    """
    validation_msgs = extract_validation_messages(error)
    error_summary = json.dumps({
        "status_code": error.status_code,
        "method": method,
        "path": path,
        "validation_messages": validation_msgs,
        "response_snippet": (error.response_text or "")[:500],
    }, ensure_ascii=False)

    payload_summary = json.dumps(payload, default=str, ensure_ascii=False)[:1000] if payload else "None"

    user_msg = (
        "Recover from this Tripletex API error.\n\n"
        "Task type: {task_type}\n"
        "Failed call: {method} {path}\n"
        "Payload sent: {payload}\n"
        "Error received: {error}\n\n"
        "Use tools to search docs, fix the payload, and retry the API call.\n"
        "Respond with a JSON tool call: {{\"tool\": \"name\", \"args\": {{...}}}}"
    ).format(
        task_type=task_type,
        method=method,
        path=path,
        payload=payload_summary,
        error=error_summary,
    )

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    for step in range(MAX_AGENT_STEPS):
        logger.info("agent_step %d/%d", step + 1, MAX_AGENT_STEPS)

        output = _call_llm(messages, thinking_level="low")
        if output is None:
            logger.warning("agent_llm_returned_none step=%d", step + 1)
            return None

        logger.info("agent_llm_output step=%d output=%s", step + 1, output[:300])

        tool_call = _parse_tool_call(output)
        if tool_call is None:
            # LLM didn't produce a tool call — give it one more chance
            messages.append({"role": "assistant", "content": output})
            messages.append({"role": "user", "content": "Please respond with a JSON tool call: {\"tool\": \"name\", \"args\": {...}}"})
            continue

        result, is_done = _execute_tool(tool_call, client)
        logger.info("agent_tool tool=%s done=%s result=%s", tool_call.get("tool"), is_done, result[:200])

        if is_done:
            try:
                done_data = json.loads(result)
                if done_data.get("success"):
                    inner = done_data.get("result", {})
                    if isinstance(inner, dict):
                        return inner
                return None
            except (json.JSONDecodeError, TypeError):
                return None

        # If call_api succeeded (no error key), we're done
        if tool_call.get("tool") == "call_api":
            try:
                api_result = json.loads(result)
                if not api_result.get("error"):
                    logger.info("agent_api_success step=%d", step + 1)
                    return api_result
            except (json.JSONDecodeError, TypeError):
                pass

        messages.append({"role": "assistant", "content": output})
        messages.append({"role": "tool", "content": result[:1500]})

    logger.warning("agent_exhausted_steps")
    return None
