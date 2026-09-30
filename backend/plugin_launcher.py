"""Single-host supervisor for synchronized plugin generations.

Only fixed application commands are launched. The web process never receives
the Docker socket, a shell command, or a package build tool. This launcher
belongs to the ordinary backend/worker images and watches their shared store.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from bot.plugins.packages import (
    bootstrap_image_package,
    mark_generation,
    observe_role,
    package_root,
    read_state,
)
from bot.services.backup_restore_job import (
    ACTIVE_STATES,
    read_job,
    stopped_marker,
    write_job,
)
from config.settings import get_settings

POLL_SECONDS = 0.5
STOP_TIMEOUT_SECONDS = 30
ROLE_COMMANDS = {
    "backend": "backend/main_backend.py",
    "worker": "backend/main_worker.py",
}


def _start(command: str, generation: int, *, safe_mode: bool = False) -> subprocess.Popen[bytes]:
    environment = os.environ.copy()
    environment["MINISHOP_PLUGIN_GENERATION"] = str(generation)
    if safe_mode:
        environment["MINISHOP_PLUGIN_SAFE_MODE"] = "1"
    else:
        environment.pop("MINISHOP_PLUGIN_SAFE_MODE", None)
    return subprocess.Popen([sys.executable, command], env=environment)


def _stop(child: subprocess.Popen[bytes] | None) -> None:
    if child is None or child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def _roles_stopped(state: dict[str, object], generation: int) -> bool:
    observations = state.get("observations")
    if not isinstance(observations, dict):
        return False
    worker = observations.get("worker")
    return worker == {"generation": generation, "status": "stopped"}


def _handle_restore_job(
    role: str, child: subprocess.Popen[bytes] | None, backup_dir: Path
) -> tuple[bool, subprocess.Popen[bytes] | None]:
    job = read_job(backup_dir)
    if not job or job.get("status") not in ACTIVE_STATES | {"recovery_required"}:
        return False, child
    if job.get("status") == "queued" and time.time() < float(job["execute_after"]):
        return False, child
    _stop(child)
    child = None
    job_id = str(job["id"])
    marker = stopped_marker(backup_dir, job_id)
    if role == "worker":
        marker.touch()
        return True, None
    if job["status"] == "recovery_required":
        return True, None
    if job["status"] == "running":
        # A supervisor restart during an uncertain database switch needs manual review.
        job["status"] = "recovery_required"
        job["error"] = "Restore supervisor restarted during database restore"
        write_job(backup_dir, job)
        return True, None
    if not marker.exists():
        if time.time() - float(job["created_at"]) > 90:
            job["status"] = "failed"
            job["error"] = "Worker did not stop for restore; check the shared backup volume"
            write_job(backup_dir, job)
            return False, None
        return True, None
    job["status"] = "running"
    write_job(backup_dir, job)
    command = [
        sys.executable,
        "-m",
        "scripts.restore_backup",
        str(job["archive_name"]),
        "--operation-id",
        job_id,
    ]
    if job.get("reset_panel_origin"):
        command.append("--reset-panel-origin")
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode == 0:
        job["status"] = "completed"
    else:
        journal = backup_dir / f"restore-{job_id}.json"
        try:
            recovery = json.loads(journal.read_text(encoding="utf-8")) if journal.exists() else {}
        except (OSError, ValueError):
            recovery = {"state": "recovery_required"}
        job["status"] = (
            "recovery_required" if recovery.get("state") == "recovery_required" else "failed"
        )
        job["error"] = (result.stderr or result.stdout).strip()[-1000:]
    write_job(backup_dir, job)
    return job["status"] == "recovery_required", None


def run(role: str) -> int:
    if role not in ROLE_COMMANDS:
        raise ValueError("unknown launcher role")
    root = package_root()
    backup_dir = Path(get_settings().BACKUP_DIR).expanduser()
    bootstrap_image_package(root, role)
    child: subprocess.Popen[bytes] | None = None
    running_generation = -1
    safe_mode = False
    crash_count = 0
    try:
        while True:
            held, child = _handle_restore_job(role, child, backup_dir)
            if held:
                time.sleep(POLL_SECONDS)
                continue
            state = read_state(root)
            desired = int(state["generation"])
            if (
                child is not None
                and child.poll() is None
                and state.get("failed_generation") == desired
                and not safe_mode
            ):
                _stop(child)
                child = None
                safe_mode = True
                observe_role(root, role, desired, "stopped")
            if child is not None and child.poll() is None and running_generation != desired:
                _stop(child)
                child = None
                observe_role(root, role, desired, "stopped")
            elif child is not None and child.poll() is not None:
                child = None
                crash_count += 1
                observe_role(root, role, running_generation, "failed")
                if crash_count >= 2:
                    safe_mode = True
                    mark_generation(root, desired, prepared=False, error="plugin_startup_failed")
            if child is None:
                if running_generation != desired:
                    crash_count = 0
                    safe_mode = False
                    observe_role(root, role, desired, "stopped")
                state = read_state(root)
                if desired and state.get("prepared_generation") != desired:
                    if state.get("failed_generation") == desired:
                        safe_mode = True
                    elif role == "backend" and _roles_stopped(state, desired):
                        # The previous generation is quiescent in both roles.
                        # Migration executes once against the exact desired set.
                        migrated = _start("backend/main_migrate.py", desired)
                        try:
                            result = migrated.wait(timeout=300)
                        except subprocess.TimeoutExpired:
                            _stop(migrated)
                            result = 1
                        mark_generation(
                            root,
                            desired,
                            prepared=result == 0,
                            error="plugin_migration_failed" if result else "",
                        )
                        safe_mode = result != 0
                    else:
                        time.sleep(POLL_SECONDS)
                        continue
                child = _start(ROLE_COMMANDS[role], desired, safe_mode=safe_mode)
                running_generation = desired
                observe_role(root, role, desired, "starting")
                time.sleep(3)
                if child.poll() is None:
                    observe_role(root, role, desired, "safe_mode" if safe_mode else "active")
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        return 0
    finally:
        _stop(child)
        observe_role(root, role, running_generation, "stopped")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: plugin_launcher.py backend|worker")
    raise SystemExit(run(sys.argv[1]))
