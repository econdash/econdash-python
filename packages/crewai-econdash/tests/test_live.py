"""Contract with the real API (free trial, no key). Run with: pytest -m live"""

import pytest
from crewai_econdash import EconDashCompareTool, EconDashSearchTool, EconDashSeriesTool

from econdash import EconDash

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def client() -> EconDash:
    return EconDash()


def test_search_finds_cpi_first(client: EconDash) -> None:
    out = EconDashSearchTool(client=client).run(query="inflation", limit=3)
    assert out.splitlines()[1].startswith("cpi-inflation-rate-percent |")


def test_series_has_figures_citation_and_chart(client: EconDash) -> None:
    out = EconDashSeriesTool(client=client).run(indicator="gdp-nominal", country="USA", start=2020)
    assert "chart: https://econdash.org/chart/gdp-nominal/USA" in out
    assert "citation: United States GDP nominal was" in out
    assert out.splitlines()[-1][:4].isdigit()


def test_series_by_code_resolves_the_chart_slug(client: EconDash) -> None:
    out = EconDashSeriesTool(client=client).run(indicator="world_bank__gdp_nominal", country="DEU")
    assert "https://econdash.org/chart/gdp-nominal/DEU" in out


def test_outside_trial_is_text_without_figures(client: EconDash) -> None:
    lines = EconDashCompareTool(client=client).run(indicator="gdp-nominal", countries="USA, ZWE")
    usa, zwe = lines.splitlines()
    assert usa.startswith("USA: ") and "https://econdash.org/chart/gdp-nominal/USA" in usa
    assert zwe.startswith("ZWE: Payment required.")
    assert not any(ch.isdigit() for ch in zwe.split("free trial")[0])
