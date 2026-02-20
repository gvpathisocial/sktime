"""Background run runtime for Studio UX."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
import threading
from typing import Any

from sktime_quant.config.schema import AppConfig
from sktime_quant.pipelines.orchestrator import Orchestrator

_LOCK = threading.Lock()
_WORKERS: dict[str, threading.Thread] = {}
_MAX_EVENTS = 200


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _registry_path(output_dir: str) -> Path:
    return Path(output_dir) / "reports" / "run_registry.json"


def _load_registry(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(payload, dict) and isinstance(payload.get("runs"), list):
        return payload["runs"]
    return []


def _write_registry(path: Path, runs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"runs": runs}, indent=2, default=str), encoding="utf-8")


def _upsert(path: Path, run_id: str, patch: dict[str, Any]) -> None:
    with _LOCK:
        runs = _load_registry(path)
        updated = False
        for row in runs:
            if str(row.get("run_id")) == run_id:
                row.update(patch)
                updated = True
                break
        if not updated:
            base = {"run_id": run_id, "events": []}
            base.update(patch)
            runs.append(base)
        runs = sorted(runs, key=lambda x: str(x.get("updated_utc", "")), reverse=True)
        _write_registry(path, runs)


def append_event(output_dir: str, run_id: str, event: dict[str, Any]) -> None:
    path = _registry_path(output_dir)
    with _LOCK:
        runs = _load_registry(path)
        for row in runs:
            if str(row.get("run_id")) != run_id:
                continue
            events = row.get("events", [])
            if not isinstance(events, list):
                events = []
            events.append(event)
            row["events"] = events[-_MAX_EVENTS:]
            row["updated_utc"] = _now()
            _write_registry(path, runs)
            return


def list_runs(output_dir: str) -> list[dict[str, Any]]:
    return _load_registry(_registry_path(output_dir))


def get_run(output_dir: str, run_id: str) -> dict[str, Any] | None:
    for row in list_runs(output_dir):
        if str(row.get("run_id")) == run_id:
            return row
    return None


def is_active(run_id: str) -> bool:
    with _LOCK:
        worker = _WORKERS.get(run_id)
    return worker.is_alive() if worker is not None else False


def start_background_run(cfg: AppConfig, profile_path: str) -> str:
    cfg_copy = AppConfig.from_dict(asdict(cfg))
    run_id = cfg_copy.run_id
    out_dir = cfg_copy.execution.output_dir
    path = _registry_path(out_dir)

    _upsert(
        path,
        run_id,
        {
            "run_id": run_id,
            "status": "queued",
            "created_utc": _now(),
            "updated_utc": _now(),
            "profile_path": profile_path,
            "source_type": cfg_copy.data.source_type,
            "events": [],
        },
    )

    def _hook(evt: dict[str, Any]) -> None:
        append_event(out_dir, run_id, evt)

    def _target() -> None:
        _upsert(path, run_id, {"status": "running", "started_utc": _now(), "updated_utc": _now()})
        try:
            result = Orchestrator().run(cfg_copy, progress_hook=_hook)
            _upsert(
                path,
                run_id,
                {
                    "status": result.run_status,
                    "updated_utc": _now(),
                    "finished_utc": _now(),
                    "summary_path": result.summary_path,
                    "orders_path": result.orders_path,
                    "data_quality_path": result.data_quality_path,
                    "model_selection_path": result.model_selection_path,
                    "model_governance_path": result.model_governance_path,
                    "report_path": result.report_path,
                    "error": None,
                },
            )
        except Exception as exc:
            _upsert(
                path,
                run_id,
                {
                    "status": "failed",
                    "updated_utc": _now(),
                    "finished_utc": _now(),
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )

    worker = threading.Thread(target=_target, daemon=True, name=f"sktime-quant-{run_id}")
    with _LOCK:
        _WORKERS[run_id] = worker
    worker.start()
    return run_id
