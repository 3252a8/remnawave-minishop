# Rathole private tunnel

Use this when the frontend server cannot reach the backend Web App API directly.

The browser still calls the frontend origin only:

```text
browser -> https://app.example.com/api -> frontend nginx -> rathole-server:18081 -> backend:8081
```

Only the Rathole control port, for example `2333/tcp`, is published between servers. The service port `18081` is internal to the frontend Docker network.

Setup outline:

1. Copy `rathole.server.toml.example` to `rathole.server.toml` on the frontend server.
2. Copy `rathole.client.toml.example` to `rathole.client.toml` on the backend server.
3. Use the same `token` in both files.
4. Start `frontend-server.docker-compose.yml` on the frontend server.
5. Start the normal backend stack plus `backend-server.override.yml` on the backend server.

Config check:

```bash
docker compose -f frontend-server.docker-compose.yml config
docker compose -f backend-server.override.yml config
```
