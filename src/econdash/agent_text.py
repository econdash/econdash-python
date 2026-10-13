"""Sentences and compact formatters shared by the agent integrations.

LlamaIndex imports these. The wording is the LangChain wording, so a model sees
the same description of the four operations in both frameworks. The search-tool
name is the only piece that changes, because each framework names that tool.
"""

from __future__ import annotations

import re
from typing import Any

from .errors import (
    EconDashAuthError,
    EconDashError,
    EconDashNotFound,
    EconDashPaymentRequired,
    EconDashRateLimitError,
)
from .models import Indicator, Series

_ISO = "Use a 3-letter ISO3 code such as USA, DEU or JPN, not a country name."

# Block the licences and sources the site refuses to embed. An empty licence is
# not a ban: unknown terms stay loadable, an explicit "no redistribution" does not.
_BLOCK_LICENSES = (
    "no redistribution",
    "не распространять",
    "third-party copyright",
    "yahoo terms",
)
_BLOCK_SOURCES = (
    "yahoo finance",
    "case-shiller",
    "ice / trading economics",
)

PAYMENT_HINT = (
    "Payment required. No figures were returned and nothing was charged. "
    "The free trial is 10 countries (USA, CHN, DEU, JPN, GBR, FRA, IND, BRA, RUS, KOR), "
    "50 indicators, 300 requests per day and 30 per minute. "
    "Set ECONDASH_API_KEY for a subscription, or pass a wallet and max_usd_per_call "
    "to the EconDash client to pay per call with x402 or MPP. "
    "A wallet pays only when it is set and the price is within the cap. "
    "Do not guess the missing value."
)


def tool_descriptions(search_tool: str = "econdash_search_indicators") -> dict[str, str]:
    """Descriptions of the four operations. `search_tool` is the name the model must call."""
    trial = (
        "Free trial only: 10 countries (USA, CHN, DEU, JPN, GBR, FRA, IND, BRA, RUS, KOR) "
        "and 50 indicators, 300 requests/day. Anything else comes back as a payment message, "
        f"not as numbers. Find the slug with {search_tool} first."
    )
    return {
        "search_indicators": (
            "Search the EconDash indicator catalog. "
            "Returns slug, name, unit, source and frequency. "
            "Call this before a series. The catalog is metadata; it has no numbers. " + trial
        ),
        "get_series": (
            "Load one indicator for one country: unit, when the data last changed, a citation "
            "with the econdash.org chart link, and the last 20 observations. " + trial
        ),
        "get_metadata": (
            "Describe one indicator: source, licence, freshness and some countries. "
            "Does not return the time series. " + trial
        ),
        "compare_countries": (
            "Latest value of one indicator for a few countries, each requested on its own. "
            "A country outside the trial is a payment message on that line; the other countries "
            "are not unlocked by it. " + trial
        ),
    }


def redistribution_allowed(indicator: Indicator) -> bool:
    """False when the source licence forbids putting the series into a document."""
    license_name = (indicator.license_name or "").lower()
    source = (indicator.source or "").lower()
    if any(part in license_name for part in _BLOCK_LICENSES):
        return False
    return not any(part in source for part in _BLOCK_SOURCES)


def country_error(code: str) -> str | None:
    if len(code) == 3 and code.isalpha():
        return None
    return f"Invalid country code {code!r}. {_ISO}"


def explain(exc: Exception, *, search_tool: str = "econdash_search_indicators") -> str:
    if isinstance(exc, EconDashPaymentRequired):
        return PAYMENT_HINT
    if isinstance(exc, EconDashRateLimitError):
        wait = f" Retry after {exc.retry_after} seconds." if exc.retry_after else ""
        return f"Rate limit reached.{wait} No data in this call."
    if isinstance(exc, EconDashNotFound):
        return f"Not found ({exc}). Search with {search_tool}. {_ISO}"
    if isinstance(exc, EconDashAuthError):
        return f"API key was rejected ({exc}). Check ECONDASH_API_KEY."
    if isinstance(exc, EconDashError):
        return f"EconDash error: {exc}"
    return f"EconDash error: {exc}"


