"""EconDashToolSpec: four tools over the econdash client.

Descriptions come from ``econdash.agent_text`` (the same sentences as the
LangChain tools). Each method returns text, including on 402 and 429.
"""

from typing import Annotated, Any

from llama_index.core.tools.tool_spec.base import BaseToolSpec

from econdash import EconDash, EconDashError, Series
from econdash.agent_text import (
    _flag,
    _iso,
    _isos,
    _limit,
    _text,
    _when,
    _year,
    country_error,
    explain,
    metadata_text,
    search_text,
    series_text,
    tool_descriptions,
)

_SEARCH = "search_indicators"
_DESC = tool_descriptions(_SEARCH)


def _documented(description: str):
    def wrap(fn):
        fn.__doc__ = description
        return fn

    return wrap


class EconDashToolSpec(BaseToolSpec):
    """Tools that use the same access as ``EconDash``.

    No key and no wallet: the free trial only. A 402 becomes a sentence for the
    model and includes no figures. Pass ``api_key=`` for a subscription. Pass a
    wallet plus ``max_usd_per_call`` to pay per call.
    """

    spec_functions = ["search_indicators", "get_series", "get_metadata", "compare_countries"]

    def __init__(
        self, client: Any | None = None, api_key: str | None = None, **client_kwargs: Any
    ) -> None:
        self.client = client if client is not None else EconDash(api_key, **client_kwargs)

    def _slug(self, indicator: str, series: Series) -> str:
        if "__" not in indicator:
            return indicator
        try:
            return self.client.get_indicator(series.indicator_code).slug or ""
        except EconDashError:
            return ""

    @_documented(_DESC["search_indicators"])
    def search_indicators(
        self,
        query: Annotated[str, "Words to match against indicator names, slugs and sources."],
        limit: Annotated[int | str | None, "How many matches to return, 1 to 20."] = 10,
        **_: Any,
    ) -> str:
        try:
            return search_text(self.client.search_indicators(_text(query), limit=_limit(limit)))
        except EconDashError as exc:
            return explain(exc, search_tool=_SEARCH)

    @_documented(_DESC["get_series"])
    def get_series(
        self,
        indicator: Annotated[str, "Slug from search_indicators, e.g. gdp-nominal."],
        country: Annotated[str, "ISO3 code, e.g. USA. Not a country name."],
        start: Annotated[
            str | int | float | None, "Start year or date, e.g. 2000. Null for the first point."
        ] = None,
        end: Annotated[
            str | int | float | None, "End year or date. Null for the latest point."
        ] = None,
        full: Annotated[
            bool | str | None,
            "Return the whole series the API sent. Default is the last 20 points.",
        ] = False,
        **_: Any,
    ) -> str:
        indicator = _text(indicator)
        country = _iso(country)
        if message := country_error(str(country)):
            return message
        try:
            series = self.client.get_series(indicator, country, start=_when(start), end=_when(end))
        except EconDashError as exc:
            return explain(exc, search_tool=_SEARCH)
        except ValueError:
            return "Invalid start or end. Use a year such as 2000 or a date such as 2000-06-30."
        return series_text(series, slug=self._slug(indicator, series), full=_flag(full))

    @_documented(_DESC["get_metadata"])
    def get_metadata(self, indicator: Annotated[str, "Indicator slug or code."], **_: Any) -> str:
        indicator = _text(indicator)
        try:
            ind = self.client.get_indicator(indicator)
        except EconDashError as exc:
            return explain(exc, search_tool=_SEARCH)
        countries: list[str] | None = None
        note = ""
        try:
            raw = self.client._get(f"{self.client.base_url}/indicators/{ind.code}/countries")
            countries = [str(code) for code in raw]
        except EconDashError as exc:
            note = explain(exc, search_tool=_SEARCH)
        return metadata_text(ind, countries, note)

    def _line(self, indicator: str, country: str, year: int | None) -> str:
        if message := country_error(country):
            return f"{country}: {message}"
        try:
            series = self.client.get_series(indicator, country, start=year, end=year)
        except EconDashError as exc:
            return f"{country}: {explain(exc, search_tool=_SEARCH)}"
        if not series.data:
            return f"{country}: no observations."
        last = series.data[-1]
        slug = self._slug(indicator, series)
        chart = f" https://econdash.org/chart/{slug}/{country}" if slug else ""
        return f"{country}: {last.value} {series.unit or ''} on {last.date.isoformat()}{chart}"

    @_documented(_DESC["compare_countries"])
    def compare_countries(
        self,
        indicator: Annotated[str, "Indicator slug, e.g. gdp-nominal."],
        countries: Annotated[list[str] | str, "1 to 8 ISO3 codes, e.g. ['USA', 'DEU', 'JPN']."],
        year: Annotated[
            int | str | float | None,
            "Calendar year, e.g. 2023. Null or 'latest' for the latest point.",
        ] = None,
        **_: Any,
    ) -> str:
        indicator = _text(indicator)
        codes = _isos(countries)
        if not 1 <= len(codes) <= 8:
            return "Pass 1 to 8 ISO3 codes per call, e.g. ['USA', 'DEU', 'JPN']."
        picked = _year(year)
        return "\n".join(self._line(indicator, code, picked) for code in codes)
