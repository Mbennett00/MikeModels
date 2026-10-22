"""Inline the shared design system (calib/web/core.css) and app code (health.js, book.js, proj.js, odds.js) into a page template."""
import os

HERE = os.path.join(os.path.dirname(__file__), "web")


def inline(html: str) -> str:
    css = open(os.path.join(HERE, "core.css")).read()
    js = "\n".join(open(os.path.join(HERE, n)).read() for n in ("health.js", "book.js", "proj.js", "odds.js"))
    sim = open(os.path.join(HERE, "sim.css")).read()   # the game simulators' shared screens
    sim_js = open(os.path.join(HERE, "sim.js")).read()
    return html.replace("/*CALIB_CSS*/", css).replace("/*SIM_CSS*/", sim).replace("/*SIM_JS*/", sim_js).replace("/*CALIB_JS*/", js)


# offline-capable, installable app: network first (always fresh prices), the last copy when offline
SW = """const C = "pikt-v1";
self.addEventListener("install", e => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  const r = e.request;
  if (r.method !== "GET" || new URL(r.url).origin !== location.origin) return;
  e.respondWith(fetch(r).then(res => { const c = res.clone(); caches.open(C).then(k => k.put(r, c)).catch(() => {}); return res; })
    .catch(() => caches.match(r).then(m => m || caches.match("./index.html"))));
});
"""
MANIFEST = dict(name="Pikt", short_name="Pikt", description="Pikt: NHL, NFL and NBA projections and game sims",
                start_url="./index.html", scope="./", display="standalone", orientation="portrait",
                background_color="#0b0f17", theme_color="#0b0f17",
                icons=[dict(src="icon-192.png", sizes="192x192", type="image/png", purpose="any"),
                       dict(src="icon-512.png", sizes="512x512", type="image/png", purpose="any")],
                shortcuts=[dict(name="NHL", url="./index.html"), dict(name="NFL", url="./nfl.html"), dict(name="NBA", url="./nba.html")])


def write_pwa(out_dir: str):
    import json
    with open(os.path.join(out_dir, "sw.js"), "w") as f:
        f.write(SW)
    with open(os.path.join(out_dir, "manifest.webmanifest"), "w") as f:
        json.dump(MANIFEST, f)


def install(template_path: str, out_path: str):
    with open(out_path, "w") as f:
        f.write(inline(open(template_path).read()))
    write_pwa(os.path.dirname(os.path.abspath(out_path)))
