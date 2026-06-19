# TLS certificates

Каноничная инструкция по Nginx: [docs/getting-started/deployment.md](../../../../docs/getting-started/deployment.md#nginx).

Installer может помочь получить сертификаты для Nginx:

- проверить DNS A-records для `WEBHOOK_HOST` и `MINIAPP_HOST`;
- выпустить wildcard-сертификат через Certbot Cloudflare DNS-01;
- выпустить отдельные сертификаты через Certbot standalone HTTP-01;
- использовать уже подготовленные файлы из этой папки.

Если сертификаты готовятся вручную, кладите их в подпапки, совпадающие с
`WEBHOOK_HOST` и `MINIAPP_HOST`:

```text
ssl/
  webhooks.example.com/
    fullchain.pem
    privkey.pem
  app.example.com/
    fullchain.pem
    privkey.pem
```
