"""Shared agent sentences stay aligned with the LangChain tools, and licences gate text."""

from econdash.agent_text import redistribution_allowed, tool_descriptions
from econdash.models import Indicator


def _indicator(**kwargs: object) -> Indicator:
    data: dict[str, object] = {
        "code": "world_bank__gdp_nominal",
        "slug": "gdp-nominal",
        "name_ru": "ВВП",
        "name_en": "GDP",
        "unit": "USD",
        "source": "World Bank",
        "license_name": "CC BY 4.0",
        "category": None,
        "fetch_method": None,
    }
    data.update(kwargs)
    return Indicator.model_validate(data)


def test_default_descriptions_match_the_langchain_sentences() -> None:
    text = tool_descriptions()
    assert text["search_indicators"] == (
        "Search the EconDash indicator catalog. Returns slug, name, unit, source and frequency. "
        "Call this before a series. The catalog is metadata; it has no numbers. "
        "Free trial only: 10 countries (USA, CHN, DEU, JPN, GBR, FRA, IND, BRA, RUS, KOR) "
        "and 50 indicators, 300 requests/day. Anything else comes back as a payment message, "
        "not as numbers. Find the slug with econdash_search_indicators first."
    )
    assert "last 20 observations" in text["get_series"]
    assert "Does not return the time series" in text["get_metadata"]
    assert "are not unlocked by it" in text["compare_countries"]
    assert all(text.values())


def test_llamaindex_descriptions_name_the_llamaindex_tool() -> None:
    text = tool_descriptions("search_indicators")
    assert "Find the slug with search_indicators first." in text["get_series"]
    assert "econdash_search_indicators" not in text["get_series"]


def test_redistribution_follows_the_site_block_list() -> None:
    assert redistribution_allowed(_indicator())
    assert redistribution_allowed(_indicator(license_name=None, source="World Bank"))
    assert not redistribution_allowed(_indicator(license_name="не распространять"))
    assert not redistribution_allowed(_indicator(license_name="No redistribution terms found"))
    assert not redistribution_allowed(_indicator(license_name="Third-party copyright via FRED"))
    assert not redistribution_allowed(
        _indicator(source="Yahoo Finance", license_name="Yahoo Terms of Service")
    )
    assert not redistribution_allowed(_indicator(source="FHFA / S&P Case-Shiller"))
    assert not redistribution_allowed(_indicator(source="ICE / Trading Economics"))
