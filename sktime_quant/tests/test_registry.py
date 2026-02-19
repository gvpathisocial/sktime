import pytest

from sktime_quant.models.registry import (
    get_available_model_names,
    get_candidate_models,
    get_daily_update_support,
    get_excluded_from_daily_update,
    get_model_health,
    get_model_overview,
    get_model_overview_rows,
    get_registered_model_names,
    make_forecaster,
)



def test_make_forecaster_naive_last():
    model = make_forecaster("naive_last")
    assert model.__class__.__name__ == "NaiveForecaster"



def test_get_candidate_models_from_asset_class():
    models = get_candidate_models(asset_class="commodity")
    assert "naive_last" in models


def test_registry_has_extended_models():
    names = get_registered_model_names()
    assert "autoets" in names
    assert "exp_smoothing" in names
    assert "ensemble_blend" in names
    assert "prophet" in names


def test_available_models_include_core_baseline():
    names = get_available_model_names()
    assert "naive_last" in names


def test_make_forecaster_unknown_raises():
    with pytest.raises(ValueError):
        make_forecaster("does_not_exist")


def test_model_overview_exists_for_registered_models():
    for name in get_registered_model_names():
        overview = get_model_overview(name)
        assert "summary" in overview
        assert "family" in overview


def test_model_overview_rows_shape():
    rows = get_model_overview_rows(["naive_last", "theta"])
    assert len(rows) == 2
    assert rows[0]["model"] == "naive_last"


def test_model_health_reports_core_model_ready():
    rows = get_model_health(["naive_last"])
    assert len(rows) == 1
    row = rows[0]
    assert row["model"] == "naive_last"
    assert row["available"] is True
    assert row["params_ok"] is True


def test_model_health_unknown_model():
    rows = get_model_health(["definitely_unknown_model"])
    assert len(rows) == 1
    row = rows[0]
    assert row["available"] is False
    assert row["health"] == "unhealthy"
    assert row["error"] == "unknown_model"


def test_daily_update_exclusion_metadata():
    support = get_daily_update_support("prophet")
    assert support["supported"] is False
    rows = get_excluded_from_daily_update(["naive_last", "prophet", "ensemble_blend"])
    names = {r["model"] for r in rows}
    assert "prophet" in names
    assert "ensemble_blend" in names
    assert "naive_last" not in names

