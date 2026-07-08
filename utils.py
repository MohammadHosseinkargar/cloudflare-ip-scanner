"""Utility helpers for the Cloudflare DNS Manager."""
from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import List


def is_valid_ipv4(ip: str) -> bool:
    """Return True if `ip` is a valid IPv4 address."""
    try:
        ipaddress.IPv4Address(ip.strip())
        return True
    except (ipaddress.AddressValueError, ValueError):
        return False


def is_valid_ipv6(ip: str) -> bool:
    """Return True if `ip` is a valid IPv6 address."""
    try:
        ipaddress.IPv6Address(ip.strip())
        return True
    except (ipaddress.AddressValueError, ValueError):
        return False


def load_ips_from_file(path: str | Path) -> List[str]:
    """Load a list of IP addresses from a TXT file.

    - Ignores empty lines and lines starting with '#'.
    - Trims whitespace.
    - Validates every IP (IPv4 only, since we create A records).
    - Raises ValueError with a helpful message on invalid entries.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ips: List[str] = []
    invalid: List[str] = []

    with file_path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if is_valid_ipv4(line):
                ips.append(line)
            else:
                invalid.append(line)

    if invalid:
        raise ValueError(
            "Invalid IPv4 address(es) found in file: " + ", ".join(invalid)
        )

    # Deduplicate while preserving order
    seen = set()
    unique: List[str] = []
    for ip in ips:
        if ip not in seen:
            seen.add(ip)
            unique.append(ip)
    return unique
