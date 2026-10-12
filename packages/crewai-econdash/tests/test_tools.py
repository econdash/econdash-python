"""CrewAI tools on a fake client: trial data comes back as text, errors as a hint, never figures."""

from datetime import date
from typing import Any

import pytest
from crewai_econdash import (
    EconDashCompareTool,
    EconDashSearchTool,
    EconDashSeriesTool,
)

from econdash import (
    EconDashNotFound,
    EconDashPaymentRequired,
    EconDashRateLimitError,
    Indicator,
    Point,
    Series,
)


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
    )


def _series(country: str) -> Series:
    points = [Point(date=date(2000 + i, 1, 1), value=float(i), country=country) for i in range(25)]
    return Series(
        indicator_code="world_bank__gdp_nominal",
        indicator_name_ru="ВВП",
        indicator_name_en="GDP",
        unit="USD",
        data=points,
    )


class Fake:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def search_indicators(self, query: str, limit: int = 20) -> list[Indicator]:
        self.calls.append(("search", query, limit))
        if query == "busy":
            raise EconDashRateLimitError("429", retry_after=30, status_code=429)
        return [_indicator()] if query == "gdp" else []

    def get_series(
        self, indicator: str, country: str, start: Any = None, end: Any = None
    ) -> Series:
        self.calls.append(("series", indicator, country, start, end))
        if start == "abc":
            raise ValueError("bad date")
        if indicator == "missing":
            raise EconDashNotFound("404: unknown", status_code=404)
        if country == "ZWE":
            raise EconDashPaymentRequired("402: outside trial", status_code=402)
        return _series(country)

    def get_indicator(self, indicator: str) -> Indicator:
        self.calls.append(("meta", indicator))
        return _indicator()


@pytest.fixture
def fake() -> Fake:
    return Fake()


def test_search_returns_slug_table(fake: Fake) -> None:
    out = EconDashSearchTool(client=fake).run(query="gdp", limit=3)
    assert "gdp-nominal | GDP | USD | World Bank | annual" in out
    assert fake.calls == [("search", "gdp", 3)]


def test_search_no_match_and_rate_limit_are_text(fake: Fake) -> None:
    tool = EconDashSearchTool(client=fake)
    assert "No indicators matched" in tool.run(query="zzz")
    assert "Retry after 30 seconds" in tool.run(query="busy")


def test_search_validates_limit(fake: Fake) -> None:
    with pytest.raises(ValueError):
        EconDashSearchTool(client=fake).run(query="gdp", limit=50)
    assert fake.calls == []


def test_series_gives_last_points_citation_and_chart_link(fake: Fake) -> None:
    out = EconDashSeriesTool(client=fake).run(indicator="gdp-nominal", country="usa", start="2000")
    assert "https://econdash.org/chart/gdp-nominal/USA" in out
    assert "citation: USA GDP was 24.0 USD on 2024-01-01" in out
    assert "points: 25 total, showing 20" in out
    assert "2004-01-01" not in out and "2005-01-01 5.0" in out
    assert fake.calls == [("series", "gdp-nominal", "USA", "2000", None)]


def test_series_full_and_code_resolves_slug(fake: Fake) -> None:
    out = EconDashSeriesTool(client=fake).run(
        indicator="world_bank__gdp_nominal", country="DEU", full=True
    )
    assert "2000-01-01 0.0" in out
    assert "https://econdash.org/chart/gdp-nominal/DEU" in out
    assert ("meta", "world_bank__gdp_nominal") in fake.calls


def test_series_payment_is_hint_without_figures(fake: Fake) -> None:
    out = EconDashSeriesTool(client=fake).run(indicator="gdp-nominal", country="ZWE")
    assert out.startswith("Payment required.")
    assert "nothing was charged" in out
    assert not any(ch.isdigit() for ch in out.split("free trial")[0])


def test_series_bad_country_date_and_missing_are_text(fake: Fake) -> None:
    tool = EconDashSeriesTool(client=fake)
    assert "ISO3" in tool.run(indicator="gdp-nominal", country="Germany")
    assert "Invalid start or end" in tool.run(indicator="gdp-nominal", country="USA", start="abc")
    assert tool.run(indicator="missing", country="USA").startswith("Not found")
    assert all(call[2] != "Germany" for call in fake.calls)


def test_series_requires_country(fake: Fake) -> None:
    with pytest.raises(ValueError):
        EconDashSeriesTool(client=fake).run(indicator="gdp-nominal")


def test_compare_each_country_on_its_own(fake: Fake) -> None:
    out = (
        EconDashCompareTool(client=fake)
        .run(indicator="gdp-nominal", countries=["USA", "ZWE", "Japan"], year=2020)
        .splitlines()
    )
    assert out[0] == "USA: 24.0 USD on 2024-01-01 https://econdash.org/chart/gdp-nominal/USA"
    assert out[1].startswith("ZWE: Payment required.")
    assert out[2].startswith("Japan: Invalid country code")
    assert [c for c in fake.calls if c[0] == "series"] == [
        ("series", "gdp-nominal", "USA", 2020, 2020),
        ("series", "gdp-nominal", "ZWE", 2020, 2020),
    ]


def test_compare_validates_country_count(fake: Fake) -> None:
    tool = EconDashCompareTool(client=fake)
    with pytest.raises(ValueError):
        tool.run(indicator="gdp-nominal", countries=[])
    with pytest.raises(ValueError):
        tool.run(indicator="gdp-nominal", countries=["USA"] * 9)


def test_default_client_and_env_var_declared(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECONDASH_API_KEY", "k")
    tool = EconDashSearchTool()
    assert tool.client.api_key == "k"
    assert [v.name for v in tool.env_vars] == ["ECONDASH_API_KEY"]
    assert tool.env_vars[0].required is False
