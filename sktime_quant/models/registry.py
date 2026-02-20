"""Model factory and candidate selection."""

from __future__ import annotations

from collections.abc import Callable
import warnings

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


def _make_autoets():
    from sktime.forecasting.ets import AutoETS

    return AutoETS(auto=True, sp=1)


def _make_exp_smoothing():
    from sktime.forecasting.exp_smoothing import ExponentialSmoothing

    return ExponentialSmoothing(trend="add", seasonal=None, sp=1)


def _make_croston():
    from sktime.forecasting.croston import Croston

    return Croston(smoothing=0.1)


def _make_ensemble_blend():
    from sktime.forecasting.compose import EnsembleForecaster

    return EnsembleForecaster(
        forecasters=[
            ("naive_last", _make_naive_last()),
            ("theta", _make_theta()),
            ("arima", _make_arima()),
        ]
    )


def _make_prophet(context: dict[str, object] | None = None):
    from sktime.forecasting.fbprophet import Prophet

    kwargs: dict[str, object] = {}
    if context is not None and "holidays" in context and context["holidays"] is not None:
        kwargs["holidays"] = context["holidays"]
    return Prophet(**kwargs)


_FACTORY: dict[str, Callable[[], object]] = {
    "naive_last": _make_naive_last,
    "naive_mean": _make_naive_mean,
    "theta": _make_theta,
    "arima": _make_arima,
    "autoets": _make_autoets,
    "exp_smoothing": _make_exp_smoothing,
    "croston": _make_croston,
    "ensemble_blend": _make_ensemble_blend,
    "prophet": _make_prophet,
}

_DEFAULT_BY_ASSET_CLASS: dict[str, list[str]] = {
    "stock": ["naive_last", "theta", "arima", "autoets", "exp_smoothing"],
    "index": ["naive_mean", "theta", "arima", "autoets"],
    "commodity": ["naive_last", "naive_mean", "theta", "arima", "croston"],
}

_MODEL_OVERVIEW: dict[str, dict[str, str]] = {
    "naive_last": {
        "family": "baseline",
        "summary": "Uses last observed value as forecast.",
        "best_for": "Strong short-term momentum or benchmarking.",
        "notes": "Fast and robust; limited pattern learning.",
    },
    "naive_mean": {
        "family": "baseline",
        "summary": "Uses rolling mean as forecast.",
        "best_for": "Low-volatility and mean-reverting series.",
        "notes": "Simple smoothing; can lag turning points.",
    },
    "theta": {
        "family": "classical",
        "summary": "Theta method with trend decomposition style behavior.",
        "best_for": "Stable daily series with mild trend.",
        "notes": "Good default classical model for many assets.",
    },
    "arima": {
        "family": "classical",
        "summary": "ARIMA(1,1,1) captures autocorrelation after differencing.",
        "best_for": "Series with short-memory linear structure.",
        "notes": "Sensitive to order misspecification.",
    },
    "autoets": {
        "family": "classical",
        "summary": "Automatic ETS model selection.",
        "best_for": "Level/trend driven series without heavy regime shifts.",
        "notes": "Interpretable and often strong on smooth dynamics.",
    },
    "exp_smoothing": {
        "family": "classical",
        "summary": "Additive exponential smoothing.",
        "best_for": "Smooth series with persistent local trend.",
        "notes": "Can underperform on abrupt breakouts.",
    },
    "croston": {
        "family": "intermittent-demand",
        "summary": "Croston method for intermittent/non-continuous demand.",
        "best_for": "Sparse event-like or intermittent commodity activity.",
        "notes": "Specialized method; less useful for dense signals.",
    },
    "prophet": {
        "family": "additive-trend",
        "summary": "Decomposable trend/seasonality model.",
        "best_for": "Series with calendar effects or structural trend changes.",
        "notes": "Heavier dependency/runtime footprint than baselines.",
    },
    "ensemble_blend": {
        "family": "ensemble",
        "summary": "Simple blend of naive_last + theta + arima.",
        "best_for": "Stable diversification across complementary classical models.",
        "notes": "Uses averaged model outputs; periodic refit recommended.",
    },
}

_MODEL_PARAM_EXPECTATIONS: dict[str, dict[str, object]] = {
    "naive_last": {"strategy": "last"},
    "naive_mean": {"strategy": "mean", "window_length": 5},
    "theta": {"sp": 1},
    "arima": {"order": (1, 1, 1)},
    "autoets": {"auto": True, "sp": 1},
    "exp_smoothing": {"trend": "add", "seasonal": None, "sp": 1},
    "croston": {"smoothing": 0.1},
}

