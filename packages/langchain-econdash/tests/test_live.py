"""Contract with the real API (free trial, no key). Run with: pytest -m live"""

import pytest
from langchain_econdash import EconDashToolkit

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def tools() -> dict:
    return {t.name: t for t in EconDashToolkit().get_tools()}


def test_search_finds_cpi_first(tools: dict) -> None:
    out = tools["econdash_search_indicators"].invoke({"query": "inflation", "limit": 3})
    assert out.splitlines()[1].startswith("cpi-inflation-rate-percent |")


@pytest.mark.asyncio
async def test_series_sync_and_async_agree(tools: dict) -> None:
    args = {"indicator": "world_bank__gdp_nominal", "country": "USA", "start": 2020}
    sync = tools["econdash_get_series"].invoke(args)
    assert "https://econdash.org/chart/gdp-nominal/USA" in sync
    assert "citation: United States GDP nominal was" in sync
    assert await tools["econdash_get_series"].ainvoke(args) == sync


def test_metadata_has_licence_and_countries(tools: dict) -> None:
    out = tools["econdash_get_metadata"].invoke({"indicator": "gdp-nominal"})
    assert "license: CC BY 4.0" in out
    assert "countries (" in out


def test_outside_trial_is_text_without_figures(tools: dict) -> None:
    out = tools["econdash_compare_countries"].invoke(
        {"indicator": "gdp-nominal", "countries": "USA ZWE"}
    )
    usa, zwe = out.splitlines()
    assert usa.startswith("USA: ") and "https://econdash.org/chart/gdp-nominal/USA" in usa
    assert zwe.startswith("ZWE: Payment required.")
    assert not any(ch.isdigit() for ch in zwe.split("free trial")[0])
