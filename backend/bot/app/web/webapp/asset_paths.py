from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "subscription_webapp.html"
ASSET_DIR = TEMPLATE_PATH.parent
APP_DEEPLINK_TEMPLATE_PATH = ASSET_DIR / "open_app_gateway.html"
APP_ROOT = Path(__file__).resolve().parents[5]
WEBAPP_LOGO_PROXY_PATH = "/webapp-logo"
WEBAPP_LOGO_CACHE_DIR = APP_ROOT / "data" / "webapp-logo"
WEBAPP_UPLOADED_LOGO_DIR = WEBAPP_LOGO_CACHE_DIR / "uploads"
WEBAPP_UPLOADED_LOGO_PATH = "/webapp-uploaded-logo"
WEBAPP_FAVICON_DIR = WEBAPP_LOGO_CACHE_DIR / "favicons"
WEBAPP_FAVICON_PATH = "/webapp-favicon"
WEBAPP_DEFAULT_BRAND_DIR = ASSET_DIR / "default-brand"
WEBAPP_DEFAULT_LOGO_FILE = WEBAPP_DEFAULT_BRAND_DIR / "default-logo.webp"
WEBAPP_DEFAULT_LOGO_PATH = "/webapp-default-logo.webp"
WEBAPP_DEFAULT_FAVICON_DIGEST = "19b2a242e5b7bc2d"
WEBAPP_DEFAULT_FAVICON_DIR = WEBAPP_DEFAULT_BRAND_DIR / "favicons" / WEBAPP_DEFAULT_FAVICON_DIGEST
WEBAPP_DEFAULT_FAVICON_URL = f"{WEBAPP_FAVICON_PATH}/{WEBAPP_DEFAULT_FAVICON_DIGEST}/icon-180.png"
