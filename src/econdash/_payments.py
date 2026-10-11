"""Pay-per-call: answer an HTTP 402 with x402 (Base), MPP Tempo or MPP Solana.

Each payer reads its own challenge from the 402, refuses anything above the
per-call cap or in an unknown token, and returns the headers for one retry.
`None` means "this 402 offers nothing for me", so the next payer is tried.
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import json
import re
from typing import Any

import httpx

USDC_DECIMALS = 6
TEMPO_USDC = "0x20c0000000000000000000000000000000000000"
SOLANA_USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
_ATA_PROGRAM = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
_MEMO_PROGRAM = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"
_TRANSFER_CHECKED = 12


class PaymentRefused(Exception):
    """The challenge was found but not paid (above the cap, unknown token, signer error)."""


def _cap_units(max_usd: float) -> int:
    return int(round(max_usd * 1_000_000))  # USDC has 6 decimals on every rail


def _check_amount(amount: Any, max_usd: float, method: str) -> int:
    units = int(amount)
    if units > _cap_units(max_usd):
        raise PaymentRefused(
            f"{method} asks {units / 10**USDC_DECIMALS:.6f} USDC, above max_usd_per_call={max_usd}"
        )
    return units


def _b64url_json(value: str) -> Any:
    return json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))


def _payment_challenges(resp: httpx.Response) -> list[dict[str, str]]:
    """`WWW-Authenticate: Payment k="v", ...` headers as dicts (one challenge per header)."""
    out = []
    for header in resp.headers.get_list("www-authenticate"):
        if header.strip().lower().startswith("payment "):
            out.append(dict(re.findall(r'(\w+)="([^"]*)"', header)))
    return out


def _run_sync(coro: Any) -> Any:
    """Run a coroutine from sync code, also when a loop is already running (Jupyter)."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


# ── x402 (USDC on Base) ──────────────────────────────────────────────────────


class X402Payer:
    method = "x402"

    def __init__(self, signer: Any, max_usd: float, sync: bool) -> None:
        try:
            from x402 import x402Client, x402ClientSync
            from x402.http import x402HTTPClient, x402HTTPClientSync
            from x402.mechanisms.evm.exact import register_exact_evm_client
        except ImportError as e:  # pragma: no cover
            raise ImportError("x402 payments need: pip install 'econdash[x402]'") from e
        client: Any = x402ClientSync() if sync else x402Client()
        register_exact_evm_client(client, signer)
        # x402 itself refuses to sign above this cap.
        client.set_spend_controls({"max_amount_per_payment": f"${max_usd}"})
        self._http: Any = x402HTTPClientSync(client) if sync else x402HTTPClient(client)

    def _args(self, resp: httpx.Response) -> tuple[dict[str, str], bytes, str] | None:
        if not resp.headers.get("payment-required"):
            return None
        return dict(resp.headers), resp.content, str(resp.request.url)

    def headers(self, resp: httpx.Response, http: httpx.Client) -> dict[str, str] | None:
        args = self._args(resp)
        if args is None:
            return None
        try:
            pay, _ = self._http.handle_402_response(*args)
        except Exception as e:
            raise PaymentRefused(f"x402: {e}") from e
        return dict(pay)

    async def aheaders(
        self, resp: httpx.Response, http: httpx.AsyncClient
    ) -> dict[str, str] | None:
        args = self._args(resp)
        if args is None:
            return None
        try:
            pay, _ = await self._http.handle_402_response(*args)
        except Exception as e:
            raise PaymentRefused(f"x402: {e}") from e
        return dict(pay)


# ── MPP Tempo (USDC on Tempo, via the official pympp client) ─────────────────


class TempoPayer:
    method = "tempo"

    def __init__(self, account: Any, max_usd: float) -> None:
        try:
            from mpp import Challenge
            from mpp.methods.tempo import ChargeIntent, tempo
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "MPP Tempo payments need Python 3.11+ and: pip install 'econdash[tempo]'"
            ) from e
        self._challenge_cls = Challenge
        self._method = tempo(account=account, intents={"charge": ChargeIntent()})
        self._max_usd = max_usd

    async def _create(self, resp: httpx.Response) -> dict[str, str] | None:
        for header in resp.headers.get_list("www-authenticate"):
            if 'method="tempo"' not in header:
                continue
            challenge = self._challenge_cls.from_www_authenticate(header)
            req = challenge.request
            if str(req.get("currency", "")).lower() != TEMPO_USDC:
                raise PaymentRefused(f"tempo: unknown currency {req.get('currency')}")
            _check_amount(req["amount"], self._max_usd, "tempo")
            try:
                credential = await self._method.create_credential(challenge)
            except Exception as e:
                raise PaymentRefused(f"tempo: {e}") from e
            name = getattr(challenge, "credential_header", None) or "Authorization"
            return {name: credential.to_authorization()}
        return None

    def headers(self, resp: httpx.Response, http: httpx.Client) -> dict[str, str] | None:
        result: dict[str, str] | None = _run_sync(self._create(resp))
        return result

    async def aheaders(
        self, resp: httpx.Response, http: httpx.AsyncClient
    ) -> dict[str, str] | None:
        return await self._create(resp)


