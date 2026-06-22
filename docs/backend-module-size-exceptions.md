# Backend Module Size Exceptions

The API refactor F5 cleanup keeps these modules intentionally colocated until their tests
can be migrated away from module-level monkeypatch targets or their provider registration
surfaces can be split without changing import paths:

- `backend/bot/payment_providers/yookassa.py`: webhook, callback, and recurring helpers
  are patched through the legacy module in provider and HWID tests; split into route,
  webhook, success, and payment-method modules together with compatibility shims.
- `backend/bot/payment_providers/wata.py`: webhook tests patch provider module DAL and
  service behavior; split config/core/service after those tests target stable helper
  modules.
- `backend/bot/payment_providers/paykilla.py`: security and payment-method tests import
  private signing/minimum helpers from the provider module; split core/service once those
  helpers have an explicit compatibility module.
- `backend/bot/app/web/admin_api_impl/users.py`: admin API tests patch auth, DAL, and
  serializer helpers through `admin_api_impl.users`; split list/detail/mutation routes
  after those patch targets move to shared dependency modules.
- `backend/bot/handlers/admin/user_management.py`: admin bot actions share one router and
  callback-state flow; split by action group after route-level tests patch handler entry
  points instead of the module namespace.
- `backend/bot/services/subscription_service_impl/lifecycle.py`: tests patch DAL objects
  through `subscription_service_impl.lifecycle`; move lifecycle phases to helper mixins
  only together with patch-target updates.
- `backend/bot/app/web/webapp/auth.py`: account-linking and referral tests patch
  `webapp.auth.user_dal` and related helpers; split OAuth, email auth, and referral
  flows after those tests target a shared dependency module.
