"""Ingest -> backtest -> forecast -> rebalance -> orders pipeline."""

from __future__ import annotations

import json
from dataclasses import replace
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from sktime_quant.backtest.walkforward import BacktestResult, WalkForwardEngine
from sktime_quant.config.schema import AppConfig
from sktime_quant.data.provider import DataProvider
from sktime_quant.execution.orders import ORDER_COLUMNS, OrderExporter
from sktime_quant.data.holidays import (
    HolidayConfig,
    build_asset_holiday_frames,
    load_holidays_by_market,
)
from sktime_quant.features.exogenous import (
    drop_exogenous_null_rows,
    encode_categorical_exogenous,
    lag_exogenous_one_step,
)
from sktime_quant.features.lagged_regressors import build_lagged_regressors
from sktime_quant.forecast.engine import ForecastEngine, ForecastResult
from sktime_quant.models.registry import (
    get_available_model_names,
    get_excluded_from_daily_update,
)
from sktime_quant.portfolio.optimizer import AllocationResult, PortfolioEngine
from sktime_quant.reporting.run_report import write_run_report


@dataclass(slots=True)
class OrchestratorResult:
    backtest: BacktestResult
    forecast: ForecastResult
    allocation: AllocationResult
    orders_path: str
    summary_path: str
    data_quality_path: str
    model_selection_path: str
    model_governance_path: str
    report_path: str
    run_status: str


