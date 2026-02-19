"""Model factory and candidate selection."""

from __future__ import annotations

from typing import Callable

from sktime.forecasting.naive import NaiveForecaster
from sktime.forecasting.theta import ThetaForecaster



def _make_naive_last() -> NaiveForecaster:
    return NaiveForecaster(strategy="last")



def _make_naive_mean() -> NaiveForecaster:
    return NaiveForecaster(strategy="mean", window_length=5)



def _make_theta() -> ThetaForecaster:
    return ThetaForecaster(sp=1)



def _make_arima():
    from sktime.forecasting.arima import ARIMA

    return ARIMA(order=(1, 1, 1))


_FACTORY: dict[str, Callable[[], object]] = {
    "naive_last": _make_naive_last,
    "naive_mean": _make_naive_mean,
    "theta": _make_theta,
    "arima": _make_arima,
}

_DEFAULT_BY_ASSET_CLASS: dict[str, list[str]] = {
    "stock": ["naive_last", "theta", "arima"],
    "index": ["naive_mean", "theta"],
    "commodity": ["naive_last", "naive_mean", "theta"],
}



def make_forecaster(name: str):
    if name not in _FACTORY:
        raise ValueError(f"Unknown forecaster: {name}")
    return _FACTORY[name]()



def get_candidate_models(
    asset_class: str | None = None, names: list[str] | None = None
) -> dict[str, object]:
    selected = names
    if selected is None:
        selected = _DEFAULT_BY_ASSET_CLASS.get(asset_class or "", ["naive_last", "theta"])

    models: dict[str, object] = {}
    for name in selected:
        models[name] = make_forecaster(name)
    return models

