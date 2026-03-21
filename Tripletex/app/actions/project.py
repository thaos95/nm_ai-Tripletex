import logging
import re
from datetime import date
from typing import Any, Dict, Optional

from app.clients.tripletex import TripletexClient
from app.schemas import Plan

LOGGER = logging.getLogger(__name__)


def _extract_project_info(prompt: str) -> Dict[str, str]:
    name_match = re.search(r"prosjekt som heter\s+([A-Za-z0-9æøåÆØÅ &\\-]+)", prompt, re.IGNORECASE)
    customer_match = re.search(r"kunden\s+([A-Za-z0-9æøåÆØÅ &\\-]+)", prompt, re.IGNORECASE)
    project_name = name_match.group(1).strip() if name_match else "Unnamed Project"
    customer_name = customer_match.group(1).strip() if customer_match else ""
    return {"project_name": project_name, "customer_name": customer_name}


def _find_customer_id(client: TripletexClient, customer_name: str) -> Optional[int]:
    if not customer_name:
        return None
    response = client.get("/customer", params={"fields": "id,name", "count": 200, "name": customer_name})
    for entry in response.get("values", []):
        if entry.get("name") == customer_name:
            return entry.get("id")
    payload = {"name": customer_name, "isCustomer": True, "isSupplier": False}
    created = client.post("/customer", payload)
    created_id = created.get("value", {}).get("id")
    if created_id:
        LOGGER.info("Created prerequisite customer id=%s name=%s", created_id, customer_name)
    return created_id


def handle(client: TripletexClient, plan: Plan) -> Dict[str, Any]:
    details = plan.steps[0].details if plan.steps else {}
    prompt = details.get("prompt", "")
    info = _extract_project_info(prompt)
    customer_id = _find_customer_id(client, info["customer_name"])
    payload: Dict[str, Any] = {
        "name": info["project_name"],
        "startDate": date.today().isoformat(),
    }
    if customer_id:
        payload["customer"] = {"id": customer_id}
    LOGGER.info("Creating project payload=%s", payload)
    response = client.post("/project", payload)
    LOGGER.info("Project creation response status=%s body=%s", response.get("status", 200), response)
    return {"status": "created", "task": plan.task_type, "project": response}
