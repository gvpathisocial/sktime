"""Dataclass-based runtime configuration for sktime_quant."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DataConfig:
    source_type: str = "timescale"
    connection_uri: str | None = None
    market_table: str = "market_data"
    exog_table: str | None = None
    csv_path: str | None = None
    folder_path: str | None = None
    start: str | None = None
    end: str | None = None
    universe: list[str] = field(default_factory=list)
    incremental_mode: bool = False
    incremental_state_path: str | None = None
    strict_schema_validation: bool = True
    db_max_retries: int = 3
    db_retry_backoff_seconds: float = 1.0
    enable_db_holidays: bool = False
    holiday_table: str = "public.holiday_calendar"
    asset_market_map: dict[str, str] = field(default_factory=dict)
    default_market: str | None = None


@dataclass(slots=True)
class BacktestConfig:
    splitter_type: str = "expanding"
    window_length: int = 90
    step_length: int = 5
    horizon: int = 1
    strategy: str = "refit"
    confidence_floor: float = 0.95
    transaction_cost_bps: float = 5.0
    slippage_bps: float = 2.0
    max_failure_rate: float = 0.4
    min_successful_folds: int = 3
    strategy_policy: str = "sign"
    signal_threshold: float = 0.0
    objective: str = "composite"


@dataclass(slots=True)
class ModelConfig:
    candidates: list[str] = field(
        default_factory=lambda: ["naive_last", "naive_mean", "theta"]
    )
    update_mode: str = "update"


@dataclass(slots=True)
class RiskConfig:
    max_drawdown: float = 0.2
    max_turnover: float = 0.25
    target_confidence: float = 0.95
    max_weight: float = 0.25


@dataclass(slots=True)
class PortfolioConfig:
    return_weight: float = 1.0
    risk_weight: float = 0.5
    confidence_weight: float = 0.75
    cash_buffer: float = 0.02


@dataclass(slots=True)
class StrategyConfig:
    mode: str = "forecast_only"
    rule_chain: str = "any"
    rules_path: str | None = None
    rules: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {
                "name": "rsi_buy",
                "feature": "rsi_14",
                "operator": "<=",
                "value": 35.0,
                "signal": 1,
            },
            {
                "name": "rsi_sell",
                "feature": "rsi_14",
                "operator": ">=",
                "value": 65.0,
                "signal": -1,
            },
        ]
    )
    classifier_type: str = "random_forest"
    classifier_min_train_samples: int = 30
    classifier_probability_threshold: float = 0.55
    blend_policy: str = "weighted_vote"
    blend_forecast_weight: float = 0.34
    blend_rule_weight: float = 0.33
    blend_classifier_weight: float = 0.33
    blend_vote_threshold: float = 0.1


@dataclass(slots=True)
class ExecutionConfig:
    output_dir: str = "results"
    orders_subdir: str = "orders"
    schema_version: str = "v1"
    file_prefix: str = "orders"
    portfolio_value: float = 1000000.0
    no_trade_band: float = 0.0
    min_order_notional: float = 0.0
    data_quality_stale_days: int = 3
    data_quality_freq_drift_tolerance: float = 0.2
    data_quality_min_points_for_freq: int = 5
    default_lot_size: int = 1
    lot_size_by_asset: dict[str, int] = field(default_factory=dict)
    max_order_notional: float = 0.0
    max_turnover_notional_per_asset: float = 0.0
    governance_coverage_alert_threshold: float = 0.9
    governance_failure_alert_threshold: float = 0.2
    governance_coverage_drop_alert: float = 0.05
    governance_history_max_records: int = 5000


@dataclass(slots=True)
class AppConfig:
    data: DataConfig = field(default_factory=DataConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    run_id: str = "default_run"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AppConfig":
        return cls(
            data=DataConfig(**payload.get("data", {})),
            backtest=BacktestConfig(**payload.get("backtest", {})),
            model=ModelConfig(**payload.get("model", {})),
            risk=RiskConfig(**payload.get("risk", {})),
            portfolio=PortfolioConfig(**payload.get("portfolio", {})),
            strategy=StrategyConfig(**payload.get("strategy", {})),
            execution=ExecutionConfig(**payload.get("execution", {})),
            run_id=payload.get("run_id", "default_run"),
        )

