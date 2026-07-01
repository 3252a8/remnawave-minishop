import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install.sh"


def test_shell_installer_help_does_not_require_python():
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    result = subprocess.run(
        ["sh", str(INSTALL_SCRIPT), "--help"],
        check=True,
        text=True,
        encoding="utf-8",
        capture_output=True,
    )

    assert "MINISHOP_INSTALL_REPO" in result.stdout
    assert "dry-run" in result.stdout
    assert "REMNASHOP_SOURCE_SCHEMA" in result.stdout
    assert "LEGACY_TGSHOP_SOURCE_DSN" in result.stdout


def test_shell_installer_exits_on_stdin_eof():
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    result = subprocess.run(
        ["sh", str(INSTALL_SCRIPT)],
        input="",
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=5,
    )

    assert result.returncode != 0
    assert "Ввод завершился во время выбора пункта" in result.stderr


def test_shell_installer_is_the_only_install_entrypoint():
    assert INSTALL_SCRIPT.exists()
    assert not (REPO_ROOT / "scripts" / "install.py").exists()


def test_shell_installer_downloads_raw_files_and_runs_import_in_container():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert script.startswith("#!/bin/sh")
    raw_github_template = (
        'printf \'https://raw.githubusercontent.com/%s/%s/%s\' "$repo" "$ref" "$path"'
    )
    assert raw_github_template in script
    assert "git clone" not in script
    assert "backend python backend/scripts/import_legacy.py" in script
    assert "run --rm -T" in script
    assert "--user 0:0" in script
    assert "mask_compose_log_args" in script
    assert "postgresql)://[^:/[:space:]@]+:" in script
    assert "Путь к .env Remnashop для переноса настроек" in script
    assert "--source-env-file /tmp/remnashop.env" in script
    assert "--dry-run" in script
    assert "Установить новый remnawave-minishop и мигрировать данные из другого бота" in script
    assert "Мигрировать данные в уже установленный remnawave-minishop" in script


def test_shell_installer_installs_compose_and_explains_bind_errors():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "install_docker_compose" in script
    assert "Попробовать установить Docker Compose автоматически" in script
    assert "docker-compose-plugin" in script
    assert "install_compose_binary_plugin" in script
    assert "validate_bind_settings" in script
    assert (
        'prompt_value "Адрес привязки HTTP" "$(env_get HTTP_BIND \'0.0.0.0:80\')" 0 0 "bind"'
    ) in script
    assert "invalid hostPort" in script
    assert "IP без порта" in script
    assert "<IP_СЕРВЕРА>:80" in script
    assert "compose-last-error.log" in script


def test_deployment_docs_explain_install_wizard_prompts():
    docs = (REPO_ROOT / "docs" / "getting-started" / "deployment.md").read_text(encoding="utf-8")

    assert "### Что спрашивает install wizard" in docs
    assert "`HTTP_BIND` / `HTTPS_BIND`" in docs
    assert "с одним IP без порта некорректно" in docs
    assert "Docker Compose не найден" in docs
    assert ".installer/compose-last-error.log" in docs


def test_shell_installer_download_helper_does_not_clobber_target_name():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")
    helper = script.split("download_to() {", 1)[1].split("\n}", 1)[0]

    assert 'download_target="$2"' in helper
    assert not re.search(r'^\s*target="\$2"', helper, flags=re.MULTILINE)


def test_shell_installer_supports_egames_reverse_proxy_profile():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "Уже установленная Remnawave через eGames" in script
    assert 'PROFILE_KEY="egames"' in script
    assert "DEPLOYMENT_PROFILE" in script
    assert "detect_egames_nginx_conf" in script
    assert "detect_egames_nginx_container" in script
    assert "configure_egames_reverse_proxy" in script
    assert "configure_egames_panel_webhook" in script
    assert "refresh_egames_nginx_after_migration" in script
    assert "PANEL_API_COOKIE" in script
    assert "TELEGRAM_OAUTH_CLIENT_SECRET" in script
    assert 'cat "$tmp" > "$nginx_conf"' in script
    assert 'mv "$tmp" "$nginx_conf"' not in script
    assert "egames_container_has_routes" in script
    assert 'docker restart "$nginx_container" >/dev/null' in script
    assert 'docker exec "$nginx_container" nginx -s reload' in script


