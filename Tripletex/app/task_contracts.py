from dataclasses import dataclass, field
from typing import Dict, List

from app.error_handling import TripletexErrorCategory
from app.schemas import TaskType


@dataclass(frozen=True)
class TaskContract:
    task_type: TaskType
    allowed_endpoints: List[str]
    prerequisites: List[str] = field(default_factory=list)
    recoverable_errors: List[TripletexErrorCategory] = field(default_factory=list)
    terminal_errors: List[TripletexErrorCategory] = field(default_factory=list)


TASK_CONTRACTS: Dict[TaskType, TaskContract] = {
    TaskType.CREATE_CUSTOMER: TaskContract(
        task_type=TaskType.CREATE_CUSTOMER,
        allowed_endpoints=["/customer"],
        prerequisites=["customer name"],
    ),
    TaskType.CREATE_PRODUCT: TaskContract(
        task_type=TaskType.CREATE_PRODUCT,
        allowed_endpoints=["/product"],
        prerequisites=["product name"],
    ),
    TaskType.CREATE_PROJECT: TaskContract(
        task_type=TaskType.CREATE_PROJECT,
        allowed_endpoints=["/customer", "/employee", "/project"],
        prerequisites=["project name"],
        recoverable_errors=[TripletexErrorCategory.NO_RESULTS],
        terminal_errors=[TripletexErrorCategory.WRONG_ENDPOINT, TripletexErrorCategory.UNAUTHORIZED],
    ),
    TaskType.CREATE_ORDER: TaskContract(
        task_type=TaskType.CREATE_ORDER,
        allowed_endpoints=["/customer", "/product", "/order"],
        prerequisites=["customer", "order line source"],
        recoverable_errors=[TripletexErrorCategory.NO_RESULTS],
        terminal_errors=[TripletexErrorCategory.WRONG_ENDPOINT, TripletexErrorCategory.UNAUTHORIZED],
    ),
    TaskType.CREATE_INVOICE: TaskContract(
        task_type=TaskType.CREATE_INVOICE,
        allowed_endpoints=["/customer", "/product", "/ledger/account", "/order", "/invoice"],
        prerequisites=["customer", "order line source"],
        recoverable_errors=[
            TripletexErrorCategory.NO_RESULTS,
            TripletexErrorCategory.VALIDATION_MISSING_FIELDS,
            TripletexErrorCategory.VALIDATION_GENERIC,
        ],
        terminal_errors=[
            TripletexErrorCategory.UNAUTHORIZED,
            TripletexErrorCategory.WRONG_ENDPOINT,
            TripletexErrorCategory.VALIDATION_ENVIRONMENT,
        ],
    ),
    TaskType.CREATE_SUPPLIER_INVOICE: TaskContract(
        task_type=TaskType.CREATE_SUPPLIER_INVOICE,
        allowed_endpoints=["/supplier", "/supplierInvoice"],
        prerequisites=["supplier", "amount", "supplier invoice number"],
        recoverable_errors=[TripletexErrorCategory.NO_RESULTS, TripletexErrorCategory.VALIDATION_MISSING_FIELDS],
        terminal_errors=[
            TripletexErrorCategory.UNAUTHORIZED,
            TripletexErrorCategory.WRONG_ENDPOINT,
            TripletexErrorCategory.VALIDATION_ENVIRONMENT,
        ],
    ),
    TaskType.CREATE_CREDIT_NOTE: TaskContract(
        task_type=TaskType.CREATE_CREDIT_NOTE,
        allowed_endpoints=["/customer", "/order", "/invoice"],
        prerequisites=["customer", "order line source"],
        recoverable_errors=[TripletexErrorCategory.NO_RESULTS, TripletexErrorCategory.VALIDATION_GENERIC],
        terminal_errors=[TripletexErrorCategory.UNAUTHORIZED, TripletexErrorCategory.WRONG_ENDPOINT],
    ),
    TaskType.CREATE_PROJECT_BILLING: TaskContract(
        task_type=TaskType.CREATE_PROJECT_BILLING,
        allowed_endpoints=["/customer", "/employee", "/project", "/order", "/invoice"],
        prerequisites=["project name", "customer", "amount"],
        recoverable_errors=[TripletexErrorCategory.NO_RESULTS, TripletexErrorCategory.VALIDATION_GENERIC],
        terminal_errors=[
            TripletexErrorCategory.UNAUTHORIZED,
            TripletexErrorCategory.WRONG_ENDPOINT,
            TripletexErrorCategory.VALIDATION_ENVIRONMENT,
        ],
    ),
    TaskType.CREATE_DIMENSION_VOUCHER: TaskContract(
        task_type=TaskType.CREATE_DIMENSION_VOUCHER,
        allowed_endpoints=["/ledger/accountingDimensionName", "/ledger/accountingDimensionValue", "/ledger/voucher"],
        prerequisites=["dimension name", "dimension value", "account number", "amount"],
        recoverable_errors=[TripletexErrorCategory.NO_RESULTS, TripletexErrorCategory.VALIDATION_MISSING_FIELDS],
        terminal_errors=[TripletexErrorCategory.UNAUTHORIZED, TripletexErrorCategory.WRONG_ENDPOINT],
    ),
    TaskType.CREATE_TRAVEL_EXPENSE: TaskContract(
        task_type=TaskType.CREATE_TRAVEL_EXPENSE,
        allowed_endpoints=["/employee", "/travelExpense"],
        prerequisites=["amount"],
        recoverable_errors=[TripletexErrorCategory.NO_RESULTS],
        terminal_errors=[TripletexErrorCategory.UNAUTHORIZED, TripletexErrorCategory.WRONG_ENDPOINT],
    ),
    TaskType.DELETE_VOUCHER: TaskContract(
        task_type=TaskType.DELETE_VOUCHER,
        allowed_endpoints=["/ledger/voucher"],
        prerequisites=["voucher id"],
        terminal_errors=[TripletexErrorCategory.UNAUTHORIZED, TripletexErrorCategory.WRONG_ENDPOINT],
    ),
}


def get_task_contract(task_type: TaskType) -> TaskContract:
    return TASK_CONTRACTS.get(
        task_type,
        TaskContract(task_type=task_type, allowed_endpoints=[]),
    )
