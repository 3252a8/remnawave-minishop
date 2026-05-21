from aiogram import Router

from bot.payment_providers import iter_unique_provider_routers

from .payments_subscription import router as subscription_selection_router

router = Router(name="user_subscription_payments_router")

router.include_router(subscription_selection_router)
for provider_router in iter_unique_provider_routers():
    router.include_router(provider_router)

__all__ = ["router"]
