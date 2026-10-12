"""Build the four tools around one EconDash client."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from econdash import EconDash
from langchain_econdash.tools import CompareCountries, GetMetadata, GetSeries, SearchIndicators


class EconDashToolkit:
    """Tools that use the same access as `EconDash`.

    No key and no wallet: the free trial only. A 402 becomes a sentence for the model.
    Pass `api_key=` for a subscription. Pass a wallet plus `max_usd_per_call` to pay
    per call; without `max_usd_per_call` the client refuses to sign anything.
    """

    def __init__(self, api_key: str | None = None, **client_kwargs: Any) -> None:
        self.client = EconDash(api_key, **client_kwargs)

    def get_tools(self) -> list[BaseTool]:
        shared = {"client": self.client}
        return [
            SearchIndicators(**shared),
            GetSeries(**shared),
            GetMetadata(**shared),
            CompareCountries(**shared),
        ]

    def close(self) -> None:
        self.client.close()

    async def aclose(self) -> None:
        self.client.close()
