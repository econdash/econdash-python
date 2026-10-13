# Changelog

All notable changes to this project are documented here. The project follows
[Semantic Versioning](https://semver.org/).

## llama-index-tools-econdash 0.1.1 - 2026-10-13

### Fixed
- Tool arguments accept what the ECO-123 model runs actually sent: an extra field,
  `limit` 0, a year as `"2020"` or `2023.0`, a bad date as text, and a country list
  pasted as JSON text. Uses the `econdash` 0.2.4 normaliser.

## [0.2.4] - 2026-10-13

### Fixed
- Agent argument normaliser: a country list sent as the text `["DEU","JPN"]` or
  `['DEU', 'JPN']` is read as ISO3 codes. The strings `None`, `null` and `latest`
  in a start or end date mean "not set", same as an empty value.

## [0.2.3] - 2026-10-13

### Added
- `econdash.agent_text`: the four tool descriptions, compact formatters and the
  redistribution check shared by the agent integrations. An empty licence is not a ban.
  "No redistribution", "не распространять", third-party copyright, Yahoo terms, Yahoo
  Finance, Case-Shiller and ICE / Trading Economics are.
- Companion package `packages/llama-index-tools-econdash` (PyPI name
  `llama-index-tools-econdash`): `EconDashToolSpec` (search, series, metadata, compare)
  and `EconDashReader` for a RAG index. Tool descriptions come from `econdash.agent_text`.
  The reader skips a series the licence forbids and does not fetch its observations.
  402 and 429 on the tools are text for the model, with no figures.

### Changed
- `langchain-econdash` 0.1.3 reads those four descriptions from `econdash.agent_text`
  instead of keeping a second copy. The sentences are unchanged. It now depends on
  `econdash>=0.2.3`.

## Companion packages 0.1.2 - 2026-10-12

### Fixed
- `crewai-econdash` and `langchain-econdash` accept arguments the way models send them:
  a country list as `"USA, DEU"` or `"USA DEU"`, padded or lower-case ISO3 codes, `null`
  for optional fields, `limit` out of range (clamped to 1-20), a year as `"2023"` or
  `"latest"`. A bad date or an empty country list is answered with text, not an exception.
- `langchain-econdash`: `ainvoke` runs the same code as `invoke` (LangChain's default
  thread executor), so async no longer drops the chart link for indicator codes.
  `EconDashToolkit` no longer creates an `AsyncEconDash` client.
- `langchain-econdash`: `econdash_compare_countries` gives the econdash.org chart link per
  country. Without it one model wrote a link from memory.
- `crewai-econdash`: 0 or more than 8 countries is a text answer, as in LangChain.

### Added
- CI runs both companion packages on Python 3.10-3.13 against the econdash in the same
  commit; the nightly live job checks the tools against the real API.

## Companion packages 0.1.1 - 2026-10-12

### Fixed
- `crewai-econdash` and `langchain-econdash`: `econdash_get_series` accepts `start`/`end` as
  a number (`2020`) as well as a string. Models often send a year as a JSON number, and the
  tool used to fail argument validation.

## [0.2.2] - 2026-10-12

### Fixed
- `search_indicators` ranking: a word found in the name or slug counts double against one
  found only in the description, and at equal score series that cover only a few countries
  go after cross-country ones. "inflation" now returns CPI inflation first, not the US-only
  daily breakeven series; "interest rate" no longer ranks government debt second.

### Added
- Companion package `packages/langchain-econdash` (PyPI name `langchain-econdash`):
  four LangChain tools over this client. Outside the free trial they return a payment
  hint and no figures, unless the caller passed an API key or a wallet with `max_usd_per_call`.
- Companion package `packages/crewai-econdash` (PyPI name `crewai-econdash`): three CrewAI
  tools (`EconDashSearchTool`, `EconDashSeriesTool`, `EconDashCompareTool`) and an example
  research crew. Same access rules as the client; 402 and 429 become text for the agent.

## [0.2.1] - 2026-10-11

### Fixed
- Docs: what an API key gives (full access, 10,000 requests/month, `cite()` included),
  corrected error descriptions (`EconDashAuthError` is key/subscription only; outside the
  trial is `EconDashPaymentRequired`), trial calls are free only within the free quota,
  release process. The API now meters keys on `/cite` too.

## [0.2.0] - 2026-10-11

### Added
- Pay per call with **MPP on Tempo** (`tempo_account=`, extra `econdash[tempo]`, Python 3.11+,
  official `pympp` client) and **MPP on Solana** (`solana_keypair=`, extra `econdash[solana]`).
- Several wallets at once: on a 402 the client tries x402, Tempo, Solana in that order.
- `EconDash.payment_methods` lists the configured rails.

### Changed
- One URL for everything: requests go to `/api/v1`, where free trial data is free and
  anything else answers 402 with payment options. Paid calls no longer go to `/api/v1/m2m`,
  so calls the free trial covers are not paid.
- Outside the trial without a key or wallet the client now raises `EconDashPaymentRequired`
  (the API answers 402 instead of 403).
- `x402_signer` alone enables x402; `pay_with_x402=True` still works but is optional.
  `max_usd_per_call` is required whenever a wallet is passed.

## [0.1.2] - 2026-10-11

### Changed
- `search_indicators` matches any query word and ranks by how many words matched, so
  agent-style queries like `"Germany inflation"` find inflation indicators instead of nothing.

## [0.1.1] - 2026-10-11

### Fixed
- `search_indicators` ranks exact slug matches and names starting with the query first
  (`"gdp"` now returns GDP nominal before CO2 per unit GDP).

## [0.1.0] - 2026-10-11

### Added
- `EconDash` (sync) and `AsyncEconDash` (async) clients on httpx.
- `search_indicators`, `list_indicators`, `get_indicator`, `get_series`, `list_countries`,
  `top_countries`, `cite`.
- Pydantic v2 models: `Indicator`, `Series`, `Point`, `Country`, `TopCountries`, `TopCountry`,
  `Citation`.
- Exceptions: `EconDashAuthError`, `EconDashNotFound`, `EconDashRateLimitError` (`retry_after`),
  `EconDashPaymentRequired` (decoded x402 challenge).
- Optional x402 pay-per-call (`econdash[x402]`), off by default and capped by `max_usd_per_call`.
- Free trial works without an API key; `ECONDASH_API_KEY` or `api_key=` for full access.
