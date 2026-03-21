from typing import Any, Dict
import logging

from app.actions import ACTION_HANDLERS
from app.clients.tripletex import TripletexClient
from app.schemas import Plan

LOGGER = logging.getLogger(__name__)


def execute_plan(client: TripletexClient, plan: Plan) -> Dict[str, Any]:
    LOGGER.info("Executing plan | task_type=%s steps=%s", plan.task_type, [step.model_dump() for step in plan.steps])

    task_handler = ACTION_HANDLERS.get(plan.task_type)
    handler = task_handler or ACTION_HANDLERS.get(plan.steps[0].action if plan.steps else "")

    if not handler:
        raise RuntimeError(f"No handler found for task_type={plan.task_type}")

    print("EXECUTOR TASK TYPE:", plan.task_type)
    print("EXECUTOR HANDLER:", handler.__module__, handler.__name__)

    LOGGER.info("Dispatching to handler=%s", handler.__name__)
    result = handler(client, plan)
    LOGGER.info("Handler result=%s", result)
    return result