"""Contract tests against the real API (trial). Run: pytest -m live.

Every field the API returns must be modelled, and every required model field must be
returned, so schema drift on either side fails here instead of silently dropping data.
Paid tests run only with funded test wallets: ECONDASH_TEST_X402_KEY (Base),
ECONDASH_TEST_TEMPO_KEY (Tempo), ECONDASH_TEST_SOLANA_KEY (Solana, base58).
"""

import os
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from econdash import (
    Citation,
    Country,
    EconDash,
    EconDashPaymentRequired,
    Indicator,
    Point,
    Series,
    TopCountries,
    TopCountry,
)

pytestmark = pytest.mark.live
BASE = os.environ.get("ECONDASH_BASE_URL", "https://econdash.org/api/v1")


def _raw(path: str, **params: Any) -> Any:
    r = httpx.get(BASE + path, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _same_fields(model: type[BaseModel], obj: dict[str, Any]) -> None:
    fields = model.model_fields
    required = {k for k, f in fields.items() if f.is_required()}
    assert set(obj) - set(fields) == set(), f"{model.__name__}: unmodelled fields"
    assert required - set(obj) == set(), f"{model.__name__}: missing required fields"
    for k, f in fields.items():
        sub = f.annotation
        if isinstance(sub, type) and issubclass(sub, BaseModel) and isinstance(obj.get(k), dict):
            _same_fields(sub, obj[k])


@pytest.fixture(scope="module")
def ed() -> EconDash:
    return EconDash(base_url=BASE)


def test_indicators(ed: EconDash) -> None:
    raw = _raw("/indicators", limit=5)
    for row in raw:
        _same_fields(Indicator, row)
    assert len(ed.list_indicators()) > 500
    assert ed.search_indicators("gdp nominal")[0].slug == "gdp-nominal"
    ind = ed.get_indicator("gdp-nominal")
    assert ind.code == "world_bank__gdp_nominal" and ind.source_url


def test_series(ed: EconDash) -> None:
    raw = _raw("/timeseries/world_bank__gdp_nominal", country="USA", start_date="2020-01-01")
    _same_fields(Series, raw)
    _same_fields(Point, raw["data"][0])
    s = ed.get_series("gdp-nominal", "USA", start=2020, end=2022)
    assert [p.date.year for p in s.data] == [2020, 2021, 2022]


def test_countries_top_cite(ed: EconDash) -> None:
    raw = _raw("/countries")
    _same_fields(Country, raw[0])
    assert any(c.iso3_code == "USA" for c in ed.list_countries())

    raw = _raw("/timeseries/world_bank__gdp_nominal/top-countries", limit=3)
    _same_fields(TopCountries, raw)
    _same_fields(TopCountry, raw["data"][0])
    assert len(ed.top_countries("gdp-nominal", limit=3).data) == 3

    _same_fields(Citation, _raw("/cite/USA/gdp-nominal"))
    assert ed.cite("gdp-nominal", "USA").citation.text


def test_outside_trial_is_402_with_all_rails(ed: EconDash) -> None:
    with pytest.raises(EconDashPaymentRequired) as ei:
        ed.get_series("world_bank__gdp_nominal", "ZWE")
    assert ei.value.challenge["accepts"][0]["network"] == "eip155:8453"
    methods = " ".join(ei.value.www_authenticate)
    assert 'method="tempo"' in methods and 'method="solana"' in methods


def _paid_zwe(**wallet: Any) -> None:
    """Spends one real call (about $0.02 USDC) and gets data outside the free trial."""
    with EconDash(base_url=BASE, max_usd_per_call=0.05, **wallet) as paid:
        s = paid.get_series("world_bank__gdp_nominal", "ZWE", start=2020)
    assert s.data and s.data[0].country == "ZWE"


@pytest.mark.skipif(not os.environ.get("ECONDASH_TEST_X402_KEY"), reason="no Base test wallet")
def test_x402_real_payment() -> None:
    from eth_account import Account

    _paid_zwe(x402_signer=Account.from_key(os.environ["ECONDASH_TEST_X402_KEY"]))


@pytest.mark.skipif(not os.environ.get("ECONDASH_TEST_TEMPO_KEY"), reason="no Tempo test wallet")
def test_tempo_real_payment() -> None:
    from mpp.methods.tempo import TempoAccount

    _paid_zwe(tempo_account=TempoAccount.from_key(os.environ["ECONDASH_TEST_TEMPO_KEY"]))


@pytest.mark.skipif(not os.environ.get("ECONDASH_TEST_SOLANA_KEY"), reason="no Solana test wallet")
def test_solana_real_payment() -> None:
    from solders.keypair import Keypair

    _paid_zwe(solana_keypair=Keypair.from_base58_string(os.environ["ECONDASH_TEST_SOLANA_KEY"]))
