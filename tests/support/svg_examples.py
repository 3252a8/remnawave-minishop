"""Representative static SVG exports and unsafe markup for both import paths."""

SAFE_SVG_EXAMPLES = (
    '<svg viewBox="0 0 24 24" aria-labelledby="title" data-name="Layer 1">'
    '<title id="title">Mark</title><path d="M0 0L10 10" vector-effect="non-scaling-stroke" '
    'paint-order="stroke fill" shape-rendering="geometricPrecision" pathLength="10"/></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
    '<defs><symbol id="mark"><path d="M0 0h2v2z"/></symbol>'
    '<linearGradient id="paint"><stop offset="0" stop-color="red"/></linearGradient>'
    '<linearGradient id="copy" xlink:href="#paint"/>'
    '<pattern id="tile" width="2" height="2" patternUnits="userSpaceOnUse">'
    '<use href="#mark"/></pattern></defs>'
    '<use xlink:href="#mark" fill="url(#copy)"/>'
    '<rect width="24" height="24" fill="url(#tile)"/></svg>',
    '<svg><defs><filter id="shadow" filterUnits="userSpaceOnUse">'
    '<feGaussianBlur in="SourceAlpha" stdDeviation="2" result="blur"/>'
    '<feOffset in="blur" dx="1" dy="1"/>'
    '<feColorMatrix type="matrix" values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 1 0"/>'
    '<feBlend in2="SourceGraphic" mode="normal"/></filter></defs>'
    '<path d="M0 0h2v2z" filter="url(#shadow)" color-interpolation-filters="sRGB"/></svg>',
    '<svg><defs><linearGradient id="paint"><stop offset="0" stop-color="red"/>'
    '</linearGradient></defs><path d="M0 0h2v2z" '
    "style=\"fill: url('#paint'); stroke: currentColor; vector-effect: non-scaling-stroke; "
    'paint-order: stroke fill; opacity: .5"/></svg>',
    '<?xml version="1.0" encoding="UTF-8"?><svg><!-- editor export -->'
    '<text x="12" y="12" font-family="sans-serif" font-size="12" font-weight="600" '
    'text-anchor="middle" dominant-baseline="central" xml:space="preserve">'
    '<tspan letter-spacing="1">OK</tspan></text></svg>',
)

UNSAFE_SVG_EXAMPLES = (
    '<svg><use href="https://evil.test/icon.svg#mark"/></svg>',
    '<svg xmlns:xlink="http://www.w3.org/1999/xlink"><use xlink:href="//evil.test/x"/></svg>',
    '<svg><use href="data:image/svg+xml,evil"/></svg>',
    '<svg xml:base="https://evil.test/"><use href="#mark"/></svg>',
    '<svg><path style="fill:url(https://evil.test/a)"/></svg>',
    '<svg><path style="fill:u/**/rl(https://evil.test/a)"/></svg>',
    '<svg><path style="fill:u\\72l(https://evil.test/a)"/></svg>',
    '<svg><path fill="url(&quot;#local\')"/></svg>',
    '<svg><path style="fill:expression(alert(1)); position:fixed"/></svg>',
    '<svg><path style="fill:expression(alert(1))"/></svg>',
    '<svg><path style="--paint:url(#local);fill:var(--paint)"/></svg>',
    "<svg><style>body{display:none}</style></svg>",
    '<svg><foreignObject><div xmlns="http://www.w3.org/1999/xhtml"/></foreignObject></svg>',
    '<svg><image href="https://evil.test/image.png"/></svg>',
    '<svg><animate attributeName="href" values="javascript:alert(1)"/></svg>',
    '<svg xmlns:x="https://evil.test/"><path x:style="fill:red"/></svg>',
    '<svg><path arbitrary="value"/></svg>',
    '<?xml-stylesheet href="https://evil.test/a.css"?><svg/>',
)
