"""Config file loading helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sktime_quant.config.schema import AppConfig


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required to load yaml config files. Install pyyaml."
        ) from exc

    with path.open("r", encoding="utf-8") as stream:
        loaded = yaml.safe_load(stream) or {}

    if not isinstance(loaded, dict):
        raise ValueError("Configuration file must deserialize to a dictionary")
    return loaded


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    suffix = config_path.suffix.lower()
    if suffix not in {".yaml", ".yml"}:
        raise ValueError("Only YAML config files are currently supported")
    payload = _load_yaml(config_path)
    return AppConfig.from_dict(payload)

