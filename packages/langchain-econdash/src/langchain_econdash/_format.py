"""Turn API errors and series into short text a model can read."""

from __future__ import annotations

from econdash import (
    EconDashAuthError,
    EconDashError,
    EconDashNotFound,
    EconDashPaymentRequired,
    EconDashRateLimitError,
    Indicator,
    Series,
)

PAYMENT_HINT = (
    "Payment required. No figures were returned and nothing was charged. "
    "The free trial is 10 countries (USA, CHN, DEU, JPN, GBR, FRA, IND, BRA, RUS, KOR), "
    "50 indicators, 300 requests per day and 30 per minute. "
    "Set ECONDASH_API_KEY for a subscription, or pass a wallet and max_usd_per_call "
    "to EconDashToolkit to pay per call with x402 or MPP. "
    "A wallet pays only when it is set and the price is within the cap."
)

_ISO = "Use a 3-letter ISO3 code such as USA, DEU or JPN, not a country name."


def country_error(code: str) -> str | None:
    if len(code) == 3 and code.isalpha():
        return None
    return f"Invalid country code {code!r}. {_ISO}"


def explain(exc: Exception) -> str:
    if isinstance(exc, EconDashPaymentRequired):
        return PAYMENT_HINT
    if isinstance(exc, EconDashRateLimitError):
        wait = f" Retry after {exc.retry_after} seconds." if exc.retry_after else ""
        return f"Rate limit reached.{wait} No data in this call."
    if isinstance(exc, EconDashNotFound):
        return f"Not found ({exc}). Search with econdash_search_indicators. {_ISO}"
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
