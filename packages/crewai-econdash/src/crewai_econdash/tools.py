"""Three CrewAI tools over the econdash client.

>>> from econdash import EconDash
>>> from crewai_econdash import EconDashCompareTool, EconDashSearchTool, EconDashSeriesTool
>>> client = EconDash()  # free trial, or ECONDASH_API_KEY from env
>>> tools = [EconDashSearchTool(client=client), EconDashSeriesTool(client=client),
...          EconDashCompareTool(client=client)]

The tools use the client's access as is: no key and no wallet means the free trial.
Errors, including 402 and 429, come back as text for the model, never as figures.
"""

from __future__ import annotations

from typing import Any

from crewai.tools import BaseTool, EnvVar
from pydantic import BaseModel, Field

from crewai_econdash._args import Flag, Iso3, Iso3List, Limit, Text, When, Year
from econdash import (
    EconDash,
    EconDashAuthError,
    EconDashError,
    EconDashNotFound,
    EconDashPaymentRequired,
    EconDashRateLimitError,
    Indicator,
    Series,
)

__all__ = ["EconDashCompareTool", "EconDashSearchTool", "EconDashSeriesTool"]

_TRIAL = (
    "Free trial only: 10 countries (USA, CHN, DEU, JPN, GBR, FRA, IND, BRA, RUS, KOR), "
    "50 indicators, 300 requests/day. Anything else comes back as a payment message, "
    "not as numbers. Find the slug with econdash_search_indicators first."
)
_PAYMENT = (
    "Payment required. No figures were returned and nothing was charged. "
    "The free trial is 10 countries (USA, CHN, DEU, JPN, GBR, FRA, IND, BRA, RUS, KOR), "
    "50 indicators, 300 requests per day and 30 per minute. "
    "Set ECONDASH_API_KEY for a subscription, or give the tools an EconDash client "
    "with a wallet and max_usd_per_call to pay per call with x402 or MPP. "
    "Do not guess the missing value."
)
_ISO = "Use a 3-letter ISO3 code such as USA, DEU or JPN, not a country name."
_ENV = [
    EnvVar(
        name="ECONDASH_API_KEY",
        description="EconDash subscription key. Without it the tools use the free trial.",
        required=False,
    )
]


def _explain(exc: Exception) -> str:
    if isinstance(exc, EconDashPaymentRequired):
        return _PAYMENT
    if isinstance(exc, EconDashRateLimitError):
        wait = f" Retry after {exc.retry_after} seconds." if exc.retry_after else ""
        return f"Rate limit reached.{wait} No data in this call."
    if isinstance(exc, EconDashNotFound):
        return f"Not found ({exc}). Search with econdash_search_indicators. {_ISO}"
    if isinstance(exc, EconDashAuthError):
        return f"API key was rejected ({exc}). Check ECONDASH_API_KEY."
    return f"EconDash error: {exc}"


def _country_error(code: str) -> str | None:
    return None if len(code) == 3 and code.isalpha() else f"Invalid country code {code!r}. {_ISO}"


def _search_text(rows: list[Indicator]) -> str:
    if not rows:
        return "No indicators matched. Try a shorter query such as gdp or inflation."
    lines = ["slug | name | unit | source | frequency"]
    for ind in rows:
        cells = [ind.slug or ind.code, ind.name, ind.unit, ind.source, ind.frequency]
        lines.append(" | ".join(c or "" for c in cells))
    return "\n".join(lines)


def _series_text(series: Series, slug: str, full: bool) -> str:
    points = series.data
    if not points:
        return "No observations for this country and period."
    shown = points if full else points[-20:]
    last = shown[-1]
    name = series.indicator_name_en or series.indicator_name_ru
    country = last.country_name or last.country
    unit = series.unit or ""
    chart = f"https://econdash.org/chart/{slug}/{last.country}" if slug else ""
    lines = [
        f"{name} — {country}",
        f"unit: {unit or 'n/a'}",
        f"frequency: {series.frequency or 'n/a'}",
        f"data_changed_at: {series.data_changed_at or 'n/a'}",
        f"points: {len(points)} total, showing {len(shown)}",
        f"chart: {chart or 'n/a'}",
        f"citation: {country} {name} was {last.value} {unit} on {last.date.isoformat()} "
        f"(EconDash). {chart}".rstrip(),
    ]
    lines += [f"{p.date.isoformat()} {p.value}" for p in shown]
    if len(points) > len(shown):
        lines.append("Set full=true only when the user asked for the whole history.")
    return "\n".join(lines)


