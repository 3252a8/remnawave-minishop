# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405


async def admin_broadcast_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    payload = await _read_json(request)
    text = str(payload.get("text") or "").strip()
    target = str(payload.get("target") or "all").strip().lower()
    if not text:
        return _error(400, "empty_text")
    if target not in {"all", "active", "inactive", "expired"}:
        target = "all"

    queue_manager = get_queue_manager()
    if not queue_manager:
        return _error(503, "queue_unavailable")

    async_session_factory: sessionmaker = request.app["async_session_factory"]
    async with async_session_factory() as session:
        if target == "active":
            user_ids = await user_dal.get_user_ids_with_active_subscription(session)
        elif target == "inactive":
            user_ids = await user_dal.get_user_ids_without_active_subscription(session)
        elif target == "expired":
            user_ids = await user_dal.get_user_ids_with_expired_subscription(session)
        else:
            user_ids = await user_dal.get_all_active_user_ids_for_broadcast(session)

        sent = 0
        failed = 0
        for uid in user_ids:
            try:
                await send_message_via_queue(
                    queue_manager,
                    int(uid),
                    MessageContent(content_type="text", text=text),
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                sent += 1
            except Exception as exc:
                failed += 1
                logger.debug("Broadcast queue failed for %s: %s", uid, exc)

        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_broadcast_webapp",
                "content": f"target={target} sent={sent} failed={failed} text={text[:120]}",
                "is_admin_event": True,
            },
        )

    return _ok({"queued": sent, "failed": failed, "target": target})
