"""Tools talk to a fake client: trial data comes back, paid data comes back as a hint."""

from datetime import date

import pytest
from langchain_econdash.tools import CompareCountries, GetMetadata, GetSeries, SearchIndicators

from econdash import EconDashNotFound, EconDashPaymentRequired, Indicator, Point, Series


def _indicator() -> Indicator:
    return Indicator(
        code="world_bank__gdp_nominal",
        slug="gdp-nominal",
        name_ru="ВВП",
        name_en="GDP",
        unit="USD",
        source="World Bank",
        frequency="annual",
        category=None,
        fetch_method=None,
        source_url="https://data.worldbank.org/indicator/NY.GDP.MKTP.CD",
        license_name="CC BY 4.0",
        description="Nominal GDP",
        data_changed_at="2026-01-01",
    )


def _series(country: str) -> Series:
    points = [Point(date=date(2000 + i, 1, 1), value=float(i), country=country) for i in range(25)]
    return Series(
        indicator_code="world_bank__gdp_nominal",
        indicator_name_ru="ВВП",
        indicator_name_en="GDP",
        unit="USD",
        data_changed_at="2026-01-01",
        data=points,
    )


class Fake:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.base_url = "https://econdash.org/api/v1"

    def search_indicators(self, query: str, limit: int = 10) -> list[Indicator]:
        self.calls.append(("search", query, limit))
        return [_indicator()] if query else []

    def get_series(self, indicator: str, country: str, start=None, end=None) -> Series:
        self.calls.append(("series", indicator, country.upper(), start, end))
        if start == "abc":
            raise ValueError("bad date")
        if country.upper() == "ZWE":
            raise EconDashPaymentRequired("outside trial", status_code=402)
        return _series(country.upper())

    def get_indicator(self, indicator: str) -> Indicator:
        self.calls.append(("meta", indicator))
        if indicator == "missing":
            raise EconDashNotFound("missing", status_code=404)
        return _indicator()

    def _get(self, url: str) -> list[str]:
        self.calls.append(("countries", url))
        return ["USA", "DEU"]

    async def search_indicators_async(self, query: str, limit: int = 10) -> list[Indicator]:
        return self.search_indicators(query, limit)

    async def get_series_async(self, indicator: str, country: str, start=None, end=None) -> Series:
        return self.get_series(indicator, country, start, end)


def test_search_returns_slug_and_not_values() -> None:
    tool = SearchIndicators(client=Fake(), async_client=Fake())
    text = tool.invoke({"query": "gdp", "limit": 5})
    assert "gdp-nominal" in text
    assert "World Bank" in text
    assert "2000-01-01" not in text


def test_series_is_last_20_and_cites_the_chart() -> None:
    fake = Fake()
    tool = GetSeries(client=fake, async_client=fake)
    text = tool.invoke({"indicator": "gdp-nominal", "country": "usa"})
    assert "2000-01-01" not in text
    assert "2005-01-01" in text
    assert "2024-01-01 24.0" in text
    assert "https://econdash.org/chart/gdp-nominal/USA" in text
    assert "data_changed_at: 2026-01-01" in text
    assert fake.calls[0][2] == "USA"


def test_full_series_includes_the_start() -> None:
    tool = GetSeries(client=Fake(), async_client=Fake())
    text = tool.invoke({"indicator": "gdp-nominal", "country": "USA", "full": True})
    assert "2000-01-01 0.0" in text


def test_series_accepts_years_as_numbers() -> None:
    # Models often send a year as a JSON number.
    fake = Fake()
    tool = GetSeries(client=fake, async_client=fake)
    text = tool.invoke({"indicator": "gdp-nominal", "country": "USA", "start": 2020, "end": 2024})
    assert "https://econdash.org/chart/gdp-nominal/USA" in text
    assert ("series", "gdp-nominal", "USA", 2020, 2024) in fake.calls


def test_outside_trial_is_a_payment_hint_without_figures() -> None:
    fake = Fake()
    tool = GetSeries(client=fake, async_client=fake)
    text = tool.invoke({"indicator": "gdp-nominal", "country": "ZWE"})
    assert "Payment required" in text
    assert "ECONDASH_API_KEY" in text
    assert "x402" in text
    assert "24.0" not in text
    assert len(fake.calls) == 1


