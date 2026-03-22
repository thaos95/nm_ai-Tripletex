import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.schemas import ExecutionPlan, ParsedTask, Plan, PlanStep, SolveRequest, TaskType

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword-based task detection (fallback when LLM is unavailable)
# Order matters: more specific patterns first to avoid false positives.
# ---------------------------------------------------------------------------

TASK_KEYWORDS: List[Tuple[str, List[str]]] = [
    # --- specific multi-word patterns first ---
    ("correct_ledger_errors", [
        "feil i hovudboka", "feil i hovedboka", "feil i hovedbok", "feil i hovudbok",
        "korriger alle feil", "korriger feil", "correct errors", "correct the errors",
        "korrigere feil", "rette bilag", "correcting entries", "correcting vouchers",
        "fehler korrigieren", "erreurs comptables", "corrigir erros",
        "duplikat bilag", "duplicate voucher", "feil konto", "wrong account",
        "manglande mva", "missing vat", "feil beløp", "wrong amount",
    ]),
    ("bank_reconciliation", [
        "avstem", "bankutskrift", "bank statement", "reconcil",
        "bank reconcil", "rapprochez", "relevé bancaire", "releve bancaire",
        "kontoavstemming", "bankavstemming", "bankabstimmung",
        "conciliación bancaria", "conciliacion bancaria",
        "reconciliação bancária", "reconciliacao bancaria",
    ]),
    ("reverse_payment", [
        "reverser betaling", "reverser betalinga", "reverser betalingen",
        "reverse payment", "returned by the bank", "returnert av banken",
        "zurückgebucht", "zuruckgebucht", "stornieren sie die zahlung",
        "annuler le paiement", "cancel the payment",
    ]),
    ("create_project_billing", [
        "prosjektfaktura", "prosjektfakturering", "project billing",
        "fastpris", "delbetaling", "partial billing",
        "timesats", "hourly rate", "stundensatz",
        "fakturer kunden", "invoice the customer",
    ]),
    ("create_supplier_invoice", [
        "leverandorfaktura", "supplier invoice", "vendor invoice",
        "lieferantenrechnung", "mottatt faktura", "received invoice",
        "inngaende faktura", "incoming invoice",
    ]),
    ("create_dimension_voucher", [
        "dimensjon", "dimension", "dimensão", "dimensao",
        "contabilística", "contabilistica",
    ]),
    ("create_payroll_voucher", [
        "payroll", "lonn", "lønn", "salary", "gehalt", "salaire",
        "bonus", "base salary", "baseSalary",
    ]),
    ("create_credit_note", [
        "kreditnota", "credit note", "creditnota", "gutschrift",
        "nota de credito", "nota de crédito", "note de crédit",
    ]),
    ("create_travel_expense", [
        "reiseregning", "reiserekning", "travel expense", "expense report",
        "despesa de viagem", "spesen", "frais de voyage",
        "gastos de viaje", "diett", "per diem",
    ]),
    ("update_travel_expense", [
        "oppdater reiseregning", "oppdater reiserekning",
        "update travel expense",
    ]),
    ("delete_travel_expense", [
        "slett reiseregning", "slett reiserekning",
        "delete travel expense", "remove travel expense",
    ]),
    ("delete_voucher", [
        "slett bilag", "delete voucher", "remove voucher",
        "löschen buchung", "loschen buchung",
    ]),
    ("register_payment", [
        "registrer betaling", "register payment", "full payment",
        "payment on this invoice", "registe o pagamento", "pagamento total",
        "registre le paiement", "paiement total", "registre el pago",
        "vollständige zahlung", "vollstandige zahlung", "bezahlen",
    ]),
    # --- update/search/list operations ---
    ("update_employee", [
        "oppdater ansatt", "update employee", "endre ansatt",
        "aktualisieren mitarbeiter",
    ]),
    ("update_customer", [
        "oppdater kunde", "update customer", "endre kunde",
        "aktualisieren kunde",
    ]),
    ("list_employees", [
        "hent ansatte", "list employees", "vis ansatte",
    ]),
    ("search_customers", [
        "finn kunder", "finn alle kunder", "search customers",
        "søk kunder", "sok kunder",
    ]),
    ("list_ledger_accounts", [
        "kontoplan", "ledger account", "chart of accounts",
    ]),
    ("list_ledger_postings", [
        "hovedboksposteringer", "ledger posting", "postings",
    ]),
    # --- entity creation (broader patterns) ---
    ("create_department", [
        "avdeling", "avdelinger", "avdelingar", "department",
        "departamento", "abteilung", "département", "departement",
    ]),
    ("create_customer", [
        "kunde", "customer", "cliente", "client",
        "leverandor", "leverandør", "supplier", "lieferant", "fournisseur",
        "fornecedor",
    ]),
    ("create_employee", [
        "ansatt", "tilsett", "tilsatt", "employee", "empleado",
        "funcionario", "mitarbeiter", "employé", "employe",
    ]),
    ("create_product", [
        "produkt", "produktet", "product", "producto", "produto",
        "produit", "produkt",
    ]),
    ("create_project", [
        "prosjekt", "prosjektet", "project", "proyecto", "projeto",
        "projekt", "projet",
    ]),
    ("create_order", [
        "ordre", "order", "pedido", "bestellung", "commande", "auftrag",
    ]),
    ("create_invoice", [
        "faktura", "invoice", "factura", "fatura", "rechnung", "facture",
    ]),
]

