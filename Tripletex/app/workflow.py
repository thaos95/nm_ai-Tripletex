import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.parser import parse_prompt
from app.planner import build_plan
from app.schemas import ExecutionResult, OperationResult, ParsedTask, TaskType
from app.validator import ValidationResult, validate_and_normalize_task
from app.workflows.executor import execute_plan


MULTI_TASK_SPLIT_RE = re.compile(
    r"\s+(?:and then|then|after that|finally|deretter|s[åa]|til slutt|em seguida|luego|ensuite)\s+",
    re.IGNORECASE,
)


@dataclass
class WorkflowContext:
    customer: Dict[str, object] = field(default_factory=dict)
    product: Dict[str, object] = field(default_factory=dict)
    employee: Dict[str, object] = field(default_factory=dict)
    project: Dict[str, object] = field(default_factory=dict)
    order: Dict[str, object] = field(default_factory=dict)
    invoice: Dict[str, object] = field(default_factory=dict)


def _copy_task(task: ParsedTask) -> ParsedTask:
    return ParsedTask(
        task_type=task.task_type,
        confidence=task.confidence,
        language_hint=task.language_hint,
        fields=dict(task.fields),
        match_fields=dict(task.match_fields),
        related_entities=dict((key, dict(value)) for key, value in task.related_entities.items()),
        attachments_required=task.attachments_required,
        notes=list(task.notes),
    )


def _split_prompt(prompt: str) -> List[str]:
    normalized = prompt.replace("\r\n", "\n").strip()
    if not normalized:
        return []

    coarse_parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", normalized) if part.strip()]
    segments: List[str] = []
    extra_split_re = re.compile(r"\s+(?:og sa|og so|und dann|e depois)\s+", re.IGNORECASE)
    for part in coarse_parts:
        finer = [item.strip(" ,") for item in MULTI_TASK_SPLIT_RE.split(part) if item.strip(" ,")]
        expanded: List[str] = []
        for item in finer if finer else [part]:
            extra_parts = [chunk.strip(" ,") for chunk in extra_split_re.split(item) if chunk.strip(" ,")]
            expanded.extend(extra_parts if extra_parts else [item])
        segments.extend(expanded)
    return segments


def _has_line_source(task: ParsedTask) -> bool:
    product = task.related_entities.get("product", {})
    order = task.related_entities.get("order", {})
    invoice = task.related_entities.get("invoice", {})
    if order.get("id"):
        return True
    if product.get("id") or product.get("name") or product.get("description"):
        return True
    if invoice.get("description") or order.get("description"):
        return True
    return any(key.startswith("order_line_") for key in task.related_entities)


def _merge_missing(target: Dict[str, object], source: Dict[str, object]) -> None:
    for key, value in source.items():
        target.setdefault(key, value)


def _apply_context(task: ParsedTask, context: WorkflowContext) -> ParsedTask:
    enriched = _copy_task(task)

    if enriched.task_type in {
        TaskType.CREATE_PROJECT,
        TaskType.CREATE_PROJECT_BILLING,
        TaskType.CREATE_ORDER,
        TaskType.CREATE_INVOICE,
        TaskType.CREATE_CREDIT_NOTE,
    }:
        if context.customer:
            customer_spec = enriched.related_entities.setdefault("customer", {})
            _merge_missing(customer_spec, context.customer)

    if enriched.task_type in {TaskType.CREATE_PROJECT, TaskType.CREATE_PROJECT_BILLING, TaskType.CREATE_PAYROLL_VOUCHER}:
        if context.employee:
            employee_key = "project_manager" if enriched.task_type != TaskType.CREATE_PAYROLL_VOUCHER else "employee"
            employee_spec = enriched.related_entities.setdefault(employee_key, {})
            _merge_missing(employee_spec, context.employee)

    if enriched.task_type in {TaskType.CREATE_ORDER, TaskType.CREATE_INVOICE, TaskType.CREATE_CREDIT_NOTE}:
        if not _has_line_source(enriched) and context.product:
            product_spec = enriched.related_entities.setdefault("product", {})
            _merge_missing(product_spec, context.product)
        if (
            enriched.task_type == TaskType.CREATE_INVOICE
            and not any(key.startswith("order_line_") for key in enriched.related_entities)
            and context.order.get("id")
        ):
            order_spec = enriched.related_entities.setdefault("order", {})
            _merge_missing(order_spec, context.order)
        if enriched.fields.get("amount") is None and context.product.get("priceExcludingVatCurrency") is not None:
            enriched.fields["amount"] = context.product["priceExcludingVatCurrency"]

    return enriched


