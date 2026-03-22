import json
import logging
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.attachment_parser import parse_attachments, attachments_to_text
from app.clients.tripletex import TripletexClient, TripletexClientError
from app.config import settings
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


def _attempt_solve(
    prompt: str,
    request: SolveRequest,
    transport: Optional[httpx.BaseTransport],
    attempt: int = 1,
    thinking_level: str = "medium",
    rag_context: str = "",
) -> Optional[str]:
    """Single solve attempt. Returns None on success, or error description on failure."""
    # Enrich prompt with RAG context on retry
    effective_prompt = prompt
    if rag_context:
        effective_prompt = f"{prompt}\n\n[API Context]\n{rag_context}"
    parsed_task = parse_prompt(effective_prompt, thinking_level=thinking_level)
    _log_parsed_task(parsed_task, attempt)

    if parsed_task.task_type == TaskType.UNSUPPORTED:
        LOGGER.warning("attempt=%d task classified as UNSUPPORTED", attempt)
        return "unsupported"

    validation = validate_and_normalize_task(parsed_task)
    if validation.blocking_error:
        LOGGER.warning("attempt=%d VALIDATION_BLOCKED: %s", attempt, validation.blocking_error)
        return "validation: {0}".format(validation.blocking_error)

    parsed_task = validation.parsed_task
    # Log again after validation (fields may have been normalized)
    _log_parsed_task(parsed_task, attempt)

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
            "EXECUTION attempt=%d task_type=%s operations=%s resource_ids=%s error=%s api_calls=%d",
            attempt, result.task_type, op_names, op_ids, result.error, len(client.operations),
        )
        if result.error:
            return "execution: {0}".format(result.error)
        if len(result.operations) == 0:
            return "execution: zero operations"
        return None  # success
    except MissingPrerequisiteError as exc:
        LOGGER.error("PREREQUISITE_ERROR attempt=%d %s", attempt, exc)
        return "prerequisite: {0}".format(str(exc)[:200])
    except TripletexClientError as exc:
        LOGGER.error(
            "EXECUTION_ERROR attempt=%d status=%s path=%s response=%s",
            attempt, exc.status_code, exc.path, (exc.response_text or "")[:2000],
        )
        return "api_error: {0} {1} {2}".format(exc.status_code, exc.path, str(exc)[:200])
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

        # 2. First attempt
        error = _attempt_solve(enriched_prompt, request, transport, attempt=1)

        # 3. Retry on failure (a 0-score failure is always worse than retrying)
        if error and error != "unsupported":
            # Query RAG for error-specific context to guide retry
            rag_context = ""
            try:
                from app.kb.rag import query_for_error
                rag_results = query_for_error("", error[:200], top_k=3)
                if rag_results:
                    rag_context = "\n".join(r["content"] for r in rag_results)
                    LOGGER.info("RAG_CONTEXT for retry: %d results, %d chars", len(rag_results), len(rag_context))
            except Exception:
                pass  # RAG is optional — never block retry
            LOGGER.info("RETRY first_error=%s thinking=high", error)
            try:
                error2 = _attempt_solve(
                    enriched_prompt, request, transport,
                    attempt=2, thinking_level="high",
                    rag_context=rag_context,
                )
                if error2:
                    LOGGER.warning("RETRY_FAILED: %s", error2)
            except Exception:
                LOGGER.exception("RETRY_EXCEPTION")

    except Exception:
        LOGGER.exception("SOLVE_EXCEPTION — returning completed anyway")

    return SolveResponse(status="completed")


@app.exception_handler(Exception)
async def _handle_exception(request: Request, exc: Exception) -> JSONResponse:
    LOGGER.exception("Unhandled exception during /solve")
    return JSONResponse(content={"status": "completed"}, status_code=200)
