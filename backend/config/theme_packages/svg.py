"""Validate imported SVG assets without executing or rewriting their markup."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .models import PackageError

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"
MAX_SVG_ELEMENTS = 20_000
MAX_SVG_DEPTH = 64

SAFE_SVG_ELEMENTS = frozenset(
    {
        "circle",
        "clipPath",
        "defs",
        "desc",
        "ellipse",
        "feBlend",
        "feColorMatrix",
        "feComponentTransfer",
        "feComposite",
        "feConvolveMatrix",
        "feDiffuseLighting",
        "feDisplacementMap",
        "feDistantLight",
        "feDropShadow",
        "feFlood",
        "feFuncA",
        "feFuncB",
        "feFuncG",
        "feFuncR",
        "feGaussianBlur",
        "feMerge",
        "feMergeNode",
        "feMorphology",
        "feOffset",
        "fePointLight",
        "feSpecularLighting",
        "feSpotLight",
        "feTile",
        "feTurbulence",
        "filter",
        "g",
        "line",
        "linearGradient",
        "marker",
        "mask",
        "path",
        "pattern",
        "polygon",
        "polyline",
        "radialGradient",
        "rect",
        "stop",
        "svg",
        "symbol",
        "text",
        "textPath",
        "title",
        "tspan",
        "use",
        "view",
    }
)
URI_ATTRIBUTES = frozenset({"href", "src"})
UNSAFE_DECLARATION_RE = re.compile(r"<!\s*(?:doctype|entity)\b", re.IGNORECASE)
UNSAFE_PROCESSING_INSTRUCTION_RE = re.compile(r"<\?(?!xml(?:\s|\?>))", re.IGNORECASE)
URL_FUNCTION_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
UNSAFE_SCHEME_RE = re.compile(r"(?:javascript|vbscript|data)\s*:", re.IGNORECASE)


def _qualified_name(name: str) -> tuple[str, str]:
    if name.startswith("{") and "}" in name:
        namespace, local = name[1:].split("}", 1)
        return namespace, local
    return "", name


def _reject(relative: str, reason: str) -> PackageError:
    return PackageError("unsafe_svg", f"{relative}: {reason}")


def validate_svg(path: Path, relative: str) -> None:
    try:
        body = path.read_bytes()
        text = body.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise _reject(relative, "SVG must be valid UTF-8 XML") from exc

    if UNSAFE_DECLARATION_RE.search(text):
        raise _reject(relative, "DTD and entity declarations are not allowed")
    if UNSAFE_PROCESSING_INSTRUCTION_RE.search(text):
        raise _reject(relative, "processing instructions are not allowed")
    try:
        root = ET.fromstring(body)
    except (ET.ParseError, ValueError) as exc:
        raise _reject(relative, "invalid XML") from exc

    root_namespace, root_name = _qualified_name(root.tag)
    if root_name != "svg" or root_namespace not in {"", SVG_NAMESPACE}:
        raise _reject(relative, "root element must be svg")

    count = 0
    stack = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        count += 1
        if count > MAX_SVG_ELEMENTS:
            raise _reject(relative, "too many elements")
        if depth > MAX_SVG_DEPTH:
            raise _reject(relative, "document is too deeply nested")

        namespace, name = _qualified_name(element.tag)
        if namespace not in {"", SVG_NAMESPACE} or name not in SAFE_SVG_ELEMENTS:
            raise _reject(relative, f"element {name or 'unknown'} is not allowed")

        for raw_name, value in element.attrib.items():
            attribute_namespace, attribute = _qualified_name(raw_name)
            if attribute_namespace not in {"", XML_NAMESPACE, XLINK_NAMESPACE}:
                raise _reject(relative, f"attribute {attribute or 'unknown'} is not allowed")
            lower_attribute = attribute.lower()
            if attribute_namespace == XML_NAMESPACE and lower_attribute not in {"lang", "space"}:
                raise _reject(relative, f"attribute xml:{attribute} is not allowed")
            if attribute_namespace == XLINK_NAMESPACE and lower_attribute != "href":
                raise _reject(relative, f"attribute xlink:{attribute} is not allowed")
            if lower_attribute.startswith("on") or lower_attribute == "style":
                raise _reject(relative, f"attribute {attribute} is not allowed")
            if UNSAFE_SCHEME_RE.search(value):
                raise _reject(relative, f"attribute {attribute} uses an unsafe URL")
            if (
                lower_attribute in URI_ATTRIBUTES
                and value.strip()
                and not value.strip().startswith("#")
            ):
                raise _reject(relative, f"attribute {attribute} must use a local fragment")
            matches = list(URL_FUNCTION_RE.finditer(value))
            if "url(" in value.lower() and not matches:
                raise _reject(relative, f"attribute {attribute} contains an invalid URL")
            if any(not match.group(2).strip().startswith("#") for match in matches):
                raise _reject(relative, f"attribute {attribute} must use a local fragment")

        stack.extend((child, depth + 1) for child in reversed(element))
