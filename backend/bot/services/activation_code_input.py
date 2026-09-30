"""Portable issuance format and bounded compatibility input for stored codes."""

import re
from typing import Annotated

from pydantic import AfterValidator, StringConstraints

CODE_MAX_LENGTH = 100


def validate_code_input(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid_activation_code")
    if (
        not value.strip()
        or len(value) > CODE_MAX_LENGTH
        or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value)
    ):
        raise ValueError("invalid_activation_code")
    return value.strip()


def validate_issued_code(value: str) -> str:
    code = validate_code_input(value)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", code):
        raise ValueError("invalid_activation_code")
    return code.upper()


ActivationCodeString = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=CODE_MAX_LENGTH),
    AfterValidator(validate_code_input),
]
IssuedCodeString = Annotated[ActivationCodeString, AfterValidator(validate_issued_code)]
