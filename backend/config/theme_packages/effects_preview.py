"""Executable previews contain only mock data and run in an opaque-origin sandbox."""

from __future__ import annotations

import base64
import html
import json
import mimetypes
import secrets
from pathlib import Path

import tinycss2

from .archive import content_digest
from .css import local_reference, walk
from .effects import validate_effects
from .models import PackageError
from .operations import candidate_folder, get_import
from .paths import confined
from .registry import read_registry

BOOTSTRAP = """
const controller = new AbortController(), cleanups = [];
let instance;
const own = fn => { cleanups.push(fn); return fn; };
const host = {
 signal: controller.signal,
 targets: name => config.targets.includes(name)
   ? [...document.querySelectorAll('[data-theme-effect-target="'+name+'"]')] : [],
 watchTargets: () => () => {},
 asset: name => { if (!(name in config.assets)) throw Error('asset'); return config.assets[name]; },
 listen: (target, name, fn) => {
   target.addEventListener(name, fn, {signal: controller.signal});
   return own(() => target.removeEventListener(name, fn));
 },
 animation: fn => {
   let id, stopped = false;
   const tick = time => { if (stopped) return; fn(time); id = requestAnimationFrame(tick); };
   id = requestAnimationFrame(tick);
   return own(() => { stopped = true; cancelAnimationFrame(id); });
 },
 timeout: (fn, ms) => { const id = setTimeout(fn, ms); return own(() => clearTimeout(id)); },
 observe: (target, fn) => {
   const observer = new ResizeObserver(fn); observer.observe(target);
   return own(() => observer.disconnect());
 }
};
const stop = () => {
 controller.abort();
 for (const cleanup of cleanups) { try { cleanup(); } catch {} }
 try { instance?.dispose(); } catch {}
};
addEventListener('pagehide', stop, {once: true});
setTimeout(stop, 60000);
try {
 const module = await import(config.entry);
 if (!controller.signal.aborted) {
   instance = await module.mount(host, config.context);
   if (controller.signal.aborted) instance?.dispose();
 }
} catch { stop(); document.documentElement.dataset.effectFailed = 'true'; }
"""


def effects_preview(root: Path, key: str, actor: int, operation_id: str = "") -> str:
    if operation_id:
        record = get_import(root, operation_id, actor)
        candidate = next((item for item in record.candidates if item.key == key), None)
        if record.state != "ready" or not candidate or not candidate.metadata:
            raise PackageError("theme_not_found", status=404)
        folder = candidate_folder(root, operation_id, candidate.path)
        metadata, digest = candidate.metadata, candidate.digest
    else:
        entry = read_registry(root).entries.get(key)
        if not entry:
            raise PackageError("theme_not_managed", status=404)
        folder = confined(root, f"_packages/{entry.digest}")
        metadata, digest = entry.metadata, entry.digest
    if content_digest(folder) != digest:
        raise PackageError("package_corrupted", status=409)
    validate_effects(folder, metadata)
    manifest = metadata.effects
    if not manifest:
        raise PackageError("theme_effects_missing", status=404)

    def data_url(name: str, mime: str | None = None) -> str:
        data = base64.b64encode(confined(folder, name).read_bytes()).decode("ascii")
        content_type = mime or mimetypes.guess_type(name)[0] or "application/octet-stream"
        return f"data:{content_type};base64,{data}"

    config = {
        "entry": data_url(manifest.entry, "text/javascript"),
        "assets": {name: data_url(name) for name in manifest.assets},
        "targets": manifest.targets,
        "context": {
            "variant": "dark",
            "colors": {"accent": "#00fe7a"},
            "language": "en",
            "reducedMotion": False,
        },
    }
    nonce = secrets.token_urlsafe(24)
    policy = (
        f"default-src 'none'; script-src 'nonce-{nonce}' data:; style-src 'unsafe-inline' data:; "
        "img-src data:; font-src data:; connect-src 'none'; worker-src 'none'; "
        "frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
    )

    def style_url(name: str) -> str:
        nodes = tinycss2.parse_stylesheet(confined(folder, name).read_text(encoding="utf-8"))

        def embed(value: str) -> str:
            relative = local_reference(value, name)
            return data_url(relative) if relative in manifest.assets else "data:,"

        walk(nodes, embed)
        css = base64.b64encode(tinycss2.serialize(nodes).encode()).decode("ascii")
        return f"data:text/css;base64,{css}"

    styles = "".join(
        f'<link rel="stylesheet" href="{style_url(name)}">' for name in manifest.styles
    )
    payload = json.dumps(config).replace("<", "\\u003c")
    return (
        f'<!doctype html><html lang="en" class="theme-key-{html.escape(key, quote=True)}">'
        '<head><meta charset="utf-8">'
        f'<meta http-equiv="Content-Security-Policy" content="{html.escape(policy, quote=True)}">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<style>body{margin:0;background:#10141d;color:white;font:16px system-ui}"
        "main{max-width:380px;margin:auto;padding:24px;position:relative;isolation:isolate}"
        "header,section{position:relative;isolation:isolate;padding:32px;margin:20px 0;"
        "border:1px solid #8886;border-radius:24px;overflow:hidden}"
        "[data-theme-effect-target]{position:absolute;inset:0;pointer-events:none;z-index:-1}"
        "h1{font-size:24px}p{line-height:1.6}</style>"
        f'{styles}</head><body><main><div data-theme-effect-target="shell.background"></div>'
        '<header><div data-theme-effect-target="home.header.surface"></div>'
        "<h1>Theme preview</h1></header><section>"
        '<div data-theme-effect-target="home.card.surface"></div>'
        "<p>Example card</p><p>123.45</p></section></main>"
        f'<script nonce="{nonce}" type="module">const config = {payload};\n{BOOTSTRAP}</script>'
        "</body></html>"
    )
