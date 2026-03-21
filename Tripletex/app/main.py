import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.attachment_parser import parse_attachments
from app.clients.tripletex import TripletexClient
from app.executor import execute_plan
from app.planner import create_plan
from app.schemas import SolveRequest, SolveResponse

LOGGER = logging.getLogger(__name__)

app = FastAPI(title="Tripletex AI Agent", version="1.0")


@app.post("/solve", response_model=SolveResponse)
async def solve(request: SolveRequest) -> SolveResponse:
    LOGGER.info(
        "Received solve request prompt=%s base_url=%s session_token_present=%s",
        request.prompt[:80],
        request.tripletex_credentials.base_url,
        bool(request.tripletex_credentials.session_token),
    )
    attachments = parse_attachments(request.files)
    plan = create_plan(request, attachments=attachments)
    client = TripletexClient(
        base_url=str(request.tripletex_credentials.base_url),
        session_token=request.tripletex_credentials.session_token,
    )
    result = None
    try:
        result = execute_plan(client, plan)
        write_calls = [op for op in client.operations if op["method"] in {"POST", "PUT", "DELETE", "PATCH"}]
        if plan.task_type.startswith("create") and not write_calls:
            raise RuntimeError("No write calls were executed for create task")
    finally:
        client.close()
    LOGGER.info("Completed plan=%s handler_result=%s", plan.model_dump(), result)
    return SolveResponse(status="completed", plan=plan)


@app.exception_handler(Exception)
async def _handle_exception(request: Request, exc: Exception) -> JSONResponse:
    LOGGER.exception("Unhandled exception during /solve")
    return JSONResponse(content={"detail": str(exc)}, status_code=500)
