"""Four tools. Each one calls the econdash client and returns text, including on 402.

Async calls (`ainvoke`) use LangChain's default: the same `_run` in a worker thread,
so sync and async answers cannot drift apart.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from econdash import EconDashError, Indicator, Series
from econdash.agent_text import tool_descriptions
from langchain_econdash._args import Flag, Iso3, Iso3List, Limit, Text, When, Year
from langchain_econdash._format import country_error, explain, search_text, series_text

_DESC = tool_descriptions()


class _ClientTool(BaseTool):
    client: Any = Field(exclude=True)
    # Kept so older code that passes it still works; async runs `_run` in a thread.
    async_client: Any = Field(default=None, exclude=True)

    model_config = {"arbitrary_types_allowed": True}

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


class SearchIndicators(_ClientTool):
    name: str = "econdash_search_indicators"
    description: str = _DESC["search_indicators"]
    args_schema: type[BaseModel] = SearchInput

    def _run(self, query: str, limit: int = 10, **_: Any) -> str:
        try:
            return search_text(self.client.search_indicators(query, limit=limit))
        except EconDashError as exc:
            return explain(exc)


class SeriesInput(BaseModel):
    indicator: Text = Field(description="Slug from econdash_search_indicators, e.g. gdp-nominal.")
    country: Iso3 = Field(description="ISO3 code, e.g. USA. Not a country name.")
    start: When = Field(
        default=None, description="Start year or date, e.g. 2000. Null for the first point."
    )
    end: When = Field(default=None, description="End year or date. Null for the latest point.")
    full: Flag = Field(
        default=False,
        description="Return the whole series the API sent. Default is the last 20 points.",
    )


class GetSeries(_ClientTool):
    name: str = "econdash_get_series"
    description: str = _DESC["get_series"]
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
        if message := country_error(country):
            return message
        try:
            series = self.client.get_series(indicator, country, start=start, end=end)
        except EconDashError as exc:
            return explain(exc)
        except ValueError:
            return "Invalid start or end. Use a year such as 2000 or a date such as 2000-06-30."
        return series_text(series, slug=self._slug(indicator, series), full=full)


class MetadataInput(BaseModel):
    indicator: Text = Field(description="Indicator slug or code.")


class GetMetadata(_ClientTool):
    name: str = "econdash_get_metadata"
    description: str = _DESC["get_metadata"]
    args_schema: type[BaseModel] = MetadataInput

    def _run(self, indicator: str, **_: Any) -> str:
        try:
            ind = self.client.get_indicator(indicator)
        except EconDashError as exc:
            return explain(exc)
        countries: list[str] | None = None
        note = ""
        try:
            raw = self.client._get(f"{self.client.base_url}/indicators/{ind.code}/countries")
            countries = [str(code) for code in raw]
        except EconDashError as exc:
            note = explain(exc)
        return _metadata_text(ind, countries, note)


def _metadata_text(ind: Indicator, countries: list[str] | None, country_note: str) -> str:
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


class CompareInput(BaseModel):
    indicator: Text = Field(description="Indicator slug, e.g. gdp-nominal.")
    countries: Iso3List = Field(description="1 to 8 ISO3 codes, e.g. ['USA', 'DEU', 'JPN'].")
    year: Year = Field(
        default=None, description="Calendar year, e.g. 2023. Null for the latest point."
    )


class CompareCountries(_ClientTool):
    name: str = "econdash_compare_countries"
    description: str = _DESC["compare_countries"]
    args_schema: type[BaseModel] = CompareInput

    def _line(self, indicator: str, country: str, year: int | None) -> str:
        if message := country_error(country):
            return f"{country}: {message}"
        try:
            series = self.client.get_series(indicator, country, start=year, end=year)
        except EconDashError as exc:
            return f"{country}: {explain(exc)}"
        if not series.data:
            return f"{country}: no observations."
        last = series.data[-1]
        slug = self._slug(indicator, series)
        # Without a link models write one from memory, e.g. /indicator/<slug>.
        chart = f" https://econdash.org/chart/{slug}/{country}" if slug else ""
        return f"{country}: {last.value} {series.unit or ''} on {last.date.isoformat()}{chart}"

    def _run(self, indicator: str, countries: list[str], year: int | None = None, **_: Any) -> str:
        if not 1 <= len(countries) <= 8:
            return "Pass 1 to 8 ISO3 codes per call, e.g. ['USA', 'DEU', 'JPN']."
        return "\n".join(self._line(indicator, c, year) for c in countries)
