from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TripletexErrorCategory(str, Enum):
    UNAUTHORIZED = "unauthorized"
    WRONG_ENDPOINT = "wrong_endpoint"
    VALIDATION_MISSING_FIELDS = "validation_missing_fields"
    VALIDATION_ENVIRONMENT = "validation_environment"
    VALIDATION_GENERIC = "validation_generic"
    NO_RESULTS = "no_results"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ClassifiedTripletexError:
    category: TripletexErrorCategory
    recoverable: bool
    summary: str
    raw_message: str


def classify_tripletex_error(raw_message: str) -> ClassifiedTripletexError:
    message = (raw_message or "").lower()

    if "401" in message and "unauthorized" in message:
        return ClassifiedTripletexError(
            category=TripletexErrorCategory.UNAUTHORIZED,
            recoverable=False,
            summary="Authentication failed against Tripletex proxy.",
            raw_message=raw_message,
        )

    if "404" in message and ("wrong endpoint path" in message or "not found" in message):
        return ClassifiedTripletexError(
            category=TripletexErrorCategory.WRONG_ENDPOINT,
            recoverable=False,
            summary="Tripletex endpoint path is invalid for this request.",
            raw_message=raw_message,
        )

    if "timeout" in message or "timed out" in message:
        return ClassifiedTripletexError(
            category=TripletexErrorCategory.TIMEOUT,
            recoverable=False,
            summary="Tripletex request timed out.",
            raw_message=raw_message,
        )

    if "values\": []" in message or "\"values\":[]" in message or "no results found" in message:
        return ClassifiedTripletexError(
            category=TripletexErrorCategory.NO_RESULTS,
            recoverable=True,
            summary="Tripletex search returned no matching results.",
            raw_message=raw_message,
        )

    if "422" in message or "validation_error" in message or "validation" in message:
        if "bankkontonummer" in message or "bank account" in message or "module" in message:
            return ClassifiedTripletexError(
                category=TripletexErrorCategory.VALIDATION_ENVIRONMENT,
                recoverable=False,
                summary="COMPANY_BANK_ACCOUNT_MISSING: Selskapet mangler bankkonto, og dette kan ikke loses via tilgjengelige API-endepunkter.",
                raw_message=raw_message,
            )
        if "required" in message or "mangler" in message or "missing" in message:
            return ClassifiedTripletexError(
                category=TripletexErrorCategory.VALIDATION_MISSING_FIELDS,
                recoverable=True,
                summary="Tripletex rejected the payload because required fields are missing.",
                raw_message=raw_message,
            )
        return ClassifiedTripletexError(
            category=TripletexErrorCategory.VALIDATION_GENERIC,
            recoverable=True,
            summary="Tripletex rejected the payload with a generic validation error.",
            raw_message=raw_message,
        )

    return ClassifiedTripletexError(
        category=TripletexErrorCategory.UNKNOWN,
        recoverable=False,
        summary="Unclassified Tripletex error.",
        raw_message=raw_message,
    )


def explain_tripletex_error(raw_message: str) -> str:
    classified = classify_tripletex_error(raw_message)
    return "{0} [{1}]".format(classified.summary, classified.category.value)
