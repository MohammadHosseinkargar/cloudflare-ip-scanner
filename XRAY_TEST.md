# v2rayN-style xray-core speed test

`xray_test.py` tests each candidate IP the same way v2rayN does: it starts
a real `xray-core` process locally with your VLESS config (SNI, Host, path,
UUID, port) but overrides the outbound `address` to the candidate IP, opens
a local SOCKS proxy, and downloads a real URL through the tunnel to measure
actual MB/s.

No custom protocol code, no origin worker required. If it works in v2rayN,
it works here.

## 1. Install xray-core

Download the latest release for your OS from:
<https://github.com/XTLS/Xray-core/releases>

Windows: extract `xray.exe` and place it next to `xray_test.py`
(or anywhere on your `PATH`).

Linux / macOS: place the `xray` binary next to the script or on PATH.

You can also point at any location:

```powershell
python xray_test.py --xray "C:\tools\xray\xray.exe" ...
```

## 2. Install Python deps

```powershell
pip install requests pysocks
```

## 3. Run it

Single-line PowerShell command (accurate speed ranking):

```powershell
python xray_test.py `
  --uuid 9be9976b-3fe6-41d3-bc4b-b63fba678b9b `
  --sni soosis.gamespeednet.top `
  --host soosis.gamespeednet.top `
  --path /au-do `
  --port 443 `
  --speed-url "https://speed.cloudflare.com/__down?bytes=10000000" `
  --min-mbps 1.0 `
  --duration 8 `
  --workers 1
```

Notes:

- `--workers 1` gives real MB/s numbers. Raising it makes it faster but the
  IPs share your bandwidth and will look slower than they are.
- `--duration` caps how long each download runs, exactly like v2rayN's
  "real delay / speed test" (default 8s).
- `--speed-url` can be any large HTTPS resource; Cloudflare's `speed.cloudflare.com/__down?bytes=...`
  is a good default because CF edges answer it directly.
- Slow IPs are still saved (ranked by speed) unless you pass `--strict`.

Outputs:

- `sorted_ips.txt` — IPs ranked fastest first
- `sorted_ips_full.txt` — same list with latency / MB/s / bytes
- `sorted_ips_all.txt` — every tested IP including failures
