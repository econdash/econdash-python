"""x402 payments: off by default, capped by max_usd_per_call, one retry with PAYMENT-SIGNATURE."""

import base64
import json

import pytest
import respx

from econdash import AsyncEconDash, EconDash, EconDashPaymentRequired

from .conftest import BASE, load

eth_account = pytest.importorskip("eth_account")
pytest.importorskip("x402")

M2M = f"{BASE}/m2m"


def _402(header: str) -> dict:
    return {
        "status_code": 402,
        "json": load("m2m_402.json"),
        "headers": {"payment-required": header},
    }


def test_requires_signer_and_cap() -> None:
    with pytest.raises(ValueError):
        EconDash(pay_with_x402=True)
    with pytest.raises(ValueError):
        EconDash(pay_with_x402=True, x402_signer=eth_account.Account.create())


@respx.mock
def test_pays_within_cap(payment_required_header: str) -> None:
    acct = eth_account.Account.create()
    route = respx.get(f"{M2M}/countries")
    route.side_effect = [
        respx.MockResponse(**_402(payment_required_header)),
        respx.MockResponse(200, json=load("countries.json")),
    ]
    ed = EconDash(pay_with_x402=True, x402_signer=acct, max_usd_per_call=0.05)
    assert len(ed.list_countries()) == 5
    assert route.call_count == 2
    sig = route.calls[1].request.headers["payment-signature"]
    payload = json.loads(base64.b64decode(sig))
    assert payload["accepted"]["amount"] == "20000"
    assert payload["payload"]["authorization"]["from"].lower() == acct.address.lower()


@respx.mock
def test_refuses_above_cap(payment_required_header: str) -> None:
    route = respx.get(f"{M2M}/countries").respond(**_402(payment_required_header))
    ed = EconDash(
        pay_with_x402=True, x402_signer=eth_account.Account.create(), max_usd_per_call=0.01
    )
    with pytest.raises(EconDashPaymentRequired, match="x402 payment not made"):
        ed.list_countries()
    assert route.call_count == 1  # nothing signed, nothing retried


@respx.mock
def test_second_402_is_raised_not_looped(payment_required_header: str) -> None:
    route = respx.get(f"{M2M}/countries").respond(**_402(payment_required_header))
    ed = EconDash(
        pay_with_x402=True, x402_signer=eth_account.Account.create(), max_usd_per_call=0.05
    )
    with pytest.raises(EconDashPaymentRequired):
        ed.list_countries()
    assert route.call_count == 2


@respx.mock
async def test_async_pays(payment_required_header: str) -> None:
    route = respx.get(f"{M2M}/countries")
    route.side_effect = [
        respx.MockResponse(**_402(payment_required_header)),
        respx.MockResponse(200, json=load("countries.json")),
    ]
    async with AsyncEconDash(
        pay_with_x402=True, x402_signer=eth_account.Account.create(), max_usd_per_call=0.05
    ) as ed:
        assert len(await ed.list_countries()) == 5
    assert "payment-signature" in route.calls[1].request.headers


@respx.mock
def test_cite_stays_on_free_endpoint() -> None:
    route = respx.get(f"{BASE}/cite/USA/gdp-nominal").respond(json=load("cite.json"))
    ed = EconDash(
        pay_with_x402=True, x402_signer=eth_account.Account.create(), max_usd_per_call=0.05
    )
    ed.cite("gdp-nominal", "USA")
    assert route.call_count == 1
