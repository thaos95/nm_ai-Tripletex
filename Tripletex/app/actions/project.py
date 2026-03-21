import logging
import re
from datetime import date
from typing import Any, Dict, Optional

from app.errors import MissingPrerequisiteError

from app.clients.tripletex import TripletexClient
from app.schemas import Plan

LOGGER = logging.getLogger(__name__)


def _extract_project_info(prompt: str) -> Dict[str, str]:
    name_match = re.search(r"prosjekt som heter\s+([A-Za-z0-9æøåÆØÅ &\\-]+)", prompt, re.IGNORECASE)
    customer_match = re.search(r"kunden\s+([A-Za-z0-9æøåÆØÅ &\\-]+)", prompt, re.IGNORECASE)
    project_name = name_match.group(1).strip() if name_match else "Unnamed Project"
    customer_name = customer_match.group(1).strip() if customer_match else ""
    return {"project_name": project_name, "customer_name": customer_name}


def _split_name(full_name: str) -> Dict[str, str]:
    parts = [part for part in re.split(r"\s+", full_name.strip()) if part]
    first_name = parts[0] if parts else "Projekt"
    last_name = " ".join(parts[1:]) if len(parts) > 1 else "Manager"
    return {"first_name": first_name, "last_name": last_name}


def _find_or_create_employee(client: TripletexClient, full_name: str) -> Optional[int]:
    parsed = _split_name(full_name)
    params = {
        "fields": "id,firstName,lastName",
        "count": 200,
        "firstName": parsed["first_name"],
        "lastName": parsed["last_name"],
    }
    response = client.get("/employee", params=params)
    for entry in response.get("values", []):
        if (
            entry.get("firstName", "").lower() == parsed["first_name"].lower()
            and entry.get("lastName", "").lower() == parsed["last_name"].lower()
        ):
            return entry.get("id")
    payload = {
        "firstName": parsed["first_name"],
        "lastName": parsed["last_name"],
        "email": f"{parsed['first_name'].lower()}.{parsed['last_name'].lower()}@example.com",
        "userType": 1,
        "employments": [{"isActive": True, "startDate": date.today().isoformat()}],
    }
    created = client.post("/employee", payload)
    created_id = created.get("value", {}).get("id") or created.get("id")
    if created_id:
        LOGGER.info("Created project manager employee id=%s name=%s", created_id, full_name)
    return created_id


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


def _extract_project_manager(prompt: str) -> Optional[str]:
    match = re.search(r"prosjektleder\s+([A-Za-zæøåÆØÅ ]+)", prompt, re.IGNORECASE)
    if match:
        return match.group(1).strip().strip(",.")
    return None


def handle(client: TripletexClient, plan: Plan) -> Dict[str, Any]:
    details = plan.steps[0].details if plan.steps else {}
    prompt = details.get("prompt", "")
    info = _extract_project_info(prompt)
    project_leader = _extract_project_manager(prompt)
    if not project_leader:
        raise MissingPrerequisiteError("project_manager", "Prosjektleder må navngis for å opprette prosjekt.")
    customer_id = _find_customer_id(client, info["customer_name"])
    payload: Dict[str, Any] = {
        "name": info["project_name"],
        "startDate": date.today().isoformat(),
    }
    if customer_id:
        payload["customer"] = {"id": customer_id}
    manager_id = _find_or_create_employee(client, project_leader)
    if manager_id is None:
        raise MissingPrerequisiteError("project_manager", "Kunne ikke opprette eller finne prosjektleder.")
    payload["projectManager"] = {"id": manager_id}
    LOGGER.info("Creating project payload=%s", payload)
    response = client.post("/project", payload)
    LOGGER.info("Project creation response status=%s body=%s", response.get("status", 200), response)
    return {"status": "created", "task": plan.task_type, "project": response}