def test_shell_installer_checks_dns_and_can_prepare_nginx_certificates():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "check_public_dns_records" in script
    assert "Проверить A-записи для WEBHOOK_HOST и MINIAPP_HOST сейчас?" in script
    assert "configure_nginx_certificates" in script
    assert "Настройка сертификатов Nginx" in script
    assert "Certbot Cloudflare DNS-01" in script
    assert "--dns-cloudflare" in script
    assert "python3-certbot-dns-cloudflare" in script
    assert "--preferred-challenges http" in script
    assert "remember_nginx_cert_mapping" in script
    assert "docker-compose exec -T nginx nginx -s reload" in script
    assert "configure_nginx_certificates || return 1" in script
    assert "check_public_dns_records || return 1" in script


def test_shell_installer_does_not_rename_bot_and_reports_migration_success():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "setMyName" not in script
    assert "setMyShortDescription" not in script
    assert "telegram_bot_profile_checklist" in script
    assert "notify_remnashop_migration_success" in script
    assert "remnashop_post_migration_next_steps" in script
    assert "remnashop-apply-summary.json" in script
    assert "remnashop-post-migration-message.txt" in script
    assert '("providers_mapped", "перенесено")' in script
    assert "for warning in warnings:" in script
    assert "warnings[:5]" not in script
    assert "Сообщение обрезано" not in script
    assert "split_telegram_messages" in script
    assert "Новые URL webhook:" in script
    assert "for action in payment_actions:" in script
    assert "payment_actions[:8]" not in script
    assert "run_compose restart backend worker frontend" in script
    assert (
        "refresh_egames_nginx_after_migration\n"
        '    notify_remnashop_migration_success "$APPLY_SUMMARY_PATH"\n'
        '    ok "Миграция завершена."\n'
        "    remnashop_post_migration_next_steps"
    ) in script


def test_shell_installer_can_reset_target_database_before_remnashop_import():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "reset_target_compose_database" in script
    assert "Сбросить целевую базу Minishop перед импортом" in script
    assert "create_pre_migration_backup" in script
    assert "backups/pre-${label}-migration" in script
    assert "restore.sh" in script
    assert "run_compose stop backend worker migrate" in script
    assert 'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"' in script


