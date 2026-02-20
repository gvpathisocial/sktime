"""Rule DSL for strategy signals."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


_VALID_OPS = {"<", "<=", ">", ">=", "==", "!=", "between"}
_VALID_CHAIN = {"any", "all"}
_VALID_SIGNAL = {-1, 0, 1}


def validate_rules(rules: list[dict[str, Any]]) -> None:
    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError(f"Rule at index {idx} must be a dictionary")
        op = str(rule.get("operator", "")).strip()
        if op not in _VALID_OPS:
            raise ValueError(f"Rule[{idx}] has invalid operator: {op}")
        signal = int(rule.get("signal", 0))
        if signal not in _VALID_SIGNAL:
            raise ValueError(f"Rule[{idx}] has invalid signal: {signal}")
        feature = str(rule.get("feature", "")).strip()
        if not feature:
            raise ValueError(f"Rule[{idx}] missing feature")
        if op == "between":
            low = rule.get("low")
            high = rule.get("high")
            if low is None or high is None:
                raise ValueError(f"Rule[{idx}] with between needs low/high")
        else:
            if "value" not in rule:
                raise ValueError(f"Rule[{idx}] missing value")


def _eval_single(value: float, rule: dict[str, Any]) -> bool:
    op = str(rule["operator"])
    if not np.isfinite(value):
        return False
    if op == "<":
        return bool(value < float(rule["value"]))
    if op == "<=":
        return bool(value <= float(rule["value"]))
    if op == ">":
        return bool(value > float(rule["value"]))
    if op == ">=":
        return bool(value >= float(rule["value"]))
    if op == "==":
        return bool(value == float(rule["value"]))
    if op == "!=":
        return bool(value != float(rule["value"]))
    if op == "between":
        return bool(float(rule["low"]) <= value <= float(rule["high"]))
    return False


def evaluate_rules_signal(
    feature_row: dict[str, Any] | None,
    rules: list[dict[str, Any]],
    *,
    chain: str = "any",
    default_signal: int = 0,
) -> int:
    if feature_row is None:
        return int(default_signal)
    if chain not in _VALID_CHAIN:
        raise ValueError(f"Unsupported chain mode: {chain}")
    if not rules:
        return int(default_signal)

    validate_rules(rules)
    by_signal: dict[int, list[bool]] = {-1: [], 1: [], 0: []}
    for rule in rules:
        feature = str(rule["feature"])
        if feature not in feature_row:
            continue
        try:
            val = float(feature_row[feature])
        except Exception:
            continue
        by_signal[int(rule["signal"])].append(_eval_single(val, rule))

    def _match(decisions: list[bool]) -> bool:
        if not decisions:
            return False
        return any(decisions) if chain == "any" else all(decisions)

    long_hit = _match(by_signal[1])
    short_hit = _match(by_signal[-1])
    if long_hit and not short_hit:
        return 1
    if short_hit and not long_hit:
        return -1
    return int(default_signal)


def save_rules_yaml(path: str | Path, rules: list[dict[str, Any]]) -> str:
    try:
        import yaml
    except ImportError as exc:
        raise ImportError("PyYAML is required to persist rule DSL files.") from exc

    validate_rules(rules)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"rules": rules}
    p.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return str(p)


def load_rules_yaml(path: str | Path) -> list[dict[str, Any]]:
    try:
        import yaml
    except ImportError as exc:
        raise ImportError("PyYAML is required to load rule DSL files.") from exc

    p = Path(path)
    if not p.exists():
        return []
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("Rule YAML root must be mapping")
    rules = raw.get("rules", [])
    if not isinstance(rules, list):
        raise ValueError("rules must be a list")
    validate_rules(rules)
    return rules
