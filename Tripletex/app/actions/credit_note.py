import logging
import re
from datetime import date
from typing import Any, Dict, Optional

from app.clients.tripletex import TripletexClient
from app.schemas import Plan

LOGGER = logging.getLogger(__name__)


def _extract_invoice_id(prompt: str) -> Optional[int]:
    match = re.search(r"faktura(?:nr\.?|en)?\s*#?(\d+)", prompt, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def handle(client: TripletexClient, plan: Plan) -> Dict[str, Any]:
    details = plan.steps[0].details if plan.steps else {}
    prompt = details.get("prompt", "")
    invoice_id = _extract_invoice_id(prompt)
    if not invoice_id:
        raise RuntimeError("No invoice id found for credit note")
    params = {"date": date.today().isoformat()}
    LOGGER.info("Creating credit note for invoice=%s params=%s", invoice_id, params)
    response = client.put(f"/invoice/{invoice_id}/:createCreditNote", params=params)
    LOGGER.info("Credit note response status=%s body=%s", response.get("status", 200), response)
    return {"status": "created", "task": plan.task_type, "credit_note": response}
