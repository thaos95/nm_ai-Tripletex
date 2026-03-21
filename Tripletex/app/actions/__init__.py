from typing import Callable, Dict

from app.actions.credit_note import handle as handle_credit_note
from app.actions.customer import handle as handle_customer
from app.actions.department import handle as handle_department
from app.actions.employee import handle as handle_employee
from app.actions.invoice import handle as handle_invoice
from app.actions.project import handle as handle_project

from app.schemas import Plan
from app.clients.tripletex import TripletexClient

ActionHandler = Callable[[TripletexClient, Plan], Dict[str, object]]

ACTION_HANDLERS: Dict[str, ActionHandler] = {
    "create_employee": handle_employee,
    "create_customer": handle_customer,
    "create_department": handle_department,
    "create_project": handle_project,
    "create_credit_note": handle_credit_note,
    "create_invoice": handle_invoice,
    "create_project_billing": handle_project,
    "register_payment": handle_project,
}
