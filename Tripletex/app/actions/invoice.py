import logging
import re
from typing import Dict, Optional

from app.clients.tripletex import TripletexClient
from app.errors import MissingPrerequisiteError
from app.schemas import Plan

LOGGER = logging.getLogger(__name__)


def _extract_invoice_reference(prompt: str) -> Optional[str]:
    match = re.search(r"faktura(?:en)?\s+([A-Za-z0-9æøåÆØÅ]+)", prompt, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def handle(client: TripletexClient, plan: Plan) -> Dict[str, Dict[str, str]]:
    details = plan.steps[0].details if plan.steps else {}
    prompt = details.get("prompt", "")
    invoice_reference = _extract_invoice_reference(prompt)
    if not invoice_reference:
        raise MissingPrerequisiteError("invoice_reference", "Vi trenger faktureferanse eller nummer for å lage ny faktura.")

    raise MissingPrerequisiteError("create_invoice", "create_invoice-støtte er ikke implementert ennå.")
