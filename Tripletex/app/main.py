import json
import logging
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.attachment_parser import parse_attachments, attachments_to_text
from app.clients.tripletex import TripletexClient, TripletexClientError
from app.config import settings
from app.error_handling import (
    TripletexErrorCategory,
    classify_tripletex_error,
    extract_validation_messages,
)
from app.errors import MissingPrerequisiteError, UnsupportedTaskError
from app.parser import parse_prompt
from app.planner import build_plan
from app.schemas import SolveRequest, SolveResponse, TaskType
from app.validator import validate_and_normalize_task
from app.workflows.executor import execute_plan

LOGGER = logging.getLogger(__name__)

app = FastAPI(title="Tripletex AI Agent", version="1.0")


def get_client_transport() -> Optional[httpx.BaseTransport]:
    """Dependency that returns the transport for TripletexClient.
    Override in tests to inject a mock transport."""
    return None


def _verify_api_key(authorization: Optional[str] = Header(default=None)) -> None:
    """Verify Bearer token if TRIPLETEX_AGENT_API_KEY is configured."""
    if not settings.api_key:
        return
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = authorization.split(" ", 1)
    token = parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else authorization
    if token != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")


def _log_parsed_task(parsed_task, attempt: int) -> None:
    """Log full parsed task details for debugging."""
    LOGGER.info(
        "PARSED attempt=%d task_type=%s confidence=%.2f fields=%s match_fields=%s related_entities=%s notes=%s",
        attempt,
        parsed_task.task_type,
        parsed_task.confidence,
        json.dumps(parsed_task.fields, default=str, ensure_ascii=False),
        json.dumps(parsed_task.match_fields, default=str, ensure_ascii=False),
        json.dumps(parsed_task.related_entities, default=str, ensure_ascii=False),
        parsed_task.notes,
    )


def _get_rag_context(query_text: str) -> str:
    """Query RAG for relevant API context. Returns empty string on failure."""
    try:
        from app.kb.rag import query as rag_query
        results = rag_query(query_text, top_k=3)
        if results:
            for r in results:
                LOGGER.info("RAG_HIT score=%.3f title=%s", r["score"], r["title"][:80])
            ctx = "\n".join(r["content"] for r in results)
            LOGGER.info("RAG_CONTEXT query=%s results=%d chars=%d", query_text[:60], len(results), len(ctx))
            return ctx
    except Exception:
        pass
    return ""


def _parse_and_validate(
    prompt: str,
    thinking_level: str = "high",
    extra_context: str = "",
) -> Optional["ParsedTask"]:
    """Parse prompt with RAG context and validate. Returns normalized task or None."""
    effective_prompt = prompt
    context_parts = []

    rag_ctx = _get_rag_context(prompt[:200])
    if rag_ctx:
        context_parts.append(rag_ctx)

    if extra_context:
        context_parts.append(extra_context)

    if context_parts:
        effective_prompt = "{0}\n\n[API Context]\n{1}".format(prompt, "\n\n".join(context_parts))

    parsed_task = parse_prompt(effective_prompt, thinking_level=thinking_level)

    if parsed_task.task_type == TaskType.UNSUPPORTED:
        LOGGER.warning("task classified as UNSUPPORTED")
        return None

    validation = validate_and_normalize_task(parsed_task)
    if validation.blocking_error:
        LOGGER.warning("VALIDATION_BLOCKED: %s", validation.blocking_error)
        return None

    return validation.parsed_task


_NON_RECOVERABLE_CATEGORIES = {
    TripletexErrorCategory.UNAUTHORIZED,
    TripletexErrorCategory.TIMEOUT,
    TripletexErrorCategory.SERVER_ERROR,
    TripletexErrorCategory.VALIDATION_ENVIRONMENT,
}


