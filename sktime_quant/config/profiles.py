"""Profile save/load helpers for AppConfig."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from sktime_quant.config.schema import AppConfig


def save_profile(config: AppConfig, path: str | Path) -> str:
    try:
        import yaml
    except ImportError as exc:
        raise ImportError("PyYAML is required to save profile files.") from exc

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(config)
    p.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return str(p)
