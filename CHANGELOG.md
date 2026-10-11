# Changelog

All notable changes to this project are documented here. The project follows
[Semantic Versioning](https://semver.org/).

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