class Orchestrator:
    def __init__(self) -> None:
        self.data_provider = DataProvider()
        self.backtest_engine = WalkForwardEngine()
        self.forecast_engine = ForecastEngine()
        self.portfolio_engine = PortfolioEngine()
        self.order_exporter = OrderExporter()

    def _artifact_paths(self, cfg: AppConfig) -> dict[str, Path]:
        base = Path(cfg.execution.output_dir)
        run = cfg.run_id
        day = datetime.now(UTC).strftime("%Y%m%d")
        paths = {
            "metrics": base / "backtests" / run / "metrics.parquet",
            "folds": base / "backtests" / run / "fold_predictions.parquet",
            "forecast": base / "forecasts" / day / "forecast.parquet",
            "orders": base / cfg.execution.orders_subdir / f"{cfg.execution.file_prefix}_{day}.csv",
            "summary": base / "reports" / f"{run}_summary.json",
            "data_quality": base / "reports" / f"{run}_data_quality.json",
            "model_selection": base / "reports" / f"{run}_model_selection.json",
            "model_governance": base / "reports" / f"{run}_model_governance.json",
            "run_report": base / "reports" / f"{run}_report.md",
            "state": base / "state" / f"{run}_last_timestamp.txt",
            "model_state_dir": base / "state" / "models",
            "governance_history": base / "governance" / "model_stability_history.json",
        }
        for path in paths.values():
            path.parent.mkdir(parents=True, exist_ok=True)
        return paths

    def _load_governance_history(self, path: Path) -> list[dict[str, object]]:
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if isinstance(payload, dict) and isinstance(payload.get("history"), list):
            return payload["history"]
        if isinstance(payload, list):
            return payload
        return []

    def _write_governance_history(
        self, path: Path, history: list[dict[str, object]], max_records: int
    ) -> None:
        trimmed = history[-max(1, int(max_records)) :]
        path.write_text(json.dumps({"history": trimmed}, indent=2), encoding="utf-8")

    def _build_model_governance(
        self, backtest: BacktestResult, cfg: AppConfig, paths: dict[str, Path]
    ) -> dict[str, object]:
        now = datetime.now(UTC).isoformat()
        metrics = backtest.metrics.copy()
        history = self._load_governance_history(paths["governance_history"])

        latest_records: list[dict[str, object]] = []
        if not metrics.empty:
            for _, row in metrics.iterrows():
                latest_records.append(
                    {
                        "timestamp_utc": now,
                        "run_id": cfg.run_id,
                        "asset": str(row["asset"]),
                        "model": str(row["model"]),
                        "risk_adjusted_score": float(row.get("risk_adjusted_score", float("nan"))),
                        "empirical_coverage": float(row.get("empirical_coverage", float("nan"))),
                        "failure_rate": float(row.get("failure_rate", float("nan"))),
                        "excluded": bool(row.get("excluded", False)),
                    }
                )

        merged_history = history + latest_records
        self._write_governance_history(
            paths["governance_history"],
            merged_history,
            cfg.execution.governance_history_max_records,
        )

        alerts: list[dict[str, object]] = []
        by_key: dict[tuple[str, str], list[dict[str, object]]] = {}
        for rec in merged_history:
            key = (str(rec.get("asset", "")), str(rec.get("model", "")))
            by_key.setdefault(key, []).append(rec)

        for asset, model in backtest.best_models.items():
            row_df = metrics[(metrics["asset"] == asset) & (metrics["model"] == model)]
            if row_df.empty:
                continue
            row = row_df.iloc[0]
            coverage = float(row.get("empirical_coverage", float("nan")))
            failure = float(row.get("failure_rate", float("nan")))

            if coverage < cfg.execution.governance_coverage_alert_threshold:
                alerts.append(
                    {
                        "type": "low_coverage",
                        "asset": asset,
                        "model": model,
                        "value": coverage,
                        "threshold": cfg.execution.governance_coverage_alert_threshold,
                    }
                )
            if failure > cfg.execution.governance_failure_alert_threshold:
                alerts.append(
                    {
                        "type": "high_failure_rate",
                        "asset": asset,
                        "model": model,
                        "value": failure,
                        "threshold": cfg.execution.governance_failure_alert_threshold,
                    }
                )

            hist_key = (str(asset), str(model))
            series = by_key.get(hist_key, [])
            if len(series) >= 2:
                prev = float(series[-2].get("empirical_coverage", coverage))
                drop = prev - coverage
                if drop > cfg.execution.governance_coverage_drop_alert:
                    alerts.append(
                        {
                            "type": "coverage_drop",
                            "asset": asset,
                            "model": model,
                            "value": drop,
                            "threshold": cfg.execution.governance_coverage_drop_alert,
                        }
                    )

        return {
            "run_id": cfg.run_id,
            "timestamp_utc": now,
            "selected_models": backtest.best_models,
            "alert_count": len(alerts),
            "alerts": alerts,
            "latest_records_count": len(latest_records),
            "history_path": str(paths["governance_history"]),
        }

    def _effective_data_config(self, cfg: AppConfig, paths: dict[str, Path]):
        if not cfg.data.incremental_mode:
            return cfg.data
        state_path = (
            Path(cfg.data.incremental_state_path)
            if cfg.data.incremental_state_path
            else paths["state"]
        )
        if not state_path.exists():
            return cfg.data

        prev_ts = state_path.read_text(encoding="utf-8").strip()
        if not prev_ts:
            return cfg.data
        if cfg.data.start and pd.Timestamp(cfg.data.start) > pd.Timestamp(prev_ts):
            return cfg.data
        return replace(cfg.data, start=prev_ts)

    def _write_incremental_state(self, cfg: AppConfig, paths: dict[str, Path], market: pd.DataFrame) -> None:
        if not cfg.data.incremental_mode or market.empty:
            return
        state_path = (
            Path(cfg.data.incremental_state_path)
            if cfg.data.incremental_state_path
            else paths["state"]
        )
        latest = pd.to_datetime(market["timestamp"]).max()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(pd.Timestamp(latest).isoformat(), encoding="utf-8")

    def _build_data_quality_report(
        self,
        market: pd.DataFrame,
        stale_days: int,
        freq_drift_tolerance: float,
        min_points_for_freq: int,
    ) -> dict[str, object]:
        if market.empty:
            return {
                "row_count": 0,
                "asset_count": 0,
                "timestamp_min_utc": None,
                "timestamp_max_utc": None,
                "duplicate_asset_timestamp_rows": 0,
                "missing_close_rows": 0,
                "assets_with_non_monotonic_timestamps": 0,
                "stale_days_threshold": stale_days,
                "stale_assets": [],
                "rows_per_asset": {},
                "inferred_base_freq_seconds": None,
                "frequency_by_asset_seconds": {},
                "assets_with_frequency_drift": [],
                "missing_bars_by_asset": {},
            }
        ts = pd.to_datetime(market["timestamp"], utc=True)
        frame = market.assign(timestamp=ts)
        max_ts = frame["timestamp"].max()
        per_asset_last = frame.groupby("asset")["timestamp"].max()
        stale_cutoff = max_ts - pd.Timedelta(days=stale_days)
        stale_assets = sorted(per_asset_last[per_asset_last < stale_cutoff].index.tolist())

        duplicate_rows = int(frame.duplicated(subset=["asset", "timestamp"]).sum())
        missing_close = int(frame["close"].isna().sum())
        invalid_order_assets = int(
            frame.groupby("asset")["timestamp"].apply(lambda s: not s.is_monotonic_increasing).sum()
        )

        freq_by_asset: dict[str, int] = {}
        missing_bars_by_asset: dict[str, int] = {}
        all_freqs: list[int] = []
        for asset, grp in frame.groupby("asset"):
            idx = grp["timestamp"].sort_values().drop_duplicates()
            if len(idx) < max(2, min_points_for_freq):
                missing_bars_by_asset[str(asset)] = 0
                continue
            diffs = idx.diff().dropna().dt.total_seconds()
            median_freq = int(diffs.median())
            if median_freq <= 0:
                missing_bars_by_asset[str(asset)] = 0
                continue
            freq_by_asset[str(asset)] = median_freq
            all_freqs.append(median_freq)
            span_seconds = int((idx.max() - idx.min()).total_seconds())
            expected_points = int(span_seconds / median_freq) + 1
            missing = max(0, expected_points - len(idx))
            missing_bars_by_asset[str(asset)] = int(missing)

        base_freq = int(np.median(all_freqs)) if all_freqs else None
        drift_assets: list[str] = []
        if base_freq and base_freq > 0:
            for asset, freq in freq_by_asset.items():
                rel_dev = abs(freq - base_freq) / base_freq
                if rel_dev > freq_drift_tolerance:
                    drift_assets.append(asset)
        drift_assets = sorted(drift_assets)

        return {
            "row_count": int(len(frame)),
            "asset_count": int(frame["asset"].nunique()),
            "timestamp_min_utc": pd.Timestamp(frame["timestamp"].min()).isoformat(),
            "timestamp_max_utc": pd.Timestamp(max_ts).isoformat(),
            "duplicate_asset_timestamp_rows": duplicate_rows,
            "missing_close_rows": missing_close,
            "assets_with_non_monotonic_timestamps": invalid_order_assets,
            "stale_days_threshold": stale_days,
            "stale_assets": stale_assets,
            "rows_per_asset": frame["asset"].value_counts().sort_index().to_dict(),
            "inferred_base_freq_seconds": base_freq,
            "frequency_by_asset_seconds": freq_by_asset,
            "assets_with_frequency_drift": drift_assets,
            "missing_bars_by_asset": missing_bars_by_asset,
        }

    def _load_asset_holidays(self, cfg: AppConfig, market: pd.DataFrame) -> dict[str, pd.DataFrame]:
        if not cfg.data.enable_db_holidays:
            return {}
        if not cfg.data.connection_uri:
            return {}
        if market.empty:
            return {}

        assets = sorted(market["asset"].astype(str).unique().tolist())
        market_map = cfg.data.asset_market_map or {}
        markets = sorted(
            set(
                m
                for m in [market_map.get(a) for a in assets]
                if isinstance(m, str) and m.strip()
            )
        )
        if cfg.data.default_market:
            markets = sorted(set(markets + [cfg.data.default_market]))
        if not markets:
            return {}

        start = pd.to_datetime(market["timestamp"], utc=True, errors="coerce").min()
        end = pd.to_datetime(market["timestamp"], utc=True, errors="coerce").max()
        if pd.isna(start) or pd.isna(end):
            return {}

        holidays_by_market = load_holidays_by_market(
            HolidayConfig(
                connection_uri=cfg.data.connection_uri,
                holiday_table=cfg.data.holiday_table,
            ),
            markets=markets,
            start=pd.Timestamp(start),
            end=pd.Timestamp(end),
        )
        return build_asset_holiday_frames(
            assets=assets,
            market_by_asset=market_map,
            holidays_by_market=holidays_by_market,
            default_market=cfg.data.default_market,
        )

    def run(self, cfg: AppConfig, progress_hook=None) -> OrchestratorResult:
        def notify(payload: dict[str, object]) -> None:
            if progress_hook is None:
                return
            try:
                progress_hook(payload)
            except Exception:
                pass

        notify({"stage": "start", "event": "run_start", "run_id": cfg.run_id})
        paths = self._artifact_paths(cfg)
        notify({"stage": "data", "event": "loading_data"})
        effective_data_cfg = self._effective_data_config(cfg, paths)
        market, exog = self.data_provider.load_history(effective_data_cfg)
        exog_lagged = drop_exogenous_null_rows(lag_exogenous_one_step(exog))
        exog_model = encode_categorical_exogenous(exog_lagged)
        holiday_by_asset = self._load_asset_holidays(cfg, market)

        data_quality = self._build_data_quality_report(
            market=market,
            stale_days=cfg.execution.data_quality_stale_days,
            freq_drift_tolerance=cfg.execution.data_quality_freq_drift_tolerance,
            min_points_for_freq=cfg.execution.data_quality_min_points_for_freq,
        )
        paths["data_quality"].write_text(json.dumps(data_quality, indent=2), encoding="utf-8")
        notify(
            {
                "stage": "data",
                "event": "data_loaded",
                "asset_count": int(market["asset"].nunique()) if not market.empty else 0,
                "row_count": int(len(market)),
            }
        )

        if market.empty:
            empty_orders = pd.DataFrame(columns=ORDER_COLUMNS)
            orders_path = self.order_exporter.to_csv(empty_orders, paths["orders"])
            paths["model_selection"].write_text(json.dumps({}, indent=2), encoding="utf-8")
            model_governance = {
                "run_id": cfg.run_id,
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "selected_models": {},
                "alert_count": 0,
                "alerts": [],
                "latest_records_count": 0,
                "history_path": str(paths["governance_history"]),
                "status": "no_new_data",
            }
            paths["model_governance"].write_text(
                json.dumps(model_governance, indent=2), encoding="utf-8"
            )
            summary = {
                "run_id": cfg.run_id,
                "assets": [],
                "best_models": {},
                "orders_path": orders_path,
                "data_quality_path": str(paths["data_quality"]),
                "model_selection_path": str(paths["model_selection"]),
                "model_governance_path": str(paths["model_governance"]),
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "allocation_diagnostics": {},
                "execution_diagnostics": self.order_exporter._empty_diagnostics(),
                "governance_alert_count": 0,
                "run_status": "no_new_data",
                "message": "No rows available after applying ingestion filters/incremental window.",
            }
            summary["report_path"] = write_run_report(
                report_path=paths["run_report"],
                run_id=cfg.run_id,
                summary=summary,
                data_quality=data_quality,
                governance=model_governance,
            )
            paths["summary"].write_text(json.dumps(summary, indent=2), encoding="utf-8")
            notify({"stage": "complete", "event": "no_new_data"})

            return OrchestratorResult(
                backtest=BacktestResult(
                    metrics=pd.DataFrame(),
                    fold_predictions=pd.DataFrame(),
                    best_models={},
                    selection_rationale={},
                ),
                forecast=ForecastResult(predictions=pd.DataFrame()),
                allocation=AllocationResult(allocations=pd.DataFrame(), diagnostics={}),
                orders_path=orders_path,
                summary_path=str(paths["summary"]),
                data_quality_path=str(paths["data_quality"]),
                model_selection_path=str(paths["model_selection"]),
                model_governance_path=str(paths["model_governance"]),
                report_path=str(paths["run_report"]),
                run_status="no_new_data",
            )

        self._write_incremental_state(cfg, paths, market)

        _ = build_lagged_regressors(market)
        candidate_models = cfg.model.candidates or get_available_model_names()
        if not candidate_models:
            candidate_models = ["naive_last"]
        excluded_daily_update = get_excluded_from_daily_update(candidate_models)
        notify(
            {
                "stage": "backtest",
                "event": "backtest_start",
                "model_count": len(candidate_models),
                "asset_count": int(market["asset"].nunique()),
            }
        )

        backtest = self.backtest_engine.run(
            market=market,
            model_names=candidate_models,
            backtest_config=cfg.backtest,
            exog=exog_model,
            holiday_by_asset=holiday_by_asset,
            progress_hook=progress_hook,
        )
        notify({"stage": "backtest", "event": "backtest_done"})
        paths["model_selection"].write_text(
            json.dumps(backtest.selection_rationale, indent=2, default=str),
            encoding="utf-8",
        )
        model_governance = self._build_model_governance(backtest, cfg, paths)
        paths["model_governance"].write_text(
            json.dumps(model_governance, indent=2), encoding="utf-8"
        )

        model_by_asset = backtest.best_models
        if not model_by_asset:
            # fallback when backtest has insufficient data
            model_by_asset = {a: candidate_models[0] for a in sorted(market["asset"].unique())}
        notify(
            {
                "stage": "forecast",
                "event": "forecast_start",
                "asset_count": len(model_by_asset),
            }
        )

        forecast = self.forecast_engine.forecast_assets(
            market=market,
            model_by_asset=model_by_asset,
            horizon=cfg.backtest.horizon,
            target_confidence=cfg.risk.target_confidence,
            update_mode=cfg.model.update_mode,
            state_dir=paths["model_state_dir"],
            exog=exog_model,
            holiday_by_asset=holiday_by_asset,
        )
        notify({"stage": "forecast", "event": "forecast_done", "rows": int(len(forecast.predictions))})

        notify({"stage": "portfolio", "event": "portfolio_start"})
        allocation = self.portfolio_engine.rebalance(
            forecast_frame=forecast.predictions,
            risk_config=cfg.risk,
            portfolio_config=cfg.portfolio,
        )
        notify({"stage": "portfolio", "event": "portfolio_done"})

        latest_prices = (
            market.sort_values("timestamp")
            .groupby("asset", as_index=False)
            .tail(1)[["asset", "close"]]
            .reset_index(drop=True)
        )
        order_day = datetime.now(UTC).strftime("%Y-%m-%d")
        orders, order_diagnostics = self.order_exporter.generate_orders_with_diagnostics(
            allocation_frame=allocation.allocations,
            price_frame=latest_prices,
            as_of_date=order_day,
            portfolio_value=cfg.execution.portfolio_value,
            strategy_id=cfg.run_id,
            no_trade_band=cfg.execution.no_trade_band,
            min_order_notional=cfg.execution.min_order_notional,
            default_lot_size=cfg.execution.default_lot_size,
            lot_size_by_asset=cfg.execution.lot_size_by_asset,
            max_order_notional=cfg.execution.max_order_notional,
            max_turnover_notional_per_asset=cfg.execution.max_turnover_notional_per_asset,
        )
        notify(
            {
                "stage": "orders",
                "event": "orders_done",
                "order_count": int(len(orders)),
            }
        )

        # Save walkforward backtest artifacts to run-specific folder structure
        # Metrics: contains per-asset/model performance: results/backtests/{run_id}/metrics.parquet
        # Folds: contains per-fold trade data (cutoff, fold_return, etc): results/backtests/{run_id}/fold_predictions.parquet
        backtest.metrics.to_parquet(paths["metrics"], index=False)
        backtest.fold_predictions.to_parquet(paths["folds"], index=False)
        forecast.predictions.to_parquet(paths["forecast"], index=False)
        orders_path = self.order_exporter.to_csv(orders, paths["orders"])

        summary = {
            "run_id": cfg.run_id,
            "assets": sorted(market["asset"].astype(str).unique().tolist()),
            "best_models": model_by_asset,
            "candidate_models": candidate_models,
            "orders_path": orders_path,
            "data_quality_path": str(paths["data_quality"]),
            "model_selection_path": str(paths["model_selection"]),
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "allocation_diagnostics": allocation.diagnostics,
            "execution_diagnostics": order_diagnostics,
            "forecast_update_mode": cfg.model.update_mode,
            "forecast_update_status_counts": forecast.predictions.get(
                "update_status", pd.Series(dtype=str)
            ).value_counts().to_dict(),
            "forecast_exog_used_count": int(
                forecast.predictions.get("exog_used", pd.Series(dtype=bool)).sum()
            ),
            "exog_columns": (
                [c for c in exog_model.columns if c not in {"timestamp", "asset"}]
                if exog_model is not None
                else []
            ),
            "holiday_assets_count": int(len(holiday_by_asset)),
            "holiday_enabled": bool(cfg.data.enable_db_holidays),
            "daily_update_excluded_models": excluded_daily_update,
            "model_governance_path": str(paths["model_governance"]),
            "governance_alert_count": int(model_governance["alert_count"]),
            "run_status": "completed",
        }
        summary["report_path"] = write_run_report(
            report_path=paths["run_report"],
            run_id=cfg.run_id,
            summary=summary,
            data_quality=data_quality,
            governance=model_governance,
        )
        paths["summary"].write_text(json.dumps(summary, indent=2), encoding="utf-8")
        notify({"stage": "complete", "event": "run_completed"})

        return OrchestratorResult(
            backtest=backtest,
            forecast=forecast,
            allocation=allocation,
            orders_path=orders_path,
            summary_path=str(paths["summary"]),
            data_quality_path=str(paths["data_quality"]),
            model_selection_path=str(paths["model_selection"]),
            model_governance_path=str(paths["model_governance"]),
            report_path=str(paths["run_report"]),
            run_status="completed",
        )
