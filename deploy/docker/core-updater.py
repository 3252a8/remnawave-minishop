#!/usr/bin/env python3
"""Host-side executor for a single enrolled, running Minishop Compose project (Linux)."""

import argparse
import contextlib
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

STATE = Path("/var/lib/minishop-updater")
SERVICES = ("migrate", "backend", "worker", "frontend")
TAG = re.compile(r"(?:latest|dev|[0-9]+\.[0-9]+\.[0-9]+)")
MARKER = "minishop-enrolled-image-tag"
CLAIM = """
redis.call('SET', KEYS[1], ARGV[1])
redis.call('SET', KEYS[2], '1', 'EX', 30)
local p = redis.call('HGET', KEYS[3], 'phase')
if p == 'queued' then
    redis.call('HSET', KEYS[3], 'phase', 'pulling')
    redis.call('EXPIRE', KEYS[3], 86400)
    return redis.call('HMGET', KEYS[3], 'tag', 'revision')
end
if ARGV[2] == '1' and (p == 'pulling' or p == 'migrating' or p == 'starting') then
    redis.call('HSET', KEYS[3], 'phase', 'failed')
end
return {}
"""


class DeploymentError(ValueError):
    """An actionable message that is safe to show in the service log."""


def command(*args, cwd=None, env=None, timeout=600):
    # Compose config includes application secrets. Never echo captured output/errors.
    result = subprocess.run(
        args, cwd=cwd or STATE, env=env, capture_output=True, check=True, timeout=timeout, text=True
    )
    return result.stdout.strip()


