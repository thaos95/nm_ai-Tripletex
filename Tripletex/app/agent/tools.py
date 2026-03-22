"""Tools available to the executor agent.

Each tool is a plain function that takes typed arguments and returns a string result.
The agent loop calls these based on LLM tool-call output.
"""
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.clients.tripletex import TripletexClient, TripletexClientError
from app.error_handling import extract_validation_messages
from app.kb.rag import query as rag_query

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Endpoint docs loaded once from the KB markdown
# ---------------------------------------------------------------------------
_ENDPOINT_DOCS: Optional[str] = None
_TASK_REGISTRY: Optional[Dict[str, Any]] = None


def _load_endpoint_docs() -> str:
    global _ENDPOINT_DOCS
    if _ENDPOINT_DOCS is not None:
        return _ENDPOINT_DOCS
    docs_path = Path(__file__).resolve().parent.parent / "kb" / "docs" / "endpoints.md"
    if docs_path.exists():
        _ENDPOINT_DOCS = docs_path.read_text(encoding="utf-8")
    else:
        _ENDPOINT_DOCS = ""
    return _ENDPOINT_DOCS


def _load_task_registry() -> Dict[str, Any]:
    global _TASK_REGISTRY
    if _TASK_REGISTRY is not None:
        return _TASK_REGISTRY
    registry_path = Path(__file__).resolve().parent.parent / "kb" / "task_registry.json"
    if registry_path.exists():
        _TASK_REGISTRY = json.loads(registry_path.read_text(encoding="utf-8"))
    else:
        _TASK_REGISTRY = {}
    return _TASK_REGISTRY


# ---------------------------------------------------------------------------
# Tool: search_api_docs
# ---------------------------------------------------------------------------
def search_api_docs(query: str) -> str:
    """Search KB endpoint docs and RAG index for API information."""
    results: List[str] = []

    # 1. Search RAG index
    rag_results = rag_query(query, top_k=3)
    for r in rag_results:
        results.append("[RAG score={0:.3f}] {1}\n{2}".format(
            r["score"], r["title"], r["content"]
        ))

    # 2. Search endpoint docs by keyword
    docs = _load_endpoint_docs()
    if docs:
        sections = docs.split("\n## ")
        query_lower = query.lower()
        for section in sections:
            first_line = section.split("\n")[0].strip()
            if any(kw in section.lower() for kw in query_lower.split()):
                results.append("[Endpoint Doc] ## {0}\n{1}".format(
                    first_line, section[:500]
                ))

    if not results:
        return "No documentation found for: {0}".format(query)
    return "\n---\n".join(results[:5])


# ---------------------------------------------------------------------------
# Tool: get_endpoint_schema
# ---------------------------------------------------------------------------
def get_endpoint_schema(endpoint: str) -> str:
    """Get the full documentation for a specific endpoint (e.g. '/employee', '/invoice')."""
    docs = _load_endpoint_docs()
    if not docs:
        return "No endpoint documentation available."

    endpoint_clean = endpoint.strip("/").lower()
    sections = docs.split("\n## ")
    matches = []
    for section in sections:
        first_line = section.split("\n")[0].strip()
        if endpoint_clean in first_line.lower():
            matches.append("## {0}\n{1}".format(first_line, section.strip()))

    if matches:
        return "\n\n".join(matches)
    return "No schema found for endpoint: {0}".format(endpoint)


