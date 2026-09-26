"""HTTP schemas for authenticated extension discovery and external orders."""

from pydantic import ConfigDict, Field, JsonValue

from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.plugins.extensions.contracts import ProductQuote


class ExtensionViewOut(HttpResponseModel):
    id: str
    view: str
    label: str
    i18nKey: str = ""
    order: int = 100
    target: str = "page"
    icon: str = "star"
    navigation: str = "primary"
    parent: str = ""
    placement: str = "after"


class ExtensionPluginOut(HttpResponseModel):
    id: str
    digest: str
    entry: str
    styles: list[str] = Field(default_factory=list)
    views: list[ExtensionViewOut] = Field(default_factory=list)


class ExtensionRuntimeOut(HttpResponseModel):
    generation: int
    plugins: list[ExtensionPluginOut]


class ExtensionOrderCreate(HttpBodyModel):
    model_config = ConfigDict(extra="forbid")
    product: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}:[a-z][a-z0-9_-]{0,63}$")
    options: dict[str, JsonValue] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=128)


class ExtensionCheckout(HttpBodyModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    method: str = Field(min_length=1, max_length=64)
    payer_email: str | None = Field(default=None, max_length=254)
    payer_phone: str | None = Field(default=None, max_length=32)


class ExtensionOrderOut(HttpResponseModel):
    id: str
    product: str
    quote: ProductQuote
    payment_id: int | None
    payment_state: str
    fulfillment_state: str
    data: dict[str, JsonValue]


class ExtensionOrdersOut(HttpResponseModel):
    orders: list[ExtensionOrderOut]


class ExtensionCheckoutOut(HttpResponseModel):
    order: ExtensionOrderOut
    payment: dict[str, JsonValue] = Field(default_factory=dict)


class ExtensionPaymentMethodOut(HttpResponseModel):
    id: str
    label: str
    label_key: str = ""


class ExtensionPaymentMethodsOut(HttpResponseModel):
    methods: list[ExtensionPaymentMethodOut]
