# llama-index-tools-econdash

LlamaIndex tools and a reader for [EconDash](https://econdash.org). They call the `econdash` client, so they follow the same access rules. They cover time series across ten categories: macroeconomics, financial markets, labor, demographics, real estate, energy, transport, healthcare, education and technology.

```bash
pip install llama-index-tools-econdash
```

Releases are tags `llamaindex-vX.Y.Z` on `econdash-python` (the `X.Y.Z` matches this
package's version). A `v*` tag publishes the `econdash` client, not this package.
LlamaIndex no longer accepts new integration packages in `run-llama/llama_index`,
so this package lives here and is published to PyPI on its own.

```python
from llama_index.tools.econdash import EconDashReader, EconDashToolSpec

tools = EconDashToolSpec().to_tool_list()  # free trial
# tools = EconDashToolSpec(api_key="ed_...").to_tool_list()

docs = EconDashReader().load_data(
    indicators=["gdp-nominal"],
    countries=["USA", "DEU"],
)
```

| Tool | What the model gets |
|---|---|
| `search_indicators` | Slug, name, unit, source, frequency. No numbers. |
| `get_series` | One country. Last 20 points, unit, freshness, a citation and the chart link. `full=true` for the whole reply. |
| `get_metadata` | Description, source, licence, freshness, a sample of countries. |
| `compare_countries` | Latest point and chart link for 1–8 ISO3 codes, each fetched on its own. |

`EconDashReader.load_data` returns one LlamaIndex `Document` per indicator and country.
The text is that same short summary plus the source and the licence. Metadata is
`slug`, `iso3`, `source_url`, `data_changed_at` and `license`. A series whose
licence forbids redistribution (Yahoo Finance, Case-Shiller, ICE / Trading Economics, a
third-party copyright, "no redistribution" or "не распространять") is skipped, and the
observations are not fetched.

The tool descriptions are the `econdash.agent_text` sentences shared with the
LangChain tools. Only the name of the search tool differs (`search_indicators`
here, `econdash_search_indicators` in LangChain).

## What is free

Without a key and without a wallet the tools only receive the free trial: 10 countries (USA, CHN, DEU, JPN, GBR, FRA, IND, BRA, RUS, KOR), 50 indicators, 300 requests a day and 30 a minute per IP.

A country or indicator outside that trial makes the API answer 402. The tool turns that into a sentence for the model (`Set ECONDASH_API_KEY` or enable x402/MPP) and does not include the figures. Nothing is charged. The reader skips that pair instead of indexing the error.

## How to pay

- **API key** from an EconDash subscription (`api_key=` or `ECONDASH_API_KEY`): full archive, no per-call charge, 10,000 requests a month.
- **Wallet:** pass `x402_signer` (Base), `tempo_account` (Tempo) or `solana_keypair` (Solana) **and** `max_usd_per_call` on the client. The client pays one call only when the price is within that cap.

A wallet means an agent can spend on every series outside the trial, up to the cap. Leave the wallet off unless that is what you want.

Examples: `examples/llamaindex_agent.ipynb` and `examples/llamaindex_rag.ipynb`.
