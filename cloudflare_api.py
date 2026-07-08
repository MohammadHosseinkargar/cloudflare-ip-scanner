"""Cloudflare API v4 client for managing DNS A records."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import requests


class CloudflareError(Exception):
    """Base error for Cloudflare API interactions."""


class CloudflareAuthError(CloudflareError):
    """Invalid API token."""


class CloudflareNotFoundError(CloudflareError):
    """Zone or record not found."""


class CloudflareRateLimitError(CloudflareError):
    """Cloudflare rate limit reached (HTTP 429)."""


@dataclass
class DNSRecord:
    id: str
    name: str
    type: str
    content: str
    proxied: bool
    ttl: int


class CloudflareAPI:
    """Thin wrapper around the Cloudflare API v4."""

    BASE_URL = "https://api.cloudflare.com/client/v4"

    def __init__(
        self,
        api_token: str,
        zone_id: str,
        timeout: int = 30,
        max_retries: int = 3,
        logger: Optional[Callable[[str], None]] = None,
    ) -> None:
        if not api_token or not api_token.strip():
            raise ValueError("API token is required")
        if not zone_id or not zone_id.strip():
            raise ValueError("Zone ID is required")

        self.api_token = api_token.strip()
        self.zone_id = zone_id.strip()
        self.timeout = timeout
        self.max_retries = max_retries
        self._log = logger or (lambda msg: None)

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    # ---------------------------------------------------------------- internals
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.BASE_URL}{path}"
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self.session.request(
                    method, url, params=params, json=json, timeout=self.timeout
                )
            except requests.exceptions.ConnectionError as e:
                raise CloudflareError(f"Network error: {e}") from e
            except requests.exceptions.Timeout as e:
                raise CloudflareError(f"Request timed out: {e}") from e
            except requests.exceptions.RequestException as e:
                raise CloudflareError(f"Request failed: {e}") from e

            if resp.status_code == 429:
                if attempt <= self.max_retries:
                    wait = int(resp.headers.get("Retry-After", 2 ** attempt))
                    self._log(
                        f"Rate limited (429). Retrying in {wait}s "
                        f"(attempt {attempt}/{self.max_retries})..."
                    )
                    time.sleep(wait)
                    continue
                raise CloudflareRateLimitError(
                    "Cloudflare rate limit exceeded (HTTP 429)."
                )

            try:
                data = resp.json()
            except ValueError:
                raise CloudflareError(
                    f"Invalid JSON from Cloudflare (HTTP {resp.status_code}): "
                    f"{resp.text[:200]}"
                )

            if resp.status_code == 401 or resp.status_code == 403:
                msg = self._extract_error_message(data) or "Unauthorized"
                raise CloudflareAuthError(f"Authentication failed: {msg}")

            if resp.status_code == 404:
                msg = self._extract_error_message(data) or "Not found"
                raise CloudflareNotFoundError(msg)

            if not resp.ok or not data.get("success", False):
                msg = self._extract_error_message(data) or f"HTTP {resp.status_code}"
                raise CloudflareError(f"Cloudflare API error: {msg}")

            return data

    @staticmethod
    def _extract_error_message(data: Dict[str, Any]) -> str:
        errors = data.get("errors") or []
        parts = []
        for err in errors:
            code = err.get("code")
            message = err.get("message")
            if code and message:
                parts.append(f"[{code}] {message}")
            elif message:
                parts.append(message)
        return "; ".join(parts)

    # ------------------------------------------------------------------- public
    def verify_token(self) -> bool:
        """Verify the API token via /user/tokens/verify."""
        data = self._request("GET", "/user/tokens/verify")
        return bool(data.get("success"))

    def list_a_records(self, name: str) -> List[DNSRecord]:
        """List all A records matching `name` in the current zone."""
        records: List[DNSRecord] = []
        page = 1
        per_page = 100
        while True:
            data = self._request(
                "GET",
                f"/zones/{self.zone_id}/dns_records",
                params={
                    "type": "A",
                    "name": name,
                    "page": page,
                    "per_page": per_page,
                },
            )
            result = data.get("result", []) or []
            for r in result:
                records.append(
                    DNSRecord(
                        id=r["id"],
                        name=r["name"],
                        type=r["type"],
                        content=r["content"],
                        proxied=bool(r.get("proxied", False)),
                        ttl=int(r.get("ttl", 1)),
                    )
                )
            info = data.get("result_info") or {}
            total_pages = int(info.get("total_pages", 1) or 1)
            if page >= total_pages:
                break
            page += 1
        return records

    def delete_record(self, record_id: str) -> None:
        """Delete a DNS record by ID."""
        self._request("DELETE", f"/zones/{self.zone_id}/dns_records/{record_id}")

    def create_a_record(
        self,
        name: str,
        ip: str,
        *,
        proxied: bool = False,
        ttl: int = 1,  # 1 == "Auto" in Cloudflare
        comment: Optional[str] = None,
    ) -> DNSRecord:
        """Create a new A record."""
        payload: Dict[str, Any] = {
            "type": "A",
            "name": name,
            "content": ip,
            "ttl": ttl,
            "proxied": proxied,
        }
        if comment:
            payload["comment"] = comment
        data = self._request(
            "POST", f"/zones/{self.zone_id}/dns_records", json=payload
        )
        r = data.get("result", {}) or {}
        return DNSRecord(
            id=r.get("id", ""),
            name=r.get("name", name),
            type=r.get("type", "A"),
            content=r.get("content", ip),
            proxied=bool(r.get("proxied", False)),
            ttl=int(r.get("ttl", ttl)),
        )
