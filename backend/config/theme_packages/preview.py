"""Opaque-origin, script-free preview using a captured mock account home."""

from __future__ import annotations

import base64
import html
import mimetypes
import re
from pathlib import Path
from urllib.parse import urlsplit

import tinycss2

from config.webapp_themes_models import WebappTheme

from .css import fork_css, local_reference, validate_token, walk
from .models import PackageError
from .operations import candidate_folder, get_import
from .paths import confined
from .registry import effective_theme, read_registry

SNAPSHOT = Path(__file__).parents[2] / "bot/app/web/themes/preview"


def preview_import_image(root: Path, operation_id: str, actor: int, key: str) -> tuple[bytes, str]:
    record = get_import(root, operation_id, actor)
    if record.state != "ready":
        raise PackageError("import_not_ready", status=409)
    candidate = next((item for item in record.candidates if item.key == key), None)
    if not candidate or candidate.error or not candidate.theme:
        raise PackageError("invalid_theme_selection")
    if not candidate.metadata.preview:
        raise PackageError("theme_preview_unavailable", status=404)
    folder = candidate_folder(root, operation_id, candidate.path)
    preview = confined(folder, candidate.metadata.preview)
    try:
        content = preview.read_bytes()
    except OSError as exc:
        raise PackageError("theme_preview_unavailable", status=404) from exc
    content_type = mimetypes.guess_type(preview.name)[0] or "application/octet-stream"
    return content, content_type


def preview_import(root: Path, operation_id: str, actor: int, key: str, variant: str) -> str:
    record = get_import(root, operation_id, actor)
    if record.state != "ready":
        raise PackageError("import_not_ready", status=409)
    candidate = next((item for item in record.candidates if item.key == key), None)
    if not candidate or candidate.error or not candidate.theme:
        raise PackageError("invalid_theme_selection")
    folder = candidate_folder(root, operation_id, candidate.path)
    return render_preview(folder, candidate.theme, variant)


def preview_installed(root: Path, key: str, variant: str) -> str:
    from config.webapp_themes_store import load_webapp_theme_dir

    entry = read_registry(root).entries.get(key)
    if entry:
        folder = confined(root, f"_packages/{entry.digest}")
        theme = effective_theme(key, entry)
        theme.css_file = entry.original.css_file
    else:
        theme = next((theme for theme in load_webapp_theme_dir(root) if theme.key == key), None)
        if theme is None:
            raise PackageError("theme_not_found", status=404)
        folder = confined(root, key)
    return render_preview(folder, theme, variant, legacy=entry is None)


def _legacy_preview_css(folder: Path, theme: WebappTheme) -> str:
    """Render old CSS best-effort; unavailable resources never block the preview."""
    try:
        path = confined(folder, theme.css_file or "")
        if path.stat().st_size > 1024 * 1024:
            return ""
        nodes = tinycss2.parse_stylesheet(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, PackageError):
        return ""
    budget = 20 * 1024 * 1024

    def embed(value: str) -> str:
        nonlocal budget
        try:
            parsed = urlsplit(value)
            if parsed.scheme or parsed.netloc:
                return "data:,"
            value = parsed.path
            prefix = f"/webapp-theme-assets/{theme.key}/"
            relative = (
                value[len(prefix) :]
                if value.startswith(prefix)
                else local_reference(value, theme.css_file or "")
            )
            resource = confined(folder, relative)
            size = resource.stat().st_size
            if size > min(budget, 10 * 1024 * 1024):
                return "data:,"
            budget -= size
            mime = mimetypes.guess_type(resource.name)[0] or "application/octet-stream"
            return "data:" + mime + ";base64," + base64.b64encode(resource.read_bytes()).decode()
        except (OSError, ValueError, PackageError):
            return "data:,"

    safe: list[object] = []
    for node in nodes:
        try:
            walk([node], embed)
        except PackageError:
            continue
        safe.append(node)
    return str(tinycss2.serialize(safe))


def render_preview(folder: Path, theme: WebappTheme, variant: str, *, legacy: bool = False) -> str:
    css = ""
    if theme.css_file and legacy:
        css = _legacy_preview_css(folder, theme)
    elif theme.css_file:
        css = confined(folder, theme.css_file).read_text(encoding="utf-8")
        nodes = tinycss2.parse_stylesheet(fork_css(css, theme.key, theme.key, theme.css_file))

        def data_url(value: str) -> str:
            resource = confined(folder, local_reference(value, theme.css_file or ""))
            mime = mimetypes.guess_type(resource.name)[0] or "application/octet-stream"
            return "data:" + mime + ";base64," + base64.b64encode(resource.read_bytes()).decode()

        walk(nodes, data_url)
        css = str(tinycss2.serialize(nodes))
    tokens = theme.tokens.model_dump(exclude_none=True)
    tokens.update(theme.variants.get(variant, theme.tokens).model_dump(exclude_none=True))
    declarations: list[str] = []
    for name, value in tokens.items():
        css_name = name.replace("_", "-")
        if name.startswith("home_logo_scale"):
            scale = float(value)
            declarations.append(f"--{css_name}:{scale / 100:g}")
        elif isinstance(value, str):
            try:
                validate_token(value)
            except PackageError:
                if legacy:
                    continue
                raise
            declarations.append(f"--{css_name}:{value}")
    base_css = (SNAPSHOT / "home.css").read_text(encoding="utf-8")
    base_css = re.sub(r"@font-face\s*\{[^}]*\}", "", base_css, flags=re.I)
    base_css = re.sub(r'url\((?![\'"]?data:)[^)]*\)', "none", base_css, flags=re.I)
    body = (SNAPSHOT / "home.html").read_text(encoding="utf-8")
    body = body.replace(
        'class="app-shell',
        'style="' + html.escape(";".join(declarations), quote=True) + '" class="app-shell',
        1,
    )
    styles = base_css + "\n" + css
    # HTML raw-text termination is independent of CSS parsing.
    styles = styles.replace("<", r"\3c ")
    mode = "light" if variant == "light" else "dark"
    body = body.replace("THEME_KEY_PLACEHOLDER", "theme-key-" + theme.key)
    body = body.replace("theme-dark", "theme-" + mode)
    policy = (
        "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
        "font-src data:; base-uri 'none'; form-action 'none'"
    )
    return (
        '<!doctype html><html lang="ru" class="theme-'
        + mode
        + " theme-key-"
        + html.escape(theme.key, quote=True)
        + '"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="' + policy + '">'
        "<title>Minishop theme preview</title><style>"
        + styles
        + "</style></head><body>"
        + body
        + "</body></html>"
    )
