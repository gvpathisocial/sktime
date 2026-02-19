"""Utilities for comparing run artifacts."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_json(path: str | Path) -> dict:
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))


def _to_float(value) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def build_summary_diff(summary_a: dict, summary_b: dict) -> pd.DataFrame:
    keys = [
        "governance_alert_count",
        "run_status",
        "allocation_diagnostics.turnover",
        "allocation_diagnostics.max_weight",
        "allocation_diagnostics.total_weight",
        "execution_diagnostics.executed_order_count",
        "execution_diagnostics.total_order_notional",
    ]

    def _get(d: dict, key: str):
        cur = d
        for part in key.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
        return cur

    rows: list[dict[str, object]] = []
    for key in keys:
        a = _get(summary_a, key)
        b = _get(summary_b, key)
        af = _to_float(a)
        bf = _to_float(b)
        delta = None if af is None or bf is None else bf - af
        rows.append({"metric": key, "run_a": a, "run_b": b, "delta": delta})
    return pd.DataFrame(rows)


def _selected_model_by_asset(selection_payload: dict) -> dict[str, str]:
    selected: dict[str, str] = {}
    for asset, records in selection_payload.items():
        if not isinstance(records, list):
            continue
        for rec in records:
            if rec.get("selected"):
                selected[str(asset)] = str(rec.get("model"))
                break
    return selected


def build_model_selection_diff(selection_a: dict, selection_b: dict) -> pd.DataFrame:
    a_sel = _selected_model_by_asset(selection_a)
    b_sel = _selected_model_by_asset(selection_b)
    assets = sorted(set(a_sel) | set(b_sel))
    rows = []
    for asset in assets:
        model_a = a_sel.get(asset)
        model_b = b_sel.get(asset)
        rows.append(
            {
                "asset": asset,
                "run_a_model": model_a,
                "run_b_model": model_b,
                "changed": model_a != model_b,
            }
        )
    return pd.DataFrame(rows)


def build_governance_alert_diff(governance_a: dict, governance_b: dict) -> pd.DataFrame:
    def _alert_type_counts(payload: dict) -> dict[str, int]:
        counts: dict[str, int] = {}
        for alert in payload.get("alerts", []):
            key = str(alert.get("type", "unknown"))
            counts[key] = counts.get(key, 0) + 1
        return counts

    a_counts = _alert_type_counts(governance_a)
    b_counts = _alert_type_counts(governance_b)
    alert_types = sorted(set(a_counts) | set(b_counts))
    rows = []
    for kind in alert_types:
        a = int(a_counts.get(kind, 0))
        b = int(b_counts.get(kind, 0))
        rows.append({"alert_type": kind, "run_a": a, "run_b": b, "delta": b - a})
    return pd.DataFrame(rows)
