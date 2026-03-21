import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.schemas import Plan, PlanStep, SolveRequest

LOGGER = logging.getLogger(__name__)

TASK_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("create_department", ["avdeling", "avdelinger", "department", "departamento"]),
    ("create_customer", ["kunde", "customer", "cliente"]),
    ("create_employee", ["employee", "ansatt", "empleado"]),
    ("create_product", ["produkt", "product", "produto"]),
    ("create_project", ["project", "prosjekt", "proyecto"]),
    ("create_invoice", ["invoice", "faktura", "factura", "facture"]),
    ("register_payment", ["payment", "betaling", "pago"]),
    ("create_project_billing", ["project billing", "prosjektfakturering"]),
    ("create_credit_note", ["credit note", "kreditnota", "creditnota"]),
]

LANGUAGE_MARKERS: Dict[str, List[str]] = {
    "nb": ["kunde", "faktura", "prosjekt"],
    "en": ["customer", "invoice", "project"],
    "es": ["cliente", "factura", "proyecto"],
    "pt": ["cliente", "fatura", "projeto"],
    "nn": ["kunde", "faktura", "prosjekt"],
    "de": ["kunde", "rechnung", "projekt"],
    "fr": ["client", "facture", "projet"],
}


def _keyword_matches(keyword: str, text: str) -> bool:
    pattern = r"\b" + re.escape(keyword) + r"\b"
    return bool(re.search(pattern, text))


def _detect_task_type(prompt: str) -> str:
    normalized = prompt.lower()
    scores: Dict[str, int] = {}
    priority: Dict[str, int] = {}
    for position, (task, keywords) in enumerate(TASK_KEYWORDS):
        priority[task] = position
        for keyword in keywords:
            if _keyword_matches(keyword, normalized):
                scores[task] = scores.get(task, 0) + 1
    if not scores:
        return "unsupported"
    best_task = max(scores.items(), key=lambda item: (item[1], -priority.get(item[0], 0)))[0]
    return best_task


def _detect_language(prompt: str) -> str:
    normalized = prompt.lower()
    for lang, markers in LANGUAGE_MARKERS.items():
        if any(marker in normalized for marker in markers):
            return lang
    return "unknown"


def create_plan(
    request: SolveRequest, attachments: Optional[List[Dict[str, Any]]] = None
) -> Plan:
    task_type = _detect_task_type(request.prompt)
    language = _detect_language(request.prompt)
    
    print("PLANNER TASK TYPE:", task_type)
    print("PLANNER PROMPT:", request.prompt)
    
    LOGGER.info("Planner detected task=%s language=%s prompt=%s", task_type, language, request.prompt[:80])
    step = PlanStep(
        id="step-1",
        name="primary-action",
        action=task_type,
        details={
            "prompt": request.prompt[:400],
            "attachments": attachments or [],
        },
    )
    return Plan(
        language=language, task_type=task_type, primary_entity=task_type, steps=[step]
    )