def search_text(rows: list[Indicator]) -> str:
    if not rows:
        return "No indicators matched. Try a shorter query such as gdp or inflation."
    lines = ["slug | name | unit | source | frequency"]
    for ind in rows:
        lines.append(
            " | ".join(
                [
                    ind.slug or ind.code,
                    ind.name,
                    ind.unit or "",
                    ind.source or "",
                    ind.frequency or "",
                ]
            )
        )
    return "\n".join(lines)


def series_text(series: Series, *, slug: str, full: bool) -> str:
    points = series.data
    shown = points if full else points[-20:]
    name = series.indicator_name_en or series.indicator_name_ru
    country = shown[-1].country if shown else ""
    country_name = shown[-1].country_name if shown else country
    last = shown[-1] if shown else None
    chart = f"https://econdash.org/chart/{slug}/{country}" if slug and country else ""
    head = [
        f"{name} — {country_name or country}",
        f"unit: {series.unit or 'n/a'}",
        f"frequency: {series.frequency or 'n/a'}",
        f"data_changed_at: {series.data_changed_at or 'n/a'}",
        f"points: {len(points)} total, showing {len(shown)}",
    ]
    if last is not None:
        head.append(
            f"citation: {country_name or country} {name} was {last.value} {series.unit or ''} "
            f"on {last.date.isoformat()}. {chart}".rstrip()
        )
    body = [f"{p.date.isoformat()} {p.value}" for p in shown]
    if not full and len(points) > len(shown):
        body.append("Set full=true only when the user asked for the whole history.")
    return "\n".join(head + body)


def metadata_text(ind: Indicator, countries: list[str] | None, country_note: str) -> str:
    sample = ", ".join(countries[:12]) if countries else "n/a"
    extra = f" ({len(countries)} countries)" if countries else ""
    lines = [
        f"{ind.slug or ind.code}: {ind.name}",
        f"code: {ind.code}",
        f"description: {ind.description or 'n/a'}",
        f"source: {ind.source or 'n/a'}",
        f"source_url: {ind.source_url or 'n/a'}",
        f"license: {ind.license_name or 'n/a'} {ind.license_url or ''}".rstrip(),
        f"attribution: {ind.attribution_text or 'n/a'}",
        f"frequency: {ind.frequency or 'n/a'}",
        f"data_changed_at: {ind.data_changed_at or 'n/a'}",
        f"data_checked_at: {ind.data_checked_at or 'n/a'}",
        f"observations: {ind.first_observation or '?'} .. {ind.last_observation or '?'}",
        f"chart: {ind.url or 'n/a'}",
        f"countries{extra}: {sample}",
    ]
    if country_note:
        lines.append(country_note)
    return "\n".join(lines)


def document_text(ind: Indicator, series: Series) -> str:
    """Compact series summary plus the source fields a RAG chunk is allowed to carry."""
    slug = ind.slug or ""
    tail = "\n".join(
        [
            f"source: {ind.source or 'n/a'}",
            f"source_url: {ind.source_url or 'n/a'}",
            f"license: {ind.license_name or 'n/a'}",
        ]
    )
    return series_text(series, slug=slug, full=False) + "\n" + tail


def _text(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _iso(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


def _isos(value: Any) -> list[str]:
    if isinstance(value, str):
        value = re.split(r"[\s,;]+", value)
    if isinstance(value, (list, tuple)):
        return [
            str(_iso(item)) for item in value if not (isinstance(item, str) and not item.strip())
        ]
    return []


def _limit(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 10
    return min(max(number, 1), 20)


def _flag(value: Any) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _when(value: Any) -> str | int | None:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        return value.strip() or None
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _year(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
