def auto_renew_user_lock_name(user_id: int) -> str:
    """Return the shared lock protecting one customer's renewal consent and charge."""

    return f"auto-renew-user:{int(user_id)}"
