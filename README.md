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

```python
from econdash import EconDash

ed = EconDash()  # free trial, no key needed

ed.search_indicators("inflation")[:3]  # -> list[Indicator]
ed.get_indicator("gdp-nominal")  # metadata, source, licence, freshness
s = ed.get_series("gdp-nominal", "USA", start=2000)
s.data[-1]  # Point(date=2025-01-01, value=3.07e13, ...)
ed.list_countries()  # -> list[Country]
ed.top_countries("gdp-nominal", year=2024, limit=10)
ed.cite(
    "gdp-nominal", "USA"
).citation.text  # 'United States GDP nominal was $30.77 tn in 2025 (World Bank, ...)'
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

- use an API key: create one at [econdash.org/dashboard/api-keys](https://econdash.org/dashboard/api-keys)
  ([plans](https://econdash.org/api-access)), then `EconDash(api_key="ed_...")` or set `ECONDASH_API_KEY`;
- or let the client pay for that one call (below).

Without a key or wallet the client raises `EconDashPaymentRequired` for such calls, and
nothing is paid.

## Async

```python
from econdash import AsyncEconDash

async with AsyncEconDash() as ed:
    series = await ed.get_series("cpi-inflation-rate-percent", "DEU", start=2010)
```

## Errors

| Exception | When |
|---|---|
| `EconDashAuthError` | 401/403: bad key, inactive subscription, data outside the trial |
| `EconDashNotFound` | 404: unknown indicator or country |
| `EconDashRateLimitError` | 429, `retry_after` in seconds |
| `EconDashPaymentRequired` | 402, `challenge` holds the x402 payment requirements |
| `EconDashError` | base class, anything else |

## Pay per call (for AI agents)

Agents without an account can pay each call in USDC, about $0.02 per call at the time of
writing. Payments are **off by default**: the client pays only when you pass a wallet
**and** `max_usd_per_call`. Anything more expensive is refused before signing. Free trial
data is never paid for, even with a wallet configured.

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
a LangChain agent, an agent paying with x402.

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

Releases are published to PyPI from GitHub Actions on a GitHub Release (trusted publishing).

MIT licence. The data itself is licensed by its original sources.
