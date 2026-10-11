from __future__ import annotations

import base64
import json
import os
from datetime import date
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, TypeAdapter

from . import __version__
from .errors import (
    EconDashAuthError,
    EconDashError,
    EconDashNotFound,
    EconDashPaymentRequired,
    EconDashRateLimitError,
)
from .models import Citation, Country, Indicator, Series, TopCountries

DEFAULT_BASE_URL = "https://econdash.org/api/v1"
M = TypeVar("M", bound=BaseModel)
DateLike = str | int | date


def _date(value: DateLike | None, *, end: bool) -> str | None:
    """'2000' -> 2000-01-01 (start) / 2000-12-31 (end); '2000-06' -> month bounds."""
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    s = str(value)
    if len(s) == 4 and s.isdigit():
        return f"{s}-12-31" if end else f"{s}-01-01"
    if len(s) == 7:
        if not end:
            return f"{s}-01"
        y, m = int(s[:4]), int(s[5:])
        nxt = date(y + m // 12, m % 12 + 1, 1)
        return date.fromordinal(nxt.toordinal() - 1).isoformat()
    return date.fromisoformat(s).isoformat()


def _is_code(indicator: str) -> bool:
    # Codes look like "world_bank__gdp_nominal", slugs like "gdp-nominal".
    return "__" in indicator


def _search(indicators: list[Indicator], query: str, limit: int) -> list[Indicator]:
    words = query.lower().split()
    hits = []
    for ind in indicators:
        hay = " ".join(
            x or ""
            for x in (
                ind.name_en,
                ind.name_ru,
                ind.slug,
                ind.code,
                ind.category,
                ind.source,
                ind.description,
            )
        ).lower()
        if all(w in hay for w in words):
            hits.append(ind)
    q = query.lower()
    slug = "-".join(words)

    def rank(i: Indicator) -> tuple[bool, bool, bool, int]:
        name = (i.name_en or "").lower()
        return (i.slug != slug, not name.startswith(q), q not in name, -i.data_points)

    hits.sort(key=rank)
    return hits[:limit]


def _payment_required(resp: httpx.Response, message: str) -> EconDashPaymentRequired:
    challenge = None
    raw = resp.headers.get("payment-required")
    if raw:
        try:
            challenge = json.loads(base64.b64decode(raw))
        except ValueError:
            challenge = None
    return EconDashPaymentRequired(
        message,
        challenge=challenge,
        www_authenticate=resp.headers.get_list("www-authenticate"),
        status_code=402,
        body=_body(resp),
    )


def _body(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return resp.text


def _check(resp: httpx.Response) -> Any:
    if resp.is_success:
        return resp.json()
    body = _body(resp)
    detail = body.get("detail") if isinstance(body, dict) else None
    msg = f"{resp.status_code}: {detail or body}"
    code = resp.status_code
    if code == 402:
        raise _payment_required(resp, msg)
    if code in (401, 403):
        raise EconDashAuthError(msg, status_code=code, body=body)
    if code == 404:
        raise EconDashNotFound(msg, status_code=code, body=body)
    if code == 429:
        ra = resp.headers.get("retry-after")
        raise EconDashRateLimitError(
            msg, retry_after=int(ra) if ra and ra.isdigit() else None, status_code=code, body=body
        )
    raise EconDashError(msg, status_code=code, body=body)


def _x402_client(signer: Any, max_usd_per_call: float, sync: bool) -> Any:
    try:
        from x402 import x402Client, x402ClientSync
        from x402.http import x402HTTPClient, x402HTTPClientSync
        from x402.mechanisms.evm.exact import register_exact_evm_client
    except ImportError as e:  # pragma: no cover
        raise ImportError("x402 payments need the extra: pip install 'econdash[x402]'") from e
    client: Any = x402ClientSync() if sync else x402Client()
    register_exact_evm_client(client, signer)
    # x402 refuses to sign anything above this cap; nothing is paid then.
    client.set_spend_controls({"max_amount_per_payment": f"${max_usd_per_call}"})
    return x402HTTPClientSync(client) if sync else x402HTTPClient(client)


class _Base:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        pay_with_x402: bool = False,
        x402_signer: Any = None,
        max_usd_per_call: float | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("ECONDASH_API_KEY") or None
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {"User-Agent": f"econdash-python/{__version__}"}
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"
        if pay_with_x402 and (x402_signer is None or not max_usd_per_call):
            raise ValueError("pay_with_x402=True needs x402_signer and max_usd_per_call")
        self.pay_with_x402 = pay_with_x402
        self._x402_signer = x402_signer
        self._max_usd = max_usd_per_call or 0.0
        # Paid (x402) access lives under /m2m; plain /api/v1 answers trial limits, not 402.
        self._data = self.base_url + ("/m2m" if pay_with_x402 else "")
        self._indicators: list[Indicator] | None = None
        self._codes: dict[str, str] = {}

    def _x402_for(self, sync: bool) -> Any:
        if not self.pay_with_x402:
            return None
        return _x402_client(self._x402_signer, self._max_usd, sync=sync)

    def _remember(self, ind: Indicator) -> Indicator:
        if ind.slug:
            self._codes[ind.slug] = ind.code
        return ind

    @staticmethod
    def _one(model: type[M], data: Any) -> M:
        return model.model_validate(data)

    @staticmethod
    def _many(model: type[M], data: Any) -> list[M]:
        return TypeAdapter(list[model]).validate_python(data)  # type: ignore[valid-type]

    def _series_params(
        self, country: str, start: DateLike | None, end: DateLike | None
    ) -> dict[str, str]:
        params = {"country": country.upper()}
        if (s := _date(start, end=False)) is not None:
            params["start_date"] = s
        if (e := _date(end, end=True)) is not None:
            params["end_date"] = e
        return params


class EconDash(_Base):
    """Synchronous client.

    >>> ed = EconDash()                      # trial, or ECONDASH_API_KEY from env
    >>> ed.get_series("gdp-nominal", "USA", start=2000).data[-1].value
    """

    def __init__(self, api_key: str | None = None, **kw: Any) -> None:
        super().__init__(api_key, **kw)
        self._http = httpx.Client(headers=self.headers, timeout=self.timeout)
        self._x402 = self._x402_for(sync=True)

    def __enter__(self) -> EconDash:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        resp = self._http.get(url, params=params)
        if resp.status_code == 402 and self._x402 is not None:
            try:
                pay, _ = self._x402.handle_402_response(
                    dict(resp.headers), resp.content, str(resp.request.url)
                )
            except Exception as e:
                raise _payment_required(resp, f"x402 payment not made: {e}") from e
            resp = self._http.get(url, params=params, headers=pay)
        return _check(resp)

    def _code(self, indicator: str) -> str:
        if _is_code(indicator):
            return indicator
        if indicator not in self._codes:
            self.get_indicator(indicator)
        return self._codes[indicator]

    def list_indicators(self) -> list[Indicator]:
        """All active indicators (cached per client)."""
        if self._indicators is None:
            data = self._get(f"{self._data}/indicators", {"limit": 1200})
            self._indicators = [self._remember(i) for i in self._many(Indicator, data)]
        return self._indicators

    def search_indicators(self, query: str, *, limit: int = 20) -> list[Indicator]:
        """Case-insensitive search over names, slugs, codes, categories and sources."""
        return _search(self.list_indicators(), query, limit)

    def get_indicator(self, indicator: str) -> Indicator:
        """Metadata by slug ("gdp-nominal") or code ("world_bank__gdp_nominal")."""
        path = indicator if _is_code(indicator) else f"by-slug/{indicator}"
        return self._remember(self._one(Indicator, self._get(f"{self._data}/indicators/{path}")))

    def get_series(
        self,
        indicator: str,
        country: str,
        *,
        start: DateLike | None = None,
        end: DateLike | None = None,
    ) -> Series:
        """Time series for one country. `start`/`end`: 2000, "2000-06" or "2000-06-30"."""
        url = f"{self._data}/timeseries/{self._code(indicator)}"
        return self._one(Series, self._get(url, self._series_params(country, start, end)))

    def list_countries(self) -> list[Country]:
        return self._many(Country, self._get(f"{self._data}/countries"))

    def top_countries(
        self, indicator: str, *, year: int | None = None, limit: int = 10
    ) -> TopCountries:
        """Ranking by the latest value (or by `year`). Includes aggregates like WLD."""
        params: dict[str, Any] = {"limit": limit}
        if year is not None:
            params["year"] = year
        url = f"{self._data}/timeseries/{self._code(indicator)}/top-countries"
        return self._one(TopCountries, self._get(url, params))

    def cite(self, indicator: str, country: str) -> Citation:
        """Latest value with ready citation strings (text, short, markdown). Free endpoint."""
        return self._one(Citation, self._get(f"{self.base_url}/cite/{country}/{indicator}"))


class AsyncEconDash(_Base):
    """Asynchronous client with the same methods as `EconDash`, all awaitable."""

    def __init__(self, api_key: str | None = None, **kw: Any) -> None:
        super().__init__(api_key, **kw)
        self._http = httpx.AsyncClient(headers=self.headers, timeout=self.timeout)
        self._x402 = self._x402_for(sync=False)

    async def __aenter__(self) -> AsyncEconDash:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        resp = await self._http.get(url, params=params)
        if resp.status_code == 402 and self._x402 is not None:
            try:
                pay, _ = await self._x402.handle_402_response(
                    dict(resp.headers), resp.content, str(resp.request.url)
                )
            except Exception as e:
                raise _payment_required(resp, f"x402 payment not made: {e}") from e
            resp = await self._http.get(url, params=params, headers=pay)
        return _check(resp)

    async def _code(self, indicator: str) -> str:
        if _is_code(indicator):
            return indicator
        if indicator not in self._codes:
            await self.get_indicator(indicator)
        return self._codes[indicator]

    async def list_indicators(self) -> list[Indicator]:
        if self._indicators is None:
            data = await self._get(f"{self._data}/indicators", {"limit": 1200})
            self._indicators = [self._remember(i) for i in self._many(Indicator, data)]
        return self._indicators

    async def search_indicators(self, query: str, *, limit: int = 20) -> list[Indicator]:
        return _search(await self.list_indicators(), query, limit)

    async def get_indicator(self, indicator: str) -> Indicator:
        path = indicator if _is_code(indicator) else f"by-slug/{indicator}"
        data = await self._get(f"{self._data}/indicators/{path}")
        return self._remember(self._one(Indicator, data))

    async def get_series(
        self,
        indicator: str,
        country: str,
        *,
        start: DateLike | None = None,
        end: DateLike | None = None,
    ) -> Series:
        url = f"{self._data}/timeseries/{await self._code(indicator)}"
        return self._one(Series, await self._get(url, self._series_params(country, start, end)))

    async def list_countries(self) -> list[Country]:
        return self._many(Country, await self._get(f"{self._data}/countries"))

    async def top_countries(
        self, indicator: str, *, year: int | None = None, limit: int = 10
    ) -> TopCountries:
        params: dict[str, Any] = {"limit": limit}
        if year is not None:
            params["year"] = year
        url = f"{self._data}/timeseries/{await self._code(indicator)}/top-countries"
        return self._one(TopCountries, await self._get(url, params))

    async def cite(self, indicator: str, country: str) -> Citation:
        data = await self._get(f"{self.base_url}/cite/{country}/{indicator}")
        return self._one(Citation, data)
