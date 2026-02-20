import pandas as pd

from sktime_quant.config.schema import DataConfig
from sktime_quant.data.connectors.csv_loader import CSVDataProvider, FolderDataProvider
from sktime_quant.data.provider import DataProvider


def _yahoo_raw_frame(symbol: str = "^NSEI") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Price": ["Ticker", "Date", "2010-01-04", "2010-01-05"],
            "Close": [symbol, "", "5232.2", "5277.9"],
            "High": [symbol, "", "5238.45", "5288.35"],
            "Low": [symbol, "", "5167.1", "5242.4"],
            "Open": [symbol, "", "5200.9", "5277.15"],
            "Volume": [symbol, "", "0", "0"],
        }
    )


def test_csv_provider_normalizes_yahoo_raw_format(tmp_path):
    path = tmp_path / "^NSEI.csv"
    _yahoo_raw_frame("^NSEI").to_csv(path, index=False)
    cfg = DataConfig(source_type="csv", csv_path=str(path))

    market, _ = CSVDataProvider().load_history(cfg)
    assert {"timestamp", "asset", "close"}.issubset(set(market.columns))
    assert market["asset"].nunique() == 1
    assert market["asset"].iloc[0] == "^NSEI"
    assert len(market) == 2


def test_folder_provider_normalizes_multiple_yahoo_files(tmp_path):
    folder = tmp_path / "raw"
    folder.mkdir(parents=True, exist_ok=True)
    _yahoo_raw_frame("^NSEI").to_csv(folder / "^NSEI.csv", index=False)
    _yahoo_raw_frame("^NSEBANK").to_csv(folder / "^NSEBANK.csv", index=False)
    cfg = DataConfig(source_type="folder", folder_path=str(folder))

    market, _ = FolderDataProvider().load_history(cfg)
    assert {"timestamp", "asset", "close"}.issubset(set(market.columns))
    assert set(market["asset"].unique()) == {"^NSEI", "^NSEBANK"}
    assert len(market) == 4


def test_data_provider_validates_normalized_yahoo_files(tmp_path):
    path = tmp_path / "^NSEI.csv"
    _yahoo_raw_frame("^NSEI").to_csv(path, index=False)
    cfg = DataConfig(source_type="csv", csv_path=str(path))

    market, _ = DataProvider().load_history(cfg)
    assert {"timestamp", "asset", "close"}.issubset(set(market.columns))
    assert pd.api.types.is_datetime64_any_dtype(market["timestamp"])
