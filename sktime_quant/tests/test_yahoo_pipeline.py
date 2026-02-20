import pandas as pd

from sktime_quant.ingestion.yahoo_pipeline import (
    YahooIngestResult,
    _normalize_yf_download,
    read_symbols,
)


def test_read_symbols_dedup_and_strip(tmp_path):
    path = tmp_path / "symbols.inf"
    path.write_text("\n^NSEI\n^NSEI\n#comment\nAAPL\n", encoding="utf-8")
    symbols = read_symbols(path)
    assert symbols == ["AAPL", "^NSEI"]


def test_normalize_yf_download_handles_multiindex_columns():
    idx = pd.DatetimeIndex(["2024-01-01", "2024-01-02"], name="Date")
    cols = pd.MultiIndex.from_tuples(
        [
            ("Open", "^NSEI"),
            ("High", "^NSEI"),
            ("Low", "^NSEI"),
            ("Close", "^NSEI"),
            ("Volume", "^NSEI"),
        ]
    )
    raw = pd.DataFrame(
        [
            [100.0, 105.0, 99.0, 104.0, 10],
            [104.0, 106.0, 103.0, 105.0, 11],
        ],
        index=idx,
        columns=cols,
    )
    out = _normalize_yf_download(raw, symbol="^NSEI")
    assert list(out.columns) == ["timestamp", "asset", "open", "high", "low", "close", "volume"]
    assert len(out) == 2
    assert out["asset"].iloc[0] == "^NSEI"


def test_yahoo_ingest_result_has_exog_count_field():
    result = YahooIngestResult(
        symbols_requested=1,
        symbols_downloaded=1,
        rows_written_csv=10,
        rows_upserted_timescale=10,
        rows_upserted_exog=8,
        errors=[],
    )
    assert result.rows_upserted_exog == 8