def read_regular(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 2**20:
            raise ValueError("Expected a regular deployment file")
        return stream.read(2**20 + 1), info


def regular(path):
    return read_regular(path)[0]


def atomic(path, content, *, preserve=None):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as out:
        try:
            out.write(content)
            out.flush()
            if preserve is not None and os.name == "posix":
                os.fchown(out.fileno(), preserve.st_uid, preserve.st_gid)
                os.fchmod(out.fileno(), stat.S_IMODE(preserve.st_mode) & 0o777)
            os.fsync(out.fileno())
            out.close()
            os.replace(out.name, path)
        finally:
            Path(out.name).unlink(missing_ok=True)


def with_tag(data, tag):
    pattern = rb"(?m)^[ \t]*(?:export[ \t]+)?IMAGE_TAG[ \t]*=[^\r\n]*"
    line = b"IMAGE_TAG=" + tag.encode("ascii")
    if len(re.findall(pattern, data)) > 1:
        raise ValueError("Duplicate IMAGE_TAG in .env")
    if re.search(pattern, data):
        return re.sub(pattern, line, data)
    if tag == "latest":
        return data
    newline = b"\r\n" if b"\r\n" in data else b"\n"
    return data + (b"" if data.endswith(b"\n") else newline) + line + newline


def fingerprint(directory):
    # IMAGE_TAG is the only setting the executor may change. Always use trusted
    # enrolled configuration to run Compose, even with a writable backup mount.
    return [
        hashlib.sha256(regular(directory / "docker-compose.yml")).hexdigest(),
        hashlib.sha256(with_tag(regular(directory / ".env"), MARKER)).hexdigest(),
    ]


def private_compose(file, *args):
    return command("docker", "compose", "--env-file", "/dev/null", "-f", str(file), *args)


def validate_mounts(model, directory):
    mounts = [
        v
        for service in model["services"].values()
        for v in service.get("volumes", [])
        if v.get("type") == "bind"
    ]
    writable = [Path(v["source"]) for v in mounts if not v.get("read_only")]
    if any(STATE.is_relative_to(p) or directory.parent.is_relative_to(p) for p in writable):
        raise ValueError("The updater and the deployment parent must be outside writable mounts")
    for service in SERVICES:
        for mount in model["services"][service].get("volumes", []):
            if mount.get("type") != "bind":
                continue
            path = Path(mount["source"])
            if path.resolve(strict=True) != path:
                raise ValueError("A service bind source is a symbolic link")
            if any(path.parent.is_relative_to(p) for p in writable):
                raise ValueError("A service bind source is inside a writable application mount")


def isolate_data_subpath(model, directory):
    # Installer profiles mount both the deployment directory for backups and
    # its data/ child. Let the engine resolve that child *inside* the volume.
    # This preserves the existing files without trusting a replaceable host path.
    entries = [
        mount
        for name in SERVICES
        for mount in model["services"][name].get("volumes", [])
        if mount.get("type") == "bind"
        and mount.get("target") == "/app/data"
        and Path(mount["source"]) == directory / "data"
    ]
    if not entries:
        return
    if (directory / "data").resolve(strict=True) != directory / "data":
        raise ValueError("Expected a deployment-local data directory")
    versions = command(
        "docker", "version", "--format", "{{.Client.APIVersion}} {{.Server.APIVersion}}"
    )
    if any(tuple(map(int, v.split("."))) < (1, 45) for v in versions.split()):
        raise ValueError("Bind-mounted data requires Docker API 1.45 or newer")
    key = "minishop-updater-data-root"
    volumes = model.setdefault("volumes", {})
    if key in volumes:
        raise ValueError("Reserved updater volume name already exists")
    volumes[key] = {
        "name": model["name"] + "_" + key,
        "driver": "local",
        "driver_opts": {"type": "none", "o": "bind", "device": str(directory)},
    }
    for entry in entries:
        entry.pop("bind", None)
        entry.update(type="volume", source=key, volume={"subpath": "data", "nocopy": True})


def redis_settings(environment):
    url = urlsplit(environment.get("REDIS_URL") or "")
    if (
        url.scheme != "redis"
        or url.hostname != "redis"
        or url.username is not None
        or url.password is not None
        or url.query
        or url.fragment
        or not re.fullmatch(r"/?[0-9]*", url.path)
    ):
        raise ValueError("Expected the local Compose redis service without authentication or TLS")
    prefix = (environment.get("REDIS_KEY_PREFIX") or "remnawave-tg-shop").strip(":")
    return prefix + ":core-update:", str(url.port or 6379), str(int(url.path.strip("/") or "0"))


def enroll(directory):
    directory = directory.resolve(strict=True)
    before = fingerprint(directory)
    source = directory / "docker-compose.yml"
    env = {**os.environ, "IMAGE_TAG": MARKER}
    model = json.loads(
        command(
            "docker",
            "compose",
            "--env-file",
            str(directory / ".env"),
            "-f",
            str(source),
            "config",
            "--format",
            "json",
            cwd=directory,
            env=env,
        )
    )
    project = model["name"]
    # Verify the running project really belongs to this single-file installation.
    container = command(
        "docker",
        "ps",
        "-q",
        "--filter",
        f"label=com.docker.compose.project={project}",
        "--filter",
        "label=com.docker.compose.service=backend",
    )
    (info,) = json.loads(command("docker", "inspect", container))
    labels = info["Config"]["Labels"]
    active_file = Path(labels["com.docker.compose.project.config_files"])
    previous = STATE / "enrollment.json"
    enrolled = (
        active_file == STATE / "target.json"
        and previous.is_file()
        and json.loads(previous.read_bytes())["directory"] == str(directory)
    )
    if not enrolled and (
        active_file != source or Path(labels["com.docker.compose.project.working_dir"]) != directory
    ):
        raise ValueError("Expected the running single-file project in the enrollment directory")
    isolate_data_subpath(model, directory)
    validate_mounts(model, directory)
    with tempfile.NamedTemporaryFile(dir=STATE, suffix=".json") as check:
        check.write(json.dumps(model).encode())
        check.flush()
        private_compose(check.name, "config", "--quiet")
    registries = set()
    for service in SERVICES:
        config = model["services"][service]
        image = config["image"]
        repo = "3252a8/remnawave-minishop-" + ("backend" if service == "migrate" else service)
        if image not in {
            f"{repo}:{MARKER}",
            f"docker.io/{repo}:{MARKER}",
            f"ghcr.io/{repo}:{MARKER}",
        }:
            raise ValueError("Expected official Minishop images controlled by IMAGE_TAG")
        registries.add("ghcr.io" if image.startswith("ghcr.io/") else "docker.io")
        config.pop("build", None)
    if len(registries) != 1 or before != fingerprint(directory):
        raise ValueError("Registry or deployment changed during enrollment")
    backend_redis = redis_settings(model["services"]["backend"]["environment"])
    if backend_redis != redis_settings(model["services"]["worker"]["environment"]):
        raise ValueError("Backend and worker must use the same local Redis database and key prefix")
    prefix, port, db = backend_redis
    redis_id = command(
        "docker",
        "ps",
        "-q",
        "--filter",
        f"label=com.docker.compose.project={project}",
        "--filter",
        "label=com.docker.compose.service=redis",
    )
    if not re.fullmatch(r"[a-f0-9]{12,64}", redis_id):
        raise ValueError("Expected one running local Redis service")
    if (
        command("docker", "exec", redis_id, "redis-cli", "-e", "-p", port, "-n", db, "PING")
        != "PONG"
    ):
        raise ValueError("The configured Redis database is unavailable")
    # Keep the approved model outside application mounts. The executor does
    # not re-evaluate deployment source files in response to a web request.
    atomic(
        STATE / "enrollment.json",
        json.dumps(
            {
                "directory": str(directory),
                "fingerprint": before,
                "model": model,
                "prefix": prefix,
                "redis_port": port,
                "redis_db": db,
                "registry": registries.pop(),
                "project": project,
            }
        ).encode(),
    )


def apply(config, tag, revision, phase):
    if not TAG.fullmatch(tag) or len(tag) > 64 or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Invalid update selection")
    directory = Path(config["directory"])
    if fingerprint(directory) != config["fingerprint"]:
        raise DeploymentError("Deployment changed. Review it and enroll again.")
    model = json.loads(json.dumps(config["model"]))
    validate_mounts(model, directory)
    images = []
    for service in SERVICES:
        entry = model["services"][service]
        entry["image"] = entry["image"].removesuffix(MARKER) + tag
        entry["environment"]["IMAGE_TAG"] = tag
        images.append(entry["image"])
    # Compose config already escapes literal dollar signs for round trips.
    target = STATE / "target.json"
    atomic(target, json.dumps(model).encode())
    phase("pulling")
    private_compose(target, "pull", *SERVICES)
    # Pin every role to the image we just verified. A second pull of a moving
    # tag must not change the image between migration and startup.
    for service, image in zip(SERVICES, images, strict=True):
        (info,) = json.loads(command("docker", "image", "inspect", image))
        if info["Config"]["Labels"].get("org.opencontainers.image.revision") != revision:
            raise DeploymentError(
                "Publication changed or the image set is incomplete. Check the tag again."
            )
        repo = image.rsplit(":", 1)[0].removeprefix("docker.io/")
        digest = next(
            d
            for d in info["RepoDigests"]
            if d.removeprefix("docker.io/").startswith(repo + "@sha256:")
        )
        model["services"][service]["image"] = digest
    atomic(target, json.dumps(model).encode())
    phase("migrating")
    private_compose(
        target,
        "up",
        "--no-deps",
        "--no-build",
        "--pull",
        "never",
        "--force-recreate",
        "--exit-code-from",
        "migrate",
        "migrate",
    )
    phase("starting")
    private_compose(
        target,
        "up",
        "-d",
        "--wait",
        "--wait-timeout",
        "180",
        "--no-deps",
        "--no-build",
        "--pull",
        "never",
        "backend",
        "worker",
        "frontend",
    )
    if fingerprint(directory) != config["fingerprint"]:
        raise DeploymentError("Deployment changed during update. Check services and enroll again.")
    env_file = directory / ".env"
    data, info = read_regular(env_file)
    if hashlib.sha256(with_tag(data, MARKER)).hexdigest() != config["fingerprint"][1]:
        raise DeploymentError("Environment changed during update. Review .env and enroll again.")
    edited = with_tag(data, tag)
    if edited != data:
        atomic(env_file, edited, preserve=info)


def serve():
    config = json.loads((STATE / "enrollment.json").read_bytes())
    prefix = config["prefix"]
    container = command(
        "docker",
        "ps",
        "-q",
        "--filter",
        f"label=com.docker.compose.project={config['project']}",
        "--filter",
        "label=com.docker.compose.service=redis",
    )
    if not re.fullmatch(r"[a-f0-9]{12,64}", container):
        raise RuntimeError("Redis unavailable")

    def redis(*args):
        return command(
            "docker",
            "exec",
            container,
            "redis-cli",
            "-e",
            "--raw",
            "-p",
            config.get("redis_port", "6379"),
            "-n",
            config.get("redis_db", "0"),
            *args,
            timeout=10,
        )

    def phase(value):
        redis("HSET", prefix + "job", "phase", value)

    fresh = True
    while True:
        job = redis(
            "EVAL",
            CLAIM,
            "3",
            prefix + "registry",
            prefix + "live",
            prefix + "job",
            config["registry"],
            "1" if fresh else "0",
        ).splitlines()
        if len(job) == 2:
            try:
                apply(config, job[0], job[1], phase)
            except (
                OSError,
                ValueError,
                KeyError,
                StopIteration,
                subprocess.SubprocessError,
            ) as exc:
                reason = str(exc) if isinstance(exc, DeploymentError) else type(exc).__name__
                print(f"Update failed: {reason}", flush=True)
                phase("failed")
            else:
                phase("complete")
        fresh = False
        time.sleep(5)


if __name__ == "__main__":
    import fcntl

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enroll", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    STATE.mkdir(mode=0o700, exist_ok=True)
    with (STATE / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.enroll:
            enroll(args.enroll)
        else:
            with contextlib.suppress(KeyboardInterrupt):
                serve()
