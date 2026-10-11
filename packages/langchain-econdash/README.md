# langchain-econdash

LangChain tools for [EconDash](https://econdash.org). They call the `econdash` client, so they follow the same access rules. They do not open a free back door to the archive.

```bash
pip install langchain-econdash
```

```python
from langchain_econdash import EconDashToolkit

tools = EconDashToolkit().get_tools()          # free trial
# tools = EconDashToolkit(api_key="ed_...").get_tools()
# from eth_account import Account
# tools = EconDashToolkit(
#     x402_signer=Account.from_key("0x..."), max_usd_per_call=0.05
# ).get_tools()
```

| Tool | What the model gets |
|---|---|
| `econdash_search_indicators` | Slug, name, unit, source, frequency. No numbers. |
| `econdash_get_series` | One country. Last 20 points, unit, freshness, a citation and the chart link. `full=true` for the whole reply. |
| `econdash_get_metadata` | Description, source, licence, freshness, a sample of countries. |
| `econdash_compare_countries` | Latest point for up to 8 ISO3 codes. |

## What is free

Without a key and without a wallet the tools only receive the free trial: 10 countries (USA, CHN, DEU, JPN, GBR, FRA, IND, BRA, RUS, KOR), 50 indicators, 300 requests a day and 30 a minute per IP.

A country or indicator outside that trial makes the API answer 402. The tool turns that into a sentence for the model (`Set ECONDASH_API_KEY` or enable x402/MPP) and does **not** include the figures. Nothing is charged.

The indicator catalog (names and slugs) is metadata and is readable inside the trial quota. The time series is not.

## How to pay

- **API key** from an EconDash subscription (`api_key=` or `ECONDASH_API_KEY`): full archive, no per-call charge, 10,000 requests a month.
- **Wallet:** pass `x402_signer` (Base), `tempo_account` (Tempo) or `solana_keypair` (Solana) **and** `max_usd_per_call`. The client pays one call only when the price is within that cap. If you omit the cap, it refuses to sign. Several wallets are tried in that order.

A wallet on the toolkit means an agent can spend on every series outside the trial, up to the cap. Leave the wallet off unless that is what you want.
