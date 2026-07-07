# Split protected upstream

Use this when the Mini App frontend runs on a separate server, but browser requests must still stay same-origin:

```text
browser -> https://app.example.com/api -> frontend nginx -> protected backend upstream
```

`WEBAPP_API_BASE_URL` remains `/api`. Configure only the frontend server's `WEBAPP_BACKEND_UPSTREAM`.

Backend routes keep two planes:

- `backend:8080` is the public webhook plane for Telegram, payment providers and Remnawave Panel.
- `backend:8081` is the private Web App API plane for `/api`, `/auth`, `/open-app` and Web App assets.

For one-backend-domain mode, route webhook paths to `backend:8080` without `MINISHOP_EDGE_TOKEN`, and route `/api/*`, `/auth/*`, `/open-app`, logo/theme/favicon paths to `backend:8081` with `X-Minishop-Edge-Token`.

For private IP/VPN mode, set `WEBAPP_BACKEND_UPSTREAM=http://10.0.0.5:8081` and restrict `8081` with firewall/VPN/allowlist.

Config checks:

```bash
docker compose -f frontend.docker-compose.yml config
docker compose -f backend.docker-compose.yml config
```