_DAILY_UPDATE_SUPPORT: dict[str, dict[str, str | bool]] = {
    "naive_last": {"supported": True, "reason": ""},
    "naive_mean": {"supported": True, "reason": ""},
    "theta": {"supported": True, "reason": ""},
    "arima": {"supported": True, "reason": ""},
    "autoets": {"supported": True, "reason": ""},
    "exp_smoothing": {"supported": True, "reason": ""},
    "croston": {"supported": True, "reason": ""},
    "prophet": {
        "supported": False,
        "reason": "excluded_from_daily_update: incremental update not supported reliably; use refit",
    },
    "ensemble_blend": {
        "supported": False,
        "reason": "excluded_from_daily_update: ensemble state/weights require explicit refit",
    },
}


def get_registered_model_names() -> list[str]:
    return sorted(_FACTORY.keys())


def get_available_model_names() -> list[str]:
    rows = get_model_health()
    return [str(r["model"]) for r in rows if bool(r["available"])]


def get_model_overview(name: str) -> dict[str, str]:
    if name not in _FACTORY:
        raise ValueError(f"Unknown forecaster: {name}")
    return _MODEL_OVERVIEW.get(
        name,
        {
            "family": "unknown",
            "summary": "",
            "best_for": "",
            "notes": "",
        },
    )


def get_model_overview_rows(names: list[str] | None = None) -> list[dict[str, str]]:
    selected = names or get_registered_model_names()
    rows: list[dict[str, str]] = []
    for name in selected:
        if name not in _FACTORY:
            continue
        overview = get_model_overview(name)
        rows.append(
            {
                "model": name,
                "family": overview["family"],
                "summary": overview["summary"],
                "best_for": overview["best_for"],
                "notes": overview["notes"],
            }
        )
    return rows


def get_daily_update_support(name: str) -> dict[str, str | bool]:
    if name not in _FACTORY:
        raise ValueError(f"Unknown forecaster: {name}")
    support = _DAILY_UPDATE_SUPPORT.get(name, {"supported": False, "reason": "not_declared"})
    return {"supported": bool(support["supported"]), "reason": str(support["reason"])}


def get_excluded_from_daily_update(names: list[str] | None = None) -> list[dict[str, str]]:
    selected = names or get_registered_model_names()
    rows: list[dict[str, str]] = []
    for name in selected:
        if name not in _FACTORY:
            rows.append({"model": name, "reason": "unknown_model"})
            continue
        support = get_daily_update_support(name)
        if not bool(support["supported"]):
            rows.append({"model": name, "reason": str(support["reason"])})
    return rows


def _check_expected_params(name: str, model: object) -> tuple[bool, str]:
    expected = _MODEL_PARAM_EXPECTATIONS.get(name, {})
    if not expected:
        return True, ""
    if not hasattr(model, "get_params"):
        return False, "Model does not expose get_params()"

    try:
        params = model.get_params(deep=False)
    except Exception as exc:
        return False, f"get_params_failed: {type(exc).__name__}: {exc}"

    for key, expected_value in expected.items():
        actual = params.get(key, None)
        if actual != expected_value:
            return False, (
                f"param_mismatch[{key}]: expected={expected_value!r}, actual={actual!r}"
            )
    return True, ""


def get_model_health(names: list[str] | None = None) -> list[dict[str, object]]:
    selected = names or get_registered_model_names()
    rows: list[dict[str, object]] = []
    for name in selected:
        if name not in _FACTORY:
            rows.append(
                {
                    "model": name,
                    "available": False,
                    "params_ok": False,
                    "daily_update_supported": False,
                    "daily_update_reason": "unknown_model",
                    "health": "unhealthy",
                    "error": "unknown_model",
                }
            )
            continue

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                model = make_forecaster(name)
                params_ok, param_error = _check_expected_params(name, model)
                rows.append(
                    {
                        "model": name,
                        "available": True,
                        "params_ok": bool(params_ok),
                        "daily_update_supported": bool(
                            get_daily_update_support(name)["supported"]
                        ),
                        "daily_update_reason": str(get_daily_update_support(name)["reason"]),
                        "health": "healthy" if params_ok else "degraded",
                        "error": param_error,
                    }
                )
            except Exception as exc:
                rows.append(
                    {
                        "model": name,
                        "available": False,
                        "params_ok": False,
                        "daily_update_supported": bool(
                            _DAILY_UPDATE_SUPPORT.get(name, {"supported": False})["supported"]
                        ),
                        "daily_update_reason": str(
                            _DAILY_UPDATE_SUPPORT.get(name, {"reason": "unavailable"}).get(
                                "reason", "unavailable"
                            )
                        ),
                        "health": "unhealthy",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
    return rows


def make_forecaster(name: str, context: dict[str, object] | None = None):
    if name not in _FACTORY:
        raise ValueError(f"Unknown forecaster: {name}")
    try:
        if name == "prophet":
            return _FACTORY[name](context)
        return _FACTORY[name]()
    except ModuleNotFoundError as exc:
        missing = exc.name or "an optional dependency/version constraint"
        msg = (
            f"Model '{name}' requires {missing}. "
            f"Original error: {exc}"
        )
        raise ImportError(msg) from exc


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

