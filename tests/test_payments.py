"""Pay-per-call on /api/v1: off by default, capped, one paid retry, three rails."""

import base64
import json
from unittest.mock import AsyncMock, patch

import pytest
import respx

from econdash import AsyncEconDash, EconDash, EconDashPaymentRequired

from .conftest import BASE, FIX, load

URL = f"{BASE}/countries"
RPC = "https://api.mainnet-beta.solana.com"
WWW = json.loads((FIX / "mpp_www_authenticate.json").read_text())  # [tempo, solana] from prod


def _402(pr_header: str | None = None, www: bool = True) -> respx.MockResponse:
    headers = [("www-authenticate", h) for h in WWW] if www else []
    if pr_header:
        headers.append(("payment-required", pr_header))
    return respx.MockResponse(402, json=load("m2m_402.json"), headers=headers)


def _ok() -> respx.MockResponse:
    return respx.MockResponse(200, json=load("countries.json"))


def test_consent_needs_wallet_and_cap() -> None:
    eth_account = pytest.importorskip("eth_account")
    with pytest.raises(ValueError):
        EconDash(pay_with_x402=True)
    with pytest.raises(ValueError, match="max_usd_per_call"):
        EconDash(x402_signer=eth_account.Account.create())


@respx.mock
def test_free_trial_data_is_never_paid() -> None:
    eth_account = pytest.importorskip("eth_account")
    route = respx.get(URL).mock(return_value=_ok())
    ed = EconDash(x402_signer=eth_account.Account.create(), max_usd_per_call=0.05)
    assert len(ed.list_countries()) == 5
    assert route.call_count == 1 and "payment-signature" not in route.calls[0].request.headers


# ── x402 (Base) ──────────────────────────────────────────────────────────────


@respx.mock
def test_x402_pays_within_cap(payment_required_header: str) -> None:
    eth_account = pytest.importorskip("eth_account")
    acct = eth_account.Account.create()
    route = respx.get(URL)
    route.side_effect = [_402(payment_required_header), _ok()]
    ed = EconDash(x402_signer=acct, max_usd_per_call=0.05)
    assert len(ed.list_countries()) == 5
    payload = json.loads(base64.b64decode(route.calls[1].request.headers["payment-signature"]))
    assert payload["accepted"]["amount"] == "20000"
    assert payload["payload"]["authorization"]["from"].lower() == acct.address.lower()


@respx.mock
def test_x402_refuses_above_cap(payment_required_header: str) -> None:
    eth_account = pytest.importorskip("eth_account")
    route = respx.get(URL).mock(return_value=_402(payment_required_header, www=False))
    ed = EconDash(x402_signer=eth_account.Account.create(), max_usd_per_call=0.01)
    with pytest.raises(EconDashPaymentRequired, match="payment not made: x402"):
        ed.list_countries()
    assert route.call_count == 1


@respx.mock
def test_second_402_is_raised_not_looped(payment_required_header: str) -> None:
    eth_account = pytest.importorskip("eth_account")
    route = respx.get(URL).mock(return_value=_402(payment_required_header))
    ed = EconDash(x402_signer=eth_account.Account.create(), max_usd_per_call=0.05)
    with pytest.raises(EconDashPaymentRequired):
        ed.list_countries()
    assert route.call_count == 2


# ── MPP Tempo ────────────────────────────────────────────────────────────────


class _Cred:
    def to_authorization(self) -> str:
        return "Payment tempo-credential"


@pytest.fixture
def tempo_account():
    pytest.importorskip("mpp.methods.tempo")
    from mpp.methods.tempo import TempoAccount

    return TempoAccount.from_key("0x" + "11" * 32)


@respx.mock
def test_tempo_pays_within_cap(tempo_account) -> None:
    route = respx.get(URL)
    route.side_effect = [_402(), _ok()]
    with patch(
        "mpp.methods.tempo.client.TempoMethod.create_credential",
        AsyncMock(return_value=_Cred()),
    ) as create:
        ed = EconDash(tempo_account=tempo_account, max_usd_per_call=0.05)
        assert len(ed.list_countries()) == 5
    challenge = create.call_args.args[0]
    assert challenge.method == "tempo" and challenge.request["amount"] == "20000"
    assert route.calls[1].request.headers["authorization"] == "Payment tempo-credential"


