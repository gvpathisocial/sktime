"""Schedulable Yahoo ingestion runner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from datetime import UTC, datetime

from sktime_quant.ingestion.yahoo_pipeline import run_yahoo_ingestion


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Yahoo CSV + optional Timescale ingestion")
    p.add_argument("--symbols-file", required=True, help="Path to symbols.inf")
    p.add_argument("--output-folder", required=True, help="Output folder for canonical CSV files")
    p.add_argument("--connection-uri", default=None, help="Timescale/Postgres SQLAlchemy URI")
    p.add_argument("--market-table", default="public.market_data", help="Target market table")
    p.add_argument("--exog-table", default="public.exog_data", help="Target exogenous table")
    p.add_argument(
        "--write-exog",
        action="store_true",
        help="Derive and upsert technical indicator exogenous features",
    )
    p.add_argument(
        "--zone-schema-json",
        default=None,
        help="Optional JSON file path for zone labeling thresholds",
    )
    p.add_argument("--full-start-date", default="2010-01-01", help="Start date for first full pull")
    p.add_argument(
        "--incremental-lookback-days",
        type=int,
        default=7,
        help="Lookback days from last stored timestamp for incremental pulls",
    )
    p.add_argument(
        "--mode",
        choices=["once", "loop"],
        default="once",
        help="Run once or keep running on a fixed interval",
    )
    p.add_argument("--interval-minutes", type=int, default=1440, help="Loop interval in minutes")
    return p


def _run_once(args: argparse.Namespace) -> int:
    zone_schema = None
    if args.zone_schema_json:
        zone_schema = json.loads(Path(args.zone_schema_json).read_text(encoding="utf-8"))
    result = run_yahoo_ingestion(
        symbols_file=args.symbols_file,
        output_folder=args.output_folder,
        connection_uri=args.connection_uri,
        market_table=args.market_table,
        exog_table=args.exog_table,
        write_exog=args.write_exog,
        zone_schema=zone_schema,
        full_start_date=args.full_start_date,
        incremental_lookback_days=args.incremental_lookback_days,
    )
    payload = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "symbols_requested": result.symbols_requested,
        "symbols_downloaded": result.symbols_downloaded,
        "rows_written_csv": result.rows_written_csv,
        "rows_upserted_timescale": result.rows_upserted_timescale,
        "rows_upserted_exog": result.rows_upserted_exog,
        "error_count": len(result.errors),
        "errors": result.errors,
    }
    print(json.dumps(payload, indent=2))
    return 0 if not result.errors else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.mode == "once":
        return _run_once(args)

    while True:
        code = _run_once(args)
        # Continue looping even if one cycle has errors; scheduler should be resilient.
        _ = code
        time.sleep(max(1, int(args.interval_minutes)) * 60)


if __name__ == "__main__":
    raise SystemExit(main())
