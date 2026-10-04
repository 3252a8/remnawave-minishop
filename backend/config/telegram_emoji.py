"""Telegram custom emoji identifiers shared by runtime and static generators."""

import re

CUSTOM_EMOJI_ID_RE = re.compile(r"^[1-9][0-9]{0,19}$")
