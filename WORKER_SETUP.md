# Option A — Your-own-origin speed test

The tester tunnels through each Cloudflare edge IP via your VLESS/WS/TLS
config, then makes an HTTP request to **your own domain** and verifies:

1. The response body starts with a **secret marker** (proves the request
   actually reached *your* Worker — not some other CF edge or a cache).
2. At least `--min-bytes` of body were downloaded.
3. The test passes `--retries` times in a row.
4. IPs are ranked by speed first, then latency.

By default, slower-but-real IPs are still written to `sorted_ips.txt` as
`usable_slow`, because they reached your Worker and downloaded the body. Add
`--strict` only if you want to reject everything below `--min-mbps`.

---

## 1. Deploy the Worker (one time, ~1 minute)

Go to <https://dash.cloudflare.com> → **Workers & Pages** → **Create** →
**Create Worker**. Paste the code below, click **Deploy**, then click
**Add custom domain** and attach it to the same domain you already use for
your VLESS config (e.g. `soosis.gamespeednet.top`) at path `/speedtest*`.

```js
// speedtest worker — returns a large random blob when the token matches
const TOKEN  = "CHANGE-ME-LONG-RANDOM-STRING";   // put anything long & random
const MARKER = "LOVABLE-SPEEDTEST-OK\n";         // must match tester
const SIZE   = 8 * 1024 * 1024;                  // 8 MB payload

export default {
  async fetch(req) {
    const url = new URL(req.url);
    if (url.pathname !== "/speedtest") return new Response("not found", { status: 404 });
    if (url.searchParams.get("t") !== TOKEN) return new Response("unauthorized", { status: 401 });

    const enc = new TextEncoder();
    const head = enc.encode(MARKER);
    const stream = new ReadableStream({
      start(c) {
        c.enqueue(head);
        const chunk = new Uint8Array(65536);
        crypto.getRandomValues(chunk);
        let sent = head.length;
        while (sent < SIZE) {
          const n = Math.min(chunk.length, SIZE - sent);
          c.enqueue(chunk.subarray(0, n));
          sent += n;
        }
        c.close();
      },
    });
    return new Response(stream, {
      headers: {
        "content-type": "application/octet-stream",
        "cache-control": "no-store",
        "content-length": String(SIZE + head.length),
      },
    });
  },
};
```

Test the worker directly in a browser once:
`https://YOUR-DOMAIN/speedtest?t=YOUR-TOKEN` — it should download ~8 MB.

---

## 2. Run the tester

```bash
python test_config.py \
  --uuid 9be9976b-3fe6-41d3-bc4b-b63fba678b9b \
  --sni soosis.gamespeednet.top \
  --host soosis.gamespeednet.top \
  --path /au-do \
  --origin-host soosis.gamespeednet.top \
  --origin-path "/speedtest?t=CHANGE-ME-LONG-RANDOM-STRING" \
  --min-bytes 2000000 \
  --min-mbps 1.0 \
  --retries 2 \
  --workers 4
```

Every saved IP actually pulled ≥ 2 MB from **your** Worker through the VLESS
tunnel, twice in a row. `--min-mbps` is now a ranking target unless you add
`--strict`.

Important: do not use high `--workers` for speed tests. If you test 20 IPs at
the same time, they share your internet bandwidth and good IPs can look slow.
Use `--workers 1` for the most accurate ranking, or `--workers 4` for a faster
scan.
