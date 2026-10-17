"""Repair a stale Cloudflare callback only after verifying immutable deployments."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from email.message import Message
from typing import IO, Any
from urllib.parse import urlsplit

REPOSITORY = "3252a8/remnawave-minishop"
GITLAB_API = "https://gitlab.com/api/v4/projects/82551396"
GITHUB_API = f"https://api.github.com/repos/{REPOSITORY}"
STATUS_NAME = "Cloudflare Pages: minishop-docs"
CLOUDFLARE_APP_ID = 85455


def request_bytes(
    url: str, *, headers: dict[str, str] | None = None, payload: dict[str, Any] | None = None
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

    request_headers = {"User-Agent": "3252a8-minishop-docs-status", **(headers or {})}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=request_headers)
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
        content = response.read(8 * 1024 * 1024 + 1)
        if response.status != 200 and response.status != 201:
            raise ValueError("Deployment endpoint did not return success")
        if len(content) > 8 * 1024 * 1024:
            raise ValueError("Deployment response is too large")
        return bytes(content)


def deployment_url(target: str) -> str:
    parsed = urlsplit(target)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
        raise ValueError("Unexpected Cloudflare deployment URL")
    if re.fullmatch(r"[0-9a-f]{8}\.minishop-docs\.pages\.dev", parsed.hostname or ""):
        return f"https://{parsed.hostname}"
    if parsed.hostname == "dash.cloudflare.com":
        match = re.search(
            r"/pages/view/minishop-docs/([0-9a-f]{8})-[0-9a-f-]{27,}(?:$|[&#])", target
        )
        if match:
            return f"https://{match[1]}.minishop-docs.pages.dev"
    raise ValueError("Unexpected Cloudflare deployment URL")


def build_identity(sha: str, branch: str) -> dict[str, str | int]:
    return {"schema": 1, "repository": REPOSITORY, "commit": sha, "branch": branch}


def github_deployment(sha: str, branch: str, github_token: str) -> str | None:
    headers = {"Authorization": f"Bearer {github_token}"} if github_token else {}
    data = json.loads(
        request_bytes(
            f"{GITHUB_API}/commits/{sha}/check-runs?app_id={CLOUDFLARE_APP_ID}"
            "&filter=all&per_page=100",
            headers=headers,
        )
    )
    for check in data["check_runs"]:
        if (
            check.get("head_sha") != sha
            or check.get("app", {}).get("id") != CLOUDFLARE_APP_ID
            or check.get("conclusion") != "success"
        ):
            continue
        match = re.search(
            r"https://[0-9a-f]{8}\.minishop-docs-github\.pages\.dev\b",
            check.get("output", {}).get("summary") or "",
        )
        if match:
            try:
                identity = json.loads(request_bytes(f"{match[0]}/_build.json"))
            except (urllib.error.URLError, TimeoutError, ValueError):
                continue
            if identity == build_identity(sha, branch):
                return match[0]
    return None


def verify_publication(gitlab_url: str, github_url: str, sha: str, branch: str) -> None:
    expected = build_identity(sha, branch)
    for origin in (gitlab_url, github_url):
        if json.loads(request_bytes(f"{origin}/_build.json")) != expected:
            raise ValueError("Published documentation does not match the requested commit")
    for route in ("/", "/changelog/"):
        gitlab_hash = hashlib.sha256(request_bytes(gitlab_url + route)).digest()
        github_hash = hashlib.sha256(request_bytes(github_url + route)).digest()
        if gitlab_hash != github_hash:
            raise ValueError("Published documentation differs between the two source builds")


def reconcile_once(sha: str, branch: str, gitlab_token: str, github_token: str) -> bool | None:
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or branch not in {"dev", "main"}:
        raise ValueError("Only a pinned dev/main commit can be reconciled")
    statuses = json.loads(
        request_bytes(
            f"{GITLAB_API}/repository/commits/{sha}/statuses?all=true&per_page=100",
            headers={"PRIVATE-TOKEN": gitlab_token},
        )
    )
    matching = [
        status
        for status in statuses
        if status.get("name") == STATUS_NAME
        and status.get("sha") == sha
        and status.get("ref") == branch
    ]
    if not matching:
        return None
    status = max(matching, key=lambda item: int(item["id"]))
    if status.get("status") == "success":
        return True
    if status.get("status") not in {"pending", "running"}:
        raise RuntimeError("Cloudflare reported a terminal error; refusing to replace its result")
    if status.get("sha") != sha or status.get("ref") != branch:
        raise ValueError("Cloudflare status belongs to a different commit or branch")
    gitlab_url = deployment_url(status.get("target_url") or "")
    github_url = github_deployment(sha, branch, github_token)
    if github_url is None:
        return False
    verify_publication(gitlab_url, github_url, sha, branch)
    pipeline_id = int(status["pipeline_id"])
    if pipeline_id <= 0 or not gitlab_token:
        raise RuntimeError("A pipeline and a project-scoped commit-status token are required")
    result = json.loads(
        request_bytes(
            f"{GITLAB_API}/statuses/{sha}",
            headers={"PRIVATE-TOKEN": gitlab_token},
            payload={
                "state": "success",
                "name": STATUS_NAME,
                "pipeline_id": pipeline_id,
                "ref": branch,
                "target_url": gitlab_url,
                "description": "Verified immutable deployment: pinned build identity, HTTP 200, "
                "and page SHA-256 match the successful Cloudflare GitHub build.",
            },
        )
    )
    if result.get("status") != "success" or result.get("pipeline_id") != pipeline_id:
        raise RuntimeError("GitLab did not confirm the deployment status update")
    print(f"Verified documentation for {sha}; reconciled pipeline {pipeline_id}")
    return True


def main() -> None:
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise SystemExit("This integration belongs to the 3252a8 Core repository")
    sha = os.environ.get("GITHUB_SHA", "")
    branch = os.environ.get("GITHUB_REF_NAME", "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or branch not in {"dev", "main"}:
        raise SystemExit("Only a pinned dev/main commit can be reconciled")
    token = os.environ.get("GITLAB_DOCS_STATUS_TOKEN", "")
    if not token:
        raise SystemExit("GITLAB_DOCS_STATUS_TOKEN is required")
    started = time.monotonic()
    while time.monotonic() - started < 20 * 60:
        try:
            done = reconcile_once(
                sha,
                branch,
                token,
                os.environ.get("GITHUB_TOKEN", ""),
            )
            if done is True:
                return
            if done is None and time.monotonic() - started >= 180:
                print("Cloudflare registered no external status; no reconciliation is required")
                return
        except urllib.error.HTTPError as error:
            if error.code in {401, 403}:
                raise SystemExit("Deployment API authorization failed") from None
            print(f"Deployment is not ready: HTTP {error.code}")
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            print(f"Deployment is not ready: {error}")
        time.sleep(30)
    raise SystemExit("Documentation publication could not be verified within 20 minutes")


if __name__ == "__main__":
    main()
