# Bot utilities package

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from aiogram import Bot, types

if TYPE_CHECKING:
    from bot.utils.message_queue import MessageQueueManager


@dataclass
class MessageContent:
    """Container for message content information"""

    content_type: str
    file_id: str | None = None
    text: str | None = None


# Supported parameter dictionaries for each message type
SUPPORTED_PARAMS = {
    "text": {
        "parse_mode",
        "entities",
        "disable_web_page_preview",
        "disable_notification",
        "protect_content",
        "reply_markup",
        "reply_to_message_id",
        "allow_sending_without_reply",
        "message_thread_id",
    },
    "photo": {
        "caption",
        "parse_mode",
        "caption_entities",
        "disable_notification",
        "protect_content",
        "reply_markup",
        "reply_to_message_id",
        "allow_sending_without_reply",
        "message_thread_id",
        "has_spoiler",
    },
    "video": {
        "duration",
        "width",
        "height",
        "thumbnail",
        "caption",
        "parse_mode",
        "caption_entities",
        "supports_streaming",
        "disable_notification",
        "protect_content",
        "reply_markup",
        "reply_to_message_id",
        "allow_sending_without_reply",
        "message_thread_id",
        "has_spoiler",
    },
    "animation": {
        "duration",
        "width",
        "height",
        "thumbnail",
        "caption",
        "parse_mode",
        "caption_entities",
        "disable_notification",
        "protect_content",
        "reply_markup",
        "reply_to_message_id",
        "allow_sending_without_reply",
        "message_thread_id",
        "has_spoiler",
    },
    "document": {
        "thumbnail",
        "caption",
        "parse_mode",
        "caption_entities",
        "disable_content_type_detection",
        "disable_notification",
        "protect_content",
        "reply_markup",
        "reply_to_message_id",
        "allow_sending_without_reply",
        "message_thread_id",
    },
    "audio": {
        "caption",
        "parse_mode",
        "caption_entities",
        "duration",
        "performer",
        "title",
        "thumbnail",
        "disable_notification",
        "protect_content",
        "reply_markup",
        "reply_to_message_id",
        "allow_sending_without_reply",
        "message_thread_id",
    },
    "voice": {
        "caption",
        "parse_mode",
        "caption_entities",
        "duration",
        "disable_notification",
        "protect_content",
        "reply_markup",
        "reply_to_message_id",
        "allow_sending_without_reply",
        "message_thread_id",
    },
    "sticker": {
        "disable_notification",
        "protect_content",
        "reply_markup",
        "reply_to_message_id",
        "allow_sending_without_reply",
        "message_thread_id",
    },
    "video_note": {
        "duration",
        "length",
        "thumbnail",
        "disable_notification",
        "protect_content",
        "reply_markup",
        "reply_to_message_id",
        "allow_sending_without_reply",
        "message_thread_id",
    },
}


