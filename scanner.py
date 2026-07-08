"""
V2Ray VLESS config scanner.

Downloads a list of VLESS configs, keeps only those using port 443,
extracts their host/IP, pings each one and saves the alive IPs to a
text file (one IP per line) that can be fed directly into the
Cloudflare DNS Manager GUI.

Usage:
    python scanner.py
    python scanner.py --url <url> --output alive_ips.txt --workers 50 --timeout 2
"""

from __future__ import annotations

import argparse
import concurrent.futures
import ipaddress
import platform
import socket
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

import requests

DEFAULT_URL = (
    "https://github.com/Epodonios/v2ray-configs/raw/main/"
    "Splitted-By-Protocol/vless.txt"
)
DEFAULT_OUTPUT = "alive_ips.txt"


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class VlessEndpoint:
    host: str      # original host (may be a hostname)
    ip: str        # resolved IPv4
    port: int


# --------------------------------------------------------------------------- #
# Download + parse
# --------------------------------------------------------------------------- #

def download_configs(url: str, timeout: int = 30) -> list[str]:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    text = resp.text

    # V2Ray subscription lists are usually base64-encoded. Try to decode; if
    # the result contains vless:// lines, use it. Otherwise fall back to raw.
    if "vless://" not in text:
        import base64
        try:
            padded = text.strip() + "=" * (-len(text.strip()) % 4)
            decoded = base64.b64decode(padded, validate=False).decode(
                "utf-8", errors="ignore"
            )
            if "vless://" in decoded:
                text = decoded
        except Exception:
            pass

    return [
        line.strip()
        for line in text.splitlines()
        if line.strip().lower().startswith("vless://")
    ]


def parse_vless(line: str) -> tuple[str, int] | None:
    """Return (host, port) for a vless:// URI, or None if unparseable."""
    try:
        # urlparse handles vless://uuid@host:port?params#name
        parsed = urlparse(line)
        host = parsed.hostname
        port = parsed.port
        if not host or not port:
            return None
        # Strip brackets from IPv6 literals just in case
        return host.strip("[]"), int(port)
    except (ValueError, TypeError):
        return None


def resolve_ipv4(host: str) -> str | None:
    """Return an IPv4 for host, or None."""
    # Already an IPv4?
    try:
        ipaddress.IPv4Address(host)
        return host
    except ValueError:
        pass
    # Skip IPv6 literals
    try:
        ipaddress.IPv6Address(host)
        return None
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET)
        return infos[0][4][0] if infos else None
    except (socket.gaierror, socket.herror, OSError):
        return None


# --------------------------------------------------------------------------- #
# Ping
# --------------------------------------------------------------------------- #

def ping(ip: str, timeout: int = 2) -> bool:
    """Cross-platform single-shot ICMP ping. Returns True on reply."""
    is_windows = platform.system().lower() == "windows"
    if is_windows:
        cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(timeout), ip]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout + 2,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def tcp_ping(ip: str, port: int, timeout: float = 2.0) -> bool:
    """Fallback: TCP connect probe. Useful when ICMP is blocked."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #

CLOUDFLARE_IPS_V4_URL = "https://www.cloudflare.com/ips-v4"

CLOUDFLARE_FALLBACK_V4 = [
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22",
    "103.31.4.0/22", "141.101.64.0/18", "108.162.192.0/18",
    "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22",
    "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
]


def fetch_cloudflare_networks(timeout: int = 15) -> list[ipaddress.IPv4Network]:
    try:
        resp = requests.get(CLOUDFLARE_IPS_V4_URL, timeout=timeout)
        resp.raise_for_status()
        cidrs = [c.strip() for c in resp.text.splitlines() if c.strip()]
    except requests.RequestException:
        cidrs = CLOUDFLARE_FALLBACK_V4
    return [ipaddress.IPv4Network(c) for c in cidrs]


def is_cloudflare_ip(ip: str, networks: list[ipaddress.IPv4Network]) -> bool:
    try:
        addr = ipaddress.IPv4Address(ip)
    except ValueError:
        return False
    return any(addr in net for net in networks)


def collect_port_443_endpoints(
    lines: Iterable[str],
    networks: list[ipaddress.IPv4Network] | None = None,
) -> list[VlessEndpoint]:
    seen: set[str] = set()
    endpoints: list[VlessEndpoint] = []
    for line in lines:
        parsed = parse_vless(line)
        if not parsed:
            continue
        host, port = parsed
        if port != 443:
            continue
        ip = resolve_ipv4(host)
        if not ip or ip in seen:
            continue
        if networks is not None and not is_cloudflare_ip(ip, networks):
            continue
        seen.add(ip)
        endpoints.append(VlessEndpoint(host=host, ip=ip, port=port))
    return endpoints


def test_endpoints(
    endpoints: list[VlessEndpoint],
    workers: int = 50,
    timeout: int = 2,
    use_tcp_fallback: bool = True,
) -> list[str]:
    alive: list[str] = []

    def check(ep: VlessEndpoint) -> str | None:
        if ping(ep.ip, timeout=timeout):
            return ep.ip
        if use_tcp_fallback and tcp_ping(ep.ip, ep.port, timeout=timeout):
            return ep.ip
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check, ep): ep for ep in endpoints}
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            ep = futures[future]
            result = future.result()
            status = "OK" if result else "--"
            print(f"[{i}/{len(endpoints)}] {status} {ep.ip} ({ep.host})")
            if result:
                alive.append(result)
    return alive


def save_ips(ips: list[str], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(ips))
        if ips:
            f.write("\n")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V2Ray VLESS 443 scanner")
    parser.add_argument("--url", default=DEFAULT_URL, help="Config list URL")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output IP file")
    parser.add_argument("--workers", type=int, default=50, help="Parallel workers")
    parser.add_argument("--timeout", type=int, default=2, help="Ping timeout (s)")
    parser.add_argument(
        "--no-tcp-fallback",
        action="store_true",
        help="Disable TCP:443 probe when ICMP fails",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Keep every port-443 IP (default: Cloudflare CDN IPs only)",
    )
    args = parser.parse_args(argv)

    print(f"Downloading {args.url} ...")
    try:
        lines = download_configs(args.url)
    except requests.RequestException as e:
        print(f"Download failed: {e}", file=sys.stderr)
        return 1
    print(f"  {len(lines)} vless entries")

    networks: list[ipaddress.IPv4Network] | None = None
    if not args.all:
        print("Fetching Cloudflare IP ranges ...")
        networks = fetch_cloudflare_networks()
        print(f"  {len(networks)} Cloudflare CIDR blocks loaded")

    print("Filtering port 443 and resolving hosts ...")
    endpoints = collect_port_443_endpoints(lines, networks=networks)
    label = "Cloudflare " if networks is not None else ""
    print(f"  {len(endpoints)} unique {label}IPv4 endpoints on port 443")

    if not endpoints:
        print("Nothing to test.")
        return 0

    print(f"Pinging with {args.workers} workers ...")
    alive = test_endpoints(
        endpoints,
        workers=args.workers,
        timeout=args.timeout,
        use_tcp_fallback=not args.no_tcp_fallback,
    )

    alive.sort()
    save_ips(alive, args.output)
    print(f"\n{len(alive)} alive IPs saved to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
