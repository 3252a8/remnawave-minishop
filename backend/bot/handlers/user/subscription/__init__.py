from aiogram import Router

from . import core, payments

router = Router(name="user_subscription_router")

# Include sub-routers
router.include_router(core.router)
router.include_router(payments.router)

# Re-export commonly used entrypoints for backward compatibility
from .core import (  # noqa: E402,F401
    display_subscription_options,
    my_devices_command_handler,
    my_subscription_command_handler,
)
