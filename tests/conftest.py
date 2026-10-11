import json
from pathlib import Path
from typing import Any

import pytest

FIX = Path(__file__).parent / "fixtures"
BASE = "https://econdash.org/api/v1"


def load(name: str) -> Any:
    return json.loads((FIX / name).read_text())


@pytest.fixture(autouse=True)
def _no_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECONDASH_API_KEY", raising=False)


@pytest.fixture
def payment_required_header() -> str:
    return (FIX / "m2m_402_payment_required.b64").read_text().strip()
