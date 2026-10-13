"""Load EconDash series as LlamaIndex documents for a RAG index.

One document per indicator and country. The text is a short summary (last 20
points, unit, source, chart link). A licence that forbids redistribution
produces no document and the series is not fetched.
"""

from __future__ import annotations

from typing import Any

from llama_index.core.readers.base import BaseReader
from llama_index.core.schema import Document

from econdash import EconDash, EconDashError
from econdash.agent_text import _iso, _isos, document_text, redistribution_allowed


def _indicators(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    return [str(part).strip() for part in value if str(part).strip()]


class EconDashReader(BaseReader):
    """Read indicator x country pairs that the caller is allowed to redistribute."""

    def __init__(
        self, client: Any | None = None, api_key: str | None = None, **client_kwargs: Any
    ) -> None:
        self.client = client if client is not None else EconDash(api_key, **client_kwargs)

    def load_data(
        self,
        indicators: list[str] | str | None = None,
        countries: list[str] | str | None = None,
    ) -> list[Document]:
        """Build one document per pair. Skip a pair the licence or the API will not give."""
        documents: list[Document] = []
        for slug in _indicators(indicators):
            try:
                indicator = self.client.get_indicator(slug)
            except EconDashError:
                continue
            if not redistribution_allowed(indicator):
                continue
            for country in _isos(countries):
                if len(country) != 3 or not country.isalpha():
                    continue
                try:
                    series = self.client.get_series(indicator.slug or indicator.code, country)
                except EconDashError:
                    continue
                if not series.data:
                    continue
                code = _iso(country)
                documents.append(
                    Document(
                        id_=f"econdash:{indicator.slug or indicator.code}:{code}",
                        text=document_text(indicator, series),
                        metadata={
                            "slug": indicator.slug or indicator.code,
                            "iso3": code,
                            "source_url": indicator.source_url or "",
                            "data_changed_at": series.data_changed_at
                            or indicator.data_changed_at
                            or "",
                            "license": indicator.license_name or "",
                        },
                    )
                )
        return documents
