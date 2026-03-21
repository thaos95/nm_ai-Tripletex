import httpx
from typing import Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status

from app.attachments.service import decode_files, describe_attachments, extract_attachment_text, summarize_attachment_hints
from app.clients.tripletex import TripletexClient, TripletexClientError
from app.config import settings
from app.error_handling import TripletexErrorCategory, classify_tripletex_error
from app.logging_utils import get_logger
from app.parser import parse_prompt
from app.planner import build_plan
from app.prompt_lab import prompt_lab_page
from app.preflight import PREFLIGHT_ENFORCED_TASKS, validate_preflight
from app.schemas import InspectRequest, InspectResponse, SolveRequest, SolveResponse, TaskType, ValidateRequest, ValidateResponse
from app.task_contracts import get_task_contract
from app.validator import validate_and_normalize_task
from app.workflow import build_workflow_plan, execute_workflow, parse_workflow
from app.workflows.executor import execute_plan

logger = get_logger()
app = FastAPI(title="Tripletex Agent", version="0.1.0")

_ENVIRONMENT_BLOCKERS: Dict[str, str] = {}


def _base_url_key(base_url: str) -> str:
    return base_url.rstrip("/")


def _environment_block_summary(base_url: str) -> Optional[str]:
    return _ENVIRONMENT_BLOCKERS.get(_base_url_key(base_url))


def _record_environment_block(base_url: str, summary: str) -> None:
    key = _base_url_key(base_url)
    _ENVIRONMENT_BLOCKERS.setdefault(key, summary)


def _is_ledger_only_block(preflight_response) -> bool:
    failure_codes = {check.code for check in preflight_response.checks if check.result == "FAIL" and check.code}
    return bool(failure_codes) and failure_codes <= {"LEDGER_ACCOUNT_MISSING"}


def require_api_key(authorization: Optional[str] = Header(default=None)) -> None:
    if not settings.api_key:
        return
    expected = f"Bearer {settings.api_key}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def get_tripletex_client(
    request: SolveRequest,
    transport: Optional[httpx.BaseTransport] = None,
) -> TripletexClient:
    return TripletexClient(
        base_url=str(request.tripletex_credentials.base_url),
        session_token=request.tripletex_credentials.session_token,
        verify_tls=settings.verify_tls,
        transport=transport,
    )


def get_client_transport() -> Optional[httpx.BaseTransport]:
    return None


def build_parsing_input(prompt: str, files) -> str:
    decoded_files = decode_files(files)
    attachment_text = extract_attachment_text(decoded_files)
    attachment_hints = summarize_attachment_hints(attachment_text)
    attachment_description = describe_attachments(decoded_files)
    parsing_input = prompt
    if attachment_description:
        parsing_input = "{0}\n\nAttachment metadata:\n{1}".format(parsing_input, attachment_description)
    if attachment_hints:
        parsing_input = "{0}\n\nAttachment hints:\n{1}".format(parsing_input, attachment_hints)
    if attachment_text:
        parsing_input = "{0}\n\nAttachment text:\n{1}".format(parsing_input, attachment_text)
    return parsing_input


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/lab")
def prompt_lab():
    return prompt_lab_page()


@app.post("/inspect", response_model=InspectResponse, dependencies=[Depends(require_api_key)])
def inspect_prompt(request: InspectRequest) -> InspectResponse:
    parsing_input = build_parsing_input(request.prompt, request.files)
    tasks, segments = parse_workflow(parsing_input)
    if not segments:
        parsed_task = parse_prompt(parsing_input)
        validation = validate_and_normalize_task(parsed_task)
        plan_obj = build_plan(validation.parsed_task)
        plan = [{"name": step.name, "resource": step.resource, "action": step.action} for step in plan_obj.steps]
        warnings = validation.warnings
    else:
        validations, plan, warnings = build_workflow_plan(tasks)
        validation = validations[-1]
    return InspectResponse(
        parsing_input=parsing_input,
        parsed_task=validation.parsed_task,
        plan=plan,
        warnings=warnings,
        safety=validation.safety,
        blocking_error=validation.blocking_error,
    )


@app.post("/validate", response_model=ValidateResponse, dependencies=[Depends(require_api_key)])
def validate_request(
    request: ValidateRequest,
    transport: Optional[httpx.BaseTransport] = Depends(get_client_transport),
) -> ValidateResponse:
    parsing_input = build_parsing_input(request.prompt, request.files)
    parsed_task = parse_prompt(parsing_input)
    validation = validate_and_normalize_task(parsed_task)
    client = get_tripletex_client(request, transport)
    try:
        return validate_preflight(client, validation.parsed_task)
    finally:
        client.close()


