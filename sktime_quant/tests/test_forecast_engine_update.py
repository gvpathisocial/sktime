import pandas as pd

from sktime_quant.forecast.engine import ForecastEngine


def _market_frame(n: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="D"),
            "asset": ["A"] * n,
            "close": [100 + i * 0.1 for i in range(n)],
        }
    )


def test_forecast_engine_persists_state_and_updates_with_delta(tmp_path):
    engine = ForecastEngine()
    state_dir = tmp_path / "model_state"

    first = engine.forecast_assets(
        market=_market_frame(40),
        model_by_asset={"A": "naive_last"},
        horizon=1,
        target_confidence=0.95,
        update_mode="update",
        state_dir=state_dir,
    )
    assert not first.predictions.empty
    assert first.predictions.iloc[0]["update_status"] == "initial_fit_no_state"

    second = engine.forecast_assets(
        market=_market_frame(45),
        model_by_asset={"A": "naive_last"},
        horizon=1,
        target_confidence=0.95,
        update_mode="update",
        state_dir=state_dir,
    )
    assert not second.predictions.empty
    assert second.predictions.iloc[0]["update_status"] == "updated_with_delta"

