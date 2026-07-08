# Cloudflare CDN Toolkit — Desktop GUI

A single dark, neon-mint hacker-style desktop app that wraps everything:

- **SCAN** — pull a VLESS config list, filter to Cloudflare port-443 IPs,
  ping/tcp-probe them, save alive IPs.
- **SPEED** — v2rayN-style real speed test using `xray-core`. Boots a local
  SOCKS proxy against your VLESS config and measures actual MB/s per IP.
  Results table sorts fastest-first live. One click sends top N IPs to the
  DNS tab.
- **DNS** — replace Cloudflare A records for a hostname with your top IPs
  (TTL Auto, unproxied).
- **PROFILES** — save/load presets (UUID, SNI, host, path, port, API token,
  zone ID, record name, scanner URL) to `profiles.json`.

## Install

```powershell
pip install -r requirements.txt
pip install PySide6 pysocks
```

Make sure `xray.exe` (from https://github.com/XTLS/Xray-core/releases) is on
your PATH or next to `app.py`, or point at it from the Speed tab.

## Run

```powershell
python app.py
```

The old single-purpose `gui.py` is still there if you only want the DNS
updater; `app.py` is the new full toolkit.
