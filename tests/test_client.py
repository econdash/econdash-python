from datetime import date

import httpx
import pytest
import respx

from econdash import (
    AsyncEconDash,
    EconDash,
    EconDashAuthError,
    EconDashError,
    EconDashNotFound,
    EconDashPaymentRequired,
    EconDashRateLimitError,
)
from econdash._client import _date

from .conftest import BASE, load

CODE = "world_bank__gdp_nominal"


@respx.mock
def test_search_indicators_filters_and_caches() -> None:
    route = respx.get(f"{BASE}/indicators").respond(json=load("indicators.json"))
    ed = EconDash()
    hits = ed.search_indicators("inflation")
    assert hits and all("inflation" in (h.name_en or "").lower() + (h.slug or "") for h in hits)
    assert ed.search_indicators("money supply")[0].slug.startswith("money-supply")
    assert ed.search_indicators("no such thing at all") == []
    assert ed.search_indicators("gdp")[0].slug == "gdp-nominal"
    assert ed.search_indicators("GDP real")[0].slug == "gdp-real"
    assert route.call_count == 1
    assert route.calls[0].request.url.params["limit"] == "1200"


@respx.mock
def test_get_series_resolves_slug_once_and_sends_dates() -> None:
    by_slug = respx.get(f"{BASE}/indicators/by-slug/gdp-nominal").respond(
        json=load("indicator.json")
    )
    ts = respx.get(f"{BASE}/timeseries/{CODE}").respond(json=load("series.json"))
    ed = EconDash()
    s = ed.get_series("gdp-nominal", "usa", start="2020", end=2024)
    ed.get_series("gdp-nominal", "USA")
    assert by_slug.call_count == 1
    params = ts.calls[0].request.url.params
    assert dict(params) == {"country": "USA", "start_date": "2020-01-01", "end_date": "2024-12-31"}
    assert s.indicator_code == CODE and s.unit == "Current USD"
    assert s.data[0].date == date(2020, 1, 1) and s.data[0].value > 1e13


@respx.mock
def test_get_series_by_code_skips_lookup() -> None:
    respx.get(f"{BASE}/timeseries/{CODE}").respond(json=load("series.json"))
    assert EconDash().get_series(CODE, "USA").data


@respx.mock
def test_indicator_countries_top_cite() -> None:
    respx.get(f"{BASE}/indicators/{CODE}").respond(json=load("indicator.json"))
    respx.get(f"{BASE}/countries").respond(json=load("countries.json"))
    top = respx.get(f"{BASE}/timeseries/{CODE}/top-countries").respond(
        json=load("top_countries.json")
    )
    respx.get(f"{BASE}/cite/USA/gdp-nominal").respond(json=load("cite.json"))
    ed = EconDash()
    ind = ed.get_indicator(CODE)
    assert ind.slug == "gdp-nominal" and ind.license_name and ind.source_url
    assert ind.url == "https://econdash.org/chart/gdp-nominal"
    assert len(ed.list_countries()) == 5
    t = ed.top_countries(CODE, year=2024, limit=3)
    assert len(t.data) == 3 and dict(top.calls[0].request.url.params) == {
        "limit": "3",
        "year": "2024",
    }
    c = ed.cite("gdp-nominal", "USA")
    assert c.citation.markdown.startswith("[United States GDP nominal")
    assert c.meta.canonical_url == "https://econdash.org/chart/gdp-nominal/USA"


@respx.mock
def test_api_key_header_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECONDASH_API_KEY", "ed_test")
    route = respx.get(f"{BASE}/countries").respond(json=[])
    EconDash().list_countries()
    req = route.calls[0].request
    assert req.headers["authorization"] == "Bearer ed_test"
    assert req.headers["user-agent"].startswith("econdash-python/")


@respx.mock
def test_no_key_sends_no_authorization() -> None:
    route = respx.get(f"{BASE}/countries").respond(json=[])
    EconDash().list_countries()
    assert "authorization" not in route.calls[0].request.headers


@pytest.mark.parametrize(
    ("status", "exc"),
    [
        (401, EconDashAuthError),
        (403, EconDashAuthError),
        (404, EconDashNotFound),
        (500, EconDashError),
    ],
)
@respx.mock
def test_errors(status: int, exc: type[Exception]) -> None:
    respx.get(f"{BASE}/countries").respond(status, json={"detail": "nope"})
    with pytest.raises(exc, match="nope") as ei:
        EconDash().list_countries()
    assert ei.value.status_code == status  # type: ignore[attr-defined]


@respx.mock
def test_rate_limit_retry_after() -> None:
    respx.get(f"{BASE}/countries").respond(
        429, json={"detail": "Trial limit: 30 requests per minute."}, headers={"Retry-After": "60"}
    )
    with pytest.raises(EconDashRateLimitError) as ei:
        EconDash().list_countries()
    assert ei.value.retry_after == 60


@respx.mock
def test_402_raises_with_challenge_and_does_not_pay(payment_required_header: str) -> None:
    route = respx.get(f"{BASE}/countries").respond(
        402,
        json=load("m2m_402.json"),
        headers=[
            ("payment-required", payment_required_header),
            ("www-authenticate", 'Payment method="tempo"'),
            ("www-authenticate", 'Payment method="solana"'),
        ],
    )
    with pytest.raises(EconDashPaymentRequired) as ei:
        EconDash().list_countries()
    assert ei.value.challenge["accepts"][0]["amount"] == "20000"
    assert len(ei.value.www_authenticate) == 2
    assert route.call_count == 1


def test_date_helper() -> None:
    assert _date("2000", end=False) == "2000-01-01"
    assert _date("2000-02", end=True) == "2000-02-29"
    assert _date("2001-12", end=True) == "2001-12-31"
    assert _date(date(2010, 5, 3), end=True) == "2010-05-03"
    assert _date(None, end=True) is None
    with pytest.raises(ValueError):
        _date("20-1", end=False)


@respx.mock
async def test_async_client() -> None:
    respx.get(f"{BASE}/indicators/by-slug/gdp-nominal").respond(json=load("indicator.json"))
    respx.get(f"{BASE}/timeseries/{CODE}").respond(json=load("series.json"))
    respx.get(f"{BASE}/indicators").respond(json=load("indicators.json"))
    respx.get(f"{BASE}/cite/USA/gdp-nominal").respond(json=load("cite.json"))
    respx.get(f"{BASE}/countries").respond(404, json={"detail": "x"})
    async with AsyncEconDash() as ed:
        assert (await ed.get_series("gdp-nominal", "USA", start=2020)).data
        assert (await ed.search_indicators("gdp"))[0].slug == "gdp-nominal"
        assert (await ed.cite("gdp-nominal", "USA")).value > 0
        with pytest.raises(EconDashNotFound):
            await ed.list_countries()


def test_timeout_is_passed() -> None:
    ed = EconDash(timeout=5)
    assert ed._http.timeout == httpx.Timeout(5)
