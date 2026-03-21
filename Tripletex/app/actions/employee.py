import logging
import re
from datetime import date
from typing import Dict, Any

from app.clients.tripletex import TripletexClient
from app.schemas import Plan

LOGGER = logging.getLogger(__name__)


def _extract_employee_data(prompt: str) -> Dict[str, str]:
    name_match = re.search(r"heter\s+([A-Za-zæøåÆØÅ]+)\s+([A-Za-zæøåÆØÅ]+)", prompt, re.IGNORECASE)
    email_match = re.search(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9-.]+", prompt)
    name = name_match.group(1).strip() if name_match else "Ola"
    surname = name_match.group(2).strip() if name_match else "Nordmann"
    email = email_match.group(0) if email_match else f"{name.lower()}.{surname.lower()}@example.com"
    return {"firstName": name, "lastName": surname, "email": email}


def handle(client: TripletexClient, plan: Plan) -> Dict[str, Any]:
    details = plan.steps[0].details if plan.steps else {}
    prompt = details.get("prompt", "")
    employee_data = _extract_employee_data(prompt)
    payload = {
        "firstName": employee_data["firstName"],
        "lastName": employee_data["lastName"],
        "email": employee_data["email"],
        "userType": 1,
        "employments": [
            {
                "isActive": True,
                "startDate": date.today().isoformat(),
            }
        ],
    }
    LOGGER.info("Creating employee payload=%s", payload)
    response = client.post("/employee", payload)
    LOGGER.info("Employee creation response status=%s body=%s", response.get("status", 200), response)
    return {"status": "created", "task": plan.task_type, "employee": response}
