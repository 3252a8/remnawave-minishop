"""Support connector API v3 for external service integrations.

Version 3 adds diagnostic facts and optional message buttons; earlier exports remain supported.
Internal implementation paths may change without requiring a new plugin ZIP.
"""

from bot.app.web.message_image_responses import message_image_response as message_image_response
from bot.app.web.support_schemas import AdminSupportMessageOut as AdminSupportMessageOut
from bot.app.web.support_schemas import AdminSupportUserOut as AdminSupportUserOut
from bot.app.web.support_schemas import SupportTicketOut as SupportTicketOut
from bot.plugins.capabilities import CORE_PLUGIN_CAPABILITIES
from bot.services.message_composition import MessageButtonInput as MessageButtonInput
from bot.services.message_image_service import MessageImageError as MessageImageError
from bot.services.message_image_service import UploadedMessageImage as UploadedMessageImage
from bot.services.message_image_service import load_message_image as load_message_image
from bot.services.message_image_service import prepare_message_image as prepare_message_image
from bot.services.support_connector_contracts import (
    SupportConnectorConflict as SupportConnectorConflict,
)
from bot.services.support_connector_contracts import SupportConnectorReply as SupportConnectorReply
from bot.services.support_connector_contracts import SupportContextMessage as SupportContextMessage
from bot.services.support_connector_contracts import SupportTicketContext as SupportTicketContext
from bot.services.support_message_body import SupportBodyError as SupportBodyError
from bot.services.support_service import SupportService as SupportService
from bot.services.support_service import TicketNotFound as TicketNotFound
from db.dal import support_dal as support_dal
from db.dal import user_dal as user_dal
from db.support_contracts import SupportTicketChange as SupportTicketChange

API_VERSION = CORE_PLUGIN_CAPABILITIES["support_connector"]