@respx.mock
def test_tempo_refuses_above_cap(tempo_account) -> None:
    route = respx.get(URL).mock(return_value=_402())
    with patch("mpp.methods.tempo.client.TempoMethod.create_credential", AsyncMock()) as create:
        ed = EconDash(tempo_account=tempo_account, max_usd_per_call=0.01)
        with pytest.raises(EconDashPaymentRequired, match="tempo asks 0.020000"):
            ed.list_countries()
    create.assert_not_called()
    assert route.call_count == 1


@respx.mock
async def test_tempo_async(tempo_account) -> None:
    route = respx.get(URL)
    route.side_effect = [_402(), _ok()]
    with patch(
        "mpp.methods.tempo.client.TempoMethod.create_credential",
        AsyncMock(return_value=_Cred()),
    ):
        async with AsyncEconDash(tempo_account=tempo_account, max_usd_per_call=0.05) as ed:
            assert len(await ed.list_countries()) == 5
    assert route.calls[1].request.headers["authorization"] == "Payment tempo-credential"


# ── MPP Solana ───────────────────────────────────────────────────────────────

BLOCKHASH = {"jsonrpc": "2.0", "id": 1, "result": {"value": {"blockhash": "1" * 32}}}


@pytest.fixture
def solana_keypair():
    solders = pytest.importorskip("solders.keypair")
    return solders.Keypair()


def _decode_solana(auth: str) -> tuple[dict, object]:
    from solders.transaction import Transaction

    raw = auth.removeprefix("Payment ")
    cred = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    tx = Transaction.from_bytes(base64.b64decode(cred["payload"]["transaction"]))
    return cred, tx


@respx.mock
def test_solana_pays_within_cap(solana_keypair) -> None:
    route = respx.get(URL)
    route.side_effect = [_402(), _ok()]
    rpc = respx.post(RPC).respond(json=BLOCKHASH)
    ed = EconDash(solana_keypair=solana_keypair, max_usd_per_call=0.05)
    assert len(ed.list_countries()) == 5
    assert rpc.call_count == 1
    cred, tx = _decode_solana(route.calls[1].request.headers["authorization"])
    ch = cred["challenge"]
    assert ch["method"] == "solana" and ch["request"]["amount"] == "20000" and ch["expires"]
    assert cred["payload"]["type"] == "transaction"
    assert tx.message.account_keys[0] == solana_keypair.pubkey()  # fee payer and signer
    transfer, memo = tx.message.instructions
    assert int.from_bytes(bytes(transfer.data)[1:9], "little") == 20000
    assert bytes(memo.data).decode() == f"econdash:{ch['id']}"
    tx.verify()  # signature is valid


@respx.mock
def test_solana_refuses_above_cap(solana_keypair) -> None:
    route = respx.get(URL).mock(return_value=_402())
    rpc = respx.post(RPC).respond(json=BLOCKHASH)
    ed = EconDash(solana_keypair=solana_keypair, max_usd_per_call=0.01)
    with pytest.raises(EconDashPaymentRequired, match="solana asks"):
        ed.list_countries()
    assert rpc.call_count == 0 and route.call_count == 1


@respx.mock
async def test_solana_async(solana_keypair) -> None:
    route = respx.get(URL)
    route.side_effect = [_402(), _ok()]
    respx.post(RPC).respond(json=BLOCKHASH)
    async with AsyncEconDash(solana_keypair=solana_keypair, max_usd_per_call=0.05) as ed:
        assert len(await ed.list_countries()) == 5
    assert route.calls[1].request.headers["authorization"].startswith("Payment ")


@respx.mock
def test_falls_back_to_next_rail(solana_keypair) -> None:
    """x402 configured but the 402 offers only MPP: Solana pays."""
    eth_account = pytest.importorskip("eth_account")
    route = respx.get(URL)
    route.side_effect = [_402(www=True), _ok()]
    respx.post(RPC).respond(json=BLOCKHASH)
    ed = EconDash(
        x402_signer=eth_account.Account.create(),
        solana_keypair=solana_keypair,
        max_usd_per_call=0.05,
    )
    assert ed.payment_methods == ["x402", "solana"]
    assert len(ed.list_countries()) == 5
    assert "payment-signature" not in route.calls[1].request.headers
    assert route.calls[1].request.headers["authorization"].startswith("Payment ")
