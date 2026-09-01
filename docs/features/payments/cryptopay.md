# CryptoPay
CryptoPay используется для криптовалютных платежей через отдельный токен и сеть Crypto Bot API.

## Настройка

1. Включите `CRYPTOPAY_ENABLED`.
2. Укажите `CRYPTOPAY_TOKEN`.
3. Выберите `CRYPTOPAY_NETWORK`: `mainnet` или `testnet`.
4. Задайте `CRYPTOPAY_CURRENCY_TYPE`: `fiat` или `crypto`.
5. Проверьте `CRYPTOPAY_ASSET`, например `RUB`, `USDT` или `BTC`.
6. Скопируйте URL вебхука из админ-панели и укажите его в CryptoPay.

## Проверка

- Testnet-токен должен использоваться только с `testnet`.
- Mainnet-токен должен использоваться только с `mainnet`.
- Если сумма или asset выглядят неверно, проверьте сочетание `CRYPTOPAY_CURRENCY_TYPE` и `CRYPTOPAY_ASSET`.

## Справочник

- [CryptoPay](../../configuration/env-vars.md#cryptopay)
