"""Inline the shared Model Health component (calib/web/health.css, health.js) into a page template."""
import os

HERE = os.path.join(os.path.dirname(__file__), "web")


def inline(html: str) -> str:
    css = open(os.path.join(HERE, "health.css")).read()
    js = open(os.path.join(HERE, "health.js")).read()
    return html.replace("/*CALIB_CSS*/", css).replace("/*CALIB_JS*/", js)


def install(template_path: str, out_path: str):
    with open(out_path, "w") as f:
        f.write(inline(open(template_path).read()))
