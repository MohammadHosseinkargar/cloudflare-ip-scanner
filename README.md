# Cloudflare CDN Toolkit

A dark, neon-mint desktop app (Windows / macOS / Linux) that helps you find
the **fastest Cloudflare IPs** for your VLESS config and point your domain at
them — all in one window.

**Read this in other languages:** [فارسی](README.fa.md)

---

## What it does

1. **SCAN** — pulls a subscription (VLESS config list), keeps only Cloudflare
   port-443 IPs, and pings them to find alive ones.
2. **SPEED** — runs a real speed test through `xray-core` on each alive IP
   (just like v2rayN) and sorts them fastest first.
3. **DNS** — replaces the A records of your domain on Cloudflare with the top
   IPs from the speed test (one click).
4. **PROFILES** — save all your settings (UUID, SNI, host, path, port, API
   token, zone ID, record name, subscription URL) so you don't retype them.

## Quick start

### 1. Install Python 3.11 or newer
Download from https://www.python.org/downloads/ (tick "Add Python to PATH").

### 2. Download this project
Click the green **Code** button on GitHub → **Download ZIP**, then unzip.
Or with git:
```bash
git clone https://github.com/MohammadHosseinkargar/cloudflare-ip-scanner.git
cd cloudflare-ip-scanner
```

### 3. Install the requirements
Open a terminal in the project folder and run:
```bash
pip install -r requirements.txt
```

### 4. Get xray-core (needed for the speed test)
Download `xray.exe` (Windows) or `xray` (macOS/Linux) from
https://github.com/XTLS/Xray-core/releases and put it **next to `app.py`**
(or anywhere on your PATH).

### 5. Run the app
```bash
python app.py
```

## Getting a Cloudflare API Token

1. Go to https://dash.cloudflare.com/profile/api-tokens
2. Click **Create Token** → use the **Edit zone DNS** template.
3. Under *Zone Resources*, pick the domain you want to manage.
4. Copy the token into the app.
5. Your **Zone ID** is on the right side of your domain's overview page.

## Tips

- Start with the **SCAN** tab, then **SPEED**, then **DNS**.
- Save a **Profile** so you can reuse everything with one click.
- The DNS tab creates records as *DNS only* (grey cloud) with TTL Auto.
- No data leaves your computer except calls to Cloudflare and your own
  subscription URL.

## Project files

```
app.py              # main GUI (run this)
scanner.py          # subscription parser + IP ping/probe
xray_test.py        # real speed test using xray-core
cloudflare_api.py   # Cloudflare API v4 client
utils.py            # helpers
gui.py / main.py    # old DNS-only mini app (optional)
requirements.txt
```

## License

MIT — do whatever you want, no warranty.
#
