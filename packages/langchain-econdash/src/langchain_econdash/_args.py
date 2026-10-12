"""Argument types that accept what models actually send.

Models send a year as a number or a string, a country list as "USA, DEU", null for a
default, and limits out of range. Each type normalises that before validation, so the
tool gets clean values instead of the agent getting a validation error.
"""

from __future__ import annotations

import re
from typing import Annotated, Any

from pydantic import BeforeValidator


def _text(v: Any) -> Any:
    return v.strip() if isinstance(v, str) else v


def _iso(v: Any) -> Any:
    return v.strip().upper() if isinstance(v, str) else v


def _isos(v: Any) -> Any:
    if isinstance(v, str):
        v = re.split(r"[\s,;]+", v)
    if isinstance(v, (list, tuple)):
        return [_iso(x) for x in v if not (isinstance(x, str) and not x.strip())]
    return v


def _limit(v: Any) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 10
    return min(max(n, 1), 20)


def _flag(v: Any) -> Any:
    return False if v is None or v == "" else v


def _when(v: Any) -> Any:
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        return v.strip() or None
    return v


def _year(v: Any) -> Any:
    if v is None or (isinstance(v, int) and not isinstance(v, bool)):
        return v
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None  # "latest", "" and the like mean the latest point


Text = Annotated[str, BeforeValidator(_text)]
Iso3 = Annotated[str, BeforeValidator(_iso)]
Iso3List = Annotated[list[str], BeforeValidator(_isos)]
Limit = Annotated[int, BeforeValidator(_limit)]
Flag = Annotated[bool, BeforeValidator(_flag)]
When = Annotated[str | int | None, BeforeValidator(_when)]
Year = Annotated[int | None, BeforeValidator(_year)]
