# crewai-econdash

[CrewAI](https://www.crewai.com) tools for [EconDash](https://econdash.org). They call the `econdash` client, so they follow the same access rules. They do not open a free back door to the archive.

```bash
pip install crewai-econdash
```

Releases are tags `crewai-vX.Y.Z` on `econdash-python` (the `X.Y.Z` matches this
package's version). A `v*` tag publishes the `econdash` client, not this package.

```python
from econdash import EconDash
from crewai_econdash import EconDashCompareTool, EconDashSearchTool, EconDashSeriesTool

client = EconDash()                        # free trial, or ECONDASH_API_KEY from env
# client = EconDash(api_key="ed_...")
# from eth_account import Account
# client = EconDash(x402_signer=Account.from_key("0x..."), max_usd_per_call=0.05)

tools = [
    EconDashSearchTool(client=client),
    EconDashSeriesTool(client=client),
    EconDashCompareTool(client=client),
]
```

Each tool builds its own `EconDash()` when you pass no client.

| Tool | Name the model sees | What the model gets |
|---|---|---|
| `EconDashSearchTool` | `econdash_search_indicators` | Slug, name, unit, source, frequency. No numbers. |
| `EconDashSeriesTool` | `econdash_get_series` | One country. Last 20 points, unit, freshness, a citation and the econdash.org chart link. `full=true` for the whole reply. |
| `EconDashCompareTool` | `econdash_compare_countries` | Latest point and chart link for 1–8 ISO3 codes, each fetched on its own. |

## What is free

Without a key and without a wallet the tools only receive the free trial: 10 countries (USA, CHN, DEU, JPN, GBR, FRA, IND, BRA, RUS, KOR), 50 indicators, 300 requests a day and 30 a minute per IP.

A country or indicator outside that trial makes the API answer 402. The tool turns that into a sentence for the agent and does **not** include the figures. Nothing is charged. A 429 becomes "Rate limit reached" with the wait time. Bad ISO3 codes and dates are answered with a hint, not an exception.

## How to pay

- **API key** from an EconDash subscription (`api_key=` or `ECONDASH_API_KEY`): full archive, no per-call charge.
- **Wallet** on the client (`x402_signer`, `tempo_account` or `solana_keypair`) together with `max_usd_per_call`: pays per call, only when the price is within the cap. See the [econdash README](https://github.com/econdash/econdash-python#pay-per-call-for-ai-agents).

## Example crew

[`examples/crewai_macro_research.py`](examples/crewai_macro_research.py): a researcher agent collects GDP growth, inflation and unemployment for a country and compares it with USA and JPN; an analyst agent writes a short brief with every figure linked to its econdash.org chart.

```bash
export MODEL=gpt-4.1-mini OPENAI_API_KEY=...   # any model CrewAI supports
python examples/crewai_macro_research.py DEU
```