@app.post("/solve", response_model=SolveResponse, dependencies=[Depends(require_api_key)])
def solve(
    request: SolveRequest,
    transport: Optional[httpx.BaseTransport] = Depends(get_client_transport),
) -> SolveResponse:
    decoded_files = decode_files(request.files)
    parsing_input = build_parsing_input(request.prompt, request.files)

    tasks, segments = parse_workflow(parsing_input)
    if not segments:
        parsed_task = parse_prompt(parsing_input)
        validation = validate_and_normalize_task(parsed_task)
        parsed_task = validation.parsed_task
        plan = build_plan(parsed_task)
        warnings = validation.warnings
    else:
        validations, _, warnings = build_workflow_plan(tasks)
        validation = validations[-1]
        parsed_task = validation.parsed_task
        plan = None

    logger.info(
        "solve_start task_type=%s language=%s attachments=%s allowed_endpoints=%r prerequisites=%r prompt=%r parsed_fields=%r match_fields=%r related=%r",
        parsed_task.task_type,
        parsed_task.language_hint,
        len(decoded_files),
        get_task_contract(parsed_task.task_type).allowed_endpoints,
        get_task_contract(parsed_task.task_type).prerequisites,
        request.prompt[:500],
        parsed_task.fields,
        parsed_task.match_fields,
        parsed_task.related_entities,
    )
    if warnings:
        logger.warning(
            "solve_validation_warnings task_type=%s safety=%s warnings=%r",
            parsed_task.task_type,
            validation.safety,
            warnings,
        )
    if validation.blocking_error:
        logger.error(
            "solve_validation_blocked task_type=%s detail=%s prompt=%r",
            parsed_task.task_type,
            validation.blocking_error,
            request.prompt[:500],
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=validation.blocking_error)

    if parsed_task.task_type == TaskType.UNSUPPORTED:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unsupported task")

    base_url = str(request.tripletex_credentials.base_url)
    client = get_tripletex_client(request, transport)
    try:
        if settings.enable_preflight and parsed_task.task_type in PREFLIGHT_ENFORCED_TASKS:
            cached_reason = _environment_block_summary(base_url)
            if cached_reason:
                logger.warning(
                    "solve_preflight_cached_block task_type=%s summary=%s",
                    parsed_task.task_type,
                    cached_reason,
                )
                raise HTTPException(
                    status_code=status.HTTP_424_FAILED_DEPENDENCY,
                    detail=f"environment_blocked: {cached_reason}",
                )
            preflight_response = validate_preflight(client, parsed_task)
            ledger_only_block = _is_ledger_only_block(preflight_response)
            if ledger_only_block:
                logger.warning(
                    "solve_preflight_ledger_issue task_type=%s summary=%s checks=%r",
                    parsed_task.task_type,
                    preflight_response.summary,
                    [check.dict() for check in preflight_response.checks],
                )
            elif not preflight_response.can_continue:
                failure_type = (
                    "missing_prerequisite"
                    if any(check.code in {"COMPANY_BANK_ACCOUNT_MISSING", "CUSTOMER_BANK_ACCOUNT_MISSING"} for check in preflight_response.checks)
                    else "user_input_not_supported"
                )
                logger.warning(
                    "solve_preflight_blocked task_type=%s failure_type=%s summary=%s checks=%r",
                    parsed_task.task_type,
                    failure_type,
                    preflight_response.summary,
                    [check.dict() for check in preflight_response.checks],
                )
                raise HTTPException(
                    status_code=status.HTTP_424_FAILED_DEPENDENCY,
                    detail=f"{failure_type}: {preflight_response.summary}",
                )
        if not segments:
            result = execute_plan(client, plan)
        else:
            result = execute_workflow(client, tasks)
    except ValueError as exc:
        logger.exception(
            "solve_failed_value_error task_type=%s prompt=%r",
            parsed_task.task_type,
            request.prompt[:500],
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    except TripletexClientError as exc:
        classified = classify_tripletex_error(exc)
        logger.exception(
            "solve_failed task_type=%s error_category=%s recoverable=%s prompt=%r",
            parsed_task.task_type,
            classified.category.value,
            classified.recoverable,
            request.prompt[:500],
        )
        if classified.category == TripletexErrorCategory.VALIDATION_ENVIRONMENT:
            _record_environment_block(base_url, classified.summary)
        if classified.category in {
            TripletexErrorCategory.UNAUTHORIZED,
            TripletexErrorCategory.WRONG_ENDPOINT,
        }:
            return SolveResponse()
        if classified.category == TripletexErrorCategory.SERVER_ERROR:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=classified.summary)
        detail = classified.summary
        if classified.category == TripletexErrorCategory.VALIDATION_PREREQUISITE:
            detail = f"missing_prerequisite: {detail}"
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
    finally:
        client.close()

    logger.info(
        "solve_completed task_type=%s operations=%s",
        result.task_type,
        len(result.operations),
    )
    return SolveResponse()