class _EconDashTool(BaseTool):
    client: Any = Field(default_factory=EconDash, exclude=True)
    env_vars: list[EnvVar] = Field(default_factory=lambda: list(_ENV))

    def _slug(self, indicator: str, series: Series) -> str:
        if "__" not in indicator:
            return indicator
        try:
            return self.client.get_indicator(series.indicator_code).slug or ""
        except EconDashError:
            return ""


class SearchInput(BaseModel):
    query: Text = Field(description="Words to match against indicator names, slugs and sources.")
    limit: Limit = Field(default=10, description="How many matches to return, 1 to 20.")


class EconDashSearchTool(_EconDashTool):
    name: str = "econdash_search_indicators"
    description: str = (
        "Search the EconDash indicator catalog. Returns slug, name, unit, source and frequency. "
        "Call this before a series. The catalog is metadata; it has no numbers. " + _TRIAL
    )
    args_schema: type[BaseModel] = SearchInput

    def _run(self, query: str, limit: int = 10, **_: Any) -> str:
        try:
            return _search_text(self.client.search_indicators(query, limit=limit))
        except EconDashError as exc:
            return _explain(exc)


class SeriesInput(BaseModel):
    indicator: Text = Field(description="Slug from econdash_search_indicators, e.g. gdp-nominal.")
    country: Iso3 = Field(description="ISO3 code, e.g. USA. Not a country name.")
    start: When = Field(default=None, description="Start year or date, e.g. 2000.")
    end: When = Field(default=None, description="End year or date.")
    full: Flag = Field(
        default=False,
        description="Return the whole series the API sent. Default is the last 20 points.",
    )


class EconDashSeriesTool(_EconDashTool):
    name: str = "econdash_get_series"
    description: str = (
        "Load one indicator for one country: unit, when the data last changed, a citation "
        "with the econdash.org chart link, and the last 20 observations. " + _TRIAL
    )
    args_schema: type[BaseModel] = SeriesInput

    def _run(
        self,
        indicator: str,
        country: str,
        start: str | int | None = None,
        end: str | int | None = None,
        full: bool = False,
        **_: Any,
    ) -> str:
        if message := _country_error(country):
            return message
        try:
            series = self.client.get_series(indicator, country, start=start, end=end)
        except EconDashError as exc:
            return _explain(exc)
        except ValueError:
            return "Invalid start or end. Use a year such as 2000 or a date such as 2000-06-30."
        return _series_text(series, self._slug(indicator, series), full)


class CompareInput(BaseModel):
    indicator: Text = Field(description="Indicator slug, e.g. gdp-nominal.")
    countries: Iso3List = Field(description="1 to 8 ISO3 codes, e.g. ['USA', 'DEU', 'JPN'].")
    year: Year = Field(default=None, description="Calendar year. Omit for the latest point.")


class EconDashCompareTool(_EconDashTool):
    name: str = "econdash_compare_countries"
    description: str = (
        "Latest value of one indicator for a few countries, each requested on its own, "
        "with the econdash.org chart link per country. A country outside the trial is a "
        "payment message on that line; the other countries are not unlocked by it. " + _TRIAL
    )
    args_schema: type[BaseModel] = CompareInput

    def _line(self, indicator: str, country: str, year: int | None) -> str:
        if message := _country_error(country):
            return f"{country}: {message}"
        try:
            series = self.client.get_series(indicator, country, start=year, end=year)
        except EconDashError as exc:
            return f"{country}: {_explain(exc)}"
        if not series.data:
            return f"{country}: no observations."
        last = series.data[-1]
        slug = self._slug(indicator, series)
        chart = f" https://econdash.org/chart/{slug}/{country}" if slug else ""
        return f"{country}: {last.value} {series.unit or ''} on {last.date.isoformat()}{chart}"

    def _run(self, indicator: str, countries: list[str], year: int | None = None, **_: Any) -> str:
        if not 1 <= len(countries) <= 8:
            return "Pass 1 to 8 ISO3 codes per call, e.g. ['USA', 'DEU', 'JPN']."
        return "\n".join(self._line(indicator, c, year) for c in countries)
