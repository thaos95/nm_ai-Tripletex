from dataclasses import dataclass, field
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional

import httpx

LOGGER = logging.getLogger(__name__)

ALLOWED_RESOURCES = {
    "employee",
    "customer",
    "product",
    "project",
    "invoice",
    "order",
    "department",
    "ledger",
    "travelExpense",
    "supplier",
    "supplierInvoice",
    "incomingInvoice",
    "voucher",
    "bank",
    "currency",
    "company",
    "token",
    "subscription",
    "contact",
    "balanceSheet",
    "resultbudget",
    "salary",
}


class TripletexClientError(RuntimeError):
    def __init__(
        self,
        *,
        status_code: Optional[int] = None,
        method: Optional[str] = None,
        path: Optional[str] = None,
        response_text: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        if message:
            super().__init__(message)
        elif status_code and method and path:
            text = response_text or ""
            super().__init__(f"Tripletex API error {status_code} on {method} {path}: {text}")
        else:
            super().__init__(message or "Tripletex client error")
        self.status_code = status_code
        self.method = method
        self.path = path
        self.response_text = response_text


@dataclass
class TripletexClient:
    base_url: str
    session_token: str
    verify_tls: bool = True
    timeout: float = 30.0
    transport: Optional[httpx.BaseTransport] = None
    operations: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            base_url=self.base_url.rstrip("/"),
            auth=("0", self.session_token),
            timeout=self.timeout,
            verify=self.verify_tls,
            transport=self.transport,
            headers={"Content-Type": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("GET", path, params=params or {})

    def post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", path, json=payload)

    def put(self, path: str, payload: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("PUT", path, json=payload or {}, params=params or {})

    def delete(self, path: str) -> Dict[str, Any]:
        return self._request("DELETE", path)

    def _request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        normalized_path = self._normalize_path(path)
        self._ensure_allowed(normalized_path)

        try:
            response = self._client.request(method, normalized_path, **kwargs)
        except httpx.HTTPError as exc:
            raise TripletexClientError(message=str(exc)) from exc
        self.operations.append(
            {
                "method": method,
                "path": normalized_path,
                "params": kwargs.get("params"),
                "json": kwargs.get("json"),
                "status_code": response.status_code,
            }
        )
        LOGGER.info(
            "Tripletex request method=%s path=%s status=%s payload=%s",
            method,
            normalized_path,
            response.status_code,
            kwargs.get("json"),
        )
        if response.is_error:
            LOGGER.error(
                "API_ERROR method=%s path=%s status=%s response=%s",
                method, normalized_path, response.status_code, response.text[:2000],
            )
            raise TripletexClientError(
                status_code=response.status_code,
                method=method,
                path=normalized_path,
                response_text=response.text,
            )
        if not response.content:
            return {}
        try:
            data = response.json()
        except ValueError:
            return {"text": response.text}
        return self._normalize_response(data)

    def _normalize_path(self, path: str) -> str:
        normalized = path if path.startswith("/") else f"/{path}"
        return normalized

    def _ensure_allowed(self, path: str) -> None:
        stripped = path.lstrip("/")
        first_segment = stripped.split("/", 1)[0].split(":", 1)[0]
        if first_segment not in ALLOWED_RESOURCES:
            raise TripletexClientError(message=f"Endpoint '{first_segment}' is not allowed")

    # ------------------------------------------------------------------
    # High-level resource helpers (used by workflows/executor)
    # ------------------------------------------------------------------

    def create_resource(self, resource: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self.post(f"/{resource}", payload)
        except TripletexClientError as exc:
            if exc.status_code != 422:
                raise
            # Try programmatic field removal before giving up
            from app.agent.tools import fix_payload_from_error
            fixed = fix_payload_from_error(payload, exc)
            if fixed is not None:
                LOGGER.info("resilient_create retrying %s after removing rejected fields", resource)
                return self.post(f"/{resource}", fixed)
            raise

    def update_resource(self, resource: str, resource_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.put(f"/{resource}/{resource_id}", payload)

    def delete_resource(self, resource: str, resource_id: int) -> Dict[str, Any]:
        return self.delete(f"/{resource}/{resource_id}")

    def list_resource(self, resource: str, fields: str = "id,*", count: int = 100, **extra_params: Any) -> Dict[str, Any]:
        params: Dict[str, Any] = {"fields": fields, "count": count}
        params.update(extra_params)
        return self.get(f"/{resource}", params=params)

    def find_by_id(self, resource: str, resource_id: int) -> Optional[Dict[str, Any]]:
        try:
            response = self.get(f"/{resource}/{resource_id}")
        except TripletexClientError as exc:
            if exc.status_code in (401, 403):
                raise
            return None
        if "value" in response and isinstance(response["value"], dict):
            return response["value"]
        if response.get("id"):
            return response
        return response if response else None

    def find_single(
        self,
        resource: str,
        match_fields: Dict[str, Any],
        fields: str = "id,*",
    ) -> Optional[Dict[str, Any]]:
        if not match_fields:
            return None

        # Build query params from match fields
        query_params: Dict[str, Any] = {"fields": fields, "count": 200}
        field_map = {
            "first_name": "firstName",
            "last_name": "lastName",
        }
        for key, value in match_fields.items():
            api_key = field_map.get(key, key)
            query_params[api_key] = value

        try:
            response = self.get(f"/{resource}", params=query_params)
        except TripletexClientError as exc:
            # Re-raise auth errors — they can't be recovered by returning None
            if exc.status_code in (401, 403):
                raise
            return None
        candidates = response.get("values", [])
        if not candidates:
            return None

        # Score candidates against match fields
        scored: List[tuple] = []
        for candidate in candidates:
            score = self._score_candidate(candidate, match_fields)
            if score > 0:
                scored.append((score, candidate))

        if not scored:
            # Fallback: if exactly one result and a strong identifier was used, return it
            strong_identifiers = {"organizationNumber", "email", "first_name", "last_name"}
            has_strong = any(k in strong_identifiers for k in match_fields)
            if len(candidates) == 1 and has_strong:
                # Don't fallback for name-only queries
                if set(match_fields.keys()) <= {"name"}:
                    return None
                return candidates[0]
            return None

        # Find unique best
        scored.sort(key=lambda x: x[0], reverse=True)
        if len(scored) >= 2 and scored[0][0] == scored[1][0]:
            return None  # Tie — ambiguous
        return scored[0][1]

    def _score_candidate(self, candidate: Dict[str, Any], match_fields: Dict[str, Any]) -> int:
        score = 0
        for key, expected in match_fields.items():
            actual = self._get_candidate_value(candidate, key)
            if actual is None or expected is None:
                continue
            if self._values_match(key, str(actual), str(expected)):
                score += 1
        return score

    def _get_candidate_value(self, candidate: Dict[str, Any], key: str) -> Optional[Any]:
        field_map = {
            "first_name": "firstName",
            "last_name": "lastName",
        }
        api_key = field_map.get(key, key)
        return candidate.get(api_key)

    def _values_match(self, key: str, actual: str, expected: str) -> bool:
        if key in ("organizationNumber", "phoneNumber", "phoneNumberMobile"):
            actual_digits = re.sub(r"[^\d+]", "", actual)
            expected_digits = re.sub(r"[^\d+]", "", expected)
            return actual_digits == expected_digits
        return self._normalize_string(actual) == self._normalize_string(expected)

    def _candidate_matches(self, candidate: Dict[str, Any], match_fields: Dict[str, Any]) -> bool:
        for key, expected in match_fields.items():
            actual = self._get_candidate_value(candidate, key)
            if actual is None:
                return False
            if not self._values_match(key, str(actual), str(expected)):
                return False
        return True

    def _normalize_string(self, value: str) -> str:
        # Remove diacritics, lowercase, strip punctuation
        nfkd = unicodedata.normalize("NFKD", value)
        stripped = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
        result = re.sub(r"[(){}[\]]", " ", stripped.lower())
        result = re.sub(r"\s+", " ", result).strip()
        return result

    def _normalize_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if "values" in data:
            return data
        if "value" in data:
            return {"value": data["value"]}
        return data
