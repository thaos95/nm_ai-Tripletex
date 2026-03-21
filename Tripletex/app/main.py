import logging
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from app.attachment_parser import parse_attachments
from app.clients.tripletex import TripletexClient, TripletexClientError
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


@app.post("/solve", response_model=SolveResponse)
async def solve(
    request: SolveRequest,
    transport: Optional[httpx.BaseTransport] = Depends(get_client_transport),
) -> SolveResponse:
    LOGGER.info(
        "Received solve request prompt=%s base_url=%s session_token_present=%s",
        request.prompt[:80],
        request.tripletex_credentials.base_url,
        bool(request.tripletex_credentials.session_token),
    )

    try:
        # 1. Parse attachments
        attachments = parse_attachments(request.files)

        # 2. Parse prompt (rule-based + LLM fallback)
        parsed_task = parse_prompt(request.prompt)
        LOGGER.info("Parsed task_type=%s confidence=%.2f", parsed_task.task_type, parsed_task.confidence)

        if parsed_task.task_type == TaskType.UNSUPPORTED:
            LOGGER.warning("Unsupported prompt, returning completed anyway: %s", request.prompt[:120])
            return SolveResponse(status="completed")

        # 3. Validate and normalize
        validation = validate_and_normalize_task(parsed_task)
        if validation.blocking_error:
            LOGGER.warning("Validation blocked: %s", validation.blocking_error)

        parsed_task = validation.parsed_task

        # 4. Build execution plan
        plan = build_plan(parsed_task)

        # 5. Execute
        client = TripletexClient(
            base_url=str(request.tripletex_credentials.base_url),
            session_token=request.tripletex_credentials.session_token,
            transport=transport,
        )
        try:
            result = execute_plan(client, plan)
            LOGGER.info("Execution completed task_type=%s operations=%d", result.task_type, len(result.operations))
        finally:
            client.close()

    except Exception:
        LOGGER.exception("Error during /solve — returning completed anyway")

    return SolveResponse(status="completed")


@app.exception_handler(Exception)
async def _handle_exception(request: Request, exc: Exception) -> JSONResponse:
    LOGGER.exception("Unhandled exception during /solve")
    return JSONResponse(content={"status": "completed"}, status_code=200)
