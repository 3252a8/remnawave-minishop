from __future__ import annotations

from bot.app.web.route_contracts import (
    BOOLEAN_SCHEMA,
    INTEGER_SCHEMA,
    NULLABLE_INTEGER_SCHEMA,
    NULLABLE_STRING_SCHEMA,
    RouteContract,
    ok_envelope_with,
    schema_ref,
)

from .contract_schemas import user_contract
from .devices import WebAppDeviceOut
from .payloads import WebAppDeviceDisconnectPayload, WebAppDeviceRenamePayload

DEVICES_ROUTE_CONTRACTS: dict[str, RouteContract] = {
    "devices_route": user_contract(
        models=(WebAppDeviceOut,),
        response_schema=ok_envelope_with(
            {
                "enabled": BOOLEAN_SCHEMA,
                "subscription_active": BOOLEAN_SCHEMA,
                "current_devices": INTEGER_SCHEMA,
                "max_devices": NULLABLE_INTEGER_SCHEMA,
                "max_devices_label": NULLABLE_STRING_SCHEMA,
                "devices": {"type": "array", "items": schema_ref(WebAppDeviceOut)},
            },
            required=[],
        ),
    ),
    "disconnect_device_route": user_contract(
        request_model=WebAppDeviceDisconnectPayload,
        response_schema=ok_envelope_with(),
    ),
    "rename_device_route": user_contract(
        request_model=WebAppDeviceRenamePayload,
        models=(WebAppDeviceOut,),
        response_schema=ok_envelope_with({"device": schema_ref(WebAppDeviceOut)}),
    ),
}
