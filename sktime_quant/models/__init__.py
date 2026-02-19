"""Model registry for candidate forecasters."""

from sktime_quant.models.health import summarize_runtime_health
from sktime_quant.models.registry import (
    get_candidate_models,
    get_daily_update_support,
    get_excluded_from_daily_update,
    make_forecaster,
)

__all__ = [
    "get_candidate_models",
    "get_daily_update_support",
    "get_excluded_from_daily_update",
    "make_forecaster",
    "summarize_runtime_health",
]

