"""Four tools. Each one calls the econdash client and returns text, including on 402."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from econdash import EconDashError, Indicator, Series
from langchain_econdash._format import country_error, explain, search_text, series_text

_TRIAL = (
    "Free trial only: 10 countries (USA, CHN, DEU, JPN, GBR, FRA, IND, BRA, RUS, KOR) "
    "and 50 indicators, 300 requests/day. Anything else comes back as a payment message, "
    "not as numbers. Find the slug with econdash_search_indicators first."
)


class _ClientTool(BaseTool):
    client: Any = Field(exclude=True)
    async_client: Any = Field(exclude=True)

    model_config = {"arbitrary_types_allowed": True}

    def _fail(self, exc: Exception) -> str:
        return explain(exc)


class SearchInput(BaseModel):
    query: str = Field(description="Words to match against indicator names, slugs and sources.")
    limit: int = Field(default=10, ge=1, le=20, description="How many matches to return.")


class SearchIndicators(_ClientTool):
    name: str = "econdash_search_indicators"
    description: str = (
        "Search the EconDash indicator catalog. Returns slug, name, unit, source and frequency. "
        "Call this before a series. The catalog is metadata; it has no numbers. " + _TRIAL
    )
    args_schema: type[BaseModel] = SearchInput

    def _run(self, query: str, limit: int = 10, **_: Any) -> str:
        try:
            return search_text(self.client.search_indicators(query, limit=limit))
        except EconDashError as exc:
            return self._fail(exc)

    async def _arun(self, query: str, limit: int = 10, **_: Any) -> str:
        try:
            return search_text(await self.async_client.search_indicators(query, limit=limit))
        except EconDashError as exc:
            return self._fail(exc)


class SeriesInput(BaseModel):
    indicator: str = Field(description="Slug from econdash_search_indicators, e.g. gdp-nominal.")
    country: str = Field(description="ISO3 code, e.g. USA. Not a country name.")
    start: str | None = Field(default=None, description="Start year or date, e.g. 2000.")
    end: str | None = Field(default=None, description="End year or date.")
    full: bool = Field(
        default=False,
        description="Return the whole series the API sent. Default is the last 20 points.",
    )


class GetSeries(_ClientTool):
    name: str = "econdash_get_series"
    description: str = (
        "Load one indicator for one country: unit, when the data last changed, a citation "
        "with the econdash.org chart link, and the last 20 observations. " + _TRIAL
    )
    args_schema: type[BaseModel] = SeriesInput

    def _text(self, series: Series, indicator: str, full: bool) -> str:
        slug = indicator if "__" not in indicator else ""
        if not slug:
            try:
                slug = self.client.get_indicator(series.indicator_code).slug or ""
            except EconDashError:
                slug = ""
        return series_text(series, slug=slug, full=full)

    def _run(
        self,
        indicator: str,
        country: str,
        start: str | None = None,
        end: str | None = None,
        full: bool = False,
        **_: Any,
    ) -> str:
        if message := country_error(country):
            return message
        try:
            series = self.client.get_series(indicator, country, start=start, end=end)
        except EconDashError as exc:
            return self._fail(exc)
        return self._text(series, indicator, full)

    async def _arun(
        self,
        indicator: str,
        country: str,
        start: str | None = None,
        end: str | None = None,
        full: bool = False,
        **_: Any,
    ) -> str:
        if message := country_error(country):
            return message
        try:
            series = await self.async_client.get_series(indicator, country, start=start, end=end)
        except EconDashError as exc:
            return self._fail(exc)
        slug = indicator if "__" not in indicator else ""
        return series_text(series, slug=slug, full=full)


class MetadataInput(BaseModel):
    indicator: str = Field(description="Indicator slug or code.")


class GetMetadata(_ClientTool):
    name: str = "econdash_get_metadata"
    description: str = (
        "Describe one indicator: source, licence, freshness and some countries. "
        "Does not return the time series. " + _TRIAL
    )
    args_schema: type[BaseModel] = MetadataInput

    def _text(self, ind: Indicator, countries: list[str] | None, country_note: str) -> str:
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

    def _run(self, indicator: str, **_: Any) -> str:
        try:
            ind = self.client.get_indicator(indicator)
        except EconDashError as exc:
            return self._fail(exc)
        countries: list[str] | None = None
        note = ""
        try:
            raw = self.client._get(f"{self.client.base_url}/indicators/{ind.code}/countries")
            countries = [str(code) for code in raw]
        except EconDashError as exc:
            note = explain(exc)
        return self._text(ind, countries, note)

    async def _arun(self, indicator: str, **_: Any) -> str:
        try:
            ind = await self.async_client.get_indicator(indicator)
        except EconDashError as exc:
            return self._fail(exc)
        countries: list[str] | None = None
        note = ""
        try:
            raw = await self.async_client._get(
                f"{self.async_client.base_url}/indicators/{ind.code}/countries"
            )
            countries = [str(code) for code in raw]
        except EconDashError as exc:
            note = explain(exc)
        return self._text(ind, countries, note)


class CompareInput(BaseModel):
    indicator: str = Field(description="Indicator slug, e.g. gdp-nominal.")
    countries: list[str] = Field(description="Up to 8 ISO3 codes, e.g. ['USA', 'DEU', 'JPN'].")
    year: int | None = Field(default=None, description="Calendar year. Omit for the latest point.")


class CompareCountries(_ClientTool):
    name: str = "econdash_compare_countries"
    description: str = (
        "Latest value of one indicator for a few countries, each requested on its own. "
        "A country outside the trial is a payment message on that line; the other countries "
        "are not unlocked by it. " + _TRIAL
    )
    args_schema: type[BaseModel] = CompareInput

    def _one(self, fetch: Any, indicator: str, country: str, year: int | None) -> str:
        if message := country_error(country):
            return f"{country}: {message}"
        try:
            if year is None:
                series = fetch(indicator, country)
            else:
                series = fetch(indicator, country, start=year, end=year)
        except EconDashError as exc:
            return f"{country}: {explain(exc)}"
        if not series.data:
            return f"{country}: no observations."
        last = series.data[-1]
        return f"{country}: {last.value} {series.unit or ''} on {last.date.isoformat()}"

    def _run(self, indicator: str, countries: list[str], year: int | None = None, **_: Any) -> str:
        if len(countries) > 8:
            return "Pass at most 8 countries per call."
        lines = [
            self._one(
                lambda ind, ctry, **kw: self.client.get_series(ind, ctry, **kw),
                indicator,
                country,
                year,
            )
            for country in countries
        ]
        return "\n".join(lines)

    async def _arun(
        self, indicator: str, countries: list[str], year: int | None = None, **_: Any
    ) -> str:
        if len(countries) > 8:
            return "Pass at most 8 countries per call."
        lines = []
        for country in countries:
            if message := country_error(country):
                lines.append(f"{country}: {message}")
                continue
            try:
                if year is None:
                    series = await self.async_client.get_series(indicator, country)
                else:
                    series = await self.async_client.get_series(
                        indicator, country, start=year, end=year
                    )
            except EconDashError as exc:
                lines.append(f"{country}: {explain(exc)}")
                continue
            if not series.data:
                lines.append(f"{country}: no observations.")
                continue
            last = series.data[-1]
            lines.append(f"{country}: {last.value} {series.unit or ''} on {last.date.isoformat()}")
        return "\n".join(lines)
