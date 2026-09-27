from pathlib import Path

from bot.services import legal_document_links
from config.settings import Settings


def _settings(**overrides: str | None) -> Settings:
    values: dict[str, str | None] = {
        "BOT_TOKEN": "123456:token",
        "POSTGRES_USER": "app_user",
        "POSTGRES_PASSWORD": "app_password",
        "SUBSCRIPTION_MINI_APP_URL": "https://app.example.com/webapp?lang=ru",
        "PRIVACY_POLICY_URL": "https://legacy.example/privacy",
        "USER_AGREEMENT_URL": "https://legacy.example/terms",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_legal_documents_prefer_existing_native_pages(tmp_path: Path, monkeypatch) -> None:
    legal_dir = tmp_path / "data" / "legal"
    legal_dir.mkdir(parents=True)
    (legal_dir / "policy.md").write_text("# Policy", encoding="utf-8")
    (legal_dir / "terms.md").write_text("# Terms", encoding="utf-8")
    monkeypatch.setattr(legal_document_links, "APP_ROOT", tmp_path)

    assert legal_document_links.legal_document_links(_settings()) == (
        "https://app.example.com/webapp/privacy-policy?lang=ru",
        "https://app.example.com/webapp/user-agreement?lang=ru",
    )


def test_legal_documents_fall_back_to_configured_urls_when_files_are_missing(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(legal_document_links, "APP_ROOT", tmp_path)

    assert legal_document_links.legal_document_links(_settings()) == (
        "https://legacy.example/privacy",
        "https://legacy.example/terms",
    )
    assert legal_document_links.legal_document_links(
        _settings(PRIVACY_POLICY_URL="", USER_AGREEMENT_URL="")
    ) == ("", "")


def test_legal_documents_keep_reserved_root_documents_reachable(
    tmp_path: Path, monkeypatch
) -> None:
    from config.documents import DocumentMetadata, create_document

    create_document(
        tmp_path,
        DocumentMetadata(title="Support", slug="support", role="privacy_policy"),
        "# Support",
    )
    monkeypatch.setattr(legal_document_links, "APP_ROOT", tmp_path)

    assert legal_document_links.legal_document_links(_settings())[0] == (
        "https://app.example.com/webapp/docs/support?lang=ru"
    )


def test_legal_documents_fall_back_to_configured_urls_when_native_pages_are_empty(
    tmp_path: Path, monkeypatch
) -> None:
    legal_dir = tmp_path / "data" / "legal"
    legal_dir.mkdir(parents=True)
    (legal_dir / "policy.md").write_text(" \n\t", encoding="utf-8")
    (legal_dir / "terms.md").write_text("", encoding="utf-8")
    monkeypatch.setattr(legal_document_links, "APP_ROOT", tmp_path)

    assert legal_document_links.legal_document_links(_settings()) == (
        "https://legacy.example/privacy",
        "https://legacy.example/terms",
    )


def test_deleted_import_does_not_restore_the_legacy_legal_link(tmp_path: Path, monkeypatch) -> None:
    from config.documents import delete_document, get_document_by_role

    legal_dir = tmp_path / "data" / "legal"
    legal_dir.mkdir(parents=True)
    (legal_dir / "policy.md").write_text("# Old policy", encoding="utf-8")
    imported = get_document_by_role(tmp_path, "privacy_policy")
    assert imported is not None
    delete_document(tmp_path, imported.slug)
    monkeypatch.setattr(legal_document_links, "APP_ROOT", tmp_path)

    assert (
        legal_document_links.legal_document_links(_settings())[0]
        == "https://legacy.example/privacy"
    )