LANGUAGE_MARKERS: Dict[str, List[str]] = {
    "nb": ["kunde", "faktura", "prosjekt", "opprett", "ansatt"],
    "nn": ["tilsett", "reiserekning", "avdelingar", "gjeld"],
    "en": ["customer", "invoice", "project", "create", "employee"],
    "es": ["cliente", "factura", "proyecto", "crear", "empleado"],
    "pt": ["cliente", "fatura", "projeto", "criar", "fornecedor"],
    "de": ["kunde", "rechnung", "projekt", "erstellen", "mitarbeiter"],
    "fr": ["client", "facture", "projet", "créez", "employé"],
}


def _keyword_matches(keyword: str, text: str) -> bool:
    if " " in keyword:
        return keyword in text
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
    lang_scores: Dict[str, int] = {}
    for lang, markers in LANGUAGE_MARKERS.items():
        for marker in markers:
            if marker in normalized:
                lang_scores[lang] = lang_scores.get(lang, 0) + 1
    if not lang_scores:
        return "unknown"
    return max(lang_scores.items(), key=lambda x: x[1])[0]


# ---------------------------------------------------------------------------
# build_plan: converts a ParsedTask into an ExecutionPlan with named steps
# ---------------------------------------------------------------------------

PLAN_STEPS: Dict[str, List[str]] = {
    "create_employee": ["create-employee"],
    "update_employee": ["find-employee", "update-employee"],
    "list_employees": ["list-employees"],
    "create_customer": ["create-customer"],
    "update_customer": ["find-customer", "update-customer"],
    "search_customers": ["search-customers"],
    "create_product": ["create-product"],
    "create_project": ["resolve-project-customer", "create-project"],
    "create_department": ["create-department"],
    "create_order": ["resolve-order-customer", "resolve-order-product", "create-order"],
    "create_invoice": ["resolve-invoice-customer", "resolve-invoice-product", "create-order", "create-invoice"],
    "create_supplier_invoice": ["resolve-supplier", "create-supplier-invoice"],
    "create_credit_note": ["resolve-credit-customer", "resolve-credit-invoice", "create-credit-note"],
    "create_project_billing": [
        "resolve-billing-customer",
        "resolve-billing-project-manager",
        "create-billing-project",
        "create-billing-order",
        "create-billing-invoice",
    ],
    "create_dimension_voucher": ["create-dimension", "create-dimension-values", "create-dimension-voucher"],
    "create_payroll_voucher": ["create-payroll-voucher"],
    "create_travel_expense": ["create-travel-expense"],
    "update_travel_expense": ["find-travel-expense", "update-travel-expense"],
    "delete_travel_expense": ["lookup-travel-expense", "delete-travel-expense"],
    "delete_voucher": ["delete-voucher"],
    "register_payment": ["resolve-payment-customer", "resolve-payment-invoice", "register-payment"],
    "reverse_payment": ["resolve-reversal-customer", "resolve-reversal-invoice", "reverse-payment"],
    "list_ledger_accounts": ["list-ledger-accounts"],
    "list_ledger_postings": ["list-ledger-postings"],
    "correct_ledger_errors": ["list-postings", "create-correcting-vouchers"],
    "bank_reconciliation": ["parse-bank-statement", "match-invoices", "register-payments"],
    "unsupported": [],
}


def build_plan(parsed_task: ParsedTask, raw_prompt: str = "") -> ExecutionPlan:
    task_type_str = parsed_task.task_type.value if isinstance(parsed_task.task_type, TaskType) else str(parsed_task.task_type)
    step_names = list(PLAN_STEPS.get(task_type_str, []))

    # Optimization: skip product resolution for invoices when description is present
    if task_type_str == "create_invoice":
        invoice_desc = parsed_task.related_entities.get("invoice", {}).get("description")
        order_desc = parsed_task.related_entities.get("order", {}).get("description")
        if invoice_desc or order_desc:
            step_names = [s for s in step_names if s != "resolve-invoice-product"]

    steps = [
        PlanStep(id=f"step-{i+1}", name=name, action=name, details={})
        for i, name in enumerate(step_names)
    ]
    return ExecutionPlan(task=parsed_task, steps=steps, raw_prompt=raw_prompt)


# ---------------------------------------------------------------------------
# create_plan: legacy entry point used by main.py (keyword-only)
# ---------------------------------------------------------------------------

def create_plan(
    request: SolveRequest, attachments: Optional[List[Dict[str, Any]]] = None
) -> Plan:
    task_type = _detect_task_type(request.prompt)
    language = _detect_language(request.prompt)

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
