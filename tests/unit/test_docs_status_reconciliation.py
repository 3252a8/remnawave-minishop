import copy
import importlib.util
import json
from datetime import UTC, datetime, timedelta
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


@pytest.mark.parametrize("queued_minutes", [21, 91])
def test_publication_wait_includes_queue_time_and_remains_bounded(
    monkeypatch, capsys, queued_minutes
):
    monkeypatch.setenv("GITHUB_REPOSITORY", docs.REPOSITORY)
    monkeypatch.setenv("GITHUB_SHA", SHA)
    monkeypatch.setenv("GITHUB_REF_NAME", "dev")
    monkeypatch.setenv("GITLAB_DOCS_STATUS_TOKEN", "project-status-token")
    monkeypatch.delenv("CLOUDFLARE_PAGES_TOKEN", raising=False)
    now = [0.0]
    calls = []

    def reconcile(*args):
        calls.append(args)
        return len(calls) > 1

    def sleep(seconds):
        assert seconds == 30
        now[0] += queued_minutes * 60

    monkeypatch.setattr(docs, "reconcile_once", reconcile)
    monkeypatch.setattr(docs.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(docs.time, "sleep", sleep)
    if queued_minutes == 21:
        docs.main()
        assert len(calls) == 2
    else:
        with pytest.raises(SystemExit, match="could not be verified within 90 minutes"):
            docs.main()
        assert len(calls) == 1
    assert "Waiting for immutable Cloudflare documentation builds" in capsys.readouterr().out


def test_recovery_api_outage_does_not_block_independent_publication_proof(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", docs.REPOSITORY)
    monkeypatch.setenv("GITHUB_SHA", SHA)
    monkeypatch.setenv("GITHUB_REF_NAME", "dev")
    monkeypatch.setenv("GITLAB_DOCS_STATUS_TOKEN", "project-status-token")
    monkeypatch.setenv("CLOUDFLARE_PAGES_TOKEN", "pages-token")
    calls = []

    def unavailable(**kwargs):
        calls.append(kwargs["sha"])
        raise TimeoutError("Pages API unavailable")

    monkeypatch.setattr(docs, "retry_stalled_deployments", unavailable)
    monkeypatch.setattr(docs, "reconcile_once", lambda *args: True)
    docs.main()
    assert calls == [SHA]


ACCOUNT = "b" * 32
NOW = datetime(2026, 10, 18, 20, 0, tzinfo=UTC)
IDENTIFIER = "12345678-1234-1234-1234-123456789abc"


class PagesApi:
    def __init__(self):
        self.record = {
            "id": IDENTIFIER,
            "created_on": (NOW - timedelta(minutes=11)).isoformat(),
            "deployment_trigger": {"metadata": {"commit_hash": SHA, "branch": "dev"}},
            "latest_stage": {"name": "queued", "status": "active"},
            "stages": [
                {"name": "queued", "status": "active"},
                {"name": "initialize", "status": "idle"},
            ],
        }
        self.records = [self.record]
        self.writes = []
        self.reads = []
        self.timeout = False
        self.log_lines = ["Failed: unable to submit build job"]

    def request(self, url, *, headers=None, payload=None):
        assert headers == {"Authorization": "Bearer pages-token"}
        assert url.startswith(f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/pages/")
        if payload is None:
            self.reads.append(url)
            result = (
                {"data": [{"line": line} for line in self.log_lines]}
                if url.endswith("/history/logs")
                else self.records
                if "/minishop-docs/" in url
                else []
            )
        else:
            assert payload == {}
            assert url.endswith(f"/{IDENTIFIER}/retry")
            self.writes.append(url)
            if self.timeout:
                raise TimeoutError("uncertain response")
            result = self.record
        return json.dumps({"success": True, "result": result}).encode()

    def recover(self, state=None, branch="dev"):
        return docs.retry_stalled_deployments(
            account=ACCOUNT,
            token="pages-token",
            sha=SHA,
            branch=branch,
            request=self.request,
            state=state or docs.RecoveryState(),
            now=NOW,
        )


def test_only_stalled_queue_is_retried_once_per_deployment():
    api = PagesApi()
    state = docs.RecoveryState()
    assert api.recover(state) is True
    assert api.recover(state) is False
    assert len(api.writes) == 1
    assert state.counts == {"minishop-docs": 1}
    assert not any("minishop-docs-main" in url for url in api.reads)


@pytest.mark.parametrize(
    "field,value",
    [
        ("created_on", (NOW - timedelta(minutes=9)).isoformat()),
        ("skip_reason", "ignored_build_step"),
        ("latest_stage", {"name": "build", "status": "active"}),
        ("latest_stage", {"name": "queued", "status": "failure"}),
        ("latest_stage", {"name": "queued", "status": "canceled"}),
        ("latest_stage", {"name": "queued", "status": "success"}),
        ("stages", [{"name": "initialize", "status": "active"}]),
        ("stages", [{"name": "build", "status": "failure"}]),
        ("stages", None),
        ("deployment_trigger", {"metadata": {"commit_hash": "c" * 40, "branch": "dev"}}),
        ("deployment_trigger", {"metadata": {"commit_hash": SHA, "branch": "main"}}),
    ],
)
def test_started_terminal_skipped_young_and_other_commit_builds_are_preserved(field, value):
    api = PagesApi()
    api.record[field] = value
    assert api.recover() is False
    assert not api.writes


def test_newest_deployment_supersedes_older_stalled_record():
    api = PagesApi()
    newer = copy.deepcopy(api.record)
    newer["created_on"] = NOW.isoformat()
    newer["latest_stage"] = {"name": "deploy", "status": "success"}
    api.records.append(newer)
    assert api.recover() is False
    assert not api.writes


def test_retry_budget_stops_new_queued_records_too():
    api = PagesApi()
    state = docs.RecoveryState(counts={"minishop-docs": 2})
    assert api.recover(state) is False
    assert not api.writes


def test_uncertain_post_response_cannot_duplicate_retry():
    api = PagesApi()
    api.timeout = True
    state = docs.RecoveryState()
    with pytest.raises(TimeoutError):
        api.recover(state)
    assert api.recover(state) is False
    assert len(api.writes) == 1
    assert state.counts == {"minishop-docs": 1}


def test_main_branch_also_checks_production_docs_project():
    api = PagesApi()
    assert api.recover(branch="main") is False
    assert any("minishop-docs-main" in url for url in api.reads)


@pytest.mark.parametrize(
    "lines,expected",
    [
        (["Failed: unable to submit build job"], True),
        (["Failed: build command exited with code 1"], False),
        (["Cloning repository...", "Failed: unable to submit build job"], False),
        ([], False),
    ],
)
def test_only_proven_cloudflare_scheduler_failure_can_retry_initialization(lines, expected):
    api = PagesApi()
    api.record["latest_stage"] = {"name": "initialize", "status": "failure"}
    api.record["created_on"] = NOW.isoformat()
    api.log_lines = lines
    assert api.recover() is expected
    assert len(api.writes) == int(expected)
