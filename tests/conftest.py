import pytest


@pytest.fixture(autouse=True)
def _disable_public_security_by_default(monkeypatch):
    """Keep existing tests focused; security tests opt back into enforcement."""
    monkeypatch.setenv("KRONOS_AUTH_DISABLED", "1")
    monkeypatch.setenv("KRONOS_RATE_LIMIT_DISABLED", "1")
    monkeypatch.setenv("KRONOS_ALERT_VALIDATE_DNS", "0")
    from kronos_fincept.api.security import clear_rate_limits

    clear_rate_limits()
    yield
    clear_rate_limits()
