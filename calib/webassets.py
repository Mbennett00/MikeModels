"""Inline the shared Model Health component (calib/web/health.css, health.js) into a page template."""
import os

HERE = os.path.join(os.path.dirname(__file__), "web")


def inline(html: str) -> str:
    css = "\n".join(open(os.path.join(HERE, n)).read() for n in ("health.css", "bets.css", "theme.css", "fun.css", "premium.css", "luxe.css", "pro.css", "fit.css"))
    js = "\n".join(open(os.path.join(HERE, n)).read() for n in ("health.js", "bets.js", "fun.js", "home.js", "sharp.js"))
    return html.replace("/*CALIB_CSS*/", css).replace("/*CALIB_JS*/", js)


# offline-capable, installable app: network first (always fresh prices), the last copy when offline
SW = """const C = "mm-v1";
self.addEventListener("install", e => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  const r = e.request;
  if (r.method !== "GET" || new URL(r.url).origin !== location.origin) return;
  e.respondWith(fetch(r).then(res => { const c = res.clone(); caches.open(C).then(k => k.put(r, c)).catch(() => {}); return res; })
    .catch(() => caches.match(r).then(m => m || caches.match("./index.html"))));
});
"""
MANIFEST = dict(name="MikeModels Sportsbook", short_name="MikeModels", description="Paper-money NHL & NFL sportsbook powered by the model",
                start_url="./index.html", scope="./", display="standalone", orientation="portrait",
                background_color="#050608", theme_color="#050608",
                icons=[dict(src="icon-192.png", sizes="192x192", type="image/png", purpose="any"),
                       dict(src="icon-512.png", sizes="512x512", type="image/png", purpose="any")],
                shortcuts=[dict(name="Hockey", url="./index.html"), dict(name="Football", url="./nfl.html")])


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