def test_deployment_examples_scope_named_volumes_to_compose_project():
    for profile in ("caddy", "nginx", "newt", "no-proxy"):
        compose = (REPO_ROOT / "deploy" / "examples" / profile / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
        assert "name: ${COMPOSE_PROJECT_NAME:-remnawave-minishop}-db-data" in compose
        assert "name: ${COMPOSE_PROJECT_NAME:-remnawave-minishop}-redis-data" in compose
        assert "name: remnawave-minishop-db-data" not in compose
        assert "name: remnawave-minishop-redis-data" not in compose


def test_shell_installer_refreshes_importer_without_prompting_inside_command_substitution():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "Use cached importer" not in script
    assert 'download_to "$url" "$tmp"' in script
    assert "Бэкап скрипта импорта сохранен" in script


def test_shell_installer_connects_local_remnashop_db_container_for_import():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "connect_local_source_db_to_target_network" in script
    assert "dsn_hostname" in script
    assert "docker network connect" in script
    assert "_remnawave-shop" in script


def test_shell_installer_supports_legacy_tgshop_volume_and_dsn_paths():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "Старый remnawave-tg-shop" in script or "старого remnawave-tg-shop" in script
    assert "remnawave-tg-shop-db-data" in script
    assert "remnawave-minishop-db-data" in script
    assert "pg_dump --clean --if-exists" in script
    assert "run_compose_checked run --rm migrate" in script


def test_shell_installer_only_prepares_data_mount_not_runtime_content():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "Подготовка каталога data" in script
    assert 'data_dir="$TARGET_DIR/data"' in script
    assert 'mkdir -p "$data_dir"' in script
    assert 'chown -R "$APP_UID:$APP_GID" "$data_dir"' in script
    assert "Контейнеры Minishop пишут runtime-файлы" in script
    assert "Обновить владельца $data_dir на $APP_UID:$APP_GID" in script
    assert (
        'confirm "Обновить владельца $data_dir на $APP_UID:$APP_GID для записи из контейнеров?" 1'
    ) in script
    assert "Adjust $data_dir owner" not in script
    assert "already exists" not in script
    assert "data_dir/themes" not in script
    assert "webapp-logo" not in script
    assert "webapp-emoji" not in script
    assert "locales-overrides.json" not in script


def test_shell_installer_prints_remnashop_webhook_checklist():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "remnashop_webhook_checklist" in script
    assert "Обновление внешних webhook" in script
    assert "Remnawave Panel -> WEBHOOK_URL" in script
    assert "PANEL_WEBHOOK_SECRET" in script
    assert "/webhook/panel" in script
    assert "/webhook/yookassa" in script
    assert "/webhook/wata" in script
    assert "/webhook/cryptopay" in script
    assert "/webhook/heleket" in script
    assert "/webhook/paykilla" in script
    assert "/webhook/freekassa" in script
    assert "/webhook/platega" in script
    assert "/tg/webhook" in script


def test_shell_installer_uses_russian_defaults_and_autodetects_sources():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert 'DEFAULT_INSTALL_DIR="${MINISHOP_INSTALL_DIR:-/opt/remnawave-minishop}"' in script
    assert "Мастер установки remnawave-minishop" in script
    assert "https://minishop.minidoc.cc/getting-started/setup/" in script
    assert "https://minishop.minidoc.cc/migrations/remnashop/" in script
    assert "detect_remnashop_source_dsn" in script
    assert "detect_remnashop_env_file" in script
    assert "Нашел Remnashop PostgreSQL" in script
    assert "Найден Remnashop" in script


def test_shell_installer_autodetects_egames_panel_credentials():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "detect_panel_api_url" in script
    assert "detect_panel_api_key" in script
    assert "detect_panel_api_cookie" in script
    assert "detect_panel_webhook_secret" in script
    assert "REMNAWAVE_HOST" in script
    assert "REMNAWAVE_TOKEN" in script
    assert "REMNAWAVE_COOKIE" in script
    assert "REMNAWAVE_WEBHOOK_SECRET" in script
    assert "FRONT_END_DOMAIN" in script
    assert "WEBHOOK_SECRET_HEADER" in script
    assert "select token from api_tokens" in script
    assert "select uuid::text from api_tokens" in script
    assert "JWT_API_TOKENS_SECRET" in script
    assert "make_panel_api_jwt" in script
    assert "Нашел API-ключ Remnawave Panel" in script
    assert "Нашел заголовок Cookie обратного прокси eGames" in script


def test_shell_installer_prefills_remnashop_telegram_settings():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "detect_bot_token" in script
    assert "detect_admin_ids" in script
    assert "detect_webhook_secret_token" in script
    assert "BOT_TOKEN" in script
    assert "BOT_OWNER_ID" in script
    assert "BOT_SECRET_TOKEN" in script
    assert "Нашел BOT_TOKEN в .env Remnashop" in script
    assert "Нашел BOT_OWNER_ID/ADMIN_IDS в .env Remnashop" in script
    assert "Нашел BOT_SECRET_TOKEN в .env Remnashop" in script
    assert "Новое значение (Enter = оставить)" in script


def test_shell_installer_uses_default_source_without_prompting_for_repo_ref():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert 'SOURCE_REPO="$DEFAULT_REPO"' in script
    assert 'SOURCE_REF="$DEFAULT_REF"' in script
    assert "install_source" in script
    assert "MINISHOP_INSTALL_REPO и MINISHOP_INSTALL_REF" in script
    assert 'GitHub репозиторий"' not in script
    assert "Git ref/ветка/тег для raw-файлов" not in script


def test_shell_installer_hides_low_level_oauth_and_required_stack_prompts():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert (
        'TELEGRAM_OAUTH_REQUEST_ACCESS_VALUE="$(env_get TELEGRAM_OAUTH_REQUEST_ACCESS write)"'
    ) in script
    assert "Telegram OAuth request access (пусто/write/phone)" not in script
    assert "Запустить Docker Compose stack перед импортом из Remnashop?" not in script
    assert "Импорту из Remnashop нужна целевая база stack. Импорт пропущен." not in script
    assert "Запускаю Docker Compose стек перед импортом из Remnashop" in script


def test_shell_installer_summarizes_remnashop_dry_run_and_hides_source_schema_prompt():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert 'suffix="Y/n"' in script
    assert 'suffix="y/N"' in script
    assert "Да/нет" not in script
    assert "да/Нет" not in script
    assert "Ответьте y или n." in script
    assert 'SOURCE_SCHEMA="${REMNASHOP_SOURCE_SCHEMA:-public}"' in script
    assert 'prompt_value "Schema источника"' not in script
    assert "remnashop-dry-run-summary.json" in script
    assert 'run_import_command 1 "$DRY_RUN_SUMMARY_PATH" 0' in script
    assert "summary_extracted=1" in script
    assert 'confirm "Применить эту миграцию по-настоящему?" 1' in script
    assert "print_remnashop_import_summary" in script
    assert "Проверка без записи прошла успешно" in script
    assert "Полный сырой вывод скрипта импорта сохранен" in script
