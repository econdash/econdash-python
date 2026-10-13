"""The reader indexes a pair only when the licence allows the numbers to be copied."""

from datetime import date

from llama_index.tools.econdash import EconDashReader

from econdash import (
    EconDashError,
    EconDashPaymentRequired,
    EconDashRateLimitError,
    Indicator,
    Point,
    Series,
)


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
        "data_changed_at": "2026-01-01",
    }
    data.update(kwargs)
    return Indicator.model_validate(data)


def _series(country: str, points: int = 25) -> Series:
    return Series(
        indicator_code="world_bank__gdp_nominal",
        indicator_name_ru="ВВП",
        indicator_name_en="GDP",
        unit="USD",
        data_changed_at="2026-02-02",
        data=[
            Point(date=date(2000 + i, 1, 1), value=float(i), country=country) for i in range(points)
        ],
    )


class Fake:
    def __init__(self, indicators: dict[str, Indicator] | None = None) -> None:
        self.indicators = indicators or {"gdp-nominal": _indicator()}
        self.calls: list[tuple] = []

    def get_indicator(self, indicator: str) -> Indicator:
        self.calls.append(("meta", indicator))
        if indicator not in self.indicators:
            raise EconDashError("missing", status_code=404)
        return self.indicators[indicator]

    def get_series(self, indicator: str, country: str, start=None, end=None) -> Series:
        self.calls.append(("series", indicator, country))
        if country == "ZWE":
            raise EconDashPaymentRequired("outside trial", status_code=402)
        if country == "VEN":
            raise EconDashRateLimitError("slow", retry_after=2, status_code=429)
        if country == "EMP":
            return _series(country, points=0)
        return _series(country)


def test_documents_carry_the_metadata_and_a_short_summary() -> None:
    fake = Fake()
    docs = EconDashReader(client=fake).load_data(indicators=["gdp-nominal"], countries=["usa"])
    assert len(docs) == 1
    doc = docs[0]
    assert doc.metadata == {
        "slug": "gdp-nominal",
        "iso3": "USA",
        "source_url": "https://data.worldbank.org/indicator/NY.GDP.MKTP.CD",
        "data_changed_at": "2026-02-02",
        "license": "CC BY 4.0",
    }
    assert "https://econdash.org/chart/gdp-nominal/USA" in doc.text
    assert "source_url: https://data.worldbank.org" in doc.text
    assert "license: CC BY 4.0" in doc.text
    assert "2024-01-01 24.0" in doc.text
    assert "2000-01-01 0.0" not in doc.text
    assert doc.id_ == "econdash:gdp-nominal:USA"


def test_blocked_licence_creates_no_document_and_does_not_fetch_the_series() -> None:
    blocked = _indicator(slug="moex", code="moex__imoex", license_name="не распространять")
    allowed = _indicator()
    fake = Fake({"gdp-nominal": allowed, "moex": blocked})
    docs = EconDashReader(client=fake).load_data(
        indicators=["gdp-nominal", "moex"],
        countries=["USA", "DEU"],
    )
    assert [doc.metadata["slug"] for doc in docs] == ["gdp-nominal", "gdp-nominal"]
    assert [doc.metadata["iso3"] for doc in docs] == ["USA", "DEU"]
    assert all("moex" not in doc.text for doc in docs)
    assert ("series", "moex", "USA") not in fake.calls
    assert ("series", "gdp-nominal", "USA") in fake.calls


def test_known_proprietary_sources_are_skipped() -> None:
    fake = Fake(
        {
            "yahoo": _indicator(
                slug="yahoo", code="yahoo__x", source="Yahoo Finance", license_name="CC BY 4.0"
            ),
            "shiller": _indicator(slug="shiller", code="shiller__x", source="S&P Case-Shiller"),
            "fred": _indicator(
                slug="fred-copy", code="fred__x", license_name="Third-party copyright via FRED"
            ),
            "none-found": _indicator(
                slug="none-found", code="none__x", license_name="No redistribution terms found"
            ),
        }
    )
    docs = EconDashReader(client=fake).load_data(
        indicators=["yahoo", "shiller", "fred-copy", "none-found"],
        countries=["USA"],
    )
    assert docs == []
    assert [call for call in fake.calls if call[0] == "series"] == []


def test_payment_rate_limit_empty_and_unknown_create_no_document() -> None:
    fake = Fake()
    docs = EconDashReader(client=fake).load_data(
        indicators=["missing", "gdp-nominal"],
        countries=["ZWE", "VEN", "EMP", "Germany", "USA"],
    )
    assert len(docs) == 1
    assert docs[0].metadata["iso3"] == "USA"
    assert "24.0" in docs[0].text
    assert "Payment required" not in docs[0].text


def test_string_arguments_and_empty_input() -> None:
    fake = Fake()
    reader = EconDashReader(client=fake)
    assert reader.load_data() == []
    docs = reader.load_data(indicators="gdp-nominal", countries="usa, deu")
    assert [doc.metadata["iso3"] for doc in docs] == ["USA", "DEU"]
