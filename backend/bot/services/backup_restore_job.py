"""Small durable handoff from the admin API to the backend and worker supervisors."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from pathlib import Path
from typing import Any

from config.theme_packages.paths import atomic_bytes, registry_lock

JOB_FILE = ".database-restore-job.json"
ACTIVE_STATES = {"queued", "running"}
TERMINAL_STATES = {"completed", "failed", "recovery_required"}


def job_path(backup_dir: Path) -> Path:
    return backup_dir / JOB_FILE


def read_job(backup_dir: Path) -> dict[str, Any] | None:
    path = job_path(backup_dir)
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Invalid restore job")
    return value


def write_job(backup_dir: Path, job: dict[str, Any]) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    atomic_bytes(job_path(backup_dir), json.dumps(job, sort_keys=True).encode("utf-8"))


def queue_job(
    backup_dir: Path, archive_name: str, *, reset_panel_origin: bool = False
) -> tuple[dict[str, Any], str]:
    token = secrets.token_urlsafe(32)
    with registry_lock(backup_dir):
        current = read_job(backup_dir)
        if current and current.get("status") in ACTIVE_STATES:
            raise RuntimeError("backup_restore_busy")
        job = {
            "id": uuid.uuid4().hex[:16],
            "archive_name": archive_name,
            "reset_panel_origin": reset_panel_origin,
            "status": "queued",
            "execute_after": time.time() + 3,
            "created_at": time.time(),
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
        }
        write_job(backup_dir, job)
    return job, token


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {key: job.get(key) for key in ("id", "archive_name", "status", "error")}


def valid_token(job: dict[str, Any], token: str) -> bool:
    expected = job.get("token_hash")
    return (
        isinstance(expected, str)
        and bool(token)
        and secrets.compare_digest(expected, hashlib.sha256(token.encode()).hexdigest())
    )


def stopped_marker(backup_dir: Path, job_id: str) -> Path:
    return backup_dir / f".database-restore-{job_id}-worker-stopped"
