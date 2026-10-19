import importlib.util
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

_spec = importlib.util.spec_from_file_location(
    "publish_docs_under_test", Path(__file__).resolve().parents[2] / "scripts" / "publish_docs.py"
)
assert _spec is not None
assert _spec.loader is not None
docs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(docs)

SHA = "a" * 40
IDENTIFIER = "12345678-1234-1234-1234-123456789abc"


def build(directory, branch="dev"):
    (directory / "changelog").mkdir(parents=True)
    (directory / "index.html").write_bytes(b"home")
    (directory / "changelog/index.html").write_bytes(b"history")
    (directory / "_build.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "repository": docs.REPOSITORY,
                "commit": SHA,
                "branch": branch,
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    "field,value",
    [("commit", "b" * 40), ("branch", "main"), ("repository", "other/project"), ("schema", 2)],
)
def test_wrong_build_identity_cannot_be_published(tmp_path, field, value):
    build(tmp_path)
    metadata = json.loads((tmp_path / "_build.json").read_bytes())
    (tmp_path / "_build.json").write_text(json.dumps({**metadata, field: value}), encoding="utf-8")
    with pytest.raises(ValueError, match="identity differs"):
        docs.file_hashes(tmp_path, SHA, "dev")


@pytest.mark.parametrize("branch", ["dev", "main"])
def test_only_gitlab_dev_and_main_can_publish(monkeypatch, branch):
    monkeypatch.setenv("CI_PROJECT_PATH", docs.REPOSITORY)
    monkeypatch.setenv("CI_SERVER_URL", "https://gitlab.com")
    monkeypatch.setenv("CI_COMMIT_SHA", SHA)
    monkeypatch.setenv("CI_COMMIT_BRANCH", branch)
    assert docs.inputs() == (SHA, branch)
    monkeypatch.setenv("CI_SERVER_URL", "https://github.com")
    with pytest.raises(ValueError, match="Only a pinned GitLab"):
        docs.inputs()


def project_record(branch="dev"):
    return {
        "production_branch": branch,
        "source": {
            "type": "gitlab",
            "config": {
                "owner": "3252a8",
                "repo_name": "remnawave-minishop",
                "production_deployments_enabled": True,
                "preview_deployment_setting": "all",
                "path_includes": ["*"],
            },
        },
    }


def test_native_scheduler_is_disabled_idempotently_without_changing_source_or_domains(monkeypatch):
    record = project_record()
    writes = []

    def pages(project, suffix="", *, payload=None):
        assert project == "minishop-docs"
        if payload is not None:
            writes.append(payload)
            record.update(payload)
        return record

    monkeypatch.setattr(docs, "pages", pages)
    docs.configure_project("minishop-docs", "dev")
    docs.configure_project("minishop-docs", "dev")
    assert len(writes) == 1
    assert set(writes[0]) == {"source"}
    assert record["production_branch"] == "dev"
    assert record["source"]["config"]["path_includes"] == ["*"]


@pytest.mark.parametrize("change", ["owner", "repo_name", "production_branch"])
def test_unexpected_pages_project_cannot_be_changed(monkeypatch, change):
    record = project_record()
    if change == "production_branch":
        record[change] = "main"
    else:
        record["source"]["config"][change] = "another"

    def pages(project, *, payload=None):
        assert payload is None
        return record

    monkeypatch.setattr(docs, "pages", pages)
    with pytest.raises(ValueError, match="Unexpected source"):
        docs.configure_project("minishop-docs", "dev")


@pytest.mark.parametrize("change", ["commit", "branch", "url", "stage"])
def test_published_deployment_requires_api_confirmation_of_exact_upload(change):
    record = {
        "id": IDENTIFIER,
        "url": "https://12345678.minishop-docs.pages.dev",
        "deployment_trigger": {"metadata": {"commit_hash": SHA, "branch": "dev"}},
        "latest_stage": {"name": "deploy", "status": "success"},
    }
    assert docs.deployment_origin(record, "minishop-docs", SHA, "dev") == record["url"]
    if change in {"commit", "branch"}:
        field = "commit_hash" if change == "commit" else "branch"
        record["deployment_trigger"]["metadata"][field] = "another"
    elif change == "url":
        record["url"] = "https://evil.example/"
    else:
        record["latest_stage"]["status"] = "failure"
    with pytest.raises(ValueError, match="pinned deployment"):
        docs.deployment_origin(record, "minishop-docs", SHA, "dev")


@pytest.mark.parametrize("branch", ["dev", "main"])
@pytest.mark.parametrize("bad_alias", [False, True])
def test_success_requires_uploaded_build_and_current_production_alias(
    monkeypatch, tmp_path, branch, bad_alias
):
    dist = tmp_path / "dist"
    build(dist, branch)
    project = docs.PROJECTS[branch]
    verified, now, configured = [], [0], []
    monkeypatch.setattr(docs, "assert_source_head", lambda *args: None)
    monkeypatch.setattr(docs.shutil, "which", lambda name: "/tools/wrangler")
    monkeypatch.setattr(docs, "configure_project", lambda *args: configured.append(args))

    def command(args, *, cwd, env, check):
        assert args[3] == str(dist.resolve())
        assert args[args.index("--project-name") + 1] == project
        assert args[args.index("--commit-hash") + 1] == SHA
        Path(env["WRANGLER_OUTPUT_FILE_PATH"]).write_text(
            json.dumps(
                {
                    "type": "pages-deploy",
                    "pages_project": project,
                    "deployment_id": IDENTIFIER,
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def pages(selected, suffix):
        assert selected == project and suffix == f"/deployments/{IDENTIFIER}"
        return {
            "id": IDENTIFIER,
            "url": f"https://12345678.{project}.pages.dev",
            "deployment_trigger": {"metadata": {"commit_hash": SHA, "branch": branch}},
            "latest_stage": {"name": "deploy", "status": "success"},
        }

    def request(url, *, headers=None, payload=None):
        assert headers is None and payload is None
        verified.append(url)
        if bad_alias and url == f"https://{project}.pages.dev/":
            now[0] = 301
            return b"old deployment"
        return (dist / docs.PROOF_ROUTES[urlsplit(url).path]).read_bytes()

    monkeypatch.setattr(docs.subprocess, "run", command)
    monkeypatch.setattr(docs, "pages", pages)
    monkeypatch.setattr(docs, "request_bytes", request)
    monkeypatch.setattr(docs.time, "monotonic", lambda: now[0])
    if bad_alias:
        with pytest.raises(RuntimeError, match="could not be verified"):
            docs.publish(dist, SHA, branch, tmp_path / "deployment.ndjson")
    else:
        assert (
            docs.publish(dist, SHA, branch, tmp_path / "deployment.ndjson")
            == f"https://12345678.{project}.pages.dev"
        )
        assert len(verified) == 6
        assert configured == [(project, branch)]


def test_stale_pipeline_cannot_upload_or_reconfigure_pages(monkeypatch, tmp_path):
    build(tmp_path)

    def moved(*args):
        raise ValueError("branch moved")

    monkeypatch.setattr(docs, "assert_source_head", moved)
    monkeypatch.setattr(
        docs, "configure_project", lambda *args: pytest.fail("must not mutate Pages")
    )
    with pytest.raises(ValueError, match="branch moved"):
        docs.publish(tmp_path, SHA, "dev", tmp_path / "deployment.ndjson")
