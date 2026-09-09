from sqlalchemy import func, or_, true
from sqlalchemy.sql.elements import ColumnElement

from db.models import Payment, User


def payment_user_search(search: str) -> ColumnElement[bool]:
    """Search the payment owner, including web-only and deleted accounts."""
    value = search.strip().lstrip("@#")
    if not value:
        return true()
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    full_name = func.trim(
        func.coalesce(User.first_name, "") + " " + func.coalesce(User.last_name, "")
    )
    conditions = [
        User.username.ilike(pattern, escape="\\"),
        User.email.ilike(pattern, escape="\\"),
        full_name.ilike(pattern, escape="\\"),
    ]
    if value.removeprefix("-").isdecimal() and len(value) <= 20:
        user_id = int(value)
        if -(2**63) <= user_id < 2**63:
            conditions.extend((Payment.user_id == user_id, User.telegram_id == user_id))
    return or_(*conditions)
