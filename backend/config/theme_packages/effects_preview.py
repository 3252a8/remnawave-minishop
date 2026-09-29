"""Executable previews contain only mock data and run in an opaque-origin sandbox.

The preview reuses Core's own script-free theme preview document (the mock home
plus the theme's CSS and tokens) and layers the theme's adapter on top of it.
That way an administrator sees the real theme and its effect together, without
ever executing theme code in an authenticated session.
"""

from __future__ import annotations

import base64
import html
import json
import mimetypes
import re
import secrets
from pathlib import Path

import tinycss2

from .archive import content_digest
from .css import local_reference, walk
from .effects import validate_effects
from .models import PackageError, ThemeEffectsManifest
from .operations import candidate_folder, get_import
from .paths import confined
from .registry import effective_theme, read_registry

CSP_META = re.compile(r'<meta http-equiv="Content-Security-Policy"[^>]*>')

# Runs inside the sandboxed preview iframe. It recreates the effect surfaces the
# real shell renders on top of the mock home, then mounts the theme adapter with
# a mock context. All network access stays disabled by the preview CSP.
BOOTSTRAP = """
const controller = new AbortController(), cleanups = [];
let instance;
const own = fn => { cleanups.push(fn); return fn; };
const host = {
  signal: controller.signal,
  targets: name => config.targets.includes(name)
    ? [...document.querySelectorAll('[data-theme-effect-target="' + name + '"]')] : [],
  watchTargets: () => () => {},
  asset: name => {
    if (!Object.hasOwn(config.assets, name)) throw Error('asset');
    return config.assets[name];
  },
  listen: (target, name, fn) => {
    target.addEventListener(name, fn, { signal: controller.signal });
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
addEventListener('pagehide', stop, { once: true });
setTimeout(stop, 60000);

function surface(name, parent) {
  if (!parent || !config.targets.includes(name)) return;
  if (parent.querySelector('[data-theme-effect-target="' + name + '"]')) return;
  const el = document.createElement('div');
  el.className = 'theme-effect-surface';
  el.setAttribute('data-theme-effect-target', name);
  el.setAttribute('aria-hidden', 'true');
  parent.prepend(el);
}
function isolate(el) {
  if (!el) return null;
  el.style.position = 'relative';
  el.style.isolation = 'isolate';
  return el;
}
try {
  const screen = isolate(document.querySelector('.phone-screen'))
    || isolate(document.querySelector('.app-shell')) || document.body;
  surface('shell.background', screen);
  surface('home.header.surface', isolate(document.querySelector('.home-brand')));
  surface('home.card.surface', isolate(document.querySelector('.status-card')));
  const module = await import(config.entry);
  if (!controller.signal.aborted) {
    instance = await module.mount(host, config.context);
    if (controller.signal.aborted) instance?.dispose();
  }
} catch { stop(); document.documentElement.dataset.effectFailed = 'true'; }
"""


def _resolve(root: Path, key: str, actor: int, operation_id: str):
    """Return ``(folder, theme, metadata, digest)`` for an import or installation."""
    if operation_id:
        record = get_import(root, operation_id, actor)
        candidate = next((item for item in record.candidates if item.key == key), None)
        if (
            record.state != "ready"
            or not candidate
            or not candidate.metadata
            or not candidate.theme
        ):
            raise PackageError("theme_not_found", status=404)
        folder = candidate_folder(root, operation_id, candidate.path)
        return folder, candidate.theme, candidate.metadata, candidate.digest
    entry = read_registry(root).entries.get(key)
    if not entry:
        raise PackageError("theme_not_managed", status=404)
    theme = effective_theme(key, entry)
    theme.css_file = entry.original.css_file
    folder = confined(root, f"_packages/{entry.digest}")
    return folder, theme, entry.metadata, entry.digest


def _data_url(folder: Path, name: str, mime: str | None = None) -> str:
    data = base64.b64encode(confined(folder, name).read_bytes()).decode("ascii")
    content_type = mime or mimetypes.guess_type(name)[0] or "application/octet-stream"
    return f"data:{content_type};base64,{data}"


def _style_url(folder: Path, name: str, assets: list[str]) -> str:
    nodes = tinycss2.parse_stylesheet(confined(folder, name).read_text(encoding="utf-8"))

    def embed(value: str) -> str:
        relative = local_reference(value, name)
        return _data_url(folder, relative) if relative in assets else "data:,"

    walk(nodes, embed)
    css = base64.b64encode(tinycss2.serialize(nodes).encode("utf-8")).decode("ascii")
    return f"data:text/css;base64,{css}"


def _context(theme, variant: str) -> dict[str, object]:
    tokens = theme.tokens.model_dump(exclude_none=True)
    tokens.update(theme.variants.get(variant, theme.tokens).model_dump(exclude_none=True))
    return {
        "variant": variant,
        "colors": {name: value for name, value in tokens.items() if isinstance(value, str)},
        "language": "en",
        "reducedMotion": False,
    }


def _policy(nonce: str) -> str:
    return (
        f"default-src 'none'; script-src 'nonce-{nonce}' data:; "
        "style-src 'unsafe-inline' data:; img-src data:; font-src data:; "
        "connect-src 'none'; worker-src 'none'; frame-src 'none'; object-src 'none'; "
        "base-uri 'none'; form-action 'none'"
    )


def effects_preview(root: Path, key: str, actor: int, operation_id: str = "") -> str:
    from .preview import render_preview

    folder, theme, metadata, digest = _resolve(root, key, actor, operation_id)
    if content_digest(folder) != digest:
        raise PackageError("package_corrupted", status=409)
    validate_effects(folder, metadata)
    manifest: ThemeEffectsManifest | None = metadata.effects
    if not manifest:
        raise PackageError("theme_effects_missing", status=404)

    variant = "light" if theme.active_variant == "light" else "dark"
    # Core's script-free preview already carries the mock home, the theme CSS
    # (assets inlined as data URLs) and the resolved tokens.
    document = CSP_META.sub("", render_preview(folder, theme, variant), count=1)

    config = {
        "entry": _data_url(folder, manifest.entry, "text/javascript"),
        "assets": {name: _data_url(folder, name) for name in manifest.assets},
        "targets": list(manifest.targets),
        "context": _context(theme, variant),
    }
    nonce = secrets.token_urlsafe(24)
    payload = json.dumps(config).replace("<", "\\u003c")
    styles = "".join(
        f'<link rel="stylesheet" href="{_style_url(folder, name, manifest.assets)}">'
        for name in manifest.styles
    )
    injection = (
        '<meta http-equiv="Content-Security-Policy" '
        f'content="{html.escape(_policy(nonce), quote=True)}">'
        "<style>.theme-effect-surface{position:absolute;inset:0;overflow:hidden;"
        "border-radius:inherit;pointer-events:none;z-index:-1}</style>"
        f"{styles}"
        f'<script nonce="{nonce}" type="module">const config = {payload};\n{BOOTSTRAP}</script>'
    )
    return document.replace("</head>", injection + "</head>", 1)
