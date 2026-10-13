"""Tools talk to a fake client: trial data comes back, paid data comes back as a hint."""

from datetime import date

import pytest
from llama_index.tools.econdash import EconDashToolSpec

from econdash import (
    EconDashNotFound,
    EconDashPaymentRequired,
    EconDashRateLimitError,
    Indicator,
    Point,
    Series,
)
from econdash.agent_text import tool_descriptions


def _indicator(**kwargs: object) -> Indicator:
    data: dict[str, object] = {
        "code": "world_bank__gdp_nominal",
        "slug": "gdp-nominal",
        "name_ru": "ВВП",
        "name_en": "GDP",
        "unit": "USD",
        "source": "World Bank",
        "frequency": "annual",
        "category": None,
        "fetch_method": None,
        "source_url": "https://data.worldbank.org/indicator/NY.GDP.MKTP.CD",
        "license_name": "CC BY 4.0",
        "description": "Nominal GDP",
        "data_changed_at": "2026-01-01",
    }
    data.update(kwargs)
    return Indicator.model_validate(data)


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
        if start in {"abc", "2020-06-31", "last 5 years"}:
            raise ValueError("bad date")
        if country.upper() == "ZWE":
            raise EconDashPaymentRequired("outside trial", status_code=402)
        if country.upper() == "VEN":
            raise EconDashRateLimitError("slow", retry_after=5, status_code=429)
        return _series(country.upper())

    def get_indicator(self, indicator: str) -> Indicator:
        self.calls.append(("meta", indicator))
        if indicator == "missing":
            raise EconDashNotFound("missing", status_code=404)
        return _indicator()

    def _get(self, url: str) -> list[str]:
        self.calls.append(("countries", url))
        return ["USA", "DEU"]


def _text(spec: EconDashToolSpec, name: str, **kwargs: object) -> str:
    tool = next(item for item in spec.to_tool_list() if item.metadata.name == name)
    result = tool.call(**kwargs)
    return str(result.raw_output)


def test_to_tool_list_has_four_tools_with_schemas() -> None:
    spec = EconDashToolSpec(client=Fake())
    tools = spec.to_tool_list()
    assert [tool.metadata.name for tool in tools] == [
        "search_indicators",
        "get_series",
        "get_metadata",
        "compare_countries",
    ]
    descriptions = tool_descriptions("search_indicators")
    expected = {
        "search_indicators": {"query"},
        "get_series": {"indicator", "country"},
        "get_metadata": {"indicator"},
        "compare_countries": {"indicator", "countries"},
    }
    for tool in tools:
        assert descriptions[tool.metadata.name] in (tool.metadata.description or "")
        assert tool.metadata.description
        schema = tool.metadata.fn_schema.model_json_schema()
        assert expected[tool.metadata.name] <= set(schema["required"])
        for name, field in schema["properties"].items():
            assert field.get("description"), name


def test_search_returns_slug_and_not_values() -> None:
    spec = EconDashToolSpec(client=Fake())
    text = _text(spec, "search_indicators", query="gdp", limit=5)
    assert "gdp-nominal" in text
    assert "World Bank" in text
    assert "2000-01-01" not in text


def test_series_is_last_20_and_cites_the_chart() -> None:
    fake = Fake()
    text = _text(
        EconDashToolSpec(client=fake), "get_series", indicator="gdp-nominal", country="usa"
    )
    assert "2000-01-01" not in text
    assert "2005-01-01" in text
    assert "2024-01-01 24.0" in text
    assert "https://econdash.org/chart/gdp-nominal/USA" in text
    assert "data_changed_at: 2026-01-01" in text
    assert fake.calls[0][2] == "USA"


def test_full_series_includes_the_start() -> None:
    text = _text(
        EconDashToolSpec(client=Fake()),
        "get_series",
        indicator="gdp-nominal",
        country="USA",
        full=True,
    )
    assert "2000-01-01 0.0" in text


def test_outside_trial_and_rate_limit_are_text_without_figures() -> None:
    fake = Fake()
    spec = EconDashToolSpec(client=fake)
    paid = _text(spec, "get_series", indicator="gdp-nominal", country="ZWE")
    assert "Payment required" in paid
    assert "ECONDASH_API_KEY" in paid
    assert "x402" in paid
    assert "24.0" not in paid
    limited = _text(spec, "get_series", indicator="gdp-nominal", country="VEN")
    assert "Rate limit reached" in limited
    assert "Retry after 5 seconds" in limited
    assert "24.0" not in limited


def test_bad_country_code_never_calls_the_api() -> None:
    fake = Fake()
    text = _text(
        EconDashToolSpec(client=fake), "get_series", indicator="gdp-nominal", country="Germany"
    )
    assert "Invalid country code" in text
    assert fake.calls == []


def test_unknown_indicator_tells_the_model_to_search() -> None:
    text = _text(EconDashToolSpec(client=Fake()), "get_metadata", indicator="missing")
    assert "Not found" in text
    assert "search_indicators" in text


def test_metadata_includes_licence_and_countries() -> None:
    text = _text(EconDashToolSpec(client=Fake()), "get_metadata", indicator="gdp-nominal")
    assert "CC BY 4.0" in text
    assert "USA, DEU" in text
    assert "source_url:" in text


