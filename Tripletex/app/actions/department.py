import logging
from typing import Dict, Any, List

from app.clients.tripletex import TripletexClient
from app.schemas import Plan

LOGGER = logging.getLogger(__name__)


def _extract_department_names(prompt: str) -> List[str]:
    if ":" not in prompt:
        return []
    payload = prompt.split(":", 1)[1]
    payload = payload.replace(" og ", ", ")
    payload = payload.replace(" and ", ", ")
    segments = [name.strip().strip(".") for name in payload.split(",") if name.strip()]
    return segments


def handle(client: TripletexClient, plan: Plan) -> Dict[str, Any]:
    details = plan.steps[0].details.get("prompt", "") if plan.steps else ""
    department_names = _extract_department_names(details)

    print("DEPARTMENT HANDLER CALLED")
    print("DEPARTMENT DETAILS:", details)
    print("DEPARTMENT NAMES:", department_names)

    created = []
    for name in department_names:
        payload = {"name": name}
        LOGGER.info("Creating department name=%s payload=%s", name, payload)
        response = client.post("/department", payload)
        created.append(
            {"name": name, "response": {"status": response.get("status", 200), "data": response}}
        )

    if not department_names:
        LOGGER.warning("No department names extracted from plan prompt=%s", details)

    return {"status": "handled", "task": plan.task_type, "departments": created}