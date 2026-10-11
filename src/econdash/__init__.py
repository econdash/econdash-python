"""Python client for the EconDash macroeconomic data API (https://econdash.org)."""

__version__ = "0.1.1"

from ._client import DEFAULT_BASE_URL, AsyncEconDash, EconDash  # noqa: E402
from .errors import (  # noqa: E402
    EconDashAuthError,
    EconDashError,
    EconDashNotFound,
    EconDashPaymentRequired,
    EconDashRateLimitError,
)
from .models import (  # noqa: E402
    Citation,
    Country,
    Indicator,
    Point,
    Series,
    TopCountries,
    TopCountry,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "AsyncEconDash",
    "Citation",
    "Country",
    "EconDash",
    "EconDashAuthError",
    "EconDashError",
    "EconDashNotFound",
    "EconDashPaymentRequired",
    "EconDashRateLimitError",
    "Indicator",
    "Point",
    "Series",
    "TopCountries",
    "TopCountry",
    "__version__",
]
