"""JSON token encoding that is safe inside an HTML script element."""

from __future__ import annotations

import json


def dumps_script_safe(value: object, *, indent: int | None = None) -> bytes:
    token = json.dumps(value, ensure_ascii=False, indent=indent)
    token = _escape_script_surface(token)
    return token.encode("utf-8")


def dumps_script_safe_string(value: str) -> bytes:
    """Return a JSON string token that cannot terminate the containing script."""

    token = json.dumps(value, ensure_ascii=False)
    token = _escape_script_surface(token)
    return token.encode("utf-8")


def _escape_script_surface(token: str) -> str:
    return token.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