def _execute(
    parsed_task, prompt: str, request: SolveRequest, transport,
) -> tuple:
    """Execute plan. Returns (error_string, rich_context) or (None, '')."""
    plan = build_plan(parsed_task, raw_prompt=prompt)
    client = TripletexClient(
        base_url=str(request.tripletex_credentials.base_url),
        session_token=request.tripletex_credentials.session_token,
        verify_tls=settings.verify_tls,
        transport=transport,
    )
    try:
        result = execute_plan(client, plan)
        op_names = [op.name for op in result.operations]
        op_ids = [op.resource_id for op in result.operations]
        LOGGER.info(
            "EXECUTION task_type=%s operations=%s resource_ids=%s error=%s api_calls=%d",
            result.task_type, op_names, op_ids, result.error, len(client.operations),
        )
        if result.error:
            return "execution: {0}".format(result.error), ""
        if len(result.operations) == 0:
            return "execution: zero operations", ""
        return None, ""
    except MissingPrerequisiteError as exc:
        LOGGER.error("PREREQUISITE_ERROR %s", exc)
        rich = "[Execution Error]\nType: Missing prerequisite\nDetail: {0}".format(str(exc))
        return "prerequisite: {0}".format(str(exc)[:200]), rich
    except TripletexClientError as exc:
        LOGGER.error(
            "EXECUTION_ERROR status=%s path=%s response=%s",
            exc.status_code, exc.path, (exc.response_text or "")[:2000],
        )
        classified = classify_tripletex_error(exc)
        validation_msgs = extract_validation_messages(exc)

        # --- Agent recovery: try lightweight agent for recoverable 422s ---
        if classified.recoverable and exc.status_code in (400, 422) and exc.path:
            try:
                from app.agent.loop import agent_recover
                LOGGER.info("AGENT_RECOVER_START path=%s", exc.path)
                agent_result = agent_recover(
                    client=client,
                    task_type=str(parsed_task.task_type),
                    method=exc.method or "POST",
                    path=exc.path,
                    payload=client.operations[-1].get("json") if client.operations else None,
                    error=exc,
                )
                if agent_result is not None:
                    LOGGER.info("AGENT_RECOVER_SUCCESS path=%s result_keys=%s", exc.path, list(agent_result.keys())[:5])
                    return None, ""
                LOGGER.info("AGENT_RECOVER_FAILED path=%s", exc.path)
            except Exception:
                LOGGER.exception("AGENT_RECOVER_EXCEPTION")

        # Build rich structured error context for retry
        rich_parts = [
            "[Execution Error]",
            "Category: {0}".format(classified.category.value),
            "Status: {0}".format(exc.status_code),
            "Path: {0}".format(exc.path),
            "Summary: {0}".format(classified.summary),
        ]
        if validation_msgs:
            rich_parts.append("Validation messages:")
            for msg in validation_msgs:
                rich_parts.append("- {0}".format(msg))
        if not classified.recoverable:
            rich_parts.append("This error is NOT recoverable by re-parsing.")

        rich_context = "\n".join(rich_parts)
        LOGGER.info("RICH_ERROR_CONTEXT category=%s recoverable=%s msgs=%s",
                     classified.category.value, classified.recoverable, validation_msgs)

        error_str = "api_error: {0} {1} {2}".format(exc.status_code, exc.path, str(exc)[:200])

        if classified.category in _NON_RECOVERABLE_CATEGORIES:
            return error_str, ""  # empty rich context signals non-recoverable

        return error_str, rich_context
    finally:
        client.close()


@app.post("/solve", response_model=SolveResponse)
async def solve(
    request: SolveRequest,
    _auth: None = Depends(_verify_api_key),
    transport: Optional[httpx.BaseTransport] = Depends(get_client_transport),
) -> SolveResponse:
    LOGGER.info(
        "SOLVE_START prompt=%s base_url=%s files=%d",
        request.prompt,
        request.tripletex_credentials.base_url,
        len(request.files),
    )

    try:
        # 1. Parse attachments and build enriched prompt
        attachments = parse_attachments(request.files)
        attachment_text = attachments_to_text(attachments)
        enriched_prompt = request.prompt
        if attachment_text:
            enriched_prompt = "{0}\n\n{1}".format(request.prompt, attachment_text)
            LOGGER.info("ATTACHMENTS enriched prompt with %d chars of attachment text", len(attachment_text))

        # 2. Smart parse (medium + validation loop with high refinement)
        parsed = _parse_and_validate(enriched_prompt)
        if parsed is None:
            return SolveResponse(status="completed")

        _log_parsed_task(parsed, 1)

        # 3. Execute once
        error, rich_context = _execute(parsed, enriched_prompt, request, transport)
        if error is None:
            return SolveResponse(status="completed")

        # 4. Skip retry for non-recoverable errors (no rich_context = non-recoverable)
        if not rich_context:
            LOGGER.warning("NON_RECOVERABLE: %s", error)
            return SolveResponse(status="completed")

        # 5. Retry with rich structured error context
        LOGGER.info("RETRY first_error=%s", error)
        error_rag = _get_rag_context(error[:200])
        full_context = "{0}\n\n{1}".format(error_rag, rich_context) if error_rag else rich_context

        try:
            parsed2 = _parse_and_validate(enriched_prompt, extra_context=full_context)
            if parsed2 is not None:
                _log_parsed_task(parsed2, 2)
                error2, _ = _execute(parsed2, enriched_prompt, request, transport)
                if error2:
                    LOGGER.warning("RETRY_FAILED: %s", error2)
                else:
                    return SolveResponse(status="completed")
        except Exception:
            LOGGER.exception("RETRY_EXCEPTION")

        # 6. Final fallback: agent-as-executor
        #    The hardcoded executor failed twice. Let the agent try from scratch
        #    with full task context, tools, and API docs.
        try:
            from app.agent.loop import agent_execute
            LOGGER.info("AGENT_EXECUTE_START task_type=%s", parsed.task_type)
            agent_client = TripletexClient(
                base_url=str(request.tripletex_credentials.base_url),
                session_token=request.tripletex_credentials.session_token,
                verify_tls=settings.verify_tls,
                transport=transport,
            )
            try:
                agent_result = agent_execute(
                    client=agent_client,
                    task_type=str(parsed.task_type.value),
                    fields=dict(parsed.fields),
                    related_entities=dict(parsed.related_entities),
                    original_prompt=enriched_prompt[:2000],
                )
                if agent_result is not None:
                    LOGGER.info("AGENT_EXECUTE_SUCCESS")
                else:
                    LOGGER.warning("AGENT_EXECUTE_FAILED")
            finally:
                agent_client.close()
        except Exception:
            LOGGER.exception("AGENT_EXECUTE_EXCEPTION")

    except Exception:
        LOGGER.exception("SOLVE_EXCEPTION — returning completed anyway")

    return SolveResponse(status="completed")


@app.exception_handler(Exception)
async def _handle_exception(request: Request, exc: Exception) -> JSONResponse:
    LOGGER.exception("Unhandled exception during /solve")
    return JSONResponse(content={"status": "completed"}, status_code=200)
