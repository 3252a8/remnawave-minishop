import asyncio
import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.services import core_update_notices, core_updates


def host_executor():
    path = Path(__file__).resolve().parents[2] / "deploy/docker/core-updater.py"
    spec = importlib.util.spec_from_file_location("core_updater_host", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_image_check_compares_published_revision_and_caches_by_tag(monkeypatch):
    revision = "a" * 40
    remote = AsyncMock(
        return_value=core_updates.Release(tag="dev", revision=revision, version="dev")
    )
    monkeypatch.setattr(core_updates, "_published_image", remote)
    monkeypatch.setattr(core_updates, "_cache", {})
    monkeypatch.setattr(core_updates, "resolve_build_provenance", lambda: "official")
    monkeypatch.setattr(core_updates, "resolve_app_version", lambda: "v3.8.6-dev+g" + revision[:8])
    assert not core_updates.available(asyncio.run(core_updates.check_image("dev", "docker.io")))
    monkeypatch.setattr(core_updates, "resolve_app_version", lambda: "v3.8.6-dev+g12345678")
    assert core_updates.available(asyncio.run(core_updates.check_image("dev", "docker.io")))
    assert asyncio.run(core_updates.check_image("other/project:latest", "docker.io")) is None
    remote.assert_awaited_once_with("dev", "docker.io")
    remote.side_effect = TimeoutError()
    assert asyncio.run(core_updates.check_image("latest", "docker.io")) is None


def test_worker_notifies_linked_admins_once_and_obeys_preference(monkeypatch):
    ctx = MagicMock()
    ctx.settings.REDIS_KEY_PREFIX = "test"
    ctx.bot.send_message = AsyncMock()
    ctx.notification_service.admin_telegram_ids = AsyncMock(return_value=[123, 456])
    ctx.require_i18n.return_value.gettext.return_value = "New image"
    values: dict[str, str] = {}

    async def write(key, value):
        values[key] = value

    redis = MagicMock()
    redis.get = AsyncMock(side_effect=values.get)
    redis.set = write
    monkeypatch.setattr(core_update_notices, "get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(core_update_notices, "resolve_build_provenance", lambda: "official")
    monkeypatch.setattr(core_update_notices, "available", lambda release: True)
    monkeypatch.setattr(core_update_notices, "resolve_app_version", lambda: "v1")
    release = core_updates.Release(tag="latest", revision="a" * 40, version="v2")
    monkeypatch.setattr(core_update_notices, "check_image", AsyncMock(return_value=release))
    lock = MagicMock()
    lock.__aenter__.return_value = True
    monkeypatch.setattr(core_update_notices, "redis_lock", lambda *args, **kwargs: lock)
    asyncio.run(core_update_notices.deliver_update_notices(ctx))
    asyncio.run(core_update_notices.deliver_update_notices(ctx))
    assert [call.args[0] for call in ctx.bot.send_message.await_args_list] == [123, 456]
    values["test:core-update:notify"] = "0"
    release.revision = "b" * 40
    asyncio.run(core_update_notices.deliver_update_notices(ctx))
    assert ctx.bot.send_message.await_count == 2


@pytest.mark.parametrize("mismatch", [True, False])
def test_host_checks_all_images_before_migration_and_persists_tag_only_on_success(
    tmp_path, monkeypatch, mismatch
):
    host = host_executor()
    private = tmp_path / "host"
    private.mkdir()
    deploy = tmp_path / "shop"
    deploy.mkdir()
    (deploy / ".env").write_bytes(b"IMAGE_TAG=latest\nKEEP=this\n")
    (deploy / "docker-compose.yml").write_bytes(b"enrolled")
    monkeypatch.setattr(host, "STATE", private)
    # This test runs on Windows too. Linux uses O_NOFOLLOW for the same regular files.
    if host.os.name == "nt":
        monkeypatch.setattr(host.os, "O_NOFOLLOW", 0, raising=False)
        monkeypatch.setattr(host.os, "O_NONBLOCK", 0, raising=False)
    services = {
        name: {
            "image": "example/" + name + ":" + host.MARKER,
            "environment": {"PASSWORD": "abc$$$$x"},
        }
        for name in host.SERVICES
    }
    config = {
        "directory": str(deploy),
        "model": {"services": services},
        "fingerprint": host.fingerprint(deploy),
    }
    revision = "a" * 40
    calls = []

    def inspect(*args):
        repo = args[-1].split(":")[0]
        rev = "b" * 40 if mismatch and repo.endswith("worker") else revision
        return json.dumps(
            [
                {
                    "Config": {"Labels": {"org.opencontainers.image.revision": rev}},
                    "RepoDigests": [repo + "@sha256:" + "a" * 64],
                }
            ]
        )

    monkeypatch.setattr(host, "command", inspect)
    monkeypatch.setattr(host, "private_compose", lambda file, *args: calls.append(args))
    phases: list[str] = []
    if mismatch:
        with pytest.raises(ValueError, match="Publication changed"):
            host.apply(config, "dev", revision, phases.append)
        assert phases == ["pulling"]
        assert (deploy / ".env").read_bytes() == b"IMAGE_TAG=latest\nKEEP=this\n"
    else:
        host.apply(config, "dev", revision, phases.append)
        assert phases == ["pulling", "migrating", "starting"]
        assert "--exit-code-from" in calls[1] and "--wait" in calls[2]
        assert (deploy / ".env").read_bytes() == b"IMAGE_TAG=dev\nKEEP=this\n"
        target = json.loads((private / "target.json").read_bytes())
        assert all(
            "@sha256:" in item["image"] and item["environment"]["PASSWORD"] == "abc$$$$x"
            for item in target["services"].values()
        )
    with pytest.raises(ValueError, match="Invalid update selection"):
        host.apply(config, "../unsafe", revision, phases.append)
    (deploy / ".env").write_bytes(b"CHANGED=1\n")
    with pytest.raises(ValueError, match="Deployment changed"):
        host.apply(config, "latest", revision, phases.append)


def test_installer_profile_reuses_data_inside_the_deployment_volume(tmp_path, monkeypatch):
    host = host_executor()
    directory = tmp_path / "store"
    (directory / "data").mkdir(parents=True)
    services = {name: {"volumes": []} for name in host.SERVICES}
    for service in ("backend", "worker", "migrate"):
        services[service]["volumes"].append(
            {"type": "bind", "source": str(directory / "data"), "target": "/app/data"}
        )
    services["backend"]["volumes"].append(
        {"type": "bind", "source": str(directory), "target": "/app/compose-source"}
    )
    model = {"name": "shop", "services": services}
    monkeypatch.setattr(host, "command", lambda *args: "1.45 1.45")
    host.isolate_data_subpath(model, directory)
    host.validate_mounts(model, directory)
    assert model["volumes"]["minishop-updater-data-root"]["driver_opts"]["device"] == str(directory)
    assert services["migrate"]["volumes"][0]["volume"] == {"subpath": "data", "nocopy": True}


def test_host_uses_the_same_redis_database_and_namespace_as_the_application():
    host = host_executor()
    assert host.redis_settings(
        {"REDIS_URL": "redis://redis:6380/3", "REDIS_KEY_PREFIX": ":shop:"}
    ) == ("shop:core-update:", "6380", "3")
    for url in (
        "redis://elsewhere/1",
        "rediss://redis/1",
        "redis://user@redis/1",
        "redis://redis/invalid",
    ):
        with pytest.raises(ValueError):
            host.redis_settings({"REDIS_URL": url})


def test_admin_routes_require_authorization_before_contacting_registry_or_host():
    from aiohttp import web
    from aiohttp.test_utils import make_mocked_request

    from bot.app.web.admin_api_impl import core_updates as routes
    from bot.app.web.context import SETTINGS

    app = web.Application()
    app[SETTINGS] = MagicMock()

    for handler in (
        routes.admin_core_updates_route,
        routes.admin_core_check_route,
        routes.admin_core_preference_route,
        routes.admin_core_apply_route,
    ):
        with pytest.raises(web.HTTPUnauthorized):
            asyncio.run(handler(make_mocked_request("POST", "/api/admin/core-updates", app=app)))
