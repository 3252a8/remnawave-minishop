APP_REPOSITORY_URL = "https://minishop.minidoc.cc/"
DEV_MOCK_END_MARKER = "<!-- WEBAPP_DEV_MOCK_END -->"
DEV_MOCK_START_MARKER = "<!-- WEBAPP_DEV_MOCK_START -->"
ROBOTS_TX = """User-agent: *
Disallow: /

User-agent: GPTBot
Disallow: /

User-agent: ChatGPT-User
Disallow: /

User-agent: OAI-SearchBot
Disallow: /

User-agent: Google-Extended
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: anthropic-ai
Disallow: /

User-agent: PerplexityBot
Disallow: /

User-agent: Applebot-Extended
Disallow: /
"""
WEBAPP_CONFIG_PLACEHOLDER = "<!-- WEBAPP_CONFIG_SCRIPT -->"
WEBAPP_CSRF_COOKIE_NAME = "rw_webapp_csrf"
WEBAPP_CSRF_EXEMPT_PATHS = {
    "/api/auth/telegram/nonce",
    "/api/auth/token",
    "/api/auth/email/request",
    "/api/auth/email/verify",
    "/api/auth/email/magic",
    "/api/auth/email/password",
    "/api/auth/passkey/options",
    "/api/auth/passkey/verify",
    "/api/auth/logout",
}
WEBAPP_CSRF_HEADER_NAME = "X-CSRF-Token"
WEBAPP_I18N_PLACEHOLDER = "<!-- WEBAPP_I18N_SCRIPT -->"
WEBAPP_JS_PLACEHOLDER = "<!-- WEBAPP_JS_SCRIPT -->"
WEBAPP_LOGO_MAX_BYTES = 2 * 1024 * 1024
WEBAPP_RATE_LIMIT_MAX_REQUESTS = 30
WEBAPP_RATE_LIMIT_WINDOW_SECONDS = 60
WEBAPP_SESSION_COOKIE_NAME = "rw_webapp_session"
WEBAPP_STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
WEBAPP_TELEGRAM_AVATAR_FETCH_TIMEOUT_SECONDS = 4
WEBAPP_TELEGRAM_AVATAR_MAX_BYTES = 512 * 1024
WEBAPP_TELEGRAM_AVATAR_REFRESH_SECONDS = 24 * 60 * 60
WEBAPP_TELEGRAM_OAUTH_STATE_COOKIE_NAME = "rw_tg_oauth_state"
WEBAPP_THEME_ASSET_CONTENT_TYPES = {
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
}
WEBAPP_THEME_ASSET_MAX_BYTES = 10 * 1024 * 1024
WEBAPP_THEME_CSS_MAX_BYTES = 1024 * 1024
