"""One-off: read SharpAPI's docs (and, once known, try the key) from the runner; writes sharp_probe.txt for upload.
The key is read from SHARP_API_KEY and never printed."""
import html
import json
import os
import re
import sys
from urllib.parse import urljoin, urlparse

import requests

H = {"User-Agent": "Mozilla/5.0 (pikt probe)"}
OUT = []


def log(s):
    OUT.append(s)


def text(h):
    h = re.sub(r"(?is)<(script|style|nav|footer|svg)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?i)<(br|/p|/h\d|/li|/tr|/pre|/div)[^>]*>", "\n", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", html.unescape(h))).strip()


def crawl(start, cap=80):
    host, seen, todo = urlparse(start).netloc, set(), [start]
    while todo and len(seen) < cap:
        u = todo.pop(0).split("#")[0]
        if u in seen:
            continue
        seen.add(u)
        try:
            r = requests.get(u, headers=H, timeout=25)
        except Exception as e:
            log(f"### {u}\nERR {e}"); continue
        ct = r.headers.get("content-type", "")
        if r.status_code != 200:
            log(f"### {u}\nHTTP {r.status_code}"); continue
        if "html" not in ct:
            log(f"### {u} ({ct})\n{r.text[:20000]}"); continue
        log(f"### {u}\n{text(r.text)[:12000]}")
        for href in re.findall(r'href="([^"]+)"', r.text):
            v = urljoin(u, href).split("#")[0]
            p = urlparse(v)
            if p.netloc == host and not re.search(r"\.(png|jpg|svg|css|js|ico|woff2?)$", p.path) and v not in seen:
                todo.append(v)


DOCS = not os.path.exists(os.path.join(os.path.dirname(__file__), "sharp_calls.json"))
for extra in () if not DOCS else ("https://docs.sharpapi.io/llms.txt", "https://docs.sharpapi.io/llms-full.txt", "https://docs.sharpapi.io/openapi.json",
              "https://sharpapi.io/llms.txt", "https://sharpapi.io/pricing"):
    try:
        r = requests.get(extra, headers=H, timeout=25)
        log(f"### {extra}\nHTTP {r.status_code}\n{(text(r.text) if 'html' in r.headers.get('content-type', '') else r.text)[:60000] if r.status_code == 200 else ''}")
    except Exception as e:
        log(f"### {extra}\nERR {e}")
if DOCS:
    crawl("https://docs.sharpapi.io/en/")

key = os.environ.get("SHARP_API_KEY", "")
log(f"### key present: {bool(key)} (length {len(key)})")
cf = os.path.join(os.path.dirname(__file__), "sharp_calls.json")   # [{"url":..., "headers":{...}, "params":{...}}] with {KEY} placeholders
calls = json.load(open(cf)) if os.path.exists(cf) else []
for c in calls:
    sub = lambda v: v.replace("{KEY}", key) if isinstance(v, str) else v
    try:
        r = requests.get(c["url"], headers={**H, **{k: sub(v) for k, v in c.get("headers", {}).items()}},
                         params={k: sub(v) for k, v in c.get("params", {}).items()}, timeout=30)
        import time; time.sleep(6)                                 # free tier: 12 requests a minute
        body = r.text.replace(key, "***") if key else r.text
        hdr = {k: v for k, v in r.headers.items() if re.search(r"rate|limit|remaining|access-control|cache", k, re.I)}
        log(f"### CALL {c['url']} -> {r.status_code} {json.dumps(hdr)}\n{body[:60000]}")
    except Exception as e:
        log(f"### CALL {c['url']} ERR {e}")

open("sharp_probe.txt", "w").write("\n\n".join(OUT))
print(f"::notice title=sharp probe::{len(OUT)} sections, {sum(map(len, OUT))} chars")
# what the run notes can carry (the release asset holding the full text isn't always reachable): every market type the
# calls returned, each call's status and error text, and snippets around a search term
allt = "\n".join(OUT)
mts = sorted(set(re.findall(r'"market_type"\s*:\s*"([^"]+)"', allt)))
print("::notice title=probe market types::" + (", ".join(mts) or "none")[:3800])
for c in re.findall(r"### CALL (\S+ -> \d+)[^\n]*\n(.{0,300})", allt):
    print("::notice title=probe call::" + (c[0] + " " + c[1]).replace("%", "%25")[:600])
want = os.environ.get("PROBE_GREP", "")
if want:
    hits = list(dict.fromkeys(m.strip() for m in re.findall(rf".{{0,100}}(?:{want}).{{0,100}}", allt, re.I)))
    for h in hits[:6]:
        print(f"::notice title=probe {want}::" + h.replace("%", "%25"))
