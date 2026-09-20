import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from bot.services.compose_data_mounts import (
    APP_DATA_SERVICES,
    app_data_mounts_are_aligned,
    compose_app_data_mounts,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install.sh"


def _run_installer_function(tmp_path: Path, shell_body: str) -> subprocess.CompletedProcess[str]:
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")
    library, marker, _ = script.rpartition('\ncase "${1:-}" in\n')
    assert marker, "installer CLI entrypoint marker is missing"
    test_script = tmp_path / "installer-function-test.sh"
    test_script.write_text(f"{library}\n{shell_body}\n", encoding="utf-8")
    return subprocess.run(
        ["sh", str(test_script)],
        text=True,
        encoding="utf-8",
        capture_output=True,
    )


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


@pytest.mark.parametrize(
    ("choice", "expected_provider"),
    [("1", "github"), ("2", "gitlab")],
)
def test_shell_installer_selects_source_provider(
    tmp_path: Path,
    choice: str,
    expected_provider: str,
) -> None:
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    result = _run_installer_function(
        tmp_path,
        f"""
choose() {{ CHOICE_VALUE={choice}; }}
choose_source_provider || exit 20
[ "$SOURCE_PROVIDER" = {expected_provider} ] || exit 21
""",
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("provider", "expected_url"),
    [
        (
            "github",
            "https://raw.githubusercontent.com/owner/repo/dev/deploy/example.yml",
        ),
        (
            "gitlab",
            "https://gitlab.com/owner/repo/-/raw/dev/deploy/example.yml",
        ),
    ],
)
def test_shell_installer_builds_provider_raw_url(
    tmp_path: Path,
    provider: str,
    expected_url: str,
) -> None:
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    result = _run_installer_function(
        tmp_path,
        f"""
SOURCE_PROVIDER={shlex.quote(provider)}
[ "$(raw_url owner/repo dev deploy/example.yml)" = {shlex.quote(expected_url)} ] || exit 20
""",
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_shell_installer_validates_telegram_socks5_proxy_urls(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    shell_body = r"""
for value in \
    'socks5://proxy.example.com:1080' \
    'socks5://192.0.2.10:1080' \
    'socks5://[2001:db8::10]:1080' \
    'socks5://user%40example:p%3A%2F%23@proxy.example.com:1080'
do
    is_valid_socks5_url "$value" || exit 20
done
for value in \
    'http://proxy.example.com:1080' \
    'socks5h://proxy.example.com:1080' \
    'SOCKS5://proxy.example.com:1080' \
    'socks5://proxy.example.com' \
    'socks5://proxy.example.com:0' \
    'socks5://proxy.example.com:65536' \
    'socks5://user@proxy.example.com:1080' \
    'socks5://user:@proxy.example.com:1080' \
    'socks5://user:raw/password@proxy.example.com:1080' \
    'socks5://proxy.example.com:1080/path' \
    'socks5://proxy.example.com:1080?' \
    'socks5://proxy.example.com:1080#'
do
    if is_valid_socks5_url "$value"; then exit 21; fi
done
"""

    result = _run_installer_function(tmp_path, shell_body)

    assert result.returncode == 0, result.stderr


def test_shell_installer_masks_telegram_proxy_summary(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    proxy_url = "socks5://proxy-user:proxy-password@proxy.example.com:1080"
    result = _run_installer_function(
        tmp_path,
        f"show_env_value TELEGRAM_BOT_PROXY_URL '{proxy_url}'",
    )

    assert result.returncode == 0, result.stderr
    assert "TELEGRAM_BOT_PROXY_URL=" in result.stdout
    assert proxy_url not in result.stdout
    assert "proxy-password" not in result.stdout


def test_telegram_proxy_deploy_contract_is_backend_only():
    backend_env_examples = (
        REPO_ROOT / ".env.example",
        REPO_ROOT / "deploy" / "dev" / "remnawave-dev.env.example",
        REPO_ROOT / "deploy" / "examples" / "angie" / ".env.example",
        REPO_ROOT / "deploy" / "examples" / "caddy" / ".env.example",
        REPO_ROOT / "deploy" / "examples" / "nginx" / ".env.example",
        REPO_ROOT / "deploy" / "examples" / "newt" / ".env.example",
        REPO_ROOT / "deploy" / "examples" / "no-proxy" / ".env.example",
        REPO_ROOT / "deploy" / "examples" / "split-protected-upstream" / ".env.backend.example",
    )
    for env_path in backend_env_examples:
        env_example = env_path.read_text(encoding="utf-8")
        assert "TELEGRAM_BOT_PROXY_URL" in env_example, env_path
        assert "TELEGRAM_BOT_API_BASE_URL" in env_example, env_path
        assert "TELEGRAM_OAUTH_USE_BOT_PROXY=True" in env_example, env_path

    frontend_env = (
        REPO_ROOT / "deploy" / "examples" / "split-protected-upstream" / ".env.frontend.example"
    ).read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_PROXY_URL" not in frontend_env
    assert "TELEGRAM_BOT_API_BASE_URL" not in frontend_env
    assert "TELEGRAM_OAUTH_USE_BOT_PROXY" not in frontend_env

    split_compose = (
        REPO_ROOT
        / "deploy"
        / "examples"
        / "split-protected-upstream"
        / "backend.docker-compose.yml"
    ).read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_PROXY_URL: ${TELEGRAM_BOT_PROXY_URL:-}" in split_compose
    assert "TELEGRAM_BOT_API_BASE_URL: ${TELEGRAM_BOT_API_BASE_URL:-}" in split_compose
    assert "TELEGRAM_OAUTH_USE_BOT_PROXY: ${TELEGRAM_OAUTH_USE_BOT_PROXY:-True}" in split_compose


def test_shell_installer_manages_only_core_telegram_proxy_key():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "TELEGRAM_BOT_PROXY_URL_VALUE" in script
    assert 'env_get TELEGRAM_BOT_PROXY_URL ""' in script
    assert 'env_line TELEGRAM_BOT_PROXY_URL "$TELEGRAM_BOT_PROXY_URL_VALUE"' in script
    assert "TELEGRAM_OAUTH_USE_BOT_PROXY_VALUE" in script
    assert "env_get TELEGRAM_OAUTH_USE_BOT_PROXY True" in script
    assert 'env_line TELEGRAM_OAUTH_USE_BOT_PROXY "$TELEGRAM_OAUTH_USE_BOT_PROXY_VALUE"' in script
    assert "\nPROXY_URL_VALUE=" not in script


def test_shell_installer_is_the_only_install_entrypoint():
    assert INSTALL_SCRIPT.exists()
    assert not (REPO_ROOT / "scripts" / "install.py").exists()


@pytest.mark.parametrize("profile", ["angie", "caddy", "newt", "nginx", "no-proxy"])
def test_install_wizard_profiles_share_application_data_mount(profile: str):
    compose_path = REPO_ROOT / "deploy" / "examples" / profile / "docker-compose.yml"

    mounts = compose_app_data_mounts(compose_path.read_text(encoding="utf-8"))

    assert set(mounts) == set(APP_DATA_SERVICES)
    assert app_data_mounts_are_aligned(mounts)


def test_shell_installer_downloads_raw_files_and_runs_import_in_container():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert script.startswith("#!/bin/sh")
    assert 'DEFAULT_SOURCE="${MINISHOP_INSTALL_SOURCE:-gitlab}"' in script
    raw_github_template = (
        'printf \'https://raw.githubusercontent.com/%s/%s/%s\' "$repo" "$ref" "$path"'
    )
    assert raw_github_template in script
    raw_gitlab_template = 'printf \'https://gitlab.com/%s/-/raw/%s/%s\' "$repo" "$ref" "$path"'
    assert raw_gitlab_template in script
    assert "git clone" not in script
    assert "backend python backend/scripts/import_legacy.py" in script
    assert "run --rm -T" in script
    assert "--user 0:0" in script
    assert "restore_app_data_permissions" in script
    assert "chown -R $APP_UID:$APP_GID /app/data" in script
    assert "mask_compose_log_args" in script
    assert "postgresql)://[^:/[:space:]@]+:" in script
    assert "Путь к .env Remnashop для переноса настроек" in script
    assert "--source-env-file /tmp/remnashop.env" in script
    assert "--dry-run" in script
    assert "Установить новый remnawave-minishop и мигрировать данные из другого бота" in script
    assert "Мигрировать данные в уже установленный remnawave-minishop" in script


def test_shell_installer_installs_compose_and_explains_bind_errors():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "Установить или обновить Docker Engine и Docker Compose до latest stable" in script
    assert "docker-compose-plugin" in script
    assert "install_compose_binary_plugin" in script
    assert 'MIN_DOCKER_ENGINE_VERSION="25.0.0"' in script
    assert 'MIN_DOCKER_COMPOSE_VERSION="2.20.2"' in script
    assert "docker_runtime_preflight" in script
    assert "SHA-256 checksum Docker Compose" in script
    assert "config --quiet" in script
    assert "validate_bind_settings" in script
    assert (
        'prompt_value "Адрес привязки HTTP" "$(env_get HTTP_BIND \'0.0.0.0:80\')" 0 0 "bind"'
    ) in script
    assert "invalid hostPort" in script
    assert "IP без порта" in script
    assert "<IP_СЕРВЕРА>:80" in script
    assert "compose-last-error.log" in script

    install_flow = script.split("install_flow() {", 1)[1].split("\n}", 1)[0]
    assert install_flow.index("docker_runtime_preflight 1") < install_flow.index(
        "installation_directory"
    )


def test_shell_installer_compares_docker_versions_semantically(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    shell_body = r"""
version_at_least v2.20.2 2.20.2 || exit 10
version_at_least 2.20.10 2.20.2 || exit 11
version_at_least 25.0.0-ce 25.0.0 || exit 12
version_at_least 26 25.0.0 || exit 13
if version_at_least 2.19.9 2.20.2; then exit 14; fi
if version_at_least 24.0.9 25.0.0; then exit 15; fi
"""

    result = _run_installer_function(tmp_path, shell_body)

    assert result.returncode == 0, result.stderr


def test_shell_installer_preflight_updates_incompatible_runtime_after_consent(
    tmp_path: Path,
):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    shell_body = r"""
runtime_ready=0
docker_runtime_compatible() { [ "$runtime_ready" = "1" ]; }
print_docker_runtime_versions() { :; }
explain_docker_runtime_incompatibility() { :; }
confirm() { return 0; }
update_docker_runtime_latest() { runtime_ready=1; }

docker_runtime_preflight 1 || exit 16
[ "$runtime_ready" = "1" ] || exit 17
[ "$DOCKER_PREFLIGHT_DONE" = "1" ] || exit 18
"""

    result = _run_installer_function(tmp_path, shell_body)

    assert result.returncode == 0, result.stderr


def test_shell_installer_preflight_stops_when_incompatible_update_is_declined(
    tmp_path: Path,
):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    shell_body = r"""
docker_runtime_compatible() { return 1; }
print_docker_runtime_versions() { :; }
explain_docker_runtime_incompatibility() { :; }
confirm() { return 1; }
update_docker_runtime_latest() { exit 90; }

if docker_runtime_preflight 1; then exit 19; fi
[ "$DOCKER_PREFLIGHT_DONE" = "0" ] || exit 20
"""

    result = _run_installer_function(tmp_path, shell_body)

    assert result.returncode == 0, result.stderr


def test_shell_installer_rejects_legacy_compose_v1(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    legacy_compose = tmp_path / "docker-compose"
    legacy_compose.write_text(
        """#!/bin/sh
if [ "$1" = "version" ] && [ "${2:-}" = "--short" ]; then
    printf '1.29.2\n'
    exit 0
fi
if [ "$1" = "version" ]; then
    printf 'docker-compose version 1.29.2\n'
    exit 0
fi
exit 1
""",
        encoding="utf-8",
    )
    legacy_compose.chmod(0o755)

    shell_body = f"""
PATH={shlex.quote(str(tmp_path))}:$PATH
docker() {{
    if [ "$1" = "compose" ]; then return 1; fi
    if [ "$1" = "version" ]; then printf '26.1.4\n'; return 0; fi
    if [ "$1" = "info" ]; then return 0; fi
    return 1
}}
if detect_compose_command; then exit 20; fi
[ -z "$COMPOSE_VERSION_VALUE" ] || exit 21
"""

    result = _run_installer_function(tmp_path, shell_body)

    assert result.returncode == 0, result.stderr


def test_shell_installer_preserves_compose_failure_status(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    shell_body = f"""
TARGET_DIR='{runtime_dir.as_posix()}'
run_compose() {{ printf 'compose failed\\n'; return 37; }}
explain_compose_failure() {{ :; }}
info() {{ :; }}
run_compose_checked pull
status=$?
[ "$status" -eq 37 ] || exit 30
grep -q 'compose failed' "$TARGET_DIR/$INSTALL_STATE_DIR/compose-last-error.log" || exit 31
"""

    result = _run_installer_function(tmp_path, shell_body)

    assert result.returncode == 0, result.stderr


def test_run_compose_does_not_consume_wizard_input(tmp_path: Path) -> None:
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    compose_answers_path = tmp_path / "compose-answers.txt"
    compose_answers_path.write_text("compose\n", encoding="utf-8", newline="\n")
    logged_answers_path = tmp_path / "logged-answers.txt"
    logged_answers_path.write_text("logged\n", encoding="utf-8", newline="\n")
    result = _run_installer_function(
        tmp_path,
        f"""
docker() {{ IFS= read -r stolen || true; }}
exec 3< {shlex.quote(compose_answers_path.as_posix())}
compose up <&3
IFS= read -r preserved <&3 || exit 20
[ "$preserved" = compose ] || exit 21

exec 3<&-
exec 3< {shlex.quote(logged_answers_path.as_posix())}
run_compose up <&3
IFS= read -r preserved <&3 || exit 22
[ "$preserved" = logged ] || exit 23
""",
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_shell_installer_explains_start_interval_compatibility_error(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    error_path = tmp_path / "compose-error.log"
    error_path.write_text(
        "services.backend.healthcheck value 'start_interval' does not match any of the "
        "regexes: '^x-'\n",
        encoding="utf-8",
    )
    shell_body = f"""
print_docker_runtime_versions() {{ :; }}
explain_compose_failure '{error_path.as_posix()}' config --quiet
"""

    result = _run_installer_function(tmp_path, shell_body)

    assert result.returncode == 0, result.stderr
    assert "не поддерживает healthcheck.start_interval" in result.stderr
    assert "Docker Compose 2.20.2+" in result.stdout
    assert "Docker Engine 25.0.0+" in result.stdout


def test_shell_installer_does_not_pull_when_compose_config_is_invalid(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    marker_path = tmp_path / "compose-command.txt"
    shell_body = f"""
TARGET_DIR='{tmp_path.as_posix()}'
ENV_PATH="$TARGET_DIR/.env"
INSTALL_NODE_ROLE_VALUE=full-stack
validate_bind_settings() {{ :; }}
validate_compose_configuration() {{ return 1; }}
run_compose_checked() {{ printf '%s\\n' "$*" > '{marker_path.as_posix()}'; }}

if start_stack 1; then exit 40; fi
[ ! -e '{marker_path.as_posix()}' ] || exit 41
"""

    result = _run_installer_function(tmp_path, shell_body)

    assert result.returncode == 0, result.stderr


def test_shell_installer_prints_migrate_logs_after_compose_failure():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "didn't complete successfully" in script
    assert "Сервис migrate завершился с ошибкой" in script
    assert "compose logs --tail 120 migrate" in script


def test_deployment_docs_explain_install_wizard_prompts():
    docs = (REPO_ROOT / "docs" / "getting-started" / "deployment.md").read_text(encoding="utf-8")

    assert "### Что спрашивает install wizard" in docs
    assert "`HTTP_BIND` / `HTTPS_BIND`" in docs
    assert "`FRONTEND_BACKEND_MODE`" in docs
    assert "split-protected-upstream" in docs
    assert "Rathole" in docs
    assert "с одним IP без порта некорректно" in docs
    assert "Docker Engine `25.0.0`" in docs
    assert "Docker Compose `2.20.2`" in docs
    assert "docker compose config --quiet" in docs
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
    assert "egames_nginx_tls_mode" in script
    assert "egames_nginx_listen_directives" in script
    assert "container_certificate_covers_host" in script
    assert "render_egames_server_block" in script
    assert "egames_container_has_routes" in script
    assert 'docker restart "$nginx_container" >/dev/null' in script
    assert 'docker exec "$nginx_container" nginx -s reload' in script


def test_shell_installer_detects_supported_egames_tls_listener_modes(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    tcp_config = tmp_path / "tcp.conf"
    tcp_config.write_text(
        """
server {
    server_name control.example.test;
    listen 443 ssl;
}
server {
    listen 443 ssl default_server;
    server_name _;
}
""",
        encoding="utf-8",
    )
    unix_config = tmp_path / "unix.conf"
    unix_config.write_text(
        """
server {
    server_name control.example.test;
    listen unix:/run/edge/tls.sock ssl proxy_protocol;
}
""",
        encoding="utf-8",
    )
    mixed_config = tmp_path / "mixed.conf"
    mixed_config.write_text(
        tcp_config.read_text(encoding="utf-8") + unix_config.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    managed_config = tmp_path / "managed.conf"
    managed_config.write_text(
        tcp_config.read_text(encoding="utf-8")
        + """
# BEGIN remnawave-minishop managed by install.sh
server {
    server_name old-route.example.test;
    listen unix:/run/edge/tls.sock ssl proxy_protocol;
}
# END remnawave-minishop managed by install.sh
""",
        encoding="utf-8",
    )

    shell_body = f"""
tcp_config={shlex.quote(tcp_config.as_posix())}
unix_config={shlex.quote(unix_config.as_posix())}
mixed_config={shlex.quote(mixed_config.as_posix())}
managed_config={shlex.quote(managed_config.as_posix())}

[ "$(egames_nginx_tls_mode "$tcp_config")" = tcp ] || exit 30
[ "$(egames_nginx_listen_directives tcp "$tcp_config")" = "    listen 443 ssl;" ] || exit 31
[ "$(egames_nginx_tls_mode "$unix_config")" = unix ] || exit 32
[ "$(egames_nginx_listen_directives unix "$unix_config")" = \
    "    listen unix:/run/edge/tls.sock ssl proxy_protocol;" ] || exit 33
mixed_mode=$(egames_nginx_tls_mode "$mixed_config" 2>/dev/null || true)
[ "$mixed_mode" = mixed ] || exit 34
[ "$(egames_nginx_tls_mode "$managed_config")" = tcp ] || exit 35
"""

    result = _run_installer_function(tmp_path, shell_body)

    assert result.returncode == 0, result.stdout + result.stderr


def test_shell_installer_selects_a_certificate_pair_by_hostname(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    nginx_config = tmp_path / "nginx.conf"
    nginx_config.write_text(
        """
server {
    server_name control.example.test;
    listen 443 ssl;
    ssl_certificate "/tls/control.pem";
    ssl_certificate_key "/tls/control.key";
}
server {
    server_name services.example.test;
    listen 443 ssl;
    ssl_certificate "/tls/services.pem";
    ssl_certificate_key "/tls/services.key";
    ssl_trusted_certificate "/tls/services-chain.pem";
}
""",
        encoding="utf-8",
    )

    config_path = shlex.quote(nginx_config.as_posix())
    shell_body = f"""
container_certificate_covers_host() {{
    [ "$2" = /tls/services.pem ] && [ "$3" = events.example.test ]
}}
pair=$(egames_certificate_pair_for_host edge-nginx \
    {config_path} events.example.test)
[ "$pair" = "/tls/services.pem|/tls/services.key|/tls/services-chain.pem" ] || exit 40
if egames_certificate_pair_for_host edge-nginx \
    {config_path} missing.example.test; then
    exit 41
fi
"""

    result = _run_installer_function(tmp_path, shell_body)

    assert result.returncode == 0, result.stdout + result.stderr


def test_shell_installer_validates_certificate_san_with_openssl(tmp_path: Path):
    if not shutil.which("sh") or not shutil.which("openssl"):
        pytest.skip("sh and openssl are required")

    certificate = tmp_path / "certificate.pem"
    private_key = tmp_path / "private-key.pem"
    openssl_config = tmp_path / "openssl.cnf"
    openssl_config.write_text("[req]\ndistinguished_name=dn\n[dn]\n", encoding="utf-8")
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-config",
            str(openssl_config),
            "-keyout",
            str(private_key),
            "-out",
            str(certificate),
            "-days",
            "1",
            "-subj",
            "/CN=control.example.test",
            "-addext",
            "subjectAltName=DNS:services.example.test",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    shell_body = f"""
certificate_path={shlex.quote(certificate.as_posix())}
docker() {{
    if [ "$1" = exec ] && [ "$3" = sh ]; then
        return 127
    fi
    if [ "$1" = exec ] && [ "$3" = cat ] && [ "$4" = /tls/certificate.pem ]; then
        cat "$certificate_path"
        return 0
    fi
    return 1
}}
container_certificate_covers_host edge-nginx /tls/certificate.pem services.example.test || exit 45
if container_certificate_covers_host edge-nginx /tls/certificate.pem control.example.test; then
    exit 46
fi
"""

    result = _run_installer_function(tmp_path, shell_body)

    assert result.returncode == 0, result.stdout + result.stderr


def test_shell_installer_rejects_legacy_openssl_zero_exit_hostname_mismatch(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    shell_body = """
docker() {
    if [ "$1" = exec ] && [ "$3" = sh ]; then
        return 127
    fi
    if [ "$1" = exec ] && [ "$3" = cat ] && [ "$4" = /tls/certificate.pem ]; then
        printf '%s\n' certificate
        return 0
    fi
    return 1
}
openssl() {
    if [ "$4" = services.example.test ]; then
        printf '%s\n' "Hostname services.example.test does match certificate"
    else
        printf '%s\n' "Hostname $4 does NOT match certificate"
    fi
    return 0
}
container_certificate_covers_host edge-nginx /tls/certificate.pem services.example.test || exit 47
if container_certificate_covers_host edge-nginx /tls/certificate.pem control.example.test; then
    exit 48
fi
"""

    result = _run_installer_function(tmp_path, shell_body)

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("listen_line", "expected_real_ip", "expected_forwarded_for", "unexpected_ip"),
    [
        ("listen 443 ssl;", "$remote_addr", "$proxy_add_x_forwarded_for", "$proxy_protocol_addr"),
        (
            "listen unix:/run/edge/tls.sock ssl proxy_protocol;",
            "$proxy_protocol_addr",
            "$proxy_protocol_addr",
            "$remote_addr",
        ),
    ],
)
def test_shell_installer_renders_egames_routes_for_detected_tls_listener(
    tmp_path: Path,
    listen_line: str,
    expected_real_ip: str,
    expected_forwarded_for: str,
    unexpected_ip: str,
):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    nginx_config = tmp_path / "nginx.conf"
    nginx_config.write_text(
        f"""
server {{
    server_name control.example.test;
    {listen_line}
    ssl_certificate "/tls/shared.pem";
    ssl_certificate_key "/tls/shared.key";
    ssl_trusted_certificate "/tls/shared.pem";
}}
""",
        encoding="utf-8",
    )

    shell_body = f"""
PROFILE_KEY=egames
WEBHOOK_HOST_VALUE=events.example.test
MINIAPP_HOST_VALUE=workspace.example.test
WEB_SERVER_BIND_VALUE=127.0.0.1:8080
FRONTEND_BIND_VALUE=127.0.0.1:8082
detect_egames_nginx_conf() {{ printf '%s' {shlex.quote(nginx_config.as_posix())}; }}
detect_egames_nginx_container() {{ printf '%s' edge-nginx; }}
prompt_value() {{ PROMPT_VALUE="$2"; }}
require_docker() {{ return 0; }}
container_certificate_covers_host() {{ return 0; }}
egames_container_has_routes() {{ return 0; }}
docker() {{ return 0; }}
configure_egames_reverse_proxy
"""

    result = _run_installer_function(tmp_path, shell_body)

    assert result.returncode == 0, result.stdout + result.stderr
    rendered = nginx_config.read_text(encoding="utf-8").split(
        "# BEGIN remnawave-minishop managed by install.sh", 1
    )[1]
    assert listen_line in rendered
    assert "server_name events.example.test;" in rendered
    assert "server_name workspace.example.test;" in rendered
    assert f"proxy_set_header X-Real-IP {expected_real_ip};" in rendered
    assert f"proxy_set_header X-Forwarded-For {expected_forwarded_for};" in rendered
    assert f"proxy_set_header X-Real-IP {unexpected_ip};" not in rendered


def test_shell_installer_keeps_egames_config_when_certificate_is_unverified(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    nginx_config = tmp_path / "nginx.conf"
    original_config = """
server {
    server_name control.example.test;
    listen 443 ssl;
    ssl_certificate "/tls/control.pem";
    ssl_certificate_key "/tls/control.key";
}
"""
    nginx_config.write_text(original_config, encoding="utf-8")

    shell_body = f"""
PROFILE_KEY=egames
WEBHOOK_HOST_VALUE=events.example.test
MINIAPP_HOST_VALUE=workspace.example.test
detect_egames_nginx_conf() {{ printf '%s' {shlex.quote(nginx_config.as_posix())}; }}
detect_egames_nginx_container() {{ printf '%s' edge-nginx; }}
prompt_value() {{ PROMPT_VALUE="$2"; }}
require_docker() {{ return 0; }}
container_certificate_covers_host() {{ return 1; }}
docker() {{ return 0; }}
if configure_egames_reverse_proxy; then
    exit 50
fi
"""

    result = _run_installer_function(tmp_path, shell_body)

    assert result.returncode == 0, result.stdout + result.stderr
    assert nginx_config.read_text(encoding="utf-8") == original_config


def test_shell_installer_requires_an_explicit_choice_for_unverified_panel_settings():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "configure_panel_integration" in script
    assert "Enter пропустит интеграцию без записи change_me" in script
    assert 'choose "Интеграция с Remnawave Panel" "$panel_setup_default" "1|2"' in script
    assert 'choose "Параметры Panel не прошли проверку" "2" "1|2|3"' in script
    assert "Сохранить непроверенные параметры и продолжить на свой риск" in script
    assert "clear_panel_configuration" in script


def test_shell_installer_validates_panel_cookie_and_live_json_response():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "panel_configuration_shape_ready" in script
    assert 'choose "Способ доступа к Remnawave Panel"' in script
    assert "Удалённая Panel за eGames reverse proxy" in script
    assert "normalize_panel_api_cookie" in script
    assert "PANEL_API_COOKIE похож на JWT/API-ключ" in script
    assert "Cookie должен иметь формат name=value" in script
    assert "probe_panel_api_configuration" in script
    assert "--header @-" in script
    assert "panel-probe-headers" not in script
    assert "application/json" in script
    assert "Panel API вернул JSON, но без ожидаемого поля response" in script
    assert "validate_panel_configuration_from_env || return 1" in script


def test_shell_installer_rejects_jwt_in_panel_cookie_field(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    result = _run_installer_function(
        tmp_path,
        """
PANEL_API_URL_VALUE=https://panel.local/api
PANEL_API_KEY_VALUE=valid-key
PANEL_API_COOKIE_VALUE=header.payload.signature
panel_configuration_shape_ready
""",
    )

    assert result.returncode != 0
    assert "PANEL_API_COOKIE похож на JWT/API-ключ" in result.stdout


def test_shell_installer_accepts_named_panel_cookie(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    result = _run_installer_function(
        tmp_path,
        """
PANEL_API_URL_VALUE=https://panel.local/api
PANEL_API_KEY_VALUE=valid-key
PANEL_API_COOKIE_VALUE=rw_session=session-value
panel_configuration_shape_ready
""",
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("provided_value", "expected_cookie"),
    [
        ("access_key=access_value", "access_key=access_value"),
        ("Cookie: access_key=access_value", "access_key=access_value"),
        (
            "Cookie: access_key=access_value; session_id=session_value",
            "access_key=access_value; session_id=session_value",
        ),
        (
            "Set-Cookie: access_key=access_value; Path=/; HttpOnly",
            "access_key=access_value",
        ),
        (
            "https://panel.remote.invalid/auth/login?access_key=access_value",
            "access_key=access_value",
        ),
    ],
)
def test_shell_installer_normalizes_remote_panel_cookie_inputs(
    tmp_path: Path,
    provided_value: str,
    expected_cookie: str,
):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    result = _run_installer_function(
        tmp_path,
        f"""
provided_value={shlex.quote(provided_value)}
expected_cookie={shlex.quote(expected_cookie)}
normalized=$(normalize_panel_api_cookie "$provided_value") || exit 20
[ "$normalized" = "$expected_cookie" ] || exit 21
""",
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "provided_value",
    [
        "header.payload.signature",
        "https://panel.remote.invalid/auth/login",
        "https://panel.remote.invalid/auth/login?access_key=access_value&next=dashboard",
        "access_key=",
        "=access_value",
        "access_key=access_value; Path=/",
        "access_key=value$HOME",
        "Cookie: access_key=access_value\nInjected=header",
    ],
)
def test_shell_installer_rejects_ambiguous_or_unsafe_panel_cookie_inputs(
    tmp_path: Path,
    provided_value: str,
):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    result = _run_installer_function(
        tmp_path,
        f"""
provided_value={shlex.quote(provided_value)}
if normalize_panel_api_cookie "$provided_value" >/dev/null; then exit 20; fi
""",
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_shell_installer_remote_panel_access_mode_extracts_cookie_from_access_url(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    result = _run_installer_function(
        tmp_path,
        """
detected_panel_api_cookie=
detected_panel_api_cookie_prefilled=0
choose() { CHOICE_VALUE=2; }
prompt_value() { PROMPT_VALUE=https://panel.remote.invalid/auth/login?access_key=access_value; }
prompt_panel_access_cookie || exit 20
[ "$PANEL_API_COOKIE_VALUE" = access_key=access_value ] || exit 21
""",
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_shell_installer_direct_panel_access_mode_clears_a_saved_cookie(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    result = _run_installer_function(
        tmp_path,
        """
detected_panel_api_cookie=access_key=stale_value
detected_panel_api_cookie_prefilled=1
PANEL_API_COOKIE_VALUE=access_key=stale_value
choose() { CHOICE_VALUE=1; }
prompt_panel_access_cookie || exit 20
[ -z "$PANEL_API_COOKIE_VALUE" ] || exit 21
[ -z "$detected_panel_api_cookie" ] || exit 22
""",
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_shell_installer_attaches_to_existing_nginx_or_caddy_containers():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "configure_existing_reverse_proxy" in script
    assert "attach_existing_reverse_proxy_container" in script
    assert "list_running_proxy_containers" in script
    assert "proxy_container_kind" in script
    assert "container_uses_host_network" in script
    assert "container_mount_source" in script
    assert "ensure_target_network_exists" in script
    assert "connect_proxy_to_target_network" in script
    assert "Другой запущенный Nginx, Angie или Caddy" in script
    # Bridge-network proxies resolve compose service names dynamically.
    assert "resolver 127.0.0.11" in script
    assert "http://backend:8080" in script
    assert "http://frontend:80" in script
    # Config changes are validated and rolled back on failure.
    assert 'docker exec "$1" nginx -t' in script
    assert "caddy validate --config" in script
    assert "caddy reload --config" in script
    # Angie containers get the same generic attach flow (nginx-compatible CLI).
    assert "attach_generic_angie_proxy" in script
    assert 'docker exec "$1" angie -t' in script
    assert "angie -s reload" in script
    assert "angie_container_httpd_host_dir" in script
    assert "strip_managed_block" in script
    assert "caddy_remove_managed_and_conflicting_sites" in script
    assert "remnawave-minishop.conf" in script


def test_caddy_routes_replace_conflicting_legacy_site_blocks(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    source = tmp_path / "Caddyfile"
    rendered = tmp_path / "Caddyfile.rendered"
    source.write_text(
        """{
    email admin@example.test
}

https://hooks.example.test {
    handle /payments {
        reverse_proxy legacy_bot:8080
    }
}

app.example.test {
    reverse_proxy legacy_bot:8080
}

untouched.example.test {
    reverse_proxy untouched:9000
}

# BEGIN remnawave-minishop managed by install.sh
hooks.example.test {
    reverse_proxy backend:8080
}
app.example.test {
    reverse_proxy frontend:80
}
# END remnawave-minishop managed by install.sh
""",
        encoding="utf-8",
    )
    shell_body = f"""
caddy_remove_managed_and_conflicting_sites \
    {shlex.quote(source.as_posix())} \
    {shlex.quote(rendered.as_posix())} \
    hooks.example.test app.example.test || exit 20
render_generic_caddy_block \
    {shlex.quote(rendered.as_posix())} \
    hooks.example.test app.example.test backend:8080 frontend:80
"""

    result = _run_installer_function(tmp_path, shell_body)

    assert result.returncode == 0, result.stdout + result.stderr
    config = rendered.read_text(encoding="utf-8")
    assert config.count("hooks.example.test {") == 1
    assert config.count("app.example.test {") == 1
    assert "legacy_bot:8080" not in config
    assert "untouched.example.test" in config
    assert "reverse_proxy untouched:9000" in config


def test_external_proxy_is_reconnected_after_target_network_recreation(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    calls = tmp_path / "network-calls"
    shell_body = f"""
EXISTING_PROXY_CONTAINER_NAME=caddy
docker_container_exists() {{ return 0; }}
container_uses_host_network() {{ return 1; }}
connect_proxy_to_target_network() {{ printf '%s\n' "$1" >> {shlex.quote(calls.as_posix())}; }}
reconnect_existing_reverse_proxy_after_stack_start || exit 20
"""

    result = _run_installer_function(tmp_path, shell_body)

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls.read_text(encoding="utf-8").strip() == "caddy"


def test_migration_database_dsn_prompts_are_secret():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")
    dsn_prompts = [
        line.strip()
        for line in script.splitlines()
        if line.lstrip().startswith('prompt_value "') and "PostgreSQL" in line and "DSN" in line
    ]

    assert len(dsn_prompts) == 5
    assert all(re.search(r' 1 1 ""$', line) for line in dsn_prompts)


def test_shell_installer_can_toggle_pangolin_newt_publication():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "docker-compose.pangolin.yml" in script
    assert "write_pangolin_compose_file" in script
    assert "enable_pangolin_compose_file" in script
    assert "disable_pangolin_compose_file" in script
    assert "pangolin_connect_in_target" in script
    assert "pangolin_disconnect_in_target" in script
    assert "offer_pangolin_connect_after_install" in script
    assert "Подключить Web App к Pangolin (Newt)." in script
    assert "Отключить Web App от Pangolin (Newt)." in script
    assert "COMPOSE_FILE" in script
    assert "unset_env_file_value" in script
    assert "rm -sf newt" in script
    assert "fosrl/newt:latest" in script
    # Disconnect keeps credentials for an easy reconnect.
    assert "оставлены в .env для быстрого повторного подключения" in script


def test_shell_installer_supports_angie_auto_tls_profile():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "Angie HTTPS - форк Nginx с автоматическими сертификатами (ACME)" in script
    assert 'PROFILE_KEY="angie"' in script
    assert "deploy/examples/angie/docker-compose.yml" in script
    assert "deploy/examples/angie/angie.conf.template" in script
    assert "deploy/examples/angie/.env.example" in script
    # Angie shares the Caddy-style prompts: hostnames, binds and DNS preflight.
    assert "caddy|angie|nginx|newt|egames)" in script
    assert "caddy|angie|nginx)" in script
    assert "caddy|angie|nginx|egames)" in script
    # Post-start runtime validation covers the angie compose service.
    assert "printf 'angie'" in script
    # Pre-migration backups capture the Angie config alongside Caddy/Nginx ones.
    assert "Caddyfile angie.conf.template nginx.conf.template" in script


def test_angie_example_uses_native_acme_auto_tls():
    example_dir = REPO_ROOT / "deploy" / "examples" / "angie"
    compose = (example_dir / "docker-compose.yml").read_text(encoding="utf-8")
    config = (example_dir / "angie.conf.template").read_text(encoding="utf-8")

    # The templated image renders {{.Env.*}} placeholders from .env values.
    assert "docker.angie.software/angie:templated" in compose
    assert "./angie.conf.template:/etc/angie/templates/angie.conf:ro" in compose
    # ACME account + certificates must survive container recreation.
    assert "angie-acme:/var/lib/angie/acme" in compose
    assert "name: ${COMPOSE_PROJECT_NAME:-remnawave-minishop}-angie-acme" in compose

    assert "{{.Env.WEBHOOK_HOST}}" in config
    assert "{{.Env.MINIAPP_HOST}}" in config
    # acme_client requires a resolver; 127.0.0.11 is Docker's embedded DNS.
    assert "resolver 127.0.0.11" in config
    assert "acme_client webhooks" in config
    assert "acme_client miniapp" in config
    assert "ssl_certificate $acme_cert_webhooks;" in config
    assert "ssl_certificate_key $acme_cert_key_webhooks;" in config
    assert "ssl_certificate $acme_cert_miniapp;" in config
    assert "ssl_certificate_key $acme_cert_key_miniapp;" in config
    # Same routing planes as every other proxy example.
    assert "server backend:8080;" in config
    assert "server frontend:80;" in config
    # Required for payment provider IP allowlists in webhook handlers.
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in config


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
    assert "docker compose exec -T nginx nginx -s reload" in script
    assert "docker-compose exec -T nginx nginx -s reload" not in script
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
        "    stop_remnashop_source_stack\n"
        "    remnashop_post_migration_next_steps"
    ) in script


def test_shell_installer_can_reset_target_database_before_remnashop_import():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "reset_target_compose_database" in script
    assert "Сбросить целевую базу Minishop перед импортом" in script
    assert "create_pre_migration_backup" in script
    assert "backups/pre-${migration_label}-migration" in script
    assert "restore.sh" in script
    assert "run_compose stop backend worker migrate" in script
    assert 'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"' in script


def test_pre_migration_backup_keeps_source_label_after_confirmation(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    target_dir = tmp_path / "target"
    target_dir.mkdir()
    shell_body = f"""
TARGET_DIR={shlex.quote(target_dir.as_posix())}
require_docker() {{ return 0; }}
check_target_postgres_auth() {{ return 1; }}
section() {{ :; }}
ok() {{ :; }}
warn() {{ :; }}
printf '\n' | create_pre_migration_backup bedolaga || exit 20
set -- "$TARGET_DIR"/backups/pre-bedolaga-migration-*
[ -d "$1" ] || exit 21
"""

    result = _run_installer_function(tmp_path, shell_body)

    assert result.returncode == 0, result.stdout + result.stderr


def test_deployment_examples_scope_named_volumes_to_compose_project():
    for profile in ("caddy", "angie", "nginx", "newt", "no-proxy"):
        compose = (REPO_ROOT / "deploy" / "examples" / profile / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
        assert "name: ${COMPOSE_PROJECT_NAME:-remnawave-minishop}-db-data" in compose
        assert "name: ${COMPOSE_PROJECT_NAME:-remnawave-minishop}-redis-data" in compose
        assert "name: remnawave-minishop-db-data" not in compose
        assert "name: remnawave-minishop-redis-data" not in compose


def test_postgres_healthchecks_validate_configured_credentials():
    compose_paths = [REPO_ROOT / "docker-compose.yml"] + [
        REPO_ROOT / "deploy" / "examples" / profile / "docker-compose.yml"
        for profile in ("caddy", "angie", "nginx", "newt", "no-proxy")
    ]

    for path in compose_paths:
        compose = path.read_text(encoding="utf-8")
        assert "PGPASSWORD=" in compose
        assert "$$POSTGRES_PASSWORD" in compose
        assert "psql -h 127.0.0.1" in compose
        assert "pg_isready -U $$POSTGRES_USER" not in compose


def test_backend_compose_profiles_pin_internal_webhook_port():
    compose_paths = [
        REPO_ROOT / "docker-compose.yml",
        REPO_ROOT / "docker-compose-dev.yml",
        REPO_ROOT
        / "deploy"
        / "examples"
        / "split-protected-upstream"
        / "backend.docker-compose.yml",
        *(
            REPO_ROOT / "deploy" / "examples" / profile / "docker-compose.yml"
            for profile in ("caddy", "angie", "nginx", "newt", "no-proxy")
        ),
    ]

    for path in compose_paths:
        compose = path.read_text(encoding="utf-8")
        assert re.search(r"WEB_SERVER_INTERNAL_PORT:\s*['\"]?8080['\"]?", compose), path


def test_shell_installer_guards_existing_postgres_volume_password_drift():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "preflight_existing_postgres_volume" in script
    assert "Найден существующий Docker volume PostgreSQL" in script
    assert "PostgreSQL принимает логин/пароль из .env" in script
    assert "InvalidPasswordError|password authentication failed" in script
    assert "Удалить volume $volume и начать с пустой БД" in script
    assert "target_ip=$1" in script
    assert 'PGPASSWORD="$POSTGRES_PASSWORD" PGCONNECT_TIMEOUT=5 psql -h "$target_ip"' in script
    assert "psql -h 127.0.0.1" not in script
    assert "preflight_compose_project_ownership" in script
    assert '-v "$1:/data:ro"' in script
    assert 'pg_isready -U "$POSTGRES_USER"' not in script


def test_shell_installer_rejects_foreign_compose_project(tmp_path: Path) -> None:
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / ".env").write_text("COMPOSE_PROJECT_NAME=shared-project\n", encoding="utf-8")
    result = _run_installer_function(
        tmp_path,
        f"""
TARGET_DIR={shlex.quote(target_dir.as_posix())}
ENV_PATH="$TARGET_DIR/.env"
fail() {{ printf '%s\n' "$*"; }}
info() {{ printf '%s\n' "$*"; }}
docker() {{
    case "$1" in
        ps) printf '%s\n' foreign-container-id ;;
        inspect)
            case "$3" in
                *working_dir*) printf '%s\n' /opt/old-minishop ;;
                *) printf '%s\n' /foreign-container ;;
            esac
            ;;
        *) return 1 ;;
    esac
}}

if preflight_compose_project_ownership; then
    exit 20
fi
""",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "shared-project" in result.stdout
    assert "/opt/old-minishop" in result.stdout


def test_shell_installer_refreshes_importer_without_prompting_inside_command_substitution():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "Use cached importer" not in script
    assert 'download_to "$url" "$tmp"' in script
    assert "Бэкап скрипта импорта сохранен" in script


def test_shell_installer_connects_local_remnashop_db_container_for_import():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "connect_local_source_db_to_target_network" in script
    assert "disconnect_local_source_db_from_target_network" in script
    assert "target_network_name()" in script
    assert "dsn_hostname" in script
    assert "docker network connect" in script
    assert "docker network disconnect" in script
    assert 'target_network="$(target_network_name)"' in script
    assert (
        "disconnect_local_source_db_from_target_network\n"
        '        fail "Проверка без записи не прошла'
    ) in script
    assert (
        'disconnect_local_source_db_from_target_network\n        warn "Миграция не применена."'
    ) in script
    assert (
        "restore_app_data_permissions || true\n    disconnect_local_source_db_from_target_network"
    ) in script


def test_shell_installer_repairs_reverse_proxy_runtime_after_start():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "validate_reverse_proxy_runtime" in script
    assert "reverse_proxy_runtime_ready" in script
    assert "reverse_proxy_upstreams_ready" in script
    assert "wait_reverse_proxy_runtime" in script
    assert "wait_reverse_proxy_upstreams" in script
    assert 'docker port "$container" 80/tcp' in script
    assert 'docker port "$container" 443/tcp' in script
    assert script.count('--force-recreate "$service"') == 1
    assert "пересоздаю proxy еще раз" not in script
    assert "http://backend:8080/healthz" in script
    assert "http://frontend/health" in script
    assert 'run_compose logs --tail 80 "$service" backend frontend' in script
    assert (
        'validate_reverse_proxy_runtime || return 1\n    ok "Команда запуска стека выполнена."'
    ) in script
    assert (
        "validate_reverse_proxy_runtime || return 1\n"
        "    validate_panel_configuration_from_env || return 1\n"
        '    ok "Команды проверки выполнены."'
    ) in script


def test_shell_installer_waits_for_reverse_proxy_upstreams_without_recreating_proxy(
    tmp_path: Path,
):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    shell_body = r"""
TARGET_DIR=.
reverse_proxy_service_name() { printf 'caddy'; }
target_network_name() { printf 'minishop_default'; }
compose_service_container_id() { printf 'caddy-container'; }
reverse_proxy_runtime_ready() { return 0; }
upstream_attempts=0
reverse_proxy_upstreams_ready() {
    upstream_attempts=$((upstream_attempts + 1))
    [ "$upstream_attempts" -ge 3 ]
}
run_compose_checked() {
    echo "unexpected compose recreate: $*" >&2
    return 9
}
run_compose() { return 0; }
section() { :; }
ok() { :; }
warn() { :; }
fail() { echo "unexpected failure: $*" >&2; return 1; }
sleep() { :; }

validate_reverse_proxy_runtime || exit "$?"
[ "$upstream_attempts" -eq 3 ] || exit 20
"""

    result = _run_installer_function(tmp_path, shell_body)

    assert result.returncode == 0, result.stderr


def test_caddyfile_redacts_panel_webhook_secret_header_from_logs():
    caddyfile = (REPO_ROOT / "deploy" / "examples" / "caddy" / "Caddyfile").read_text(
        encoding="utf-8"
    )

    assert "log default" in caddyfile
    assert "format filter" in caddyfile
    assert "request>headers>X-Telegram-Bot-Api-Secret-Token replace REDACTED" in caddyfile


def test_shell_installer_stops_remnashop_after_successful_migration_without_deleting_data():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "REMNASHOP_RUNTIME_CONTAINERS" in script
    assert "remnashop-taskiq-worker" in script
    assert "remnashop-taskiq-scheduler" in script
    assert "stop_remnashop_source_stack" in script
    assert "Остановить старые контейнеры Remnashop без удаления данных" in script
    assert "run_compose stop" in script
    assert 'docker stop "$container"' in script
    assert 'ok "Миграция завершена."\n    stop_remnashop_source_stack' in script


def test_shell_installer_supports_split_frontend_backend_modes():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    for key in (
        "FRONTEND_BACKEND_MODE",
        "INSTALL_NODE_ROLE",
        "WEBAPP_BACKEND_UPSTREAM",
        "WEBAPP_BACKEND_UPSTREAM_HOST",
        "MINISHOP_EDGE_TOKEN",
        "MINISHOP_EDGE_TOKEN_HEADER",
        "WEBAPP_SERVER_BIND",
        "RATHOLE_IMAGE",
        "RATHOLE_CONTROL_BIND",
        "RATHOLE_CONTROL_REMOTE",
        "RATHOLE_SERVICE_TOKEN",
        "RATHOLE_SERVICE_PORT",
    ):
        assert key in script
    assert "prompt_frontend_node_env" in script
    assert "choose_install_node_role" in script
    assert "deploy/examples/split-protected-upstream/.env.frontend.example" in script
    assert "deploy/examples/split-protected-upstream/.env.backend.example" in script
    assert (
        'cp "$TARGET_DIR/rathole/rathole.server.toml" "$TARGET_DIR/rathole.server.toml"' in script
    )
    assert "Как frontend будет обращаться к backend WebApp API?" in script
    assert "Защищенный backend upstream" in script
    assert "Приватный tunnel Rathole" in script
    assert "Rathole TOML сохранены" in script


def test_shell_installer_migrates_legacy_tgshop_through_dsn_restore():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "Старый remnawave-tg-shop" in script or "старого remnawave-tg-shop" in script
    assert "detect_tgshop_source_dsn" in script
    assert "LEGACY_TGSHOP_DB_CONTAINER" in script
    assert "create_tgshop_source_backup" in script
    assert "pre-remnawave-tg-shop-source" in script
    assert "reset_target_postgres_volume" in script
    assert 'docker volume rm "$volume"' in script
    assert "копирования raw PostgreSQL volume" in script
    assert "pg_dump --clean --if-exists" in script
    assert 'psql "$TARGET_DSN" -v ON_ERROR_STOP=1' in script
    assert "host_user_spec()" in script
    assert script.count('--user "$(host_user_spec)"') >= 2
    assert "run_compose_checked run --rm migrate" in script
    assert "skip_existing_volume_preflight" in script
    assert "start_stack 0 1" in script
    assert "run_tgshop_volume_migration" not in script
    assert "copy_volume_if_safe" not in script


def test_shell_installer_sets_tls_profile_public_urls():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert (
        'WEBHOOK_PUBLIC_URL_VALUE="$(env_get WEBHOOK_PUBLIC_URL "https://$WEBHOOK_HOST_VALUE")"'
    ) in script
    assert (
        'MINIAPP_PUBLIC_URL_VALUE="$(env_get MINIAPP_PUBLIC_URL "https://$MINIAPP_HOST_VALUE/")"'
    ) in script


def test_shell_installer_suppresses_noisy_certbot_cloudflare_warning():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "PYTHONWARNINGS=ignore::PendingDeprecationWarning certbot certonly" in script


def test_shell_installer_stops_when_certbot_required_prompts_fail():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert (
        'prompt_value "Email аккаунта Let\'s Encrypt" "$(env_get LETSENCRYPT_EMAIL \'\')" '
        '1 0 "" || return 1'
    ) in script
    assert (
        'prompt_value "Cloudflare DNS API token" "$(env_get CLOUDFLARE_DNS_API_TOKEN \'\')" '
        '1 1 "" || return 1'
    ) in script


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
    assert "Нашел BOT_TOKEN в .env $(legacy_source_label)" in script
    assert "Нашел ADMIN_IDS в .env $(legacy_source_label)" in script
    assert "Нашел Telegram webhook secret в .env $(legacy_source_label)" in script
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
    assert "Импортер завершился без корректного JSON-итога" in script
    assert 'confirm "Применить эту миграцию по-настоящему?" 1' in script
    assert "print_remnashop_import_summary" in script
    assert "Проверка без записи прошла успешно" in script
    assert "Полный сырой вывод скрипта импорта сохранен" in script
    assert "REMNASHOP_BALANCE_CURRENCY" in script
    assert '--balance-currency "$BALANCE_CURRENCY"' in script
    assert "read_remnashop_balance_plan" in script
    assert 'set_env_file_value "$ENV_PATH" USER_BALANCE_CURRENCY' in script
    assert 'set_env_file_value "$ENV_PATH" USER_BALANCE_ENABLED true' in script
    assert "партнерские профили не создаются" in script


def test_shell_installer_preserves_importer_failures_and_requires_json_summary(
    tmp_path: Path,
) -> None:
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    target_dir = tmp_path / "target"
    target_dir.mkdir()
    importer_path = tmp_path / "import_legacy.py"
    importer_path.write_text("# test importer\n", encoding="utf-8")
    result = _run_installer_function(
        tmp_path,
        f"""
TARGET_DIR={shlex.quote(target_dir.as_posix())}
IMPORTER_PATH={shlex.quote(importer_path.as_posix())}
SOURCE_ENV_PATH=""
TARIFF_MAP_PATH=""
SOURCE_DSN=postgresql://source/db
SOURCE_SCHEMA=public
TARGET_DSN=postgresql://target/db
BALANCE_CURRENCY=""
fail() {{ printf '%s\n' "$*" >&2; }}
MODE=failed
run_compose() {{
    if [ "$MODE" = failed ]; then
        printf '%s\n' importer-failed
        return 23
    fi
    printf '%s\n' importer-finished-without-summary
}}

status=0
run_import_command 1 "$TARGET_DIR/failed-summary.json" 0 remnashop || status=$?
[ "$status" -eq 23 ] || exit 20
grep -q importer-failed "$TARGET_DIR/failed-summary.json.raw" || exit 21

MODE=invalid
status=0
run_import_command 1 "$TARGET_DIR/invalid-summary.json" 0 remnashop || status=$?
[ "$status" -ne 0 ] || exit 22
""",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "importer-finished-without-summary" in result.stdout
    assert "корректного JSON-итога" in result.stderr


def test_shell_installer_supports_guarded_bedolaga_migration():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "DOCS_BEDOLAGA_URL" in script
    assert "detect_bedolaga_env_file" in script
    assert "detect_bedolaga_db_container" in script
    assert "detect_bedolaga_source_dsn" in script
    assert 'LEGACY_SOURCE="bedolaga"' in script
    assert "run_bedolaga_migration" in script
    assert '--source-type "$source_type"' in script
    assert "--inventory-output" in script
    assert "--config-plan-output" in script
    assert "--reconciliation-output" in script
    assert "bedolaga-dry-run-summary.json" in script
    assert "bedolaga-apply-summary.json" in script
    assert "bedolaga-inventory.json" in script
    assert "bedolaga-config-plan.json" in script
    assert "bedolaga-reconciliation.json" in script
    assert "bedolaga-post-migration.md" in script
    assert "sync_bedolaga_bootstrap_env" in script
    assert "backfill_bedolaga_panel_subscription_ids" in script
    assert "perform_bedolaga_cutover" in script
    assert "stop_bedolaga_source_stack" in script
    assert "docker update --restart=no" in script
    assert "wait_target_runtime_healthy" in script
    assert "verify_bedolaga_subscription_links" in script
    assert "lower(coalesce(imported.provider, '')) <> 'trial'" in script
    assert "bedolaga_external_integrations_checklist" in script
    assert "Minishop не может автоматически изменить redirect/callback" in script
    assert "/auth/telegram/callback" in script
    assert "/auth/google/callback" in script
    assert "/auth/yandex/callback" in script
    assert "/webhook/cloudpayments" in script
    assert "/webhook/stripe" in script
    assert "/webhook/tribute" in script
    assert (
        "    perform_bedolaga_cutover || return 1\n    bedolaga_external_integrations_checklist"
    ) in script


def test_shell_installer_prints_bedolaga_external_callback_urls(tmp_path: Path) -> None:
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    target_dir = tmp_path / "minishop"
    target_dir.mkdir()
    env_path = target_dir / ".env"
    env_path.write_text(
        "WEBHOOK_PUBLIC_URL=https://hooks.new.example/\n"
        "MINIAPP_PUBLIC_URL=https://app.new.example/\n",
        encoding="utf-8",
    )

    result = _run_installer_function(
        tmp_path,
        f"""
TARGET_DIR={shlex.quote(str(target_dir))}
ENV_PATH={shlex.quote(str(env_path))}
MINIAPP_PUBLIC_URL_VALUE=
MINIAPP_HOST_VALUE=
bedolaga_external_integrations_checklist
""",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "https://app.new.example/auth/telegram/callback" in result.stdout
    assert "https://app.new.example/auth/google/callback" in result.stdout
    assert "https://app.new.example/auth/yandex/callback" in result.stdout
    assert "https://hooks.new.example/webhook/yookassa" in result.stdout
    assert "https://hooks.new.example/webhook/cloudpayments" in result.stdout
    assert "https://hooks.new.example/webhook/stripe" in result.stdout
    assert "https://hooks.new.example/webhook/tribute" in result.stdout
    assert "https://hooks.new.example/tg/webhook" in result.stdout


def test_shell_installer_copies_compatible_bedolaga_env_with_masked_confirmation(
    tmp_path: Path,
) -> None:
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    source_dir = tmp_path / "bedolaga"
    target_dir = tmp_path / "minishop"
    source_dir.mkdir()
    target_dir.mkdir()
    source_env = source_dir / ".env"
    target_env = target_dir / ".env"
    source_env.write_text(
        "\n".join(
            (
                "BOT_TOKEN=source-bot-secret",
                "ADMIN_IDS=101;202",
                "WEBHOOK_SECRET_TOKEN=source-webhook-secret",
                "REMNAWAVE_API_URL=https://panel.example.com",
                "REMNAWAVE_API_KEY=source-panel-secret",
                "TELEGRAM_OIDC_CLIENT_ID=telegram-client",
                "TELEGRAM_OIDC_CLIENT_SECRET=telegram-client-secret",
                "OAUTH_GOOGLE_ENABLED=True",
                "OAUTH_GOOGLE_CLIENT_ID=google-client",
                "OAUTH_GOOGLE_CLIENT_SECRET=google-client-secret",
                "SMTP_HOST=smtp.example.com",
                "SMTP_PORT=465",
                "SMTP_USER=mailer@example.com",
                "SMTP_PASSWORD=smtp-secret",
                "SMTP_FROM_NAME=Example Mailer",
                "SMTP_USE_TLS=False",
                "SMTP_USE_SSL=True",
                "DEFAULT_LANGUAGE=ru",
                "LOG_LEVEL=WARNING",
                "TZ=Europe/Moscow",
                "BACKUP_AUTO_ENABLED=True",
                "BACKUP_INTERVAL_HOURS=6",
                "BACKUP_MAX_KEEP=14",
                "WEBHOOK_URL=https://bot.example.com/webhook/source",
                "CABINET_URL=https://cabinet.example.com/",
                "POSTGRES_PASSWORD=must-not-copy",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    target_env.write_text(
        "BOT_TOKEN=old-token\nADMIN_IDS=1\nPOSTGRES_PASSWORD=target-db-secret\n",
        encoding="utf-8",
    )

    result = _run_installer_function(
        tmp_path,
        f"""
TARGET_DIR={shlex.quote(target_dir.as_posix())}
ENV_PATH={shlex.quote(target_env.as_posix())}
SOURCE_ENV_PATH={shlex.quote(source_env.as_posix())}
LEGACY_SOURCE=bedolaga
confirm() {{ return 0; }}
section() {{ :; }}
info() {{ printf '%s\n' "$*"; }}
warn() {{ printf '%s\n' "$*"; }}
ok() {{ :; }}
fail() {{ printf '%s\n' "$*" >&2; }}

sync_bedolaga_bootstrap_env || exit 20
[ "$(env_file_get BOT_TOKEN "$ENV_PATH")" = source-bot-secret ] || exit 21
[ "$(env_file_get ADMIN_IDS "$ENV_PATH")" = 101,202 ] || exit 22
[ "$(env_file_get WEBHOOK_SECRET_TOKEN "$ENV_PATH")" = source-webhook-secret ] || exit 23
[ "$(env_file_get PANEL_API_URL "$ENV_PATH")" = https://panel.example.com/api ] || exit 24
[ "$(env_file_get PANEL_API_KEY "$ENV_PATH")" = source-panel-secret ] || exit 25
[ "$(env_file_get TELEGRAM_OAUTH_CLIENT_ID "$ENV_PATH")" = telegram-client ] || exit 26
[ "$(env_file_get TELEGRAM_OAUTH_CLIENT_SECRET "$ENV_PATH")" = telegram-client-secret ] || exit 26
[ "$(env_file_get GOOGLE_OIDC_CLIENT_SECRET "$ENV_PATH")" = google-client-secret ] || exit 27
[ "$(env_file_get GOOGLE_OIDC_ENABLED "$ENV_PATH")" = True ] || exit 27
[ "$(env_file_get GOOGLE_OIDC_CLIENT_ID "$ENV_PATH")" = google-client ] || exit 27
[ "$(env_file_get SMTP_HOST "$ENV_PATH")" = smtp.example.com ] || exit 27
[ "$(env_file_get SMTP_PORT "$ENV_PATH")" = 465 ] || exit 27
[ "$(env_file_get SMTP_USERNAME "$ENV_PATH")" = mailer@example.com ] || exit 27
[ "$(env_file_get SMTP_PASSWORD "$ENV_PATH")" = smtp-secret ] || exit 27
[ "$(env_file_get SMTP_FROM_EMAIL "$ENV_PATH")" = mailer@example.com ] || exit 27
[ "$(env_file_get SMTP_FROM_NAME "$ENV_PATH")" = 'Example Mailer' ] || exit 27
[ "$(env_file_get SMTP_STARTTLS "$ENV_PATH")" = False ] || exit 27
[ "$(env_file_get SMTP_USE_SSL "$ENV_PATH")" = True ] || exit 27
[ "$(env_file_get DEFAULT_LANGUAGE "$ENV_PATH")" = ru ] || exit 27
[ "$(env_file_get LOG_LEVEL "$ENV_PATH")" = WARNING ] || exit 27
[ "$(env_file_get TZ "$ENV_PATH")" = Europe/Moscow ] || exit 27
[ "$(env_file_get BACKUP_ENABLED "$ENV_PATH")" = True ] || exit 27
[ "$(env_file_get BACKUP_INTERVAL_SECONDS "$ENV_PATH")" = 21600 ] || exit 28
[ "$(env_file_get BACKUP_LOCAL_RETENTION "$ENV_PATH")" = 14 ] || exit 28
[ "$(env_file_get WEBHOOK_HOST "$ENV_PATH")" = bot.example.com ] || exit 29
[ "$(env_file_get WEBHOOK_PUBLIC_URL "$ENV_PATH")" = https://bot.example.com ] || exit 29
[ "$(env_file_get MINIAPP_HOST "$ENV_PATH")" = cabinet.example.com ] || exit 30
[ "$(env_file_get MINIAPP_PUBLIC_URL "$ENV_PATH")" = https://cabinet.example.com/ ] || exit 30
[ "$(env_file_get POSTGRES_PASSWORD "$ENV_PATH")" = target-db-secret ] || exit 31
""",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "source-bot-secret" not in result.stdout
    assert "source-webhook-secret" not in result.stdout
    assert "source-panel-secret" not in result.stdout
    assert "google-client-secret" not in result.stdout
    assert "smtp-secret" not in result.stdout
    assert "must-not-copy" not in target_env.read_text(encoding="utf-8")


def test_bedolaga_migration_removes_imported_panel_url_override(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    target_dir = tmp_path / "target"
    target_dir.mkdir()
    calls = tmp_path / "compose-calls"
    shell_body = f"""
TARGET_DIR={shlex.quote(target_dir.as_posix())}
BEDOLAGA_LOCAL_TARGET=1
check_target_postgres_auth() {{ return 0; }}
run_compose() {{ printf '%s\n' "$*" >> {shlex.quote(calls.as_posix())}; }}
ok() {{ :; }}
fail() {{ :; }}
remove_imported_bedolaga_panel_url_override || exit 20
"""

    result = _run_installer_function(tmp_path, shell_body)

    assert result.returncode == 0, result.stdout + result.stderr
    command = calls.read_text(encoding="utf-8")
    assert "DELETE FROM app_setting_overrides" in command
    assert "PANEL_API_URL" in command


def test_bedolaga_panel_subscription_backfill_uses_inherited_dsns(tmp_path: Path):
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    target_dir = tmp_path / "target"
    target_dir.mkdir()
    calls = tmp_path / "compose-calls"
    program = tmp_path / "backfill.py"
    result = _run_installer_function(
        tmp_path,
        f"""
TARGET_DIR={shlex.quote(target_dir.as_posix())}
SOURCE_DSN=postgresql://source-user:source-secret@source/bedolaga
TARGET_DSN=postgresql://target-user:target-secret@postgres/minishop
SOURCE_SCHEMA=public
CALLS={shlex.quote(calls.as_posix())}
PROGRAM={shlex.quote(program.as_posix())}
section() {{ :; }}
ok() {{ :; }}
fail() {{ printf '%s\n' "$*" >&2; }}
run_compose() {{
    printf '%s\n' "$*" > "$CALLS"
    cat > "$PROGRAM"
}}

backfill_bedolaga_panel_subscription_ids || exit 20
""",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    command = calls.read_text(encoding="utf-8")
    assert "-e SOURCE_DSN" in command
    assert "-e TARGET_DSN" in command
    assert "source-secret" not in command
    assert "target-secret" not in command
    source = program.read_text(encoding="utf-8")
    assert "remnawave_short_uuid" in source
    assert "panel_subscription_uuid" in source
    assert "legacy_import_mappings" in source


def test_shell_installer_bedolaga_cutover_stops_old_stack_before_start_and_healthcheck(
    tmp_path: Path,
) -> None:
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    order_file = tmp_path / "cutover-order.txt"
    result = _run_installer_function(
        tmp_path,
        f"""
TARGET_DIR={shlex.quote(tmp_path.as_posix())}
ENV_PATH="$TARGET_DIR/.env"
BEDOLAGA_LOCAL_TARGET=1
ORDER_FILE={shlex.quote(order_file.as_posix())}
confirm() {{ return 0; }}
section() {{ :; }}
warn() {{ :; }}
ok() {{ :; }}
stop_bedolaga_source_stack() {{
    printf '%s\n' stop-bedolaga >> "$ORDER_FILE"
    BEDOLAGA_SOURCE_CUTOVER_STARTED=1
    BEDOLAGA_STOPPED_CONTAINER_IDS=bedolaga-app
}}
start_stack() {{ printf '%s\n' start-minishop >> "$ORDER_FILE"; }}
wait_target_runtime_healthy() {{ printf '%s\n' health-minishop >> "$ORDER_FILE"; }}
validate_stack() {{ printf '%s\n' validate-minishop >> "$ORDER_FILE"; }}
verify_bedolaga_source_disabled() {{ printf '%s\n' verify-bedolaga >> "$ORDER_FILE"; }}
verify_bedolaga_subscription_links() {{ printf '%s\n' verify-subscriptions >> "$ORDER_FILE"; }}
configure_egames_panel_webhook() {{ printf '%s\n' switch-panel-webhook >> "$ORDER_FILE"; }}

perform_bedolaga_cutover || exit 20
""",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert order_file.read_text(encoding="utf-8").splitlines() == [
        "stop-bedolaga",
        "start-minishop",
        "health-minishop",
        "validate-minishop",
        "verify-bedolaga",
        "verify-subscriptions",
        "switch-panel-webhook",
    ]


def test_shell_installer_disables_bedolaga_container_restart_policy(
    tmp_path: Path,
) -> None:
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    source_dir = tmp_path / "bedolaga"
    source_dir.mkdir()
    (source_dir / ".env").write_text("BOT_TOKEN=secret\n", encoding="utf-8")
    (source_dir / "docker-compose.yml").write_text("services: {{}}\n", encoding="utf-8")
    calls_file = tmp_path / "docker-calls.txt"

    result = _run_installer_function(
        tmp_path,
        f"""
SOURCE_ENV_PATH={shlex.quote((source_dir / ".env").as_posix())}
CALLS_FILE={shlex.quote(calls_file.as_posix())}
section() {{ :; }}
info() {{ :; }}
warn() {{ :; }}
ok() {{ :; }}
fail() {{ printf '%s\n' "$*" >&2; }}
bedolaga_autostart_preflight() {{ return 0; }}
systemctl() {{
    case "$1" in
        list-unit-files) return 0 ;;
        *) return 1 ;;
    esac
}}
compose() {{
    case "$1 ${{2:-}}" in
        'ps -aq') printf '%s\n' bedolaga-app bedolaga-db ;;
        *) return 1 ;;
    esac
}}
run_compose() {{
    case "$1 ${{2:-}}" in
        'stop ') printf '%s\n' compose-stop >> "$CALLS_FILE" ;;
        *) return 1 ;;
    esac
}}
docker() {{
    case "$1" in
        update)
            printf 'update:%s:%s\n' "$2" "$3" >> "$CALLS_FILE"
            ;;
        inspect)
            case "$3" in
                *State.Running*) printf '%s\n' false ;;
                *RestartPolicy*) printf '%s\n' no ;;
                *) return 0 ;;
            esac
            ;;
        stop)
            printf 'stop:%s\n' "$2" >> "$CALLS_FILE"
            ;;
        *) return 0 ;;
    esac
}}

stop_bedolaga_source_stack || exit 20
""",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    calls = calls_file.read_text(encoding="utf-8").splitlines()
    assert calls == [
        "compose-stop",
        "update:--restart=no:bedolaga-app",
        "update:--restart=no:bedolaga-db",
    ]


def test_shell_installer_bedolaga_cutover_with_real_docker(tmp_path: Path) -> None:
    if os.environ.get("MINISHOP_RUN_DOCKER_INTEGRATION") != "1":
        pytest.skip("set MINISHOP_RUN_DOCKER_INTEGRATION=1 to run Docker cutover test")
    if not shutil.which("sh") or not shutil.which("docker"):
        pytest.skip("sh and docker are required")
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        pytest.skip("Docker daemon is unavailable")

    source_dir = tmp_path / "bedolaga-source"
    target_dir = tmp_path / "minishop-target"
    source_dir.mkdir()
    target_dir.mkdir()
    (source_dir / ".env").write_text("BOT_TOKEN=local-only\n", encoding="utf-8")
    service = """    image: alpine:3.20
    command: [\"sh\", \"-c\", \"while true; do sleep 60; done\"]
"""
    (source_dir / "docker-compose.yml").write_text(
        "services:\n"
        f"  app:\n{service}    restart: unless-stopped\n"
        f"  db:\n{service}    restart: unless-stopped\n",
        encoding="utf-8",
    )
    (target_dir / "docker-compose.yml").write_text(
        f"""services:
  backend:
{service}    healthcheck:
      test: [\"CMD\", \"true\"]
      interval: 1s
      timeout: 1s
      retries: 10
  worker:
{service}  frontend:
{service}    healthcheck:
      test: [\"CMD\", \"true\"]
      interval: 1s
      timeout: 1s
      retries: 10
""",
        encoding="utf-8",
    )
    (target_dir / ".env").write_text("BOT_TOKEN=local-only\n", encoding="utf-8")

    subprocess.run(
        ["docker", "compose", "up", "-d"],
        cwd=source_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        result = _run_installer_function(
            tmp_path,
            f"""
SOURCE_ENV_PATH={shlex.quote((source_dir / ".env").as_posix())}
TARGET_DIR={shlex.quote(target_dir.as_posix())}
ENV_PATH="$TARGET_DIR/.env"
BEDOLAGA_LOCAL_TARGET=1
confirm() {{ return 0; }}
section() {{ :; }}
info() {{ :; }}
warn() {{ :; }}
ok() {{ :; }}
fail() {{ printf '%s\n' "$*" >&2; }}
bedolaga_autostart_preflight() {{ return 0; }}
disable_bedolaga_systemd_autostart() {{ return 0; }}
configure_egames_panel_webhook() {{ return 0; }}
validate_stack() {{ return 0; }}
start_stack() {{ (cd "$TARGET_DIR" && docker compose up -d); }}
run_compose() {{ docker compose "$@"; }}

perform_bedolaga_cutover || exit 20
for container in $(cd {shlex.quote(source_dir.as_posix())} && docker compose ps -aq); do
    [ "$(docker inspect -f '{{{{.State.Running}}}}' "$container")" = false ] || exit 21
    [ "$(docker inspect -f '{{{{.HostConfig.RestartPolicy.Name}}}}' "$container")" = no ] || exit 22
done
for service_name in backend worker frontend; do
    container=$(cd "$TARGET_DIR" && docker compose ps -q "$service_name")
    [ -n "$container" ] || exit 23
    [ "$(docker inspect -f '{{{{.State.Running}}}}' "$container")" = true ] || exit 24
done
""",
        )
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        for directory in (target_dir, source_dir):
            subprocess.run(
                ["docker", "compose", "down", "--volumes", "--remove-orphans"],
                cwd=directory,
                check=False,
                capture_output=True,
                text=True,
            )
