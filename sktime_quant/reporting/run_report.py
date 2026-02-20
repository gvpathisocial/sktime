"""Run-level markdown reporting."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def _line(key: str, value: object) -> str:
    return f"- **{key}**: {value}"


def write_run_report(
    *,
    report_path: Path,
    run_id: str,
    summary: dict[str, object],
    data_quality: dict[str, object],
    governance: dict[str, object],
) -> str:
    """Write a compact markdown report for one pipeline run."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        f"# sktime_quant Run Report `{run_id}`",
        "",
        _line("generated_utc", datetime.now(UTC).isoformat()),
        _line("run_status", summary.get("run_status", "unknown")),
        _line("orders_path", summary.get("orders_path", "")),
        _line("model_selection_path", summary.get("model_selection_path", "")),
        "",
        "## Data Quality",
        "",
        _line("row_count", data_quality.get("row_count", 0)),
        _line("asset_count", data_quality.get("asset_count", 0)),
        _line(
            "duplicate_asset_timestamp_rows",
            data_quality.get("duplicate_asset_timestamp_rows", 0),
        ),
        _line("missing_close_rows", data_quality.get("missing_close_rows", 0)),
        _line("stale_assets", data_quality.get("stale_assets", [])),
        "",
        "## Model Governance",
        "",
        _line("alert_count", governance.get("alert_count", 0)),
        _line(
            "selected_models",
            len(governance.get("selected_models", {}))
            if isinstance(governance.get("selected_models"), dict)
            else 0,
        ),
        "",
        "## Allocation/Execution Diagnostics",
        "",
    ]
    allocation_diag = summary.get("allocation_diagnostics", {})
    if isinstance(allocation_diag, dict) and allocation_diag:
        lines.append(_line("allocation_diagnostics", allocation_diag))
    else:
        lines.append("- No allocation diagnostics available.")
    execution_diag = summary.get("execution_diagnostics", {})
    if isinstance(execution_diag, dict) and execution_diag:
        lines.append(_line("execution_diagnostics", execution_diag))
    else:
        lines.append("- No execution diagnostics available.")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(report_path)
