import pytest

from sktime_quant.data.connectors.timescale import TimescaleDataProvider


def test_validate_columns_map_accepts_valid_market_schema():
    provider = TimescaleDataProvider()
    cols = {
        "timestamp": "timestamp with time zone",
        "asset": "text",
        "close": "double precision",
    }
    provider._validate_columns_map(cols, "public.market_data")


def test_validate_columns_map_rejects_missing_required_columns():
    provider = TimescaleDataProvider()
    cols = {
        "timestamp": "timestamp with time zone",
        "asset": "text",
    }
    with pytest.raises(ValueError, match="missing required columns"):
        provider._validate_columns_map(cols, "public.market_data")


def test_validate_columns_map_rejects_invalid_types():
    provider = TimescaleDataProvider()
    cols = {
        "timestamp": "text",
        "asset": "integer",
        "close": "text",
    }
    with pytest.raises(ValueError):
        provider._validate_columns_map(cols, "public.market_data")
