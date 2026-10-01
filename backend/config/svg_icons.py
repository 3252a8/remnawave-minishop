"""Allow only inert SVG geometry in subscription guide icons."""

import re
from xml.etree import ElementTree

_SVG_NAMESPACE = "{http://www.w3.org/2000/svg}"
_TAGS = {
    "svg",
    "g",
    "path",
    "rect",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "title",
    "desc",
    "defs",
    "clipPath",
    "mask",
    "linearGradient",
    "radialGradient",
    "stop",
}
_ATTRIBUTES = {
    "viewBox",
    "width",
    "height",
    "x",
    "y",
    "x1",
    "y1",
    "x2",
    "y2",
    "cx",
    "cy",
    "r",
    "rx",
    "ry",
    "d",
    "points",
    "fill",
    "fill-rule",
    "fill-opacity",
    "stroke",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "stroke-dasharray",
    "stroke-dashoffset",
    "stroke-opacity",
    "opacity",
    "transform",
    "clip-rule",
    "clip-path",
    "mask",
    "id",
    "class",
    "role",
    "aria-hidden",
    "aria-label",
    "focusable",
    "preserveAspectRatio",
    "gradientUnits",
    "gradientTransform",
    "offset",
    "stop-color",
    "stop-opacity",
    "spreadMethod",
    "fx",
    "fy",
    "fr",
    "maskUnits",
    "maskContentUnits",
    "clipPathUnits",
    "version",
}


def inert_svg(svg: str) -> bool:
    if len(svg.encode("utf-8")) > 256 * 1024 or "<!" in svg or "<?" in svg:
        return False
    try:
        root = ElementTree.fromstring(svg)
    except ElementTree.ParseError:
        return False
    if root.tag not in {"svg", _SVG_NAMESPACE + "svg"}:
        return False
    for element in root.iter():
        tag = element.tag.removeprefix(_SVG_NAMESPACE)
        if tag not in _TAGS:
            return False
        for attribute, value in element.attrib.items():
            if attribute not in _ATTRIBUTES:
                return False
            # Paint servers may reference local definitions, never another document.
            for reference in re.findall(r"url\s*\((.*?)\)", value, re.IGNORECASE):
                if not re.fullmatch(r"['\"]?#[A-Za-z_][\w.-]*['\"]?", reference.strip()):
                    return False
    return True
