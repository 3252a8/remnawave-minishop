# TLS-сертификаты для Nginx

Положите сюда сертификаты для доменов из `.env`.

Пример структуры:

```text
ssl/
  webhooks.example.com/
    fullchain.pem
    privkey.pem
  app.example.com/
    fullchain.pem
    privkey.pem
```

Если используете wildcard-сертификат, можно положить одинаковые `fullchain.pem` и `privkey.pem` в обе папки.

