"""Run every test, including Linux installer and live upgrade QA, from any host."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILES = ("docker-compose-dev.yml", "docker-compose.remnawave-dev.yml")
SOURCE_VERSION = "2.8.1"
TARGET_VERSION = "3.4.3"


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", line):
            key, value = line.split("=", 1)
            values[key] = value
    return values


class FullTestRun:
    def __init__(self, *, keep_stand: bool) -> None:
        self.project = f"minishop-qa-{uuid.uuid4().hex[:10]}"
        self.output = ROOT / "tmp" / self.project
        self.output.mkdir(parents=True)
        self.env_path = self.output / "stand.env"
        (self.output / "empty.env").write_text("", encoding="utf-8")
        self.compose_path = self.output / "compose.json"
        self.keep_stand = keep_stand
        self.environment = dict(os.environ)
        # A developer's exported production settings must not override the QA env file.
        for filename in COMPOSE_FILES:
            source = (ROOT / filename).read_text(encoding="utf-8")
            for key in re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", source):
                self.environment.pop(key, None)
        self.values = read_env(ROOT / "deploy/dev/remnawave-dev.env.example")
        self.values.update(
            read_env(ROOT / f"deploy/dev/remnawave-stands/{SOURCE_VERSION}/stand.env")
        )
        self.values.update(
            APP_ENV_FILE=self.env_path.as_posix(),
            PANEL_WRITE_MODE="live",
            SUBSCRIPTION_MINI_APP_URL="http://frontend/",
            WEBHOOK_BASE_URL="http://backend:8080",
        )
        for key in self.values:
            self.environment.pop(key, None)
        self.environment["PYTHONUTF8"] = "1"
        self.npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        if not self.npm:
            raise RuntimeError("Node.js 22+ and npm must be installed on the host")

    def run(self, command: list[str], *, log: str | None = None) -> None:
        print(f"Running: {' '.join(command[:7])}", flush=True)
        if log is None:
            subprocess.run(command, cwd=ROOT, env=self.environment, check=True)
            return
        path = self.output / log
        print(f"Log: {path}", flush=True)
        with path.open("w", encoding="utf-8") as stream:
            subprocess.run(
                command,
                cwd=ROOT,
                env=self.environment,
                stdout=stream,
                stderr=subprocess.STDOUT,
                check=True,
            )

    def compose(self, *args: str) -> list[str]:
        return [
            "docker",
            "compose",
            "--project-name",
            self.project,
            "--project-directory",
            str(ROOT),
            "--env-file",
            str(self.env_path),
            "-f",
            str(self.compose_path),
            *args,
        ]

    def write_compose(self, *, upgraded: bool = False) -> None:
        self.env_path.write_text(
            "".join(f"{key}={value}\n" for key, value in self.values.items()),
            encoding="utf-8",
            newline="\n",
        )
        command = [
            "docker",
            "compose",
            "--project-name",
            self.project,
            "--project-directory",
            str(ROOT),
            "--env-file",
            str(self.env_path),
        ]
        for filename in COMPOSE_FILES:
            command.extend(("-f", str(ROOT / filename)))
        command.extend(("--profile", "seed", "config", "--format", "json"))
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=self.environment,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        config = json.loads(result.stdout)
        config["name"] = self.project
        services: dict[str, Any] = config["services"]
        for unwanted in ("newt", "worker", "dev-mock-data"):
            services.pop(unwanted, None)
        for service in services.values():
            service.pop("container_name", None)
            service.pop("ports", None)
            service.pop("profiles", None)
            service["restart"] = "no"
            service.get("depends_on", {}).pop("dev-mock-data", None)
            for mount in service.get("volumes", []):
                if mount["target"] == "/app/data":
                    mount.clear()
                    mount.update(type="volume", source="qa-app-data", target="/app/data")
                elif mount["target"] == "/app/compose-source":
                    mount["read_only"] = True
            if "build" in service:
                target = service["build"]["target"]
                service["image"] = f"{self.project}-{target}:local"
        for resource in (*config["volumes"].values(), *config["networks"].values()):
            resource.pop("name", None)
            resource.pop("external", None)
        config["volumes"]["qa-app-data"] = {}
        for seed in ("dev-seed", "remnawave-dev-seed"):
            services["backend"]["depends_on"][seed] = {
                "condition": "service_completed_successfully",
                "required": True,
            }
        services["qa"] = {
            "image": f"{self.project}-tests:local",
            "build": {
                "context": str(ROOT),
                "dockerfile": "deploy/docker/Dockerfile",
                "target": "qa",
            },
            "working_dir": "/workspace",
            "environment": {
                "PYTHONPATH": "/workspace/backend:/workspace",
                "PYTHONDONTWRITEBYTECODE": "1",
                "COVERAGE_FILE": "/reports/.coverage",
                "QA_FULLSTACK": "1",
                "QA_ENV_FILE": "/reports/stand.env",
                "QA_REMNAWAVE_UPGRADE": "1" if upgraded else "0",
                "QA_REMNAWAVE_UPGRADE_FROM": SOURCE_VERSION,
                "QA_REMNAWAVE_PRESET": TARGET_VERSION if upgraded else SOURCE_VERSION,
                "QA_API_BASE_URL": "http://frontend",
                "QA_FRONTEND_URL": "http://frontend",
                "QA_WEBHOOK_BASE_URL": "http://backend:8080",
                "QA_REMNAWAVE_API_URL": "http://remnawave:3000/api",
                "QA_REMNAWAVE_HEALTH_URL": "http://remnawave:3001/health",
                "QA_DB_DSN": "postgresql://remnawave_minishop:remnawave_minishop@postgres:5432/remnawave_minishop",
                "QA_PAYMENT_SECRET": self.values["QA_PAYMENT_SECRET"],
                "MINISHOP_RUN_DOCKER_INTEGRATION": "1",
            },
            "volumes": [
                {"type": "bind", "source": str(ROOT), "target": "/workspace", "read_only": True},
                {"type": "bind", "source": str(self.output), "target": "/reports"},
                {
                    "type": "bind",
                    "source": "/var/run/docker.sock",
                    "target": "/var/run/docker.sock",
                },
                *[
                    {
                        "type": "bind",
                        "source": str(self.output / "empty.env"),
                        "target": f"/workspace/{name}",
                        "read_only": True,
                    }
                    for name in (".env", ".env.remnawave-dev")
                    if (ROOT / name).exists()
                ],
            ],
            "networks": ["remnawave-minishop"],
        }
        self.compose_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    def pytest(self, report: str, *paths: str) -> None:
        self.run(
            self.compose(
                "run",
                "--rm",
                "--no-deps",
                "qa",
                "python",
                "-m",
                "pytest",
                "-q",
                "-rs",
                "-o",
                "cache_dir=/tmp/pytest-cache",
                f"--junitxml=/reports/{report}.xml",
                *paths,
            ),
            log=f"{report}.log",
        )
        root = ElementTree.parse(self.output / f"{report}.xml").getroot()
        skipped = root.findall(".//testcase/skipped")
        if skipped:
            reasons = sorted({item.get("message", "unknown reason") for item in skipped})
            raise RuntimeError(f"{len(skipped)} tests skipped: {'; '.join(reasons)}")
        print(f"{report}: {len(root.findall('.//testcase'))} tests, zero skips", flush=True)

    def execute(self) -> None:
        self.run(["docker", "info", "--format", "{{.OSType}}"])
        self.run(["docker", "compose", "version", "--short"])
        self.write_compose()
        try:
            self.run(self.compose("config", "--quiet"))
            self.run(self.compose("build", "backend", "frontend", "qa"), log="build.log")
            self.run(
                self.compose(
                    "up",
                    "-d",
                    "--wait",
                    "--wait-timeout",
                    "300",
                    "postgres",
                    "redis",
                    "remnawave-db",
                    "remnawave-redis",
                    "remnawave",
                    "remnawave-dev-seed",
                    "remnawave-subscription-page",
                    "migrate",
                    "dev-seed",
                    "backend",
                    "frontend",
                ),
                log="start.log",
            )
            self.pytest("source-panel", "tests/qa/test_remnawave_panel_contract.py")
            print(
                f"Upgrading Panel {SOURCE_VERSION} -> {TARGET_VERSION} on the same database",
                flush=True,
            )
            self.values["REMNAWAVE_DEV_VERSION"] = TARGET_VERSION
            lock = json.loads(
                (
                    ROOT / f"deploy/dev/remnawave-stands/{TARGET_VERSION}/versions.lock.json"
                ).read_text(encoding="utf-8")
            )
            self.values["REMNAWAVE_NODE_VERSION"] = lock["remnawave_node"]
            self.values["REMNAWAVE_SUBSCRIPTION_PAGE_VERSION"] = lock["subscription_page"]
            self.write_compose(upgraded=True)
            self.run(self.compose("pull", "remnawave"), log="upgrade-pull.log")
            self.run(
                self.compose(
                    "up", "-d", "--no-deps", "--wait", "--wait-timeout", "300", "remnawave"
                ),
                log="upgrade.log",
            )
            # Drop cached source-version capabilities in the backend after the live upgrade.
            self.run(
                self.compose(
                    "up",
                    "-d",
                    "--no-deps",
                    "--force-recreate",
                    "--wait",
                    "--wait-timeout",
                    "180",
                    "backend",
                ),
                log="backend-restart.log",
            )
            self.pytest("all-tests", "tests")
            assert self.npm is not None
            for check in (
                "check:lockfiles",
                "check:docs",
                "check:architecture",
                "lint:py",
                "format:check:py",
                "typecheck:py",
                "check:frontend",
            ):
                self.run([self.npm, "run", check], log=f"{check.replace(':', '-')}.log")
            print(f"All checks passed without skipped tests. Reports: {self.output}", flush=True)
        finally:
            if self.compose_path.exists():
                with (self.output / "compose.log").open("w", encoding="utf-8") as stream:
                    subprocess.run(
                        self.compose("logs", "--no-color", "--tail", "200"),
                        cwd=ROOT,
                        env=self.environment,
                        stdout=stream,
                        stderr=subprocess.STDOUT,
                        check=False,
                    )
                if self.keep_stand:
                    print(
                        f"Stand retained: {self.project}; config: {self.compose_path}", flush=True
                    )
                else:
                    self.run(
                        self.compose("down", "--volumes", "--remove-orphans"), log="cleanup.log"
                    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep-stand",
        action="store_true",
        help="Retain this run's containers and volumes for debugging",
    )
    args = parser.parse_args()
    run = FullTestRun(keep_stand=args.keep_stand)
    print(f"QA project: {run.project}\nReports: {run.output}", flush=True)
    try:
        run.execute()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Full test run failed: {exc}\nLogs: {run.output}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
