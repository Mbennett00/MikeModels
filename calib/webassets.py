"""Inline the shared Model Health component (calib/web/health.css, health.js) into a page template."""
import os

HERE = os.path.join(os.path.dirname(__file__), "web")


def inline(html: str) -> str:
    css = "\n".join(open(os.path.join(HERE, n)).read() for n in ("health.css", "bets.css", "theme.css", "fun.css", "premium.css"))
    js = "\n".join(open(os.path.join(HERE, n)).read() for n in ("health.js", "bets.js", "fun.js"))
    return html.replace("/*CALIB_CSS*/", css).replace("/*CALIB_JS*/", js)


def install(template_path: str, out_path: str):
    with open(out_path, "w") as f:
        f.write(inline(open(template_path).read()))
