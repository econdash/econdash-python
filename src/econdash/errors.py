from __future__ import annotations

from typing import Any


class EconDashError(Exception):
    """Base class. `status_code` and `body` carry the raw API answer."""

    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class EconDashAuthError(EconDashError):
    """401/403: bad API key, inactive subscription, or data outside the free trial."""


class EconDashNotFound(EconDashError):
    """404: unknown indicator, country or series."""


class EconDashRateLimitError(EconDashError):
    """429: trial or key quota exhausted. `retry_after` is in seconds."""

    def __init__(self, message: str, *, retry_after: int | None = None, **kw: Any) -> None:
        super().__init__(message, **kw)
        self.retry_after = retry_after


class EconDashPaymentRequired(EconDashError):
    """402: the call needs payment. `challenge` is the decoded x402 PAYMENT-REQUIRED
    object, `www_authenticate` the raw MPP challenges. Nothing was paid."""

    def __init__(
        self,
        message: str,
        *,
        challenge: dict[str, Any] | None = None,
        www_authenticate: list[str] | None = None,
        **kw: Any,
    ) -> None:
        super().__init__(message, **kw)
        self.challenge = challenge
        self.www_authenticate = www_authenticate or []