# ── MPP Solana (USDC on Solana: TransferChecked + memo, server broadcasts) ──


class SolanaPayer:
    method = "solana"

    def __init__(self, keypair: Any, max_usd: float, rpc_url: str = SOLANA_RPC_URL) -> None:
        try:
            import solders  # noqa: F401
        except ImportError as e:  # pragma: no cover
            raise ImportError("MPP Solana payments need: pip install 'econdash[solana]'") from e
        self._keypair = keypair
        self._max_usd = max_usd
        self._rpc_url = rpc_url

    def _challenge(self, resp: httpx.Response) -> dict[str, Any] | None:
        for ch in _payment_challenges(resp):
            if ch.get("method") != "solana":
                continue
            req = _b64url_json(ch["request"])
            if req.get("currency") != SOLANA_USDC:
                raise PaymentRefused(f"solana: unknown currency {req.get('currency')}")
            _check_amount(req["amount"], self._max_usd, "solana")
            return {**ch, "request": req}
        return None

    def _authorization(self, ch: dict[str, Any], blockhash: str) -> dict[str, str]:
        tx = build_solana_transfer(
            self._keypair,
            recipient=ch["request"]["recipient"],
            amount=int(ch["request"]["amount"]),
            memo=f"econdash:{ch['id']}",
            blockhash=blockhash,
        )
        challenge: dict[str, Any] = {
            k: ch[k] for k in ("id", "realm", "method", "intent") if k in ch
        }
        challenge["request"] = ch["request"]
        if ch.get("expires"):
            challenge["expires"] = ch["expires"]
        credential = {
            "challenge": challenge,
            "payload": {"type": "transaction", "transaction": base64.b64encode(tx).decode()},
        }
        raw = json.dumps(credential, separators=(",", ":"), ensure_ascii=False).encode()
        return {"Authorization": "Payment " + base64.urlsafe_b64encode(raw).decode().rstrip("=")}

    _BLOCKHASH = {"jsonrpc": "2.0", "id": 1, "method": "getLatestBlockhash", "params": []}

    def headers(self, resp: httpx.Response, http: httpx.Client) -> dict[str, str] | None:
        ch = self._challenge(resp)
        if ch is None:
            return None
        try:
            r = http.post(self._rpc_url, json=self._BLOCKHASH)
            blockhash = r.json()["result"]["value"]["blockhash"]
        except Exception as e:
            raise PaymentRefused(f"solana: blockhash: {e}") from e
        return self._authorization(ch, blockhash)

    async def aheaders(
        self, resp: httpx.Response, http: httpx.AsyncClient
    ) -> dict[str, str] | None:
        ch = self._challenge(resp)
        if ch is None:
            return None
        try:
            r = await http.post(self._rpc_url, json=self._BLOCKHASH)
            blockhash = r.json()["result"]["value"]["blockhash"]
        except Exception as e:
            raise PaymentRefused(f"solana: blockhash: {e}") from e
        return self._authorization(ch, blockhash)


def build_solana_transfer(
    keypair: Any, *, recipient: str, amount: int, memo: str, blockhash: str
) -> bytes:
    """Signed legacy transaction: USDC TransferChecked to the recipient's ATA + memo."""
    from solders.hash import Hash
    from solders.instruction import AccountMeta, Instruction
    from solders.pubkey import Pubkey
    from solders.transaction import Transaction

    token, ata_prog, mint = (
        Pubkey.from_string(x) for x in (_TOKEN_PROGRAM, _ATA_PROGRAM, SOLANA_USDC)
    )
    owner = keypair.pubkey()

    def ata(wallet: Any) -> Any:
        return Pubkey.find_program_address([bytes(wallet), bytes(token), bytes(mint)], ata_prog)[0]

    transfer = Instruction(
        program_id=token,
        accounts=[
            AccountMeta(ata(owner), is_signer=False, is_writable=True),
            AccountMeta(mint, is_signer=False, is_writable=False),
            AccountMeta(ata(Pubkey.from_string(recipient)), is_signer=False, is_writable=True),
            AccountMeta(owner, is_signer=True, is_writable=False),
        ],
        data=bytes([_TRANSFER_CHECKED]) + amount.to_bytes(8, "little") + bytes([USDC_DECIMALS]),
    )
    note = Instruction(
        program_id=Pubkey.from_string(_MEMO_PROGRAM),
        accounts=[AccountMeta(owner, is_signer=True, is_writable=False)],
        data=memo.encode(),
    )
    tx = Transaction.new_signed_with_payer(
        [transfer, note], owner, [keypair], Hash.from_string(blockhash)
    )
    return bytes(tx)
