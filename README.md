# econdash

[![PyPI](https://img.shields.io/pypi/v/econdash)](https://pypi.org/project/econdash/)
[![CI](https://github.com/econdash/econdash-python/actions/workflows/ci.yml/badge.svg)](https://github.com/econdash/econdash-python/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/econdash)](https://pypi.org/project/econdash/)

Python client for the [EconDash](https://econdash.org) macroeconomic data API: 750+ indicators
(GDP, inflation, debt, trade, labour, money supply, …) for 290+ countries and regions, with
source, licence and freshness metadata for every series.

```bash
pip install econdash
```

LangChain agents use the separate package [`langchain-econdash`](packages/langchain-econdash)
(`EconDashToolkit`). It calls this client, so the free trial, an API key and pay-per-call
behave the same way. A 402 becomes a sentence for the model instead of a traceback.

```python
from econdash import EconDash

ed = EconDash()  # free trial, no key needed

ed.search_indicators("inflation")[:3]  # -> list[Indicator]
ed.get_indicator("gdp-nominal")  # metadata, source, licence, freshness
s = ed.get_series("gdp-nominal", "USA", start=2000)
s.data[-1]  # Point(date=2025-01-01, value=3.07e13, ...)
ed.list_countries()  # -> list[Country]
ed.top_countries("gdp-nominal", year=2024, limit=10)
ed.cite("gdp-nominal", "USA").citation.text
# 'United States GDP nominal was $30.77 tn in 2025 (World Bank, 2025-01-01)'
```

Indicators can be addressed by slug (`gdp-nominal`, as in
`econdash.org/chart/gdp-nominal/USA`) or by code (`world_bank__gdp_nominal`).
`start`/`end` accept `2000`, `"2000-06"`, `"2000-06-30"` or a `date`.

## Free trial, API key, or pay per call

One URL for everything. Without a key the **free trial** answers right away:

| Limit | Trial |
|---|---|
| Requests | 300 per day, 30 per minute (per IP) |
| Countries | 10: USA, CHN, DEU, JPN, GBR, FRA, IND, BRA, RUS, KOR |
| Indicators | 50 core series (GDP, CPI, money supply, debt, trade, …) |

Anything outside the trial (another country or indicator, or more requests than the free
quota) answers **HTTP 402** with payment options. You can either:

- use an API key (subscription): create one at [econdash.org/dashboard/api-keys](https://econdash.org/dashboard/api-keys)
  ([plans](https://econdash.org/api-access)), then `EconDash(api_key="ed_...")` or set `ECONDASH_API_KEY`;
- or let the client pay for that one call (below).

Without a key or wallet the client raises `EconDashPaymentRequired` for such calls, and
nothing is paid.

### With an API key

A key from an active subscription opens every indicator and country with full history, no
per-IP trial limits, on every method including `cite()`. It allows 10,000 requests per
calendar month; per-endpoint rate limits (60–120 requests per minute) still apply. A wrong
or deactivated key gives `EconDashAuthError` (401), an inactive or expired subscription
`EconDashAuthError` (403), and the monthly quota `EconDashRateLimitError` (429). With a key
the client never pays per call.

## Async

```python
from econdash import AsyncEconDash

async with AsyncEconDash() as ed:
    series = await ed.get_series("cpi-inflation-rate-percent", "DEU", start=2010)
```

## Errors

| Exception | When |
|---|---|
| `EconDashAuthError` | 401/403: wrong or deactivated key, inactive or expired subscription |
| `EconDashNotFound` | 404: unknown indicator or country |
| `EconDashRateLimitError` | 429: monthly key quota or per-minute rate limit, `retry_after` in seconds |
| `EconDashPaymentRequired` | 402: outside the free trial or over its quota. `challenge` holds the x402 requirements, `www_authenticate` the MPP ones. Nothing was paid |
| `EconDashError` | base class, anything else |

## Pay per call (for AI agents)

Agents without an account can pay each call in USDC, about $0.02 per call at the time of
writing. Payments are **off by default**: the client pays only when you pass a wallet
**and** `max_usd_per_call`. Anything more expensive is refused before signing. Calls the free
trial covers are not paid even with a wallet configured; once the free quota is used up, they
are paid like any other call.

| Rail | Install | Wallet argument |
|---|---|---|
| [x402](https://www.x402.org), USDC on Base | `pip install "econdash[x402]"` | `x402_signer=eth_account.Account.from_key(...)` |
| [MPP](https://mpp.dev), USDC on Tempo | `pip install "econdash[tempo]"` (Python 3.11+) | `tempo_account=mpp.methods.tempo.TempoAccount.from_key(...)` |
| MPP, USDC on Solana | `pip install "econdash[solana]"` | `solana_keypair=solders.keypair.Keypair.from_base58_string(...)` |

```python
import os

from econdash import EconDash
from solders.keypair import Keypair

ed = EconDash(
    solana_keypair=Keypair.from_base58_string(os.environ["AGENT_SOLANA_KEY"]),
    max_usd_per_call=0.05,
)
ed.get_series("gdp-nominal", "ZWE")  # outside the trial: one paid call
ed.get_series("gdp-nominal", "USA")  # inside the trial: free
```

You can configure several wallets; on a 402 the client tries x402 (Base), then MPP Tempo,
then MPP Solana, and pays with the first one the API offers within your cap. On Solana the
API broadcasts the signed transfer and answers after confirmation, so a paid call can take
up to ~40 seconds. Keep agent wallets funded with small amounts only.

## Examples

Notebooks in [`examples/`](examples/): search → series → pandas chart, comparing countries,
a LangChain agent, an agent paying per call (x402 / MPP).

## Data and licences

Every `Indicator` carries `source`, `source_url`, `license_name`, `license_url` and
`attribution_text`. Source licences differ (World Bank CC BY 4.0, IMF, OECD, FRED, …);
see [econdash.org/data-license](https://econdash.org/data-license). Please keep the
attribution when you publish charts or numbers.

## Links

- Website: <https://econdash.org>
- API docs: <https://econdash.org/docs>, OpenAPI: <https://econdash.org/openapi.json>
- Python docs: <https://econdash.org/docs/python>

## Development

```bash
uv sync --all-extras
uv run pytest            # offline tests on recorded API answers
uv run pytest -m live    # contract tests against the real API
uv run ruff check . && uv run mypy
```

Releases: bump `__version__`, `CHANGELOG.md` and `CITATION.cff`, then push a tag `vX.Y.Z`;
GitHub Actions publishes to PyPI with trusted publishing (no tokens).

MIT licence. The data itself is licensed by its original sources.
