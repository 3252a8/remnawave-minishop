"""Publish a GitLab-built documentation artifact without the Pages build scheduler."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import IO

REPOSITORY = "3252a8/remnawave-minishop"
CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"
PROJECTS = {"dev": "minishop-docs", "main": "minishop-docs-main"}
PROOF_ROUTES = {
    "/_build.json": "_build.json",
    "/": "index.html",
    "/changelog/": "changelog/index.html",
}


def object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return {str(key): item for key, item in value.items()}


def inputs() -> tuple[str, str]:
    sha, branch = os.environ.get("CI_COMMIT_SHA", ""), os.environ.get("CI_COMMIT_BRANCH", "")
    if (
        os.environ.get("CI_PROJECT_PATH") != REPOSITORY
        or os.environ.get("CI_SERVER_URL") != "https://gitlab.com"
        or not re.fullmatch(r"[0-9a-f]{40}", sha)
        or branch not in PROJECTS
    ):
        raise ValueError("Only a pinned GitLab 3252a8 Core dev/main commit can be published")
    return sha, branch


def request_bytes(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    payload: dict[str, object] | None = None,
    method: str | None = None,
) -> bytes:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(
            self,
            req: urllib.request.Request,
            fp: IO[bytes],
            code: int,
            msg: str,
            headers: Message,
            newurl: str,
        ) -> None:
            return None

    request_headers = {"User-Agent": "3252a8-minishop-docs-publisher", **(headers or {})}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
        content = response.read(8 * 1024 * 1024 + 1)
        if response.status not in {200, 201} or len(content) > 8 * 1024 * 1024:
            raise ValueError(f"Unexpected deployment response from {url}")
        return bytes(content)


def assert_source_head(sha: str, branch: str) -> None:
    result = subprocess.run(
        ["git", "ls-remote", f"https://gitlab.com/{REPOSITORY}.git", f"refs/heads/{branch}"],
        capture_output=True,
        text=True,
        check=True,
    )
    if result.stdout.split() != [sha, f"refs/heads/{branch}"]:
        raise ValueError("The GitLab branch moved; refusing a stale documentation deployment")


def file_hashes(dist: Path, sha: str, branch: str) -> dict[str, str]:
    identity = {"schema": 1, "repository": REPOSITORY, "commit": sha, "branch": branch}
    if json.loads((dist / "_build.json").read_bytes()) != identity:
        raise ValueError("Build identity differs from the requested commit and branch")
    files = {}
    for path in sorted(dist.rglob("*")):
        if path.is_symlink():
            raise ValueError("Documentation assets must not contain symlinks")
        if path.is_file():
            files[path.relative_to(dist).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not set(PROOF_ROUTES.values()).issubset(files):
        raise ValueError("Documentation build is incomplete")
    return files


def pages(project: str, suffix: str = "", *, payload: dict[str, object] | None = None) -> object:
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if project not in PROJECTS.values() or not re.fullmatch(r"[0-9a-f]{32}", account) or not token:
        raise ValueError("A pinned Pages project, account ID and Pages Edit token are required")
    response = object_dict(
        json.loads(
            request_bytes(
                f"{CLOUDFLARE_API}/accounts/{account}/pages/projects/{project}{suffix}",
                headers={"Authorization": f"Bearer {token}"},
                payload=payload,
                method="PATCH" if payload is not None else "GET",
            )
        )
    )
    if response.get("success") is not True:
        raise ValueError(f"Cloudflare did not confirm the request for {project}")
    return response.get("result")


def configure_project(project: str, branch: str) -> None:
    record = object_dict(pages(project))
    source = object_dict(record.get("source"))
    config = object_dict(source.get("config"))
    if (
        source.get("type") != "gitlab"
        or config.get("owner") != "3252a8"
        or config.get("repo_name") != "remnawave-minishop"
        or record.get("production_branch") != branch
        or PROJECTS.get(branch) != project
    ):
        raise ValueError(f"Unexpected source or production branch for {project}")
    if (
        config.get("production_deployments_enabled") is False
        and config.get("preview_deployment_setting") == "none"
    ):
        return
    pages(
        project,
        payload={
            "source": {
                **source,
                "config": {
                    **config,
                    "production_deployments_enabled": False,
                    "preview_deployment_setting": "none",
                },
            }
        },
    )
    updated = object_dict(object_dict(object_dict(pages(project)).get("source")).get("config"))
    if (
        updated.get("production_deployments_enabled") is not False
        or updated.get("preview_deployment_setting") != "none"
    ):
        raise ValueError(f"Native Pages builds are still enabled for {project}")
    print(f"GitLab CI owns documentation builds: {project}", flush=True)


def deployment_origin(record: dict[str, object], project: str, sha: str, branch: str) -> str:
    identifier, origin = record.get("id"), record.get("url")
    metadata = object_dict(object_dict(record.get("deployment_trigger")).get("metadata"))
    stage = object_dict(record.get("latest_stage"))
    if (
        not isinstance(identifier, str)
        or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", identifier)
        or origin != f"https://{identifier[:8]}.{project}.pages.dev"
        or metadata.get("commit_hash") != sha
        or metadata.get("branch") != branch
        or stage.get("name") != "deploy"
        or stage.get("status") != "success"
    ):
        raise ValueError(f"Pages did not confirm a successful pinned deployment for {project}")
    return str(origin)


def verify_publication(origins: list[str], files: dict[str, str]) -> None:
    deadline = time.monotonic() + 300
    while True:
        try:
            for origin in origins:
                for route, path in PROOF_ROUTES.items():
                    actual = hashlib.sha256(request_bytes(origin + route)).hexdigest()
                    if actual != files[path]:
                        raise ValueError(
                            f"Published asset differs from the CI build: {origin}{route}"
                        )
            return
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            if isinstance(error, urllib.error.HTTPError) and error.code in {401, 403}:
                raise
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Documentation publication could not be verified: {error}"
                ) from error
            print(f"Waiting for uploaded documentation: {error}", flush=True)
            time.sleep(15)


def publish(dist: Path, sha: str, branch: str, output: Path) -> str:
    project = PROJECTS[branch]
    files = file_hashes(dist, sha, branch)
    assert_source_head(sha, branch)
    wrangler = shutil.which("wrangler")
    if wrangler is None:
        raise RuntimeError("The pinned Wrangler CLI is required")
    configure_project(project, branch)
    output.unlink(missing_ok=True)
    subprocess.run(
        [
            wrangler,
            "pages",
            "deploy",
            str(dist.resolve()),
            "--project-name",
            project,
            "--branch",
            branch,
            "--commit-hash",
            sha,
            "--commit-message",
            f"Documentation {sha}",
            "--commit-dirty=false",
        ],
        cwd=dist.resolve().parent,
        check=True,
        env={
            **os.environ,
            "WRANGLER_SEND_METRICS": "false",
            "WRANGLER_OUTPUT_FILE_PATH": str(output.resolve()),
        },
    )
    entries = [
        object_dict(json.loads(line)) for line in output.read_text(encoding="utf-8").splitlines()
    ]
    results = [
        entry
        for entry in entries
        if entry.get("type") == "pages-deploy" and entry.get("pages_project") == project
    ]
    if len(results) != 1 or not isinstance(results[0].get("deployment_id"), str):
        raise ValueError(f"Wrangler did not identify the uploaded deployment for {project}")
    identifier = str(results[0]["deployment_id"])
    if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", identifier):
        raise ValueError("Invalid deployment ID")
    origin = deployment_origin(
        object_dict(pages(project, f"/deployments/{identifier}")), project, sha, branch
    )
    verify_publication([origin, f"https://{project}.pages.dev"], files)
    assert_source_head(sha, branch)
    print(f"Verified GitLab documentation: {origin} ({branch}, {sha})", flush=True)
    return origin


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("docs-site/dist"))
    parser.add_argument("--output", type=Path, default=Path("pages-deployment.ndjson"))
    args = parser.parse_args()
    sha, branch = inputs()
    publish(args.dist, sha, branch, args.output)


if __name__ == "__main__":
    main()
