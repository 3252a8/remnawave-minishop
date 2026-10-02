"""Shared static SVG policy for inline guide icons and imported theme assets."""

import json
import re
from pathlib import Path
from xml.etree import ElementTree

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"
MAX_SVG_ELEMENTS = 20_000
MAX_SVG_DEPTH = 64

# One static drawing/presentation vocabulary for the backend and docs demo.
# No scripting, navigation, external images, animation, or page stylesheets.
_POLICY: dict[str, list[str]] = json.loads(
    (Path(__file__).parent / "defaults" / "svg_policy.json").read_text(encoding="utf-8")
)
SAFE_SVG_ELEMENTS = frozenset(_POLICY["elements"])
SVG_PRESENTATION_PROPERTIES = frozenset(_POLICY["presentationProperties"])
SAFE_SVG_ATTRIBUTES = frozenset(_POLICY["attributes"])
UNSAFE_DECLARATION_RE = re.compile(r"<!\s*(?:doctype|entity)\b", re.IGNORECASE)
UNSAFE_PROCESSING_INSTRUCTION_RE = re.compile(r"<\?(?!xml(?:\s|\?>))", re.IGNORECASE)
UNSAFE_SCHEME_RE = re.compile(r"(?:javascript|vbscript|data):", re.IGNORECASE)
LOCAL_FRAGMENT_RE = re.compile(r"#[A-Za-z_][\w.:-]*")
URL_FUNCTION_RE = re.compile(r"url\s*\(\s*(['\"]?)(#[A-Za-z_][\w.:-]*)\1\s*\)", re.IGNORECASE)


def _qualified_name(name: str) -> tuple[str, str]:
    if name.startswith("{") and "}" in name:
        namespace, local = name[1:].split("}", 1)
        return namespace, local
    return "", name


def _value_error(value: str) -> str | None:
    # CSS escapes/comments can conceal url() or a scheme from a text matcher.
    if "\\" in value or "/*" in value or "*/" in value:
        return "CSS escapes and comments are not allowed"
    if re.search(r"expression\s*\(|-moz-binding|behavior\s*:", value, re.IGNORECASE):
        return "active CSS is not allowed"
    if UNSAFE_SCHEME_RE.search(re.sub(r"\s+", "", value)):
        return "uses an unsafe URL"
    without_local_urls = URL_FUNCTION_RE.sub("", value)
    if re.search(r"url\s*\(", without_local_urls, re.IGNORECASE):
        return "must use a local fragment"
    return None


def _style_error(value: str) -> str | None:
    for declaration in value.split(";"):
        if not declaration.strip():
            continue
        property_name, separator, property_value = declaration.partition(":")
        if not separator or property_name.strip().lower() not in SVG_PRESENTATION_PROPERTIES:
            return "contains an unsupported CSS property"
        if not property_value.strip() or any(char in property_value for char in "{}@<>"):
            return "contains an invalid CSS value"
    return None


def svg_markup_error(svg: str) -> str | None:
    """Return the rejection reason, preserving accepted markup without rewriting."""
    if UNSAFE_DECLARATION_RE.search(svg):
        return "DTD and entity declarations are not allowed"
    if UNSAFE_PROCESSING_INSTRUCTION_RE.search(svg):
        return "processing instructions are not allowed"
    try:
        root = ElementTree.fromstring(svg)
    except (ElementTree.ParseError, ValueError):
        return "SVG must be valid UTF-8 XML"
    root_namespace, root_name = _qualified_name(root.tag)
    if root_name != "svg" or root_namespace not in {"", SVG_NAMESPACE}:
        return "root element must be svg"

    count = 0
    stack = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        count += 1
        if count > MAX_SVG_ELEMENTS:
            return "too many elements"
        if depth > MAX_SVG_DEPTH:
            return "document is too deeply nested"
        namespace, name = _qualified_name(element.tag)
        if namespace not in {"", SVG_NAMESPACE} or name not in SAFE_SVG_ELEMENTS:
            return f"element {name or 'unknown'} is not allowed"

        for raw_name, value in element.attrib.items():
            attribute_namespace, attribute = _qualified_name(raw_name)
            if attribute_namespace not in {"", XML_NAMESPACE, XLINK_NAMESPACE}:
                return f"attribute {attribute} is not allowed"
            if attribute_namespace == XML_NAMESPACE:
                if attribute not in {"lang", "space"}:
                    return f"attribute xml:{attribute} is not allowed"
            elif attribute_namespace == XLINK_NAMESPACE:
                if attribute != "href":
                    return f"attribute xlink:{attribute} is not allowed"
            elif (
                attribute not in SAFE_SVG_ATTRIBUTES
                and attribute != "style"
                and not re.fullmatch(r"aria-[a-z-]+", attribute)
                and not re.fullmatch(r"data-[a-z][a-z0-9_.:-]*", attribute)
            ):
                return f"attribute {attribute} is not allowed"
            error = _value_error(value)
            if error:
                return f"attribute {attribute} {error}"
            if attribute == "href" and not LOCAL_FRAGMENT_RE.fullmatch(value.strip()):
                return f"attribute {attribute} must use a local fragment"
            if attribute == "style" and (error := _style_error(value)):
                return f"attribute style {error}"
        stack.extend((child, depth + 1) for child in reversed(element))
    return None


def inert_svg(svg: str) -> bool:
    try:
        size = len(svg.encode("utf-8"))
    except UnicodeError:
        return False
    return size <= 256 * 1024 and svg_markup_error(svg) is None
