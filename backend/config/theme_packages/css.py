"""Parse CSS, constrain resource references, and relocate portable assets."""

from __future__ import annotations

import posixpath
from collections.abc import Callable, Iterable
from pathlib import Path
from urllib.parse import unquote, urlsplit

import tinycss2
from tinycss2 import ast

from .models import PackageError
from .paths import confined, relative_path


def local_reference(value: str, css_path: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or value.startswith("/"):
        raise PackageError("external_css_url", value[:180])
    decoded = unquote(value)
    if "\\" in decoded or ":" in decoded or "\x00" in decoded:
        raise PackageError("unsafe_path", value[:180])
    path = posixpath.normpath(posixpath.join(posixpath.dirname(css_path), decoded))
    return relative_path(path)


def walk(nodes: Iterable[object], visit_url: Callable[[str], str], depth: int = 0) -> None:
    if depth > 64:
        raise PackageError("css_too_deep")
    for node in nodes:
        if isinstance(node, ast.ParseError):
            raise PackageError("invalid_css", str(node.message))
        if isinstance(node, ast.AtRule) and node.lower_at_keyword in {"import", "namespace"}:
            raise PackageError("css_import_not_allowed")
        if isinstance(node, ast.Declaration) and node.lower_name in {"behavior", "-moz-binding"}:
            raise PackageError("unsafe_css_property", str(node.lower_name))
        if isinstance(node, ast.URLToken):
            value = visit_url(str(node.value))
            node.value = value
            node.representation = 'url("' + value.replace("\\", "\\\\").replace('"', '\\"') + '")'
        elif isinstance(node, ast.FunctionBlock):
            if node.lower_name in {"image-set", "-webkit-image-set", "image"}:
                for item in node.arguments:
                    if isinstance(item, ast.StringToken):
                        value = visit_url(str(item.value))
                        item.value = value
                        item.representation = '"' + value.replace('"', "%22") + '"'
            if node.lower_name == "expression":
                raise PackageError("unsafe_css_function")
            if node.lower_name == "url":
                args = [
                    item
                    for item in node.arguments
                    if getattr(item, "type", "") not in {"whitespace", "comment"}
                ]
                if len(args) != 1 or not isinstance(args[0], ast.StringToken):
                    raise PackageError("invalid_css_url")
                value = visit_url(str(args[0].value))
                args[0].value = value
                args[0].representation = '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
            else:
                walk(node.arguments, visit_url, depth + 1)
        for attribute in ("prelude", "content", "value"):
            children = getattr(node, attribute, None)
            if isinstance(children, list):
                walk(children, visit_url, depth + 1)


def validate_css(text: str, theme_root: Path, css_path: str) -> None:
    if len(text.encode("utf-8")) > 1024 * 1024:
        raise PackageError("css_too_large", css_path)

    def check(value: str) -> str:
        local = local_reference(value, css_path)
        resource = confined(theme_root, local)
        if not resource.is_file() or resource.suffix.lower() not in {
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".gif",
            ".ico",
            ".woff",
            ".woff2",
            ".ttf",
            ".otf",
        }:
            raise PackageError("missing_css_asset", local)
        return value

    walk(tinycss2.parse_stylesheet(text, skip_comments=False, skip_whitespace=False), check)

    # Parse declaration blocks as well: malformed declarations must not be
    # accepted just because the tokenizer can produce a qualified rule.
    def declarations(nodes: Iterable[object]) -> None:
        for node in nodes:
            if isinstance(node, ast.QualifiedRule):
                walk(tinycss2.parse_declaration_list(node.content), check)
            elif isinstance(node, ast.AtRule) and node.content is not None:
                if node.lower_at_keyword == "font-face":
                    walk(tinycss2.parse_declaration_list(node.content), check)
                else:
                    declarations(tinycss2.parse_rule_list(node.content))

    declarations(tinycss2.parse_stylesheet(text))


def validate_token(value: str) -> None:
    if len(value) > 1000 or "<" in value or ">" in value:
        raise PackageError("invalid_theme_token")

    def no_url(_value: str) -> str:
        raise PackageError("url_in_theme_token")

    nodes = tinycss2.parse_declaration_list(
        "theme-value:" + value, skip_comments=True, skip_whitespace=True
    )
    if len(nodes) != 1 or not isinstance(nodes[0], ast.Declaration):
        raise PackageError("invalid_theme_token")
    walk(nodes, no_url)


def relocate_css(text: str, key: str, digest: str, css_path: str) -> str:
    nodes = tinycss2.parse_stylesheet(text)
    walk(
        nodes,
        lambda url: (
            f"/webapp-theme-assets/{key}/revisions/{digest}/{local_reference(url, css_path)}"
        ),
    )
    return str(tinycss2.serialize(nodes))


def fork_css(text: str, old_key: str, new_key: str, css_path: str) -> str:
    """Rewrite selector identifiers, not substrings in comments or filenames."""
    nodes = tinycss2.parse_stylesheet(text)
    nodes = [
        node
        for node in nodes
        if not (isinstance(node, ast.AtRule) and node.lower_at_keyword == "import")
    ]

    def rewrite_url(value: str) -> str:
        prefix = f"/webapp-theme-assets/{old_key}/"
        if value.startswith(prefix):
            value = urlsplit(value[len(prefix) :]).path
            return posixpath.relpath(value, posixpath.dirname(css_path) or ".")
        return value

    walk(nodes, rewrite_url)

    def selectors(items: Iterable[object]) -> None:
        for node in items:
            if isinstance(node, ast.IdentToken) and node.value == f"theme-key-{old_key}":
                node.value = f"theme-key-{new_key}"
            for attribute in ("prelude", "content", "arguments"):
                children = getattr(node, attribute, None)
                if isinstance(children, list):
                    selectors(children)

    selectors(nodes)
    return str(tinycss2.serialize(nodes))
