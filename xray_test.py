"""
v2rayN-style real-world speed test using xray-core.

For each IP in the input list this script:
    1. Writes a temporary xray config that uses YOUR VLESS setup
       (uuid / sni / host / path / port) but overrides the outbound
       server address to the candidate IP.
    2. Starts `xray run -c <tmp>` locally, listening on a random SOCKS
       inbound port.
    3. Downloads a real speed-test URL through that SOCKS proxy and
       measures MB/s and latency, exactly like v2rayN's built-in
       "real delay / speed test".
    4. Kills xray, records the result, and moves to the next IP.

Requirements:
    - xray-core binary next to this script (xray.exe on Windows, xray on Linux/macOS)
      or reachable on PATH, or passed via --xray <path>.
    - `pip install requests pysocks`

Typical usage (PowerShell, one line):

    python xray_test.py --uuid 9be9976b-3fe6-41d3-bc4b-b63fba678b9b `
      --sni soosis.gamespeednet.top --host soosis.gamespeednet.top `
      --path /au-do --port 443 `
      --speed-url https://speed.cloudflare.com/__down?bytes=10000000 `
      --min-mbps 1.0 --duration 8 --workers 1
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import requests
except ImportError:
    print("Missing dependency. Run:  pip install requests pysocks", file=sys.stderr)
    raise

DEFAULT_INPUT = "alive_ips.txt"
DEFAULT_OUTPUT = "sorted_ips.txt"
DEFAULT_UUID = ""
DEFAULT_SNI = ""
DEFAULT_HOST = ""
DEFAULT_PATH = "/"
DEFAULT_PORT = 443
DEFAULT_SPEED_URL = "https://speed.cloudflare.com/__down?bytes=10000000"
DEFAULT_MIN_MBPS = 1.0
DEFAULT_DURATION = 8.0
DEFAULT_TIMEOUT = 15.0
DEFAULT_WORKERS = 1


@dataclass
class Result:
    ip: str
    latency_ms: float | None = None
    mbps: float = 0.0
    bytes_read: int = 0
    status: str = ""
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _find_xray(explicit: str | None) -> str:
    if explicit:
        p = Path(explicit)
        if p.exists():
            return str(p.resolve())
        raise SystemExit(f"xray binary not found at {explicit}")
    here = Path(__file__).parent
    for name in ("xray.exe", "xray"):
        candidate = here / name
        if candidate.exists():
            return str(candidate.resolve())
    on_path = shutil.which("xray") or shutil.which("xray.exe")
    if on_path:
        return on_path
    raise SystemExit(
        "xray binary not found. Download xray-core from "
        "https://github.com/XTLS/Xray-core/releases and place xray.exe "
        "next to this script, or pass --xray <path>."
    )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _build_config(
    socks_port: int,
    ip: str,
    port: int,
    uuid: str,
    sni: str,
    host: str,
    path: str,
) -> dict:
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "listen": "127.0.0.1",
                "port": socks_port,
                "protocol": "socks",
                "settings": {"udp": False, "auth": "noauth"},
                "sniffing": {"enabled": False},
            }
        ],
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": ip,
                            "port": port,
                            "users": [
                                {"id": uuid, "encryption": "none", "level": 0}
                            ],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "ws",
                    "security": "tls",
                    "tlsSettings": {
                        "serverName": sni,
                        "alpn": ["http/1.1"],
                    },
                    "wsSettings": {
                        "path": path,
                        "headers": {"Host": host},
                    },
                },
                "tag": "proxy",
            },
            {"protocol": "freedom", "tag": "direct"},
        ],
    }


def _wait_for_port(port: int, timeout: float = 3.0) -> bool:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def probe_ip(
    ip: str,
    xray_bin: str,
    port: int,
    uuid: str,
    sni: str,
    host: str,
    path: str,
    speed_url: str,
    duration: float,
    timeout: float,
) -> Result:
    socks_port = _free_port()
    cfg = _build_config(socks_port, ip, port, uuid, sni, host, path)

    tmp = tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    )
    try:
        json.dump(cfg, tmp)
        tmp.flush()
        tmp.close()

        creationflags = 0
        if os.name == "nt":
            creationflags = 0x08000000  # CREATE_NO_WINDOW

        proc = subprocess.Popen(
            [xray_bin, "run", "-c", tmp.name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
        try:
            if not _wait_for_port(socks_port, timeout=10.0):
                try:
                    proc.terminate()
                    out, _ = proc.communicate(timeout=2)
                except Exception:
                    out = b""
                msg = (out or b"").decode("utf-8", "replace").strip().replace("\r", "").replace("\n", " | ")
                if not msg:
                    msg = "xray exited silently; check --xray path & config"
                return Result(ip, None, 0.0, 0, "xray_boot", msg[-600:])

            proxies = {
                "http": f"socks5h://127.0.0.1:{socks_port}",
                "https": f"socks5h://127.0.0.1:{socks_port}",
            }

            start = time.perf_counter()
            try:
                # v2rayN-style: single streaming GET, cap wall-clock at `duration`,
                # measure real bytes/second delivered through the tunnel.
                with requests.get(
                    speed_url,
                    proxies=proxies,
                    stream=True,
                    timeout=timeout,
                    headers={"User-Agent": "Mozilla/5.0"},
                ) as resp:
                    first_byte = time.perf_counter()
                    latency_ms = (first_byte - start) * 1000.0
                    if resp.status_code >= 400:
                        return Result(
                            ip, latency_ms, 0.0, 0,
                            "http_error", f"HTTP {resp.status_code}",
                        )
                    total = 0
                    body_start = time.perf_counter()
                    for chunk in resp.iter_content(chunk_size=65536):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if time.perf_counter() - body_start >= duration:
                            break
                    body_seconds = max(0.001, time.perf_counter() - body_start)
                    mbps = (total / 1_000_000.0) / body_seconds
                    if total <= 0:
                        return Result(ip, latency_ms, 0.0, 0, "no_body", "empty response")
                    return Result(
                        ip, latency_ms, mbps, total, "ok",
                        f"{total} B / {body_seconds:.2f}s",
                    )
            except requests.exceptions.ConnectTimeout:
                return Result(ip, None, 0.0, 0, "connect_timeout", "")
            except requests.exceptions.ReadTimeout:
                return Result(ip, None, 0.0, 0, "read_timeout", "")
            except requests.exceptions.ProxyError as e:
                return Result(ip, None, 0.0, 0, "proxy_error", str(e)[:60])
            except requests.exceptions.RequestException as e:
                return Result(ip, None, 0.0, 0, "req_error", str(e)[:60])
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def load_ips(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        return [
            line.strip().split()[0].strip(",")
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]


def save_outputs(results: list[Result], plain_path: str, min_mbps: float, strict: bool) -> tuple[str, str]:
    def keep(r: Result) -> bool:
        if strict:
            return r.ok and r.mbps >= min_mbps
        return r.ok

    ranked = sorted(
        (r for r in results if keep(r)),
        key=lambda r: (-r.mbps, r.latency_ms or float("inf")),
    )
    with open(plain_path, "w", encoding="utf-8") as f:
        for r in ranked:
            f.write(f"{r.ip}\n")

    full = plain_path.rsplit(".", 1)[0] + "_full.txt"
    with open(full, "w", encoding="utf-8") as f:
        f.write("# ip\tlatency_ms\tmbps\tbytes\tstatus\tdetail\n")
        for r in ranked:
            lat = f"{r.latency_ms:.1f}" if r.latency_ms is not None else "-"
            f.write(f"{r.ip}\t{lat}\t{r.mbps:.2f}\t{r.bytes_read}\t{r.status}\t{r.detail}\n")

    all_path = plain_path.rsplit(".", 1)[0] + "_all.txt"
    with open(all_path, "w", encoding="utf-8") as f:
        f.write("# ip\tlatency_ms\tmbps\tbytes\tstatus\tdetail\n")
        for r in results:
            lat = f"{r.latency_ms:.1f}" if r.latency_ms is not None else "-"
            f.write(f"{r.ip}\t{lat}\t{r.mbps:.2f}\t{r.bytes_read}\t{r.status}\t{r.detail}\n")
    return full, all_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="v2rayN-style xray-core real speed test")
    p.add_argument("--input", default=DEFAULT_INPUT)
    p.add_argument("--output", default=DEFAULT_OUTPUT)
    p.add_argument("--xray", default=None, help="Path to xray/xray.exe (default: next to script or on PATH)")
    p.add_argument("--uuid", default=DEFAULT_UUID)
    p.add_argument("--sni", default=DEFAULT_SNI)
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--path", default=DEFAULT_PATH)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--speed-url", default=DEFAULT_SPEED_URL,
                   help="URL fetched through the tunnel to measure real speed")
    p.add_argument("--min-mbps", type=float, default=DEFAULT_MIN_MBPS,
                   help="Ranking target. IPs below this are still saved unless --strict.")
    p.add_argument("--duration", type=float, default=DEFAULT_DURATION,
                   help="Max seconds to spend downloading per IP (v2rayN uses ~8-10)")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                   help="Per-request network timeout (connect + read)")
    p.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                   help="Parallel xray instances. Keep at 1 for accurate MB/s.")
    p.add_argument("--strict", action="store_true",
                   help="Only save IPs that meet --min-mbps.")
    p.add_argument("--shuffle", action="store_true", help="Shuffle IPs before testing")
    p.add_argument("--limit", type=int, default=0, help="Stop after testing N IPs (0 = all)")
    args = p.parse_args(argv)

    xray_bin = _find_xray(args.xray)
    print(f"xray  : {xray_bin}")

    # Quick sanity check — the #1 cause of "xray_boot" is a wrong/broken binary.
    try:
        ver = subprocess.run(
            [xray_bin, "version"], capture_output=True, timeout=5, text=True
        )
        first = (ver.stdout or ver.stderr or "").splitlines()[:1]
        if first:
            print(f"version: {first[0]}")
        else:
            print("WARNING: xray produced no version output — binary may be broken.")
    except Exception as e:
        print(f"WARNING: could not run '{xray_bin} version': {e}")

    try:
        ips = load_ips(args.input)
    except FileNotFoundError:
        print(f"Input file not found: {args.input}", file=sys.stderr)
        return 1
    if args.shuffle:
        random.shuffle(ips)
    if args.limit > 0:
        ips = ips[: args.limit]
    if not ips:
        print("No IPs to test.")
        return 0

    print(
        f"Testing {len(ips)} IPs via xray-core "
        f"(SNI={args.sni}, Host={args.host}, path={args.path}, port={args.port})"
        f"\n  speed URL : {args.speed_url}"
        f"\n  target    : >= {args.min_mbps} MB/s   duration cap: {args.duration}s"
        f"\n  workers   : {args.workers}   strict: {args.strict}"
    )

    results: list[Result] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                probe_ip,
                ip, xray_bin, args.port, args.uuid,
                args.sni, args.host, args.path,
                args.speed_url, args.duration, args.timeout,
            ): ip
            for ip in ips
        }
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            r = fut.result()
            results.append(r)
            if r.ok:
                tag = "OK  " if r.mbps >= args.min_mbps else "SLOW"
                lat = f"{r.latency_ms:>7.1f}" if r.latency_ms is not None else "   ---"
                print(f"[{i}/{len(ips)}] {tag} {r.ip:<16} {lat} ms  {r.mbps:>6.2f} MB/s  {r.bytes_read:>8} B")
            else:
                lat = f"{r.latency_ms:>7.1f}" if r.latency_ms is not None else "   ---"
                print(f"[{i}/{len(ips)}] FAIL {r.ip:<16} {lat}     {r.status} {r.detail}")

    full, all_path = save_outputs(results, args.output, args.min_mbps, args.strict)
    good = sum(1 for r in results if r.ok and r.mbps >= args.min_mbps)
    usable = sum(1 for r in results if r.ok)
    print(
        f"\n{good}/{len(results)} IPs met {args.min_mbps} MB/s target; "
        f"{usable}/{len(results)} completed a real download."
        f"\nSorted IPs  : {args.output}"
        f"\nWith detail : {full}"
        f"\nAll results : {all_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
