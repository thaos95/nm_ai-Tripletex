"""Lightweight ReAct agent loop for Tripletex API execution and error recovery.

Architecture:
  1. Programmatic fix (no LLM) — fastest, handles field removal on 422
  2. Agent recovery (1-5 LLM calls) — fixes complex errors with tools
  3. Agent execution (1-10 LLM calls) — full task execution as fallback executor

The agent can operate in two modes:
  - Recovery mode: activated after hardcoded executor fails, fixes ONE error
  - Execution mode: primary executor for tasks the hardcoded path can't handle
"""
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.agent.prompts import AGENT_EXECUTE_PROMPT, AGENT_RECOVER_PROMPT
from app.agent.tools import (
    call_api,
    extract_rejected_fields,
    fix_payload_from_error,
    get_endpoint_schema,
    get_task_spec,
    resolve_entity,
    search_api_docs,
)
from app.clients.tripletex import TripletexClient, TripletexClientError
from app.config import settings
from app.error_handling import extract_validation_messages

logger = logging.getLogger(__name__)

MAX_RECOVER_STEPS = 5
MAX_EXECUTE_STEPS = 10


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
        response = httpx.post(url, headers=headers, json=payload, timeout=60.0, trust_env=False)
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

    # Try progressively larger substrings (finds first complete JSON object)
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(text[start:i + 1])
                    # Must have a "tool" key to be a valid tool call
                    if "tool" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    pass
                # Keep looking for next JSON object
                start = text.find("{", i + 1)
                if start == -1:
                    return None
                depth = 0
                i = start - 1  # will be incremented by loop
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
        return result[:2000], False

    if tool_name == "get_endpoint_schema":
        result = get_endpoint_schema(args.get("endpoint", ""))
        return result[:2000], False

    if tool_name == "get_task_spec":
        result = get_task_spec(args.get("task_type", ""))
        return result[:2000], False

    if tool_name == "resolve_entity":
        search_fields = args.get("search_fields", {})
        if isinstance(search_fields, str):
            try:
                search_fields = json.loads(search_fields)
            except (json.JSONDecodeError, TypeError):
                search_fields = {}
        result = resolve_entity(
            client,
            entity_type=args.get("entity_type", ""),
            search_fields=search_fields,
        )
        return result[:2000], False

    if tool_name == "call_api":
        result = call_api(
            client,
            method=args.get("method", "GET"),
            path=args.get("path", "/"),
            payload=args.get("payload"),
            params=args.get("params"),
        )
        return result[:2000], False

    if tool_name == "done":
        success = args.get("success", False)
        summary = args.get("summary", "")
        return json.dumps({"done": True, "success": success, "summary": summary}), True

    return "Unknown tool: {0}. Available: search_api_docs, get_endpoint_schema, get_task_spec, resolve_entity, call_api, done".format(tool_name), False


def _run_agent_loop(
    client: TripletexClient,
    system_prompt: str,
    user_msg: str,
    max_steps: int,
    thinking_level: str = "low",
) -> Optional[Dict[str, Any]]:
    """Core agent loop. Returns the last successful API response, or None."""
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]

    last_api_success: Optional[Dict[str, Any]] = None
    retries_without_progress = 0

    for step in range(max_steps):
        logger.info("agent_step %d/%d", step + 1, max_steps)

        output = _call_llm(messages, thinking_level=thinking_level)
        if output is None:
            logger.warning("agent_llm_returned_none step=%d", step + 1)
            return last_api_success

        logger.info("agent_llm_output step=%d output=%s", step + 1, output[:300])

        tool_call = _parse_tool_call(output)
        if tool_call is None:
            retries_without_progress += 1
            if retries_without_progress >= 2:
                logger.warning("agent_no_tool_calls_giving_up step=%d", step + 1)
                return last_api_success
            messages.append({"role": "assistant", "content": output})
            messages.append({"role": "user", "content": 'Respond with ONLY a JSON tool call: {"tool": "name", "args": {...}}'})
            continue

        retries_without_progress = 0
        result, is_done = _execute_tool(tool_call, client)
        logger.info("agent_tool tool=%s done=%s result=%s", tool_call.get("tool"), is_done, result[:200])

        if is_done:
            try:
                done_data = json.loads(result)
                if done_data.get("success"):
                    return last_api_success or {"agent_done": True}
            except (json.JSONDecodeError, TypeError):
                pass
            return last_api_success

        # Track successful API calls
        if tool_call.get("tool") == "call_api":
            try:
                api_result = json.loads(result)
                if not api_result.get("error"):
                    logger.info("agent_api_success step=%d path=%s", step + 1, tool_call.get("args", {}).get("path"))
                    last_api_success = api_result
            except (json.JSONDecodeError, TypeError):
                pass

        messages.append({"role": "assistant", "content": output})
        messages.append({"role": "tool", "content": result[:1500]})

    logger.warning("agent_exhausted_steps last_success=%s", last_api_success is not None)
    return last_api_success


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
    """Run the agent to recover from an API error.

    Returns the successful API response, or None if recovery failed.
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
        'Respond with a JSON tool call: {{"tool": "name", "args": {{...}}}}'
    ).format(
        task_type=task_type,
        method=method,
        path=path,
        payload=payload_summary,
        error=error_summary,
    )

    return _run_agent_loop(
        client=client,
        system_prompt=AGENT_RECOVER_PROMPT,
        user_msg=user_msg,
        max_steps=MAX_RECOVER_STEPS,
        thinking_level="low",
    )


def agent_execute(
    client: TripletexClient,
    task_type: str,
    fields: Dict[str, Any],
    related_entities: Dict[str, Any],
    original_prompt: str,
) -> Optional[Dict[str, Any]]:
    """Run the agent as a primary executor for a task.

    This is the fallback executor — activated when the hardcoded executor
    doesn't have a handler or fails completely. The agent reasons about
    the task from scratch using tools.

    Returns the last successful API response, or None if execution failed.
    """
    fields_summary = json.dumps(fields, default=str, ensure_ascii=False)
    related_summary = json.dumps(related_entities, default=str, ensure_ascii=False)

    user_msg = (
        "Execute this Tripletex accounting task.\n\n"
        "Task type: {task_type}\n"
        "Parsed fields: {fields}\n"
        "Related entities: {related}\n"
        "Original prompt: {prompt}\n\n"
        "Start by calling get_task_spec to understand the task requirements, "
        "then resolve prerequisites and execute the task.\n"
        'Respond with a JSON tool call: {{"tool": "name", "args": {{...}}}}'
    ).format(
        task_type=task_type,
        fields=fields_summary[:1500],
        related=related_summary[:1000],
        prompt=original_prompt[:500],
    )

    return _run_agent_loop(
        client=client,
        system_prompt=AGENT_EXECUTE_PROMPT,
        user_msg=user_msg,
        max_steps=MAX_EXECUTE_STEPS,
        thinking_level="medium",
    )
