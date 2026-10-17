import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

_spec = importlib.util.spec_from_file_location(
    "reconcile_docs_status_under_test",
    Path(__file__).resolve().parents[2] / "scripts" / "reconcile_docs_status.py",
)
assert _spec is not None
assert _spec.loader is not None
docs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(docs)

SHA = "a" * 40
GL_URL = "https://12345678.minishop-docs.pages.dev"
GH_URL = "https://87654321.minishop-docs-github.pages.dev"
OTHER_BRANCH_URL = "https://99999999.minishop-docs-github.pages.dev"


class DeploymentApi:
    def __init__(self) -> None:
        self.statuses = [
            {
                "id": 100,
                "name": docs.STATUS_NAME,
                "sha": SHA,
                "ref": "dev",
                "status": "running",
                "pipeline_id": 123,
                "target_url": "https://dash.cloudflare.com/?to=/:account/pages/view/"
                "minishop-docs/12345678-1234-1234-1234-123456789abc",
            }
        ]
        self.check = {
            "head_sha": SHA,
            "app": {"id": docs.CLOUDFLARE_APP_ID},
            "conclusion": "success",
            "output": {"summary": f"<a href='{GH_URL}'>{GH_URL}</a>"},
        }
        self.checks = [self.check]
        self.metadata = {
            "schema": 1,
            "repository": docs.REPOSITORY,
            "commit": SHA,
            "branch": "dev",
        }
        self.mismatched_html = False
        self.writes: list[dict[str, Any]] = []

    def request(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> bytes:
        if payload is not None:
            assert url == f"{docs.GITLAB_API}/statuses/{SHA}"
            assert headers == {"PRIVATE-TOKEN": "project-status-token"}
            self.writes.append(payload)
            return json.dumps({"status": "success", "pipeline_id": 123}).encode()
        # Credentials must never reach either public deployment.
        if url.startswith((GL_URL, GH_URL, OTHER_BRANCH_URL)):
            assert not headers
            if url.endswith("/_build.json"):
                if url.startswith(OTHER_BRANCH_URL):
                    return json.dumps({**self.metadata, "branch": "main"}).encode()
                return json.dumps(self.metadata).encode()
            return b"different" if self.mismatched_html and url.startswith(GH_URL) else b"page"
        if url.startswith(docs.GITLAB_API):
            assert headers == {"PRIVATE-TOKEN": "project-status-token"}
            return json.dumps(self.statuses).encode()
        assert url.startswith(docs.GITHUB_API)
        assert headers == {"Authorization": "Bearer github-checks-token"}
        return json.dumps({"check_runs": self.checks}).encode()


@pytest.mark.parametrize("other_branch_status", [False, True])
def test_pending_callback_requires_matching_immutable_publication(monkeypatch, other_branch_status):
    api = DeploymentApi()
    if other_branch_status:
        api.statuses.append({**api.statuses[0], "id": 101, "ref": "main", "status": "success"})
    monkeypatch.setattr(docs, "request_bytes", api.request)
    assert docs.reconcile_once(SHA, "dev", "project-status-token", "github-checks-token") is True
    assert len(api.writes) == 1
    assert api.writes[0]["pipeline_id"] == 123
    assert api.writes[0]["name"] == docs.STATUS_NAME
    assert api.writes[0]["target_url"] == GL_URL


@pytest.mark.parametrize(
    "field,value",
    [("commit", "b" * 40), ("branch", "main"), ("repository", "another/repository"), ("schema", 2)],
)
def test_wrong_build_identity_never_updates_status(monkeypatch, field, value):
    api = DeploymentApi()
    api.metadata[field] = value
    monkeypatch.setattr(docs, "request_bytes", api.request)
    assert docs.reconcile_once(SHA, "dev", "project-status-token", "github-checks-token") is False
    assert not api.writes


def test_same_commit_on_two_branches_selects_the_matching_immutable_build(monkeypatch):
    api = DeploymentApi()
    api.checks.insert(
        0, {**api.check, "output": {"summary": f"<a href='{OTHER_BRANCH_URL}'>main</a>"}}
    )
    monkeypatch.setattr(docs, "request_bytes", api.request)
    assert docs.reconcile_once(SHA, "dev", "project-status-token", "github-checks-token") is True
    assert len(api.writes) == 1


@pytest.mark.parametrize("state", ["failed", "canceled", "skipped"])
def test_terminal_cloudflare_failure_is_preserved(monkeypatch, state):
    api = DeploymentApi()
    api.statuses[0]["status"] = state
    monkeypatch.setattr(docs, "request_bytes", api.request)
    with pytest.raises(RuntimeError, match="refusing to replace"):
        docs.reconcile_once(SHA, "dev", "project-status-token", "github-checks-token")
    assert not api.writes


@pytest.mark.parametrize("change", ["app", "head_sha", "conclusion"])
def test_untrusted_or_incomplete_github_check_cannot_authorize_repair(monkeypatch, change):
    api = DeploymentApi()
    api.check[change] = {"id": 1} if change == "app" else "untrusted"
    monkeypatch.setattr(docs, "request_bytes", api.request)
    assert docs.reconcile_once(SHA, "dev", "project-status-token", "github-checks-token") is False
    assert not api.writes


def test_different_published_pages_never_update_status(monkeypatch):
    api = DeploymentApi()
    api.mismatched_html = True
    monkeypatch.setattr(docs, "request_bytes", api.request)
    with pytest.raises(ValueError, match="differs"):
        docs.reconcile_once(SHA, "dev", "project-status-token", "github-checks-token")
    assert not api.writes


@pytest.mark.parametrize(
    "url",
    [
        "http://12345678.minishop-docs.pages.dev",
        "https://evil.example/minishop-docs/12345678-1234-1234-1234-123456789abc",
        "https://user:password@12345678.minishop-docs.pages.dev",
        "https://12345678.minishop-docs.pages.dev:8443",
    ],
)
def test_deployment_urls_cannot_redirect_proof_or_credentials_elsewhere(url):
    with pytest.raises(ValueError, match="Unexpected"):
        docs.deployment_url(url)
