"""A vector index over the reader returns the series the question names."""

import hashlib
from datetime import date

from llama_index.core import VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.tools.econdash import EconDashReader

from econdash import Indicator, Point, Series


class WordEmbedding(BaseEmbedding):
    """Counts tokens into a fixed vector so retrieval works without an embedding API."""

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * 64
        for token in text.lower().replace("|", " ").split():
            slot = int(hashlib.md5(token.encode()).hexdigest(), 16) % 64
            vector[slot] += 1.0
        return vector

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._vector(text)

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._vector(query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._vector(query)


def _indicator(slug: str, name: str) -> Indicator:
    return Indicator.model_validate(
        {
            "code": f"world_bank__{slug}",
            "slug": slug,
            "name_ru": name,
            "name_en": name,
            "unit": "USD",
            "source": "World Bank",
            "license_name": "CC BY 4.0",
            "source_url": f"https://example.test/{slug}",
            "category": None,
            "fetch_method": None,
        }
    )


class Fake:
    def get_indicator(self, indicator: str) -> Indicator:
        names = {"gdp-nominal": "GDP nominal", "unemployment-rate-u3": "Unemployment"}
        return _indicator(indicator, names[indicator])

    def get_series(self, indicator: str, country: str, start=None, end=None) -> Series:
        ind = self.get_indicator(indicator)
        return Series(
            indicator_code=ind.code,
            indicator_name_ru=ind.name,
            indicator_name_en=ind.name,
            unit="USD",
            data_changed_at="2026-01-01",
            data=[Point(date=date(2024, 1, 1), value=1.0, country=country, country_name=country)],
        )


def test_retriever_returns_the_series_named_in_the_question() -> None:
    docs = EconDashReader(client=Fake()).load_data(
        indicators=["gdp-nominal", "unemployment-rate-u3"],
        countries=["USA", "DEU"],
    )
    assert len(docs) == 4
    index = VectorStoreIndex.from_documents(docs, embed_model=WordEmbedding())
    hits = index.as_retriever(similarity_top_k=1).retrieve("United States GDP nominal")
    assert hits[0].metadata["slug"] == "gdp-nominal"
    assert hits[0].metadata["iso3"] == "USA"
