"""Single-host supervisor for synchronized plugin generations.

Only fixed application commands are launched. The web process never receives
the Docker socket, a shell command, or a package build tool. This launcher
belongs to the ordinary backend/worker images and watches their shared store.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

from bot.plugins.packages import (
    bootstrap_image_package,
    mark_generation,
    observe_role,
    package_root,
    read_state,
)

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


def run(role: str) -> int:
    if role not in ROLE_COMMANDS:
        raise ValueError("unknown launcher role")
    root = package_root()
    bootstrap_image_package(root, role)
    child: subprocess.Popen[bytes] | None = None
    running_generation = -1
    safe_mode = False
    crash_count = 0
    try:
        while True:
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
