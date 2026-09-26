"""Support connector API v1 for external service integrations.

Keep these exports stable while capability ``support_connector`` is version 1.
Internal implementation paths may change without requiring a new plugin ZIP.
"""

from bot.app.web.message_image_responses import message_image_response as message_image_response
from bot.app.web.support_schemas import AdminSupportMessageOut as AdminSupportMessageOut
from bot.app.web.support_schemas import AdminSupportUserOut as AdminSupportUserOut
from bot.app.web.support_schemas import SupportTicketOut as SupportTicketOut
from bot.plugins.capabilities import CORE_PLUGIN_CAPABILITIES
from bot.services.message_image_service import MessageImageError as MessageImageError
from bot.services.message_image_service import UploadedMessageImage as UploadedMessageImage
from bot.services.message_image_service import load_message_image as load_message_image
from bot.services.message_image_service import prepare_message_image as prepare_message_image
from bot.services.support_message_body import SupportBodyError as SupportBodyError
from bot.services.support_service import SupportService as SupportService
from bot.services.support_service import TicketNotFound as TicketNotFound
from db.dal import support_dal as support_dal
from db.dal import user_dal as user_dal

API_VERSION = CORE_PLUGIN_CAPABILITIES["support_connector"]
