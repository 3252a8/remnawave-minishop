from pathlib import Path

from bot.services.compose_data_mounts import (
    app_data_mounts_are_aligned,
    compose_app_data_mounts,
    find_compose_file,
)


def test_shared_bind_mounts_are_aligned():
    compose = """
services:
  migrate:
    volumes:
      - ./data:/app/data
  backend:
    volumes:
      - "./data:/app/data:rw"
  worker:
    volumes:
      - ${APP_DATA_SOURCE:-./data}:/app/data
"""

    mounts = compose_app_data_mounts(compose)

    assert mounts == {
        "migrate": "./data",
        "backend": "./data",
        "worker": "${APP_DATA_SOURCE:-./data}",
    }
    assert app_data_mounts_are_aligned(mounts)


def test_shared_named_volume_mounts_are_aligned():
    compose = """
services:
  migrate:
    volumes:
      - shop-data:/app/data
  backend:
    volumes:
      - shop-data:/app/data
  worker:
    volumes:
      - shop-data:/app/data
volumes:
  shop-data:
"""

    mounts = compose_app_data_mounts(compose)

    assert app_data_mounts_are_aligned(mounts)


def test_different_mount_sources_are_not_aligned():
    compose = """
services:
  migrate:
    volumes:
      - shop-data:/app/data
  backend:
    volumes:
      - ./data:/app/data
  worker:
    volumes:
      - shop-data:/app/data
"""

    mounts = compose_app_data_mounts(compose)

    assert not app_data_mounts_are_aligned(mounts)


def test_missing_worker_mount_is_not_aligned():
    compose = """
services:
  migrate:
    volumes:
      - ./data:/app/data
  backend:
    volumes:
      - ./data:/app/data
  worker:
    image: example/worker
"""

    mounts = compose_app_data_mounts(compose)

    assert mounts["worker"] is None
    assert not app_data_mounts_are_aligned(mounts)


def test_long_volume_syntax_is_supported():
    compose = """
services:
  backend:
    volumes:
      - type: bind
        source: ./data
        target: /app/data
  worker:
    volumes:
      - type: bind
        source: ./data
        target: /app/data
"""

    mounts = compose_app_data_mounts(compose)

    assert mounts == {"backend": "./data", "worker": "./data"}
    assert app_data_mounts_are_aligned(mounts)


def test_find_compose_file_uses_supported_name(tmp_path: Path):
    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text("services: {}\n", encoding="utf-8")

    assert find_compose_file(tmp_path) == compose_path