def test_compare_keeps_paid_countries_out_of_the_answer() -> None:
    text = _text(
        EconDashToolSpec(client=Fake()),
        "compare_countries",
        indicator="gdp-nominal",
        countries=["USA", "ZWE"],
    )
    assert "USA: 24.0 USD on 2024-01-01 https://econdash.org/chart/gdp-nominal/USA" in text
    zwe = next(line for line in text.splitlines() if line.startswith("ZWE"))
    assert "Payment required" in zwe
    assert "24.0" not in zwe


def test_compare_rejects_a_long_list() -> None:
    text = _text(
        EconDashToolSpec(client=Fake()),
        "compare_countries",
        indicator="gdp-nominal",
        countries=[f"A{i:02d}" for i in range(9)],
    )
    assert "Pass 1 to 8" in text


@pytest.mark.asyncio
async def test_async_answers_match_sync() -> None:
    spec = EconDashToolSpec(client=Fake())
    tool = next(item for item in spec.to_tool_list() if item.metadata.name == "get_series")
    args = {"indicator": "world_bank__gdp_nominal", "country": "DEU"}
    sync = str(tool.call(**args).raw_output)
    assert "https://econdash.org/chart/gdp-nominal/DEU" in sync
    assert str((await tool.acall(**args)).raw_output) == sync


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "args", "expected"),
    [
        ("search_indicators", {"query": " gdp ", "limit": "5"}, "gdp-nominal"),
        ("search_indicators", {"query": "gdp", "limit": 50}, "gdp-nominal"),
        ("search_indicators", {"query": "gdp", "limit": None}, "gdp-nominal"),
        ("search_indicators", {"query": "gdp", "limit": 0}, "gdp-nominal"),
        ("get_series", {"indicator": " gdp-nominal ", "country": " usa "}, "/gdp-nominal/USA"),
        ("get_series", {"indicator": "gdp-nominal", "country": "USA", "extra": 1}, "/USA"),
        ("get_series", {"indicator": "gdp-nominal", "country": "USA", "start": 2020.0}, "/USA"),
        ("get_series", {"indicator": "gdp-nominal", "country": "USA", "start": ""}, "/USA"),
        ("get_series", {"indicator": "gdp-nominal", "country": "USA", "full": None}, "/USA"),
        (
            "get_series",
            {"indicator": "gdp-nominal", "country": "USA", "start": "abc"},
            "Invalid start",
        ),
        (
            "get_series",
            {"indicator": "gdp-nominal", "country": "USA", "start": "2020-06-31"},
            "Invalid start",
        ),
        (
            "get_series",
            {"indicator": "gdp-nominal", "country": "USA", "start": "last 5 years"},
            "Invalid start",
        ),
        ("get_series", {"indicator": "gdp-nominal", "country": "US"}, "ISO3"),
        ("get_metadata", {"indicator": " gdp-nominal "}, "gdp-nominal: GDP"),
        ("compare_countries", {"indicator": "gdp-nominal", "countries": "USA,DEU"}, "DEU: 24.0"),
        (
            "compare_countries",
            {"indicator": "gdp-nominal", "countries": '["DEU", "JPN", "USA"]'},
            "JPN: 24.0",
        ),
        (
            "compare_countries",
            {"indicator": "gdp-nominal", "countries": "['DEU', 'USA']"},
            "DEU: 24.0",
        ),
        (
            "get_series",
            {"indicator": "gdp-nominal", "country": "USA", "end": "None"},
            "/USA",
        ),
        ("compare_countries", {"indicator": "gdp-nominal", "countries": "USA, deu"}, "DEU: 24.0"),
        ("compare_countries", {"indicator": "gdp-nominal", "countries": "USA DEU"}, "DEU: 24.0"),
        ("compare_countries", {"indicator": "gdp-nominal", "countries": "USA"}, "USA: 24.0"),
        ("compare_countries", {"indicator": "gdp-nominal", "countries": [" usa "]}, "USA: 24.0"),
        (
            "compare_countries",
            {"indicator": "gdp-nominal", "countries": ["USA"], "year": "latest"},
            "USA:",
        ),
        (
            "compare_countries",
            {"indicator": "gdp-nominal", "countries": ["USA"], "year": "2020"},
            "USA:",
        ),
        (
            "compare_countries",
            {"indicator": "gdp-nominal", "countries": ["USA"], "year": 2023.0},
            "USA:",
        ),
        ("compare_countries", {"indicator": "gdp-nominal", "countries": []}, "Pass 1 to 8"),
        ("compare_countries", {"indicator": "gdp-nominal", "countries": ""}, "Pass 1 to 8"),
    ],
)
async def test_model_shaped_arguments(name: str, args: dict, expected: str) -> None:
    spec = EconDashToolSpec(client=Fake())
    tool = next(item for item in spec.to_tool_list() if item.metadata.name == name)
    sync = str(tool.call(**args).raw_output)
    assert expected in sync
    assert str((await tool.acall(**args)).raw_output) == sync
