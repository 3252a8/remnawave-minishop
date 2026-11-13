import pytest

from bot.services.device_detection import detect_device


@pytest.mark.parametrize(
    ("metadata", "router_platform"),
    [
        ({"platform": "OpenWrt", "os_version": "24.10"}, "openwrt"),
        ({"user_agent": "sing-box/1.12 (Linux; OpenWrt)"}, "openwrt"),
        ({"device_model": "GL-MT3000", "platform": "LEDE"}, "openwrt"),
        ({"device_model": "Keenetic Giga", "platform": "Linux"}, "keenetic"),
        ({"platform": "KeeneticOS", "os_version": "4.3"}, "keenetic"),
        ({"user_agent": "curl/8.0 (NDMS 4.3)"}, "keenetic"),
        ({"device_model": "MikroTik hAP", "platform": "RouterOS"}, "routeros"),
        ({"os_version": "DD-WRT v3"}, "dd-wrt"),
        ({"platform": "AsusWRT-Merlin"}, "asuswrt"),
        ({"platform": "FreshTomato"}, "tomato"),
        ({"platform": "AdvancedTomato"}, "tomato"),
        ({"device_model": "Home Router"}, None),
    ],
)
def test_explicit_router_metadata_precedes_generic_linux(metadata, router_platform):
    detection = detect_device(**metadata)
    assert detection.device_type == "router"
    assert detection.router_platform == router_platform


@pytest.mark.parametrize(
    ("metadata", "device_type"),
    [
        ({"device_model": "iPhone 15", "platform": "iOS"}, "phone"),
        ({"device_model": "iPad Air", "user_agent": "Mozilla/5.0 (Macintosh)"}, "tablet"),
        ({"device_model": "MacBook Air", "platform": "macOS"}, "laptop"),
        ({"device_model": "iMac", "platform": "macOS"}, "desktop"),
        ({"device_model": "Android TV", "platform": "Android"}, "tv"),
        ({"platform": "Android", "user_agent": "Mozilla/5.0 (Linux; Android 15)"}, "phone"),
        ({"platform": "Linux", "user_agent": "Mihomo/1.19"}, "desktop"),
        ({"user_agent": "sing-box/1.12"}, "unknown"),
        ({"user_agent": "curl/8.0"}, "unknown"),
        ({"device_model": "Studios Notepad", "user_agent": "Happ/3.1"}, "unknown"),
        ({"device_model": "notopenwrt keeneticized routerostest"}, "unknown"),
        ({}, "unknown"),
    ],
)
def test_other_devices_and_ambiguous_clients_are_not_assumed_to_be_routers(metadata, device_type):
    detection = detect_device(**metadata)
    assert detection.device_type == device_type
    assert detection.router_platform is None