def _update_context(context: WorkflowContext, task: ParsedTask, result: ExecutionResult) -> None:
    create_customer = next((op for op in result.operations if op.name == "create-customer" and op.resource_id), None)
    if task.task_type == TaskType.CREATE_CUSTOMER and create_customer is not None:
        context.customer = dict(task.fields)
        context.customer["id"] = create_customer.resource_id

    create_product = next((op for op in result.operations if op.name == "create-product" and op.resource_id), None)
    if task.task_type == TaskType.CREATE_PRODUCT and create_product is not None:
        context.product = dict(task.fields)
        context.product["id"] = create_product.resource_id

    create_employee = next((op for op in result.operations if op.name == "create-employee" and op.resource_id), None)
    if task.task_type == TaskType.CREATE_EMPLOYEE and create_employee is not None:
        context.employee = dict(task.fields)
        context.employee["id"] = create_employee.resource_id

    create_project = next((op for op in result.operations if op.name in {"create-project", "create-billing-project"} and op.resource_id), None)
    if create_project is not None:
        context.project = dict(task.fields)
        context.project["id"] = create_project.resource_id

    create_order = next((op for op in result.operations if op.name == "create-order" and op.resource_id), None)
    if create_order is not None:
        description = (
            task.related_entities.get("order", {}).get("description")
            or task.related_entities.get("invoice", {}).get("description")
            or task.related_entities.get("product", {}).get("description")
            or task.related_entities.get("product", {}).get("name")
        )
        context.order = {"id": create_order.resource_id}
        if description:
            context.order["description"] = description

    create_invoice = next(
        (op for op in result.operations if op.name in {"create-invoice", "create-credit-note", "create-billing-invoice"} and op.resource_id),
        None,
    )
    if create_invoice is not None:
        context.invoice = {"id": create_invoice.resource_id}


def _seed_context_from_task(context: WorkflowContext, task: ParsedTask) -> None:
    if task.task_type == TaskType.CREATE_CUSTOMER:
        context.customer = dict(task.fields)

    if task.task_type == TaskType.CREATE_PRODUCT:
        context.product = dict(task.fields)

    if task.task_type == TaskType.CREATE_EMPLOYEE:
        context.employee = dict(task.fields)

    if task.related_entities.get("customer"):
        _merge_missing(context.customer, task.related_entities["customer"])

    if task.related_entities.get("product"):
        _merge_missing(context.product, task.related_entities["product"])

    if task.related_entities.get("employee"):
        _merge_missing(context.employee, task.related_entities["employee"])

    if task.related_entities.get("project_manager"):
        _merge_missing(context.employee, task.related_entities["project_manager"])

    if task.related_entities.get("order"):
        _merge_missing(context.order, task.related_entities["order"])


def parse_workflow(prompt: str) -> Tuple[List[ParsedTask], List[str]]:
    whole_task = parse_prompt(prompt)
    if whole_task.task_type in {
        TaskType.CREATE_SUPPLIER_INVOICE,
        TaskType.CREATE_PROJECT_BILLING,
        TaskType.CREATE_CREDIT_NOTE,
        TaskType.CREATE_PAYROLL_VOUCHER,
    }:
        return [whole_task], []
    segments = _split_prompt(prompt)
    if len(segments) < 2:
        return [whole_task], []

    parsed_segments: List[ParsedTask] = []
    effective_segments: List[str] = []
    for segment in segments:
        parsed = parse_prompt(segment)
        if parsed.task_type != TaskType.UNSUPPORTED:
            effective_segments.append(segment)
            parsed_segments.append(parsed)
            continue

        if effective_segments:
            effective_segments[-1] = "{0}. {1}".format(effective_segments[-1].rstrip(". "), segment)
            reparsed = parse_prompt(effective_segments[-1])
            if reparsed.task_type != TaskType.UNSUPPORTED:
                parsed_segments[-1] = reparsed

    if len(parsed_segments) < 2:
        return [whole_task], []

    whole_validation = validate_and_normalize_task(whole_task)
    split_validations, _ = validate_workflow(parsed_segments)
    if (
        any(validation.blocking_error for validation in split_validations)
        and not whole_validation.blocking_error
    ):
        return [whole_task], []

    return parsed_segments, effective_segments


def validate_workflow(tasks: List[ParsedTask]) -> Tuple[List[ValidationResult], List[str]]:
    context = WorkflowContext()
    validations: List[ValidationResult] = []
    warnings: List[str] = []

    for task in tasks:
        enriched = _apply_context(task, context)
        validation = validate_and_normalize_task(enriched)
        validations.append(validation)
        warnings.extend(validation.warnings)
        if validation.blocking_error:
            break
        _seed_context_from_task(context, validation.parsed_task)

    return validations, warnings


def build_workflow_plan(tasks: List[ParsedTask]) -> Tuple[List[ValidationResult], List[Dict[str, str]], List[str]]:
    context = WorkflowContext()
    validations: List[ValidationResult] = []
    combined_plan: List[Dict[str, str]] = []
    combined_warnings: List[str] = []

    for task in tasks:
        enriched = _apply_context(task, context)
        validation = validate_and_normalize_task(enriched)
        validations.append(validation)
        combined_warnings.extend(validation.warnings)
        if validation.blocking_error:
            break
        plan = build_plan(validation.parsed_task)
        combined_plan.extend([{"name": step.name, "resource": step.resource, "action": step.action} for step in plan.steps])
        _seed_context_from_task(context, validation.parsed_task)

    return validations, combined_plan, combined_warnings


def execute_workflow(client, tasks: List[ParsedTask]) -> ExecutionResult:
    context = WorkflowContext()
    all_operations: List[OperationResult] = []
    last_task_type = TaskType.UNSUPPORTED

    for task in tasks:
        enriched = _apply_context(task, context)
        validation = validate_and_normalize_task(enriched)
        if validation.blocking_error:
            raise ValueError(validation.blocking_error)
        plan = build_plan(validation.parsed_task)
        result = execute_plan(client, plan)
        all_operations.extend(result.operations)
        _update_context(context, validation.parsed_task, result)
        last_task_type = validation.parsed_task.task_type

    return ExecutionResult(task_type=last_task_type, operations=all_operations)
