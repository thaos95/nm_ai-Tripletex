from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
import re
import unicodedata


class TripletexClientError(RuntimeError):
    pass


@dataclass
class TripletexClient:
    base_url: str
    session_token: str
    verify_tls: bool = True
    transport: Optional[httpx.BaseTransport] = None
    operations: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            base_url=self.base_url.rstrip("/"),
            auth=("0", self.session_token),
            timeout=20.0,
            verify=self.verify_tls,
            transport=self.transport,
        )

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        response = self._client.request(method, path, **kwargs)
        self.operations.append(
            {
                "method": method,
                "path": path,
                "params": kwargs.get("params"),
                "json": kwargs.get("json"),
                "status_code": response.status_code,
            }
        )
        if response.is_error:
            raise TripletexClientError(
                "Tripletex API error {0} on {1} {2}: {3}".format(
                    response.status_code, method, path, response.text
                )
            )
        if not response.content:
            return {}
        return response.json()

    def list_resource(self, resource: str, **params: Any) -> Dict[str, Any]:
        return self._request("GET", "/" + resource.strip("/"), params=params)

    def create_resource(self, resource: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/" + resource.strip("/"), json=payload)

    def update_resource(self, resource: str, resource_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PUT", "/{0}/{1}".format(resource.strip("/"), resource_id), json=payload)

    def delete_resource(self, resource: str, resource_id: int) -> Dict[str, Any]:
        return self._request("DELETE", "/{0}/{1}".format(resource.strip("/"), resource_id))

    def _match_value(self, candidate: Dict[str, Any], field: str) -> Optional[str]:
        value = candidate.get(field)
        if value is not None:
            return self._normalize_field_value(field, value)
        nested_map = {
            "first_name": "firstName",
            "last_name": "lastName",
            "mobilePhoneNumber": "mobilePhoneNumber",
            "phoneNumberMobile": "phoneNumberMobile",
            "phoneNumber": "phoneNumber",
        }
        nested = nested_map.get(field)
        if nested and candidate.get(nested) is not None:
            return self._normalize_field_value(field, candidate.get(nested))
        return None

    def _normalize_field_value(self, field: str, value: Any) -> str:
        if value is None:
            return ""

        text = str(value).strip()
        if field in {"organizationNumber", "employeeNumber", "productNumber"}:
            return "".join(ch for ch in text if ch.isdigit())
        if field in {"phoneNumber", "phoneNumberMobile", "mobilePhoneNumber"}:
            return "".join(ch for ch in text if ch.isdigit() or ch == "+")
        if field == "email":
            return text.lower()
        return self._normalize_string(text)

    def _normalize_string(self, value: Any) -> str:
        text = unicodedata.normalize("NFKD", str(value))
        text = "".join(char for char in text if not unicodedata.combining(char))
        text = text.strip().lower()
        text = re.sub(r"[^\w@.+\-]+", " ", text, flags=re.UNICODE)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _candidate_matches(self, candidate: Dict[str, Any], normalized_match: Dict[str, str]) -> bool:
        if all(self._match_value(candidate, key) == value for key, value in normalized_match.items()):
            return True

        first_name = normalized_match.get("first_name")
        last_name = normalized_match.get("last_name")
        if first_name and last_name:
            candidate_full_name = self._normalize_string(
                "{0} {1}".format(candidate.get("firstName", ""), candidate.get("lastName", "")).strip()
            )
            target_full_name = self._normalize_string("{0} {1}".format(first_name, last_name))
            return candidate_full_name == target_full_name
        return False

    def _candidate_score(self, candidate: Dict[str, Any], normalized_match: Dict[str, str]) -> int:
        score = 0
        weights = {
            "organizationNumber": 6,
            "email": 6,
            "employeeNumber": 6,
            "productNumber": 6,
            "first_name": 3,
            "last_name": 3,
            "name": 2,
            "phoneNumber": 2,
            "phoneNumberMobile": 2,
            "mobilePhoneNumber": 2,
        }

        for key, value in normalized_match.items():
            candidate_value = self._match_value(candidate, key)
            if candidate_value is None:
                continue
            if candidate_value == value:
                score += weights.get(key, 1)
                continue
            if key == "name":
                if candidate_value.startswith(value) or value.startswith(candidate_value):
                    score += 1
            elif key in {"first_name", "last_name"}:
                if candidate_value.startswith(value) or value.startswith(candidate_value):
                    score += 1

        first_name = normalized_match.get("first_name")
        last_name = normalized_match.get("last_name")
        if first_name and last_name:
            candidate_full_name = self._normalize_string(
                "{0} {1}".format(candidate.get("firstName", ""), candidate.get("lastName", "")).strip()
            )
            target_full_name = self._normalize_string("{0} {1}".format(first_name, last_name))
            if candidate_full_name == target_full_name:
                score += 4

        return score

    def _has_strong_identifier(self, normalized_match: Dict[str, str]) -> bool:
        if any(
            normalized_match.get(key)
            for key in ("organizationNumber", "email", "employeeNumber", "productNumber", "phoneNumber", "phoneNumberMobile", "mobilePhoneNumber")
        ):
            return True
        return bool(normalized_match.get("first_name") and normalized_match.get("last_name"))

    def find_single(self, resource: str, match_fields: Dict[str, Any], fields: str = "*") -> Optional[Dict[str, Any]]:
        if not match_fields:
            return None

        query_params = {"fields": fields, "count": 200}
        for key in ("name", "email", "first_name", "last_name", "organizationNumber", "productNumber", "employeeNumber"):
            if key in match_fields:
                param_name = "firstName" if key == "first_name" else "lastName" if key == "last_name" else key
                query_params[param_name] = match_fields[key]

        response = self.list_resource(resource, **query_params)
        values = response.get("values", [])
        if not values:
            return None

        normalized_match = dict((key, self._normalize_field_value(key, value)) for key, value in match_fields.items())
        exact_matches = []
        for candidate in values:
            if self._candidate_matches(candidate, normalized_match):
                exact_matches.append(candidate)

        if len(exact_matches) == 1:
            return exact_matches[0]
        if exact_matches:
            return None
        scored = sorted(
            ((self._candidate_score(candidate, normalized_match), candidate) for candidate in values),
            key=lambda item: item[0],
            reverse=True,
        )
        if scored and scored[0][0] >= 2:
            if len(scored) == 1 or scored[0][0] > scored[1][0]:
                return scored[0][1]
        if len(values) == 1 and self._has_strong_identifier(normalized_match):
            return values[0]
        return None

    def find_by_id(self, resource: str, resource_id: int, fields: str = "*") -> Optional[Dict[str, Any]]:
        response = self._request("GET", "/{0}/{1}".format(resource.strip("/"), resource_id), params={"fields": fields})
        if "value" in response and isinstance(response["value"], dict):
            return response["value"]
        if response:
            return response
        return None
