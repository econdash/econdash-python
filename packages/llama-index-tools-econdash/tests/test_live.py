"""Contract with the real API (free trial, no key). Run with: pytest -m live"""

import pytest
from llama_index.tools.econdash import EconDashReader, EconDashToolSpec

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def tools() -> dict:
    return {tool.metadata.name: tool for tool in EconDashToolSpec().to_tool_list()}


def _out(tool, **kwargs: object) -> str:
    return str(tool.call(**kwargs).raw_output)


def test_search_finds_cpi_first(tools: dict) -> None:
    out = _out(tools["search_indicators"], query="inflation", limit=3)
    assert out.splitlines()[1].startswith("cpi-inflation-rate-percent |")


def test_series_cites_the_chart(tools: dict) -> None:
    out = _out(tools["get_series"], indicator="gdp-nominal", country="USA", start=2020)
    assert "https://econdash.org/chart/gdp-nominal/USA" in out
    assert "citation:" in out


def test_metadata_has_licence(tools: dict) -> None:
    out = _out(tools["get_metadata"], indicator="gdp-nominal")
    assert "license: CC BY 4.0" in out
    assert "countries (" in out


def test_outside_trial_is_text_without_figures(tools: dict) -> None:
    out = _out(tools["compare_countries"], indicator="gdp-nominal", countries="USA ZWE")
    usa, zwe = out.splitlines()
    assert usa.startswith("USA: ") and "https://econdash.org/chart/gdp-nominal/USA" in usa
    assert zwe.startswith("ZWE: Payment required.")
    assert not any(ch.isdigit() for ch in zwe.split("free trial")[0])


def test_reader_indexes_a_trial_pair_and_skips_a_paid_country() -> None:
    docs = EconDashReader().load_data(indicators=["gdp-nominal"], countries=["USA", "ZWE"])
    assert len(docs) == 1
    assert docs[0].metadata["iso3"] == "USA"
    assert docs[0].metadata["license"]
    assert docs[0].metadata["source_url"]
    assert "https://econdash.org/chart/gdp-nominal/USA" in docs[0].text
    assert "ZWE" not in docs[0].text