# ---------------------------------------------------------------------------
# Tool: get_task_spec
# ---------------------------------------------------------------------------
def get_task_spec(task_type: str) -> str:
    """Get the full task specification from the KB registry.

    Returns endpoint, method, payload_fields, prerequisites, gotchas, forbidden_fields.
    """
    registry = _load_task_registry()
    spec = registry.get(task_type)
    if spec is None:
        return "No task spec found for: {0}. Available: {1}".format(
            task_type, ", ".join(sorted(registry.keys()))
        )
    return json.dumps(spec, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool: resolve_entity
# ---------------------------------------------------------------------------
def resolve_entity(
    client: TripletexClient,
    entity_type: str,
    search_fields: Dict[str, Any],
) -> str:
    """Find an existing entity by search fields. Returns the entity or 'not found'.

    entity_type: customer, employee, supplier, department, project, product, activity
    search_fields: e.g. {"organizationNumber": "123456789"} or {"name": "Acme Inc"}
    """
    try:
        result = client.find_single(entity_type, search_fields)
        if result:
            return json.dumps(result, default=str, ensure_ascii=False)[:2000]
        return json.dumps({"found": False, "entity_type": entity_type, "searched": search_fields})
    except TripletexClientError as exc:
        return json.dumps({
            "error": True,
            "status_code": exc.status_code,
            "message": str(exc)[:300],
        })


# ---------------------------------------------------------------------------
# Tool: call_api
# ---------------------------------------------------------------------------
def call_api(
    client: TripletexClient,
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> str:
    """Make a Tripletex API call. Returns JSON response or error details."""
    try:
        kwargs: Dict[str, Any] = {}
        if payload is not None:
            kwargs["json"] = payload
        if params is not None:
            kwargs["params"] = params
        response = client._request(method, path, **kwargs)
        return json.dumps(response, default=str, ensure_ascii=False)[:2000]
    except TripletexClientError as exc:
        messages = extract_validation_messages(exc)
        return json.dumps({
            "error": True,
            "status_code": exc.status_code,
            "path": exc.path,
            "validation_messages": messages,
            "response_text": (exc.response_text or "")[:1000],
        }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool: fix_payload (programmatic — no LLM needed)
# ---------------------------------------------------------------------------
_FIELD_NAME_PATTERN = re.compile(
    r'["\']?(\w+)["\']?\s*[:]\s*(?:Feltet eksisterer ikke|Field does not exist|'
    r'er ugyldig|is invalid|Kan ikke være null|Cannot be null)',
    re.IGNORECASE,
)

_FIELD_FROM_MSG_PATTERN = re.compile(
    r'^(\w+)\s*:', re.MULTILINE,
)


def extract_rejected_fields(exc: TripletexClientError) -> List[str]:
    """Extract field names that the API rejected from validation messages."""
    messages = extract_validation_messages(exc)
    raw_text = exc.response_text or ""
    fields: List[str] = []

    for msg in messages:
        # Pattern: "fieldName: Feltet eksisterer ikke i objektet"
        m = _FIELD_FROM_MSG_PATTERN.match(msg)
        if m:
            fields.append(m.group(1))
            continue
        # Pattern: "Field 'fieldName' does not exist"
        m2 = re.search(r"['\"](\w+)['\"]", msg)
        if m2 and ("eksisterer ikke" in msg or "does not exist" in msg or "ugyldig" in msg):
            fields.append(m2.group(1))

    # Also try the raw response text
    for m in _FIELD_NAME_PATTERN.finditer(raw_text):
        field = m.group(1)
        if field not in fields:
            fields.append(field)

    return fields


def fix_payload_from_error(
    payload: Dict[str, Any],
    exc: TripletexClientError,
) -> Optional[Dict[str, Any]]:
    """Remove rejected fields from payload. Returns fixed payload or None if nothing to fix."""
    rejected = extract_rejected_fields(exc)
    if not rejected:
        return None

    fixed = dict(payload)
    removed = []
    for field in rejected:
        if field in fixed:
            del fixed[field]
            removed.append(field)
        # Also check nested structures (e.g., invoiceHeader, orderLines)
        for key, value in list(fixed.items()):
            if isinstance(value, dict) and field in value:
                value = dict(value)
                del value[field]
                fixed[key] = value
                removed.append("{0}.{1}".format(key, field))
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict) and field in item:
                        item = dict(item)
                        del item[field]
                        value[i] = item
                        removed.append("{0}[{1}].{2}".format(key, i, field))

    if removed:
        logger.info("fix_payload removed_fields=%s", removed)
        return fixed
    return None


# ---------------------------------------------------------------------------
# Tool definitions for the agent (JSON schema for LLM)
# ---------------------------------------------------------------------------
TOOL_DEFINITIONS = [
    {
        "name": "search_api_docs",
        "description": "Search Tripletex API documentation and knowledge base for endpoint info, field requirements, and common errors.",
        "parameters": {
            "query": "Search query (e.g. 'POST /employee required fields', '422 vatType error')",
        },
    },
    {
        "name": "get_endpoint_schema",
        "description": "Get full documentation for a specific Tripletex API endpoint.",
        "parameters": {
            "endpoint": "Endpoint path (e.g. '/employee', '/invoice', '/travelExpense')",
        },
    },
    {
        "name": "get_task_spec",
        "description": "Get the full task specification from the knowledge base: endpoint, method, payload fields, prerequisites, gotchas, forbidden fields.",
        "parameters": {
            "task_type": "Task type (e.g. 'create_employee', 'create_invoice', 'register_payment')",
        },
    },
    {
        "name": "resolve_entity",
        "description": "Search for an existing entity in Tripletex (customer, employee, supplier, department, project, product). Returns the entity with its ID if found.",
        "parameters": {
            "entity_type": "Entity type: customer, employee, supplier, department, project, product, activity",
            "search_fields": "Search criteria as JSON object, e.g. {\"organizationNumber\": \"123456789\"} or {\"name\": \"Acme Inc\"}",
        },
    },
    {
        "name": "call_api",
        "description": "Make a Tripletex API call. Returns the response or error details with validation messages.",
        "parameters": {
            "method": "HTTP method: GET, POST, PUT, DELETE",
            "path": "API path (e.g. '/employee', '/ledger/account', '/invoice/{id}/:payment')",
            "payload": "(Optional) JSON body for POST/PUT requests",
            "params": "(Optional) Query parameters",
        },
    },
    {
        "name": "done",
        "description": "Signal that task execution is complete.",
        "parameters": {
            "success": "Whether the task was completed successfully (true/false)",
            "summary": "Brief description of what was done or why it failed",
        },
    },
]