def test_bad_country_code_never_calls_the_api() -> None:
    fake = Fake()
    tool = GetSeries(client=fake, async_client=fake)
    text = tool.invoke({"indicator": "gdp-nominal", "country": "Germany"})
    assert "Invalid country code" in text
    assert fake.calls == []


def test_unknown_indicator_tells_the_model_to_search() -> None:
    tool = GetMetadata(client=Fake(), async_client=Fake())
    text = tool.invoke({"indicator": "missing"})
    assert "Not found" in text
    assert "econdash_search_indicators" in text


def test_metadata_includes_licence_and_countries() -> None:
    tool = GetMetadata(client=Fake(), async_client=Fake())
    text = tool.invoke({"indicator": "gdp-nominal"})
    assert "CC BY 4.0" in text
    assert "USA, DEU" in text
    assert "source_url:" in text


def test_compare_keeps_paid_countries_out_of_the_answer() -> None:
    tool = CompareCountries(client=Fake(), async_client=Fake())
    text = tool.invoke({"indicator": "gdp-nominal", "countries": ["USA", "ZWE"]})
    assert "USA: 24.0" in text
    zwe = next(line for line in text.splitlines() if line.startswith("ZWE"))
    assert "Payment required" in zwe
    assert "24.0" not in zwe


def test_compare_rejects_a_long_list() -> None:
    tool = CompareCountries(client=Fake(), async_client=Fake())
    text = tool.invoke({"indicator": "gdp-nominal", "countries": [f"A{i:02d}" for i in range(9)]})
    assert "Pass 1 to 8" in text


@pytest.mark.asyncio
async def test_async_answers_match_sync() -> None:
    # A code instead of a slug: the chart link needs a metadata lookup on both paths.
    tool = GetSeries(client=Fake())
    args = {"indicator": "world_bank__gdp_nominal", "country": "DEU"}
    sync = tool.invoke(args)
    assert "https://econdash.org/chart/gdp-nominal/DEU" in sync
    assert await tool.ainvoke(args) == sync


# Arguments shaped the way models send them. Each must give text, never an exception.
MODEL_ARGS = [
    (SearchIndicators, {"query": " gdp ", "limit": "5"}, "gdp-nominal"),
    (SearchIndicators, {"query": "gdp", "limit": 50}, "gdp-nominal"),
    (SearchIndicators, {"query": "gdp", "limit": None}, "gdp-nominal"),
    (GetSeries, {"indicator": " gdp-nominal ", "country": " usa "}, "/gdp-nominal/USA"),
    (GetSeries, {"indicator": "gdp-nominal", "country": "USA", "start": 2020.0}, "/USA"),
    (GetSeries, {"indicator": "gdp-nominal", "country": "USA", "start": ""}, "/USA"),
    (GetSeries, {"indicator": "gdp-nominal", "country": "USA", "full": None}, "/USA"),
    (GetSeries, {"indicator": "gdp-nominal", "country": "USA", "start": "abc"}, "Invalid start"),
    (GetSeries, {"indicator": "gdp-nominal", "country": "US"}, "ISO3"),
    (GetMetadata, {"indicator": " gdp-nominal "}, "gdp-nominal: GDP"),
    (CompareCountries, {"indicator": "gdp-nominal", "countries": "USA, deu"}, "DEU: 24.0"),
    (CompareCountries, {"indicator": "gdp-nominal", "countries": "USA DEU"}, "DEU: 24.0"),
    (CompareCountries, {"indicator": "gdp-nominal", "countries": "USA"}, "USA: 24.0"),
    (
        CompareCountries,
        {"indicator": "gdp-nominal", "countries": ["USA"], "year": "latest"},
        "USA:",
    ),
    (CompareCountries, {"indicator": "gdp-nominal", "countries": []}, "Pass 1 to 8"),
    (CompareCountries, {"indicator": "gdp-nominal", "countries": ""}, "Pass 1 to 8"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("cls", "args", "expected"), MODEL_ARGS)
async def test_model_shaped_arguments(cls: type, args: dict, expected: str) -> None:
    tool = cls(client=Fake())
    sync = tool.invoke(args)
    assert expected in sync
    assert await tool.ainvoke(args) == sync
