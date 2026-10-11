"""Response models. Field names and types follow the EconDash API schema
(`IndicatorResponse`, `TimeSeriesResponse`, `CountryResponse`, ... in the backend OpenAPI).
Unknown fields are ignored, so new API fields never break old clients."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class Indicator(BaseModel):
    code: str
    slug: str | None
    name_ru: str
    name_en: str | None
    category: str | None
    source: str | None
    unit: str | None
    fetch_method: str | None
    data_points: int = 0
    description: str | None = None
    updated_at: str | None = None
    frequency: str | None = None
    first_observation: str | None = None
    last_observation: str | None = None
    data_changed_at: str | None = None
    data_checked_at: str | None = None
    source_series_id: str | None = None
    source_url: str | None = None
    source_url_template: str | None = None
    source_publisher: str | None = None
    license_name: str | None = None
    license_url: str | None = None
    attribution_text: str | None = None
    is_based_on: list[str] | None = None

    @property
    def name(self) -> str:
        return self.name_en or self.name_ru

    @property
    def url(self) -> str | None:
        """Chart hub page on econdash.org."""
        return f"https://econdash.org/chart/{self.slug}" if self.slug else None


class Point(BaseModel):
    date: date
    value: float
    country: str
    country_name: str | None = None
    is_projection: bool | None = None


class Series(BaseModel):
    indicator_code: str
    indicator_name_ru: str
    indicator_name_en: str | None
    unit: str | None
    frequency: str | None = None
    first_observation: str | None = None
    last_observation: str | None = None
    data_points: int | None = None
    data_changed_at: str | None = None
    data_checked_at: str | None = None
    data: list[Point]


class Country(BaseModel):
    iso3_code: str
    iso2_code: str | None
    name: str
    region: str | None
    income_level: str | None
    data_points: int = 0


class TopCountry(BaseModel):
    iso3_code: str
    country_name: str | None
    value: float
    date: date
    yoy_change_pct: float | None = None


class TopCountries(BaseModel):
    indicator_code: str
    unit: str | None
    data: list[TopCountry]


class CiteSource(BaseModel):
    name: str
    acronym: str | None = None
    url: str | None = None
    release_date: str | None = None


class CitationStrings(BaseModel):
    text: str
    short: str
    markdown: str


class CiteMeta(BaseModel):
    updated_at: str
    next_update: str | None = None
    frequency: str | None = None
    canonical_url: str


class Citation(BaseModel):
    type: str = "economic_indicator"
    indicator: str
    indicator_name: str
    country: str
    country_name: str
    value: float
    unit: str
    change: str | None = None
    period: str
    previous_value: float | None = None
    previous_period: str | None = None
    trend: str | None = None
    trend_magnitude: float | None = None
    definition: str | None = None
    source: CiteSource
    citation: CitationStrings
    meta: CiteMeta
    is_projection: bool = False
    projection_label: str | None = None
