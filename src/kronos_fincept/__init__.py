"""KronosFinceptLab package."""

from kronos_fincept.schemas import ForecastRequest, ForecastRow

__all__ = ["ForecastRequest", "ForecastRow", "forecast_from_request"]


def __getattr__(name: str):
    """Lazily expose heavy service helpers without loading pandas on import."""
    if name == "forecast_from_request":
        from kronos_fincept.service import forecast_from_request

        return forecast_from_request
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
