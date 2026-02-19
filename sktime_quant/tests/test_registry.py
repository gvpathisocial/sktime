from sktime_quant.models.registry import get_candidate_models, make_forecaster



def test_make_forecaster_naive_last():
    model = make_forecaster("naive_last")
    assert model.__class__.__name__ == "NaiveForecaster"



def test_get_candidate_models_from_asset_class():
    models = get_candidate_models(asset_class="commodity")
    assert "naive_last" in models

