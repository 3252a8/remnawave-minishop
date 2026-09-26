"""Regression guards for writable information-page storage in runtime images."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE_PATH = ROOT / "deploy" / "docker" / "Dockerfile"
ENTRYPOINT_PATH = ROOT / "deploy" / "docker" / "backend-entrypoint.sh"


def test_runtime_entrypoint_repairs_persisted_information_page_directory_ownership() -> None:
    entrypoint = ENTRYPOINT_PATH.read_text(encoding="utf-8")

    assert "for directory in /app/data/legal /app/data/pages /app/data/docs; do" in entrypoint
    assert 'if [ -L "$directory" ]; then' in entrypoint
    assert 'chown --no-dereference -R appuser:appuser "$directory"' in entrypoint
    assert "export HOME=/home/appuser" in entrypoint
    assert "exec setpriv --reuid=appuser --regid=appuser --init-groups" in entrypoint


def test_backend_image_installs_the_unprivileged_runtime_entrypoint() -> None:
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")

    assert dockerfile.count("COPY deploy/docker/backend-entrypoint.sh /usr/local/bin/") == 1
    assert dockerfile.count('ENTRYPOINT ["/usr/local/bin/backend-entrypoint.sh"]') == 1
