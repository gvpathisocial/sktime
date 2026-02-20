"""CLI runner for sktime_quant."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sktime_quant.config.loader import load_config
from sktime_quant.pipelines.orchestrator import Orchestrator


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run sktime_quant pipeline")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    parser.add_argument("--run-id", help="Override run_id in config")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run with dry-run suffix and output under dry_run/",
    )
    parser.add_argument(
        "--print-summary",
        action="store_true",
        help="Print summary JSON content after run",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    cfg = load_config(args.config)

    if args.run_id:
        cfg.run_id = args.run_id
    if args.dry_run:
        cfg.run_id = f"{cfg.run_id}_dryrun"
        cfg.execution.output_dir = str(Path(cfg.execution.output_dir) / "dry_run")

    result = Orchestrator().run(cfg)
    print(f"run_status={result.run_status}")
    print(f"summary={result.summary_path}")
    print(f"data_quality={result.data_quality_path}")
    print(f"model_selection={result.model_selection_path}")
    print(f"model_governance={result.model_governance_path}")
    print(f"report={result.report_path}")
    print(f"orders={result.orders_path}")

    if args.print_summary:
        summary = Path(result.summary_path).read_text(encoding="utf-8")
        print(summary)

    if result.run_status == "completed":
        return 0
    if result.run_status == "no_new_data":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