def filter_kwargs(content_type: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Filter kwargs to parameters supported by this message type"""
    supported = SUPPORTED_PARAMS.get(content_type, set())
    return {k: v for k, v in kwargs.items() if k in supported}


def get_message_content(message: types.Message) -> MessageContent:
    """# noqa: E501
    Determine the message content type and return its data.
    Use match/case instead of long if/elif chains.
    """
    text = (message.text or message.caption or "").strip()

    # Check for media content
    media_content = None
    if message.photo:
        media_content = ("photo", message.photo[-1].file_id)
    elif message.video:
        media_content = ("video", message.video.file_id)
    elif message.animation:
        media_content = ("animation", message.animation.file_id)
    elif message.document:
        media_content = ("document", message.document.file_id)
    elif message.audio:
        media_content = ("audio", message.audio.file_id)
    elif message.voice:
        media_content = ("voice", message.voice.file_id)
    elif message.sticker:
        media_content = ("sticker", message.sticker.file_id)
    elif message.video_note:
        media_content = ("video_note", message.video_note.file_id)

    # Use match/case to determine the content type
    match media_content:
        case (content_type, file_id):
            return MessageContent(content_type=content_type, file_id=file_id, text=text)
        case None:
            return MessageContent(content_type="text", text=text)
        case _:
            return MessageContent(content_type="text", text=text)


async def send_message_by_type(
    bot: Bot, chat_id: int, content: MessageContent, **kwargs: Any
) -> None:
    """
    Send a message of the specified type.
    Use match/case instead of long if/elif chains.
    Automatically filter unsupported parameters.
    """
    # Filter kwargs for this message type
    filtered_kwargs = filter_kwargs(content.content_type, kwargs)

    match content.content_type:
        case "text":
            await bot.send_message(chat_id=chat_id, text=cast(str, content.text), **filtered_kwargs)
        case "photo":
            await bot.send_photo(
                chat_id=chat_id,
                photo=cast(str, content.file_id),
                caption=content.text or None,
                **filtered_kwargs,
            )
        case "video":
            await bot.send_video(
                chat_id=chat_id,
                video=cast(str, content.file_id),
                caption=content.text or None,
                **filtered_kwargs,
            )
        case "animation":
            await bot.send_animation(
                chat_id=chat_id,
                animation=cast(str, content.file_id),
                caption=content.text or None,
                **filtered_kwargs,
            )
        case "document":
            await bot.send_document(
                chat_id=chat_id,
                document=cast(str, content.file_id),
                caption=content.text or None,
                **filtered_kwargs,
            )
        case "audio":
            await bot.send_audio(
                chat_id=chat_id,
                audio=cast(str, content.file_id),
                caption=content.text or None,
                **filtered_kwargs,
            )
        case "voice":
            await bot.send_voice(
                chat_id=chat_id,
                voice=cast(str, content.file_id),
                caption=content.text or None,
                **filtered_kwargs,
            )
        case "sticker":
            await bot.send_sticker(
                chat_id=chat_id, sticker=cast(str, content.file_id), **filtered_kwargs
            )
        case "video_note":
            await bot.send_video_note(
                chat_id=chat_id, video_note=cast(str, content.file_id), **filtered_kwargs
            )
        case _:
            # Fallback for unknown types: send as text
            text_kwargs = filter_kwargs("text", kwargs)
            await bot.send_message(
                chat_id=chat_id, text=content.text or "Unknown content type", **text_kwargs
            )


async def send_message_via_queue(
    queue_manager: "MessageQueueManager",
    uid: int,
    content: MessageContent,
    **kwargs: Any,
) -> None:
    """
    Send a message through the queue according to its content type.
    Use match/case instead of long if/elif chains.
    Automatically filter unsupported parameters.
    """
    # Filter kwargs for this message type
    filtered_kwargs = filter_kwargs(content.content_type, kwargs)

    match content.content_type:
        case "text":
            await queue_manager.send_message(chat_id=uid, text=content.text, **filtered_kwargs)
        case "photo":
            await queue_manager.send_photo(
                chat_id=uid, photo=content.file_id, caption=content.text or None, **filtered_kwargs
            )
        case "video":
            await queue_manager.send_video(
                chat_id=uid, video=content.file_id, caption=content.text or None, **filtered_kwargs
            )
        case "animation":
            await queue_manager.send_animation(
                chat_id=uid,
                animation=content.file_id,
                caption=content.text or None,
                **filtered_kwargs,
            )
        case "document":
            await queue_manager.send_document(
                chat_id=uid,
                document=content.file_id,
                caption=content.text or None,
                **filtered_kwargs,
            )
        case "audio":
            await queue_manager.send_audio(
                chat_id=uid, audio=content.file_id, caption=content.text or None, **filtered_kwargs
            )
        case "voice":
            await queue_manager.send_voice(
                chat_id=uid, voice=content.file_id, caption=content.text or None, **filtered_kwargs
            )
        case "sticker":
            await queue_manager.send_sticker(
                chat_id=uid, sticker=content.file_id, **filtered_kwargs
            )
        case "video_note":
            await queue_manager.send_video_note(
                chat_id=uid, video_note=content.file_id, **filtered_kwargs
            )
        case _:
            # Fallback for unknown types: send as text
            text_kwargs = filter_kwargs("text", kwargs)
            await queue_manager.send_message(
                chat_id=uid, text=content.text or "Unknown content type", **text_kwargs
            )


async def send_direct_message(
    bot: Bot,
    chat_id: int,
    content: MessageContent,
    extra_text: str = "",
    **kwargs: Any,
) -> None:
    """
    Send a direct message with additional handling for sticker and video_note.
    For these media types, send a separate text message
    because they do not support captions.
    Automatically filter unsupported parameters.
    """
    match content.content_type:
        case "sticker":
            # Send the sticker with filtered parameters
            sticker_kwargs = filter_kwargs("sticker", kwargs)
            await bot.send_sticker(
                chat_id=chat_id, sticker=cast(str, content.file_id), **sticker_kwargs
            )
            # Send caption text separately when present
            if content.text or extra_text:
                text_to_send = (content.text + extra_text) if content.text else extra_text
                text_kwargs = filter_kwargs("text", kwargs)
                await bot.send_message(chat_id, text_to_send, **text_kwargs)
        case "video_note":
            # Send the video note with filtered parameters
            video_note_kwargs = filter_kwargs("video_note", kwargs)
            await bot.send_video_note(
                chat_id=chat_id, video_note=cast(str, content.file_id), **video_note_kwargs
            )
            # Send caption text separately when present
            if content.text or extra_text:
                text_to_send = (content.text + extra_text) if content.text else extra_text
                text_kwargs = filter_kwargs("text", kwargs)
                await bot.send_message(chat_id, text_to_send, **text_kwargs)
        case "text":
            # Combine text with extra_text
            final_text = (content.text + extra_text) if content.text else extra_text
            text_kwargs = filter_kwargs("text", kwargs)
            await bot.send_message(chat_id=chat_id, text=final_text, **text_kwargs)
        case _:
            # Use caption for all other media types
            final_caption = (content.text + extra_text) if content.text else None
            await send_message_by_type(
                bot,
                chat_id,
                MessageContent(content.content_type, content.file_id, final_caption),
                **kwargs,
            )
