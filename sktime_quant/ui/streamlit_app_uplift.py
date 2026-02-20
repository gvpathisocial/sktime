"""Uplifted Streamlit UI for sktime_quant workflows.

This app keeps backend logic intact and focuses on a clearer operator UX:
- Run Studio: configure + execute in one place
- Run Explorer: strict per-run artifact view
- Governance: run-level alerts + cross-run trend history
- Orders: run-scoped order inspection/download
- Performance Analytics: risk metrics + equity curve visualization
- Config Lab: full YAML editor for advanced profile fields
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
import random
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import streamlit as st
import yaml

try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

from sktime_quant.config.loader import load_config
from sktime_quant.config.profiles import save_profile
from sktime_quant.config.schema import AppConfig
from sktime_quant.models.health import summarize_runtime_health
from sktime_quant.models.registry import (
    get_available_model_names,
    get_excluded_from_daily_update,
    get_model_health,
    get_model_overview_rows,
    get_registered_model_names,
)
from sktime_quant.pipelines.orchestrator import Orchestrator

try:
    from sktime_quant.risk.metrics import (
        sortino_ratio,
        sharpe_ratio,
        max_drawdown,
        calmar_ratio,
        cumulative_returns,
        annualized_volatility,
    )
    HAS_RISK_METRICS = True
except ImportError:
    HAS_RISK_METRICS = False


st.set_page_config(page_title="sktime quant uplift", layout="wide")


def _apply_style() -> None:
    st.markdown(
        """
        <style>
        .main .block-container {padding-top: 1.1rem; padding-bottom: 1.8rem;}
        h1, h2, h3 {letter-spacing: -0.02em;}
        .sq-card {
          border: 1px solid #e6e8ef;
          border-radius: 14px;
          padding: 0.9rem 1rem;
          background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
          margin-bottom: 0.75rem;
        }
        .sq-chip {
          display: inline-block; padding: 0.2rem 0.55rem; border-radius: 999px;
          border: 1px solid #d7deed; margin-right: 0.3rem; margin-bottom: 0.3rem;
          font-size: 0.78rem; background: #f4f8ff;
        }
        .sq-muted {color: #4f5b75; font-size: 0.9rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _init_state() -> None:
    if "cfg" not in st.session_state:
        st.session_state.cfg = AppConfig()
    if "result" not in st.session_state:
        st.session_state.result = None
    if "profile_path" not in st.session_state:
        st.session_state.profile_path = "profiles/quant_profile.yaml"
    if "run_history" not in st.session_state:
        st.session_state.run_history = []
    if "progress_events" not in st.session_state:
        st.session_state.progress_events = []
    if "last_error" not in st.session_state:
        st.session_state.last_error = None
    if "advanced_cfg_yaml" not in st.session_state:
        st.session_state.advanced_cfg_yaml = ""
    if "use_history_window" not in st.session_state:
        st.session_state.use_history_window = False
    if "history_years" not in st.session_state:
        st.session_state.history_years = 5


def _generate_run_id() -> str:
    adjectives = [
        "atlas",
        "ember",
        "harbor",
        "lumen",
        "nova",
        "opal",
        "ridge",
        "swift",
        "terra",
        "vivid",
    ]
    nouns = [
        "alpha",
        "beacon",
        "delta",
        "matrix",
        "orbit",
        "pulse",
        "signal",
        "summit",
        "vector",
        "wave",
    ]
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"{random.choice(adjectives)}_{random.choice(nouns)}_{stamp}"


def _source_details(cfg: AppConfig) -> str:
    if cfg.data.source_type == "folder":
        return f"folder={cfg.data.folder_path or '<empty>'}"
    if cfg.data.source_type == "csv":
        return f"csv={cfg.data.csv_path or '<empty>'}"
    if cfg.data.source_type == "timescale":
        uri = cfg.data.connection_uri or ""
        market = cfg.data.market_table or "market_data"
        exog = cfg.data.exog_table or "-"
        if uri:
            p = urlparse(uri)
            host = p.hostname or "unknown-host"
            db = p.path.lstrip("/") if p.path else "unknown-db"
            return f"timescale={host}/{db} market_table={market} exog_table={exog}"
        return f"timescale=<missing-uri> market_table={market} exog_table={exog}"
    return cfg.data.source_type


def _safe_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_object_dtype(out[col]):
            out[col] = out[col].map(lambda x: str(x) if x is not None else "")
    return out


def _show_df(df: pd.DataFrame, *, height: int | None = None) -> None:
    st.dataframe(_safe_dataframe(df), use_container_width=True, height=height)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _run_id_from_summary_file(name: str) -> str:
    suffix = "_summary.json"
    return name[: -len(suffix)] if name.endswith(suffix) else name


def _report_dir(cfg: AppConfig) -> Path:
    return Path(cfg.execution.output_dir) / "reports"


def _summary_files(cfg: AppConfig) -> list[Path]:
    report_dir = _report_dir(cfg)
    if not report_dir.exists():
        return []
    return sorted(report_dir.glob("*_summary.json"), reverse=True)


def _load_backtest_results(run_id: str, cfg: AppConfig) -> pd.DataFrame | None:
    """
    Load backtest results from walkforward engine output.
    
    Loads fold_predictions from the walkforward run and aggregates returns.
    Falls back to metrics if fold_predictions is empty/missing.
    
    :param run_id: run identifier
    :param cfg: AppConfig for output dir reference
    :return: DataFrame with columns: date, returns, equity_value, or None if not found
    """
    results_dir = Path(cfg.execution.output_dir) / "backtests" / run_id
    if not results_dir.exists():
        return None
    
    # Load fold predictions from walkforward output (per-fold trade data)
    folds_path = results_dir / "fold_predictions.parquet"
    if folds_path.exists():
        try:
            df = pd.read_parquet(folds_path)
            if not df.empty:
                # Normalize cutoff to datetime and sort
                df = df.copy()
                df["date"] = pd.to_datetime(df["cutoff"], errors="coerce")
                df = df.dropna(subset=["date"])
                
                # Check if fold_return column exists, otherwise skip
                if "fold_return" in df.columns:
                    df = df.sort_values("date")
                    
                    # Aggregate returns (sum across assets + models per day for portfolio view)
                    daily = df.groupby("date").agg({
                        "fold_return": "sum",  # total portfolio return that day
                    }).reset_index()
                    daily.columns = ["date", "returns"]
                    
                    # Build equity curve from cumulative returns
                    daily["equity_value"] = (1 + daily["returns"].fillna(0)).cumprod() * 100000
                    return daily
        except Exception:
            pass
    
    # Fallback: try metrics file (metrics-only view, no per-fold detail)
    metrics_path = results_dir / "metrics.parquet"
    if metrics_path.exists():
        try:
            metrics_df = pd.read_parquet(metrics_path)
            if not metrics_df.empty and "max_drawdown" in metrics_df.columns:
                # Create synthetic daily returns from metrics aggregates
                daily = pd.DataFrame({
                    "date": [pd.Timestamp.now()],
                    "returns": [metrics_df["sharpe"].mean() / 252],  # rough proxy
                    "equity_value": [100000],  # single point
                })
                return daily
        except Exception:
            pass
    
    return None



def _compute_risk_metrics(backtest_df: pd.DataFrame) -> dict | None:
    """
    Compute risk metrics from backtest results DataFrame.
    
    Expected columns: date, returns, equity_value (or similar names)
    
    :param backtest_df: DataFrame with backtest results
    :return: dict with risk metrics or None
    """
    if not HAS_RISK_METRICS:
        return None
    
    if backtest_df is None or backtest_df.empty:
        return None
    
    # Normalize column names to lowercase
    df = backtest_df.copy()
    df.columns = map(str.lower, df.columns)
    
    # Try to find returns column
    returns = None
    for col in ["returns", "daily_returns", "pnl_return", "return"]:
        if col in df.columns:
            returns = pd.to_numeric(df[col], errors="coerce").dropna()
            break
    
    if returns is None or returns.empty or len(returns) < 2:
        return None
    
    # Try to find equity column
    equity = None
    for col in ["equity_value", "cumulative_equity", "equity", "portfolio_value"]:
        if col in df.columns:
            equity = pd.to_numeric(df[col], errors="coerce").dropna()
            break
    
    if equity is None or equity.empty:
        equity = (1 + returns.fillna(0)).cumprod() * 100000  # assume $100k starting
    
    try:
        metrics = {
            "sortino": float(sortino_ratio(returns, target_return=0.0, periods=252)) if not returns.empty else np.nan,
            "sharpe": float(sharpe_ratio(returns, risk_free_rate=0.02, periods=252)) if not returns.empty else np.nan,
            "max_drawdown": float(max_drawdown(returns)) if not returns.empty else np.nan,
            "calmar": float(calmar_ratio(equity, periods=252)) if not equity.empty else np.nan,
            "total_return": float(cumulative_returns(equity)) if not equity.empty else np.nan,
            "avg_daily_return": float(returns.mean()) if not returns.empty else np.nan,
            "volatility": float(annualized_volatility(returns, periods=252)) if not returns.empty else np.nan,
            "win_rate": float((returns > 0).sum() / len(returns)) if len(returns) > 0 else 0.0,
            "num_trades": int(len(returns)),
        }
        return metrics
    except Exception as exc:
        st.warning(f"Error computing risk metrics: {exc}")
        return None


def _plot_equity_curve(backtest_df: pd.DataFrame) -> go.Figure | None:
    """Plot equity curve from backtest results."""
    if not HAS_PLOTLY:
        return None
    
    if backtest_df is None or backtest_df.empty:
        return None
    
    df = backtest_df.copy()
    df.columns = map(str.lower, df.columns)
    
    # Find date and equity columns
    date_col = None
    for col in ["date", "timestamp", "time"]:
        if col in df.columns:
            date_col = col
            break
    
    equity_col = None
    for col in ["equity_value", "cumulative_equity", "equity", "portfolio_value"]:
        if col in df.columns:
            equity_col = col
            break
    
    if date_col is None or equity_col is None:
        return None
    
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df[equity_col] = pd.to_numeric(df[equity_col], errors="coerce")
    df = df.sort_values(date_col).dropna(subset=[date_col, equity_col])
    
    if df.empty:
        return None
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[date_col],
        y=df[equity_col],
        mode="lines",
        name="Equity",
        line=dict(color="#1f77b4", width=2),
    ))
    
    fig.update_layout(
        title="Equity Curve",
        xaxis_title="Date",
        yaxis_title="Portfolio Value",
        hovermode="x unified",
        template="plotly_white",
        height=400,
    )
    return fig


def _plot_rolling_sortino(backtest_df: pd.DataFrame, window: int = 30) -> go.Figure | None:
    """Plot rolling Sortino ratio from backtest results."""
    if not HAS_PLOTLY or not HAS_RISK_METRICS:
        return None
    
    if backtest_df is None or backtest_df.empty:
        return None
    
    df = backtest_df.copy()
    df.columns = map(str.lower, df.columns)
    
    # Find date and returns columns
    date_col = None
    for col in ["date", "timestamp", "time"]:
        if col in df.columns:
            date_col = col
            break
    
    returns_col = None
    for col in ["returns", "daily_returns", "pnl_return", "return"]:
        if col in df.columns:
            returns_col = col
            break
    
    if date_col is None or returns_col is None:
        return None
    
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df[returns_col] = pd.to_numeric(df[returns_col], errors="coerce")
    df = df.sort_values(date_col).dropna(subset=[date_col, returns_col])
    
    if len(df) < window + 1:
        return None
    
    rolling_sortino = []
    dates = []
    
    for i in range(window, len(df)):
        window_returns = df[returns_col].iloc[i - window:i]
        s_ratio = sortino_ratio(window_returns, target_return=0.0, periods=252)
        rolling_sortino.append(s_ratio if not pd.isna(s_ratio) else None)
        dates.append(df[date_col].iloc[i])
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates,
        y=rolling_sortino,
        mode="lines",
        name=f"Rolling Sortino ({window}d)",
        line=dict(color="#ff7f0e", width=2),
        fill="tozeroy",
    ))
    
    fig.update_layout(
        title=f"Rolling Sortino Ratio ({window}-day window)",
        xaxis_title="Date",
        yaxis_title="Sortino Ratio",
        hovermode="x unified",
        template="plotly_white",
        height=400,
    )
    return fig


def _plot_drawdown(backtest_df: pd.DataFrame) -> go.Figure | None:
    """Plot drawdown (underwater plot) from backtest results."""
    if not HAS_PLOTLY:
        return None
    
    if backtest_df is None or backtest_df.empty:
        return None
    
    df = backtest_df.copy()
    df.columns = map(str.lower, df.columns)
    
    # Find date column
    date_col = None
    for col in ["date", "timestamp", "time"]:
        if col in df.columns:
            date_col = col
            break
    
    # Find equity column
    equity_col = None
    for col in ["equity_value", "cumulative_equity", "equity", "portfolio_value"]:
        if col in df.columns:
            equity_col = col
            break
    
    if date_col is None or equity_col is None:
        return None
    
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df[equity_col] = pd.to_numeric(df[equity_col], errors="coerce")
    df = df.sort_values(date_col).dropna(subset=[date_col, equity_col])
    
    if df.empty:
        return None
    
    running_max = df[equity_col].expanding().max()
    drawdown = (df[equity_col] - running_max) / running_max * 100
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[date_col],
        y=drawdown,
        mode="lines",
        name="Drawdown %",
        line=dict(color="#d62728", width=2),
        fill="tozeroy",
    ))
    
    fig.update_layout(
        title="Drawdown from Peak",
        xaxis_title="Date",
        yaxis_title="Drawdown (%)",
        hovermode="x unified",
        template="plotly_white",
        height=400,
    )
    return fig



def _fmt_event(evt: dict[str, object]) -> str:
    stage = str(evt.get("stage", "unknown"))
    event = str(evt.get("event", ""))
    if stage == "backtest" and event == "model_start":
        return (
            f"backtest [{evt.get('task_index')}/{evt.get('task_total')}] "
            f"{evt.get('asset')} -> {evt.get('model')}"
        )
    if stage == "backtest" and event == "backtest_start":
        return f"backtest start: assets={evt.get('asset_count')} models={evt.get('model_count')}"
    if stage == "forecast" and event == "forecast_start":
        return f"forecast start: assets={evt.get('asset_count')}"
    if stage == "orders" and event == "orders_done":
        return f"orders done: count={evt.get('order_count')}"
    return f"{stage}:{event}"


def _render_profile_box(cfg: AppConfig) -> AppConfig:
    st.sidebar.markdown("### Session")
    st.session_state.profile_path = st.sidebar.text_input(
        "Profile path", value=st.session_state.profile_path
    )
    col1, col2 = st.sidebar.columns(2)
    if col1.button("Load"):
        loaded = load_config(st.session_state.profile_path)
        st.session_state.cfg = loaded
        cfg = loaded
        st.success(f"Loaded profile: {st.session_state.profile_path}")
    if col2.button("Save"):
        saved = save_profile(cfg, st.session_state.profile_path)
        st.success(f"Saved profile: {saved}")
    if st.sidebar.button("New run_id"):
        cfg.run_id = _generate_run_id()
        st.session_state.cfg = cfg
    st.sidebar.caption(f"`run_id`: `{cfg.run_id}`")
    st.sidebar.caption(f"`source`: {_source_details(cfg)}")
    return cfg


def _render_data_inputs(cfg: AppConfig) -> None:
    source = st.selectbox("Source", ["timescale", "csv", "folder"], index=["timescale", "csv", "folder"].index(cfg.data.source_type))
    cfg.data.source_type = source

    c1, c2, c3 = st.columns([1, 1, 1.2])
    st.session_state.use_history_window = c1.checkbox(
        "Limit history window",
        value=bool(st.session_state.use_history_window),
        help="Trim historical rows to reduce run time.",
    )
    if st.session_state.use_history_window:
        st.session_state.history_years = int(
            c2.number_input("History years", min_value=1, max_value=30, value=int(st.session_state.history_years))
        )
        start_ts = pd.Timestamp.now(tz="UTC") - pd.DateOffset(years=int(st.session_state.history_years))
        cfg.data.start = start_ts.date().isoformat()
        c3.caption(f"Computed start: `{cfg.data.start}`")
    else:
        cfg.data.start = c2.text_input("Start (YYYY-MM-DD)", cfg.data.start or "") or None

    cfg.data.end = st.text_input("End (YYYY-MM-DD)", cfg.data.end or "") or None
    cfg.data.incremental_mode = st.checkbox("Incremental mode", value=cfg.data.incremental_mode)

    if source == "timescale":
        cfg.data.connection_uri = st.text_input("Connection URI", cfg.data.connection_uri or "")
        col_a, col_b = st.columns(2)
        cfg.data.market_table = col_a.text_input("Market table", cfg.data.market_table)
        cfg.data.exog_table = col_b.text_input("Exogenous table", cfg.data.exog_table or "")
        cfg.data.incremental_state_path = st.text_input(
            "Incremental state path",
            cfg.data.incremental_state_path or "",
        ) or None
        cfg.data.enable_db_holidays = st.checkbox(
            "Enable holiday table (Prophet-ready)",
            value=cfg.data.enable_db_holidays,
        )
        if cfg.data.enable_db_holidays:
            col_h1, col_h2 = st.columns(2)
            cfg.data.holiday_table = col_h1.text_input("Holiday table", cfg.data.holiday_table)
            cfg.data.default_market = col_h2.text_input(
                "Default market",
                cfg.data.default_market or "",
            ) or None
            mapping_raw = st.text_area(
                "Asset -> market JSON",
                value=json.dumps(cfg.data.asset_market_map or {}, indent=2),
                height=120,
            )
            try:
                parsed = json.loads(mapping_raw) if mapping_raw.strip() else {}
                cfg.data.asset_market_map = {str(k): str(v) for k, v in dict(parsed).items()}
            except Exception as exc:
                st.warning(f"Invalid market map JSON, keeping previous value: {exc}")

    if source == "csv":
        cfg.data.csv_path = st.text_input("CSV path", cfg.data.csv_path or "")
    if source == "folder":
        cfg.data.folder_path = st.text_input("Folder path", cfg.data.folder_path or "")


def _render_model_inputs(cfg: AppConfig) -> None:
    cfg.backtest.splitter_type = st.selectbox(
        "Splitter",
        ["expanding", "sliding"],
        index=["expanding", "sliding"].index(cfg.backtest.splitter_type),
    )
    col1, col2, col3 = st.columns(3)
    cfg.backtest.window_length = int(col1.number_input("Window", min_value=10, value=cfg.backtest.window_length))
    cfg.backtest.step_length = int(col2.number_input("Step", min_value=1, value=cfg.backtest.step_length))
    cfg.backtest.horizon = int(col3.number_input("Horizon", min_value=1, value=cfg.backtest.horizon))

    available_models = get_available_model_names()
    default_models = [m for m in cfg.model.candidates if m in available_models]
    if not default_models:
        default_models = [m for m in ["naive_last", "theta"] if m in available_models]
    selected = st.multiselect(
        "Candidate models",
        options=available_models,
        default=default_models,
        help="Leave empty to auto-use all available models at run time.",
    )
    cfg.model.candidates = selected
    cfg.model.update_mode = st.selectbox(
        "Update mode",
        ["update", "refit"],
        index=["update", "refit"].index(cfg.model.update_mode),
    )

    if cfg.model.update_mode == "update" and cfg.model.candidates:
        excluded = get_excluded_from_daily_update(cfg.model.candidates)
        if excluded:
            st.warning("Some selected models cannot use daily delta update and will refit.")
            _show_df(pd.DataFrame(excluded), height=180)

    health_rows = get_model_health(get_registered_model_names())
    if health_rows:
        st.markdown('<div class="sq-card"><b>Model availability health</b><div class="sq-muted">Dependency/runtime checks for this environment.</div></div>', unsafe_allow_html=True)
        _show_df(pd.DataFrame(health_rows), height=240)

    if cfg.model.candidates:
        overviews = get_model_overview_rows(cfg.model.candidates)
        if overviews:
            st.markdown('<div class="sq-card"><b>Selected model overviews</b></div>', unsafe_allow_html=True)
            _show_df(pd.DataFrame(overviews), height=220)
            with st.expander("Model notes"):
                for row in overviews:
                    st.write(
                        f"{row['model']}: {row['summary']} | best_for={row['best_for']} | notes={row['notes']}"
                    )


def _render_risk_execution_inputs(cfg: AppConfig) -> None:
    col1, col2, col3 = st.columns(3)
    cfg.risk.target_confidence = col1.slider("Target confidence", 0.5, 0.99, float(cfg.risk.target_confidence), 0.01)
    cfg.risk.max_turnover = col2.slider("Max turnover", 0.01, 1.0, float(cfg.risk.max_turnover), 0.01)
    cfg.risk.max_weight = col3.slider("Max weight", 0.01, 1.0, float(cfg.risk.max_weight), 0.01)

    col4, col5, col6 = st.columns(3)
    cfg.execution.no_trade_band = col4.slider("No-trade band", 0.0, 0.1, float(cfg.execution.no_trade_band), 0.001)
    cfg.execution.min_order_notional = col5.number_input("Min order notional", min_value=0.0, value=float(cfg.execution.min_order_notional), step=100.0)
    cfg.execution.max_order_notional = col6.number_input("Max order notional", min_value=0.0, value=float(cfg.execution.max_order_notional), step=100.0)

    col7, col8, col9 = st.columns(3)
    cfg.execution.max_turnover_notional_per_asset = col7.number_input(
        "Max turnover/asset/day",
        min_value=0.0,
        value=float(cfg.execution.max_turnover_notional_per_asset),
        step=100.0,
    )
    cfg.execution.default_lot_size = int(
        col8.number_input("Default lot size", min_value=1, value=int(cfg.execution.default_lot_size), step=1)
    )
    cfg.execution.portfolio_value = float(
        col9.number_input("Portfolio value", min_value=1000.0, value=float(cfg.execution.portfolio_value), step=10000.0)
    )


def _run_pipeline(cfg: AppConfig) -> None:
    st.session_state.last_error = None
    st.session_state.progress_events = []
    with st.status("Running pipeline", expanded=True) as status:
        status.write(f"run_id={cfg.run_id}")
        status.write(f"source={_source_details(cfg)}")
        status.write(f"profile={st.session_state.profile_path}")

        def hook(evt: dict[str, object]) -> None:
            st.session_state.progress_events.append(evt)
            status.write(_fmt_event(evt))

        try:
            result = Orchestrator().run(cfg, progress_hook=hook)
            st.session_state.result = result
            st.session_state.run_history.append(
                {
                    "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                    "run_id": cfg.run_id,
                    "run_status": result.run_status,
                    "source_type": cfg.data.source_type,
                    "summary_path": result.summary_path,
                    "orders_path": result.orders_path,
                    "profile_path": st.session_state.profile_path,
                }
            )
            status.update(label=f"Run completed: {result.run_status}", state="complete")
        except Exception as exc:
            st.session_state.result = None
            st.session_state.last_error = f"{type(exc).__name__}: {exc}"
            status.update(label="Run failed", state="error")


def _render_run_explorer(cfg: AppConfig) -> None:
    files = _summary_files(cfg)
    if not files:
        st.info("No run summaries found yet.")
        return

    chosen = st.selectbox("Select run summary", [f.name for f in files], key="uplift_run_pick")
    summary_path = _report_dir(cfg) / chosen
    summary = _load_json(summary_path)
    run_id = _run_id_from_summary_file(chosen)

    st.markdown(f"### Run `{run_id}`")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", str(summary.get("run_status", "unknown")))
    c2.metric("Assets", len(summary.get("assets", [])) if isinstance(summary.get("assets"), list) else 0)
    c3.metric("Governance Alerts", int(summary.get("governance_alert_count", 0)) if str(summary.get("governance_alert_count", "")).isdigit() else str(summary.get("governance_alert_count", 0)))
    best = summary.get("best_models", {})
    c4.metric("Best Models", len(best) if isinstance(best, dict) else 0)

    if isinstance(best, dict) and best:
        st.markdown("#### Best model by asset")
        _show_df(pd.DataFrame([{"asset": a, "model": m} for a, m in best.items()]), height=250)

    dq = _load_json(Path(summary.get("data_quality_path", ""))) if summary.get("data_quality_path") else {}
    if dq:
        st.markdown("#### Data quality")
        dq_rows = [
            {"metric": "row_count", "value": dq.get("row_count")},
            {"metric": "asset_count", "value": dq.get("asset_count")},
            {"metric": "duplicate_asset_timestamp_rows", "value": dq.get("duplicate_asset_timestamp_rows")},
            {"metric": "missing_close_rows", "value": dq.get("missing_close_rows")},
            {"metric": "inferred_base_freq_seconds", "value": dq.get("inferred_base_freq_seconds")},
        ]
        _show_df(pd.DataFrame(dq_rows), height=200)

    sel = _load_json(Path(summary.get("model_selection_path", ""))) if summary.get("model_selection_path") else {}
    if sel:
        st.markdown("#### Model selection diagnostics")
        rows = []
        for asset, recs in sel.items():
            if isinstance(recs, list) and recs:
                top = recs[0]
                rows.append(
                    {
                        "asset": asset,
                        "model": top.get("model"),
                        "rank": top.get("rank"),
                        "risk_adjusted_score": top.get("risk_adjusted_score"),
                        "excluded": top.get("excluded"),
                    }
                )
        if rows:
            _show_df(pd.DataFrame(rows), height=260)

    gov = _load_json(Path(summary.get("model_governance_path", ""))) if summary.get("model_governance_path") else {}
    if gov:
        st.markdown("#### Governance alerts")
        alerts = gov.get("alerts", [])
        if alerts:
            _show_df(pd.DataFrame(alerts), height=240)
        else:
            st.caption("No governance alerts for this run.")

    with st.expander("Raw artifacts JSON (selected run only)"):
        st.markdown("**Summary**")
        st.json(summary)
        if dq:
            st.markdown("**Data quality**")
            st.json(dq)
        if sel:
            st.markdown("**Model selection**")
            st.json(sel)
        if gov:
            st.markdown("**Governance**")
            st.json(gov)


def _render_governance(cfg: AppConfig) -> None:
    st.markdown("### Governance")
    files = _summary_files(cfg)
    if files:
        chosen = st.selectbox(
            "Run for governance details",
            [f.name for f in files],
            key="uplift_gov_run_pick",
        )
        summary = _load_json(_report_dir(cfg) / chosen)
        gov = _load_json(Path(summary.get("model_governance_path", ""))) if summary.get("model_governance_path") else {}
        if gov:
            col1, col2 = st.columns(2)
            col1.metric("Alert count", int(gov.get("alert_count", 0)))
            col2.metric("Selected models", len(gov.get("selected_models", {})))
            alerts = gov.get("alerts", [])
            if alerts:
                _show_df(pd.DataFrame(alerts), height=220)
            else:
                st.caption("No run-specific governance alerts.")

    hist_path = Path(cfg.execution.output_dir) / "governance" / "model_stability_history.json"
    if not hist_path.exists():
        st.info("No governance history file yet.")
        return
    payload = _load_json(hist_path)
    history = payload.get("history", [])
    hist_df = pd.DataFrame(history)
    if hist_df.empty:
        st.info("Governance history exists but is empty.")
        return

    if "timestamp_utc" in hist_df.columns:
        hist_df["timestamp_utc"] = pd.to_datetime(hist_df["timestamp_utc"], errors="coerce", utc=True)
    hist_df = hist_df.sort_values("timestamp_utc")
    assets = sorted(hist_df["asset"].dropna().astype(str).unique().tolist()) if "asset" in hist_df else []
    models = sorted(hist_df["model"].dropna().astype(str).unique().tolist()) if "model" in hist_df else []
    c1, c2 = st.columns(2)
    pick_asset = c1.selectbox("Asset", ["All"] + assets, key="uplift_gov_asset")
    pick_model = c2.selectbox("Model", ["All"] + models, key="uplift_gov_model")

    filt = hist_df.copy()
    if pick_asset != "All":
        filt = filt[filt["asset"] == pick_asset]
    if pick_model != "All":
        filt = filt[filt["model"] == pick_model]
    if filt.empty:
        st.info("No history rows match selected filters.")
        return

    st.caption(f"History rows: {len(filt)}")
    if "empirical_coverage" in filt.columns:
        st.markdown("#### Empirical coverage trend")
        st.line_chart(filt.groupby("timestamp_utc")["empirical_coverage"].mean().sort_index())
    if "failure_rate" in filt.columns:
        st.markdown("#### Failure rate trend")
        st.line_chart(filt.groupby("timestamp_utc")["failure_rate"].mean().sort_index())
    if "risk_adjusted_score" in filt.columns:
        st.markdown("#### Risk-adjusted score trend")
        st.line_chart(filt.groupby("timestamp_utc")["risk_adjusted_score"].mean().sort_index())
    with st.expander("History rows table"):
        _show_df(filt, height=260)


def _render_orders(cfg: AppConfig) -> None:
    st.markdown("### Orders")
    files = _summary_files(cfg)
    if not files:
        st.info("No run summaries found.")
        return
    chosen = st.selectbox("Run for orders", [f.name for f in files], key="uplift_orders_run_pick")
    summary = _load_json(_report_dir(cfg) / chosen)
    order_path_s = summary.get("orders_path", "")
    if not order_path_s:
        st.warning("Selected run summary has no orders_path.")
        return
    order_path = Path(order_path_s)
    st.caption(f"Orders file: `{order_path}`")
    if not order_path.exists():
        st.error("Orders file does not exist on disk.")
        return

    try:
        orders = pd.read_csv(order_path)
    except Exception as exc:
        st.error(f"Unable to read orders CSV: {exc}")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Rows", len(orders))
    c2.metric("Assets", int(orders["asset"].nunique()) if "asset" in orders.columns else 0)
    if "quantity" in orders.columns:
        c3.metric("Total quantity", float(pd.to_numeric(orders["quantity"], errors="coerce").fillna(0.0).sum()))
    else:
        c3.metric("Total quantity", 0.0)

    exec_diag = summary.get("execution_diagnostics", {})
    if isinstance(exec_diag, dict) and exec_diag:
        st.markdown("#### Execution diagnostics")
        diag_rows = [{"metric": k, "value": v} for k, v in exec_diag.items() if not isinstance(v, dict)]
        if diag_rows:
            _show_df(pd.DataFrame(diag_rows), height=170)
        dropped = exec_diag.get("dropped_reason_counts", {})
        if isinstance(dropped, dict) and dropped:
            st.markdown("Dropped reason counts")
            _show_df(
                pd.DataFrame([{"reason": k, "count": v} for k, v in dropped.items()]).sort_values("count", ascending=False),
                height=180,
            )

    _show_df(orders, height=330)
    st.download_button(
        "Download orders CSV",
        data=order_path.read_bytes(),
        file_name=order_path.name,
        mime="text/csv",
    )


def _render_config_lab(cfg: AppConfig) -> AppConfig:
    st.markdown("### Config Lab")
    st.caption("Use this for profile-only/advanced fields not exposed in Run Studio widgets.")
    if not st.session_state.advanced_cfg_yaml:
        st.session_state.advanced_cfg_yaml = yaml.safe_dump(
            asdict(cfg), sort_keys=False, allow_unicode=False
        )
    st.session_state.advanced_cfg_yaml = st.text_area(
        "AppConfig YAML",
        value=st.session_state.advanced_cfg_yaml,
        height=460,
    )
    col1, col2 = st.columns(2)
    if col1.button("Sync from current config"):
        st.session_state.advanced_cfg_yaml = yaml.safe_dump(
            asdict(st.session_state.cfg), sort_keys=False, allow_unicode=False
        )
        st.rerun()
    if col2.button("Validate + apply YAML"):
        try:
            payload = yaml.safe_load(st.session_state.advanced_cfg_yaml) or {}
            if not isinstance(payload, dict):
                raise ValueError("Root YAML object must be a mapping")
            new_cfg = AppConfig.from_dict(payload)
            st.session_state.cfg = new_cfg
            cfg = new_cfg
            st.success("Applied YAML config to current session.")
        except Exception as exc:
            st.error(f"Invalid YAML config: {type(exc).__name__}: {exc}")
    return cfg


def _render_performance_analytics(cfg: AppConfig) -> None:
    """Render the Performance Analytics tab."""
    st.markdown("### Performance Analytics")
    st.caption("Review risk-adjusted returns and equity performance from walkforward backtests.")
    
    if not HAS_PLOTLY or not HAS_RISK_METRICS:
        st.error(
            "Performance Analytics requires plotly and risk.metrics modules. "
            "Install with: pip install plotly"
        )
        return
    
    files = _summary_files(cfg)
    if not files:
        st.info("No run summaries found. Run a backtest first.")
        return
    
    run_ids = [_run_id_from_summary_file(f.name) for f in files]
    selected_run = st.selectbox("Select Run", run_ids, key="perf_run_select")
    
    # Load backtest results
    backtest_df = _load_backtest_results(selected_run, cfg)
    
    if backtest_df is None:
        output_dir = Path(cfg.execution.output_dir)
        st.warning(f"No backtest results loaded for run: `{selected_run}`")
        st.info(
            "**Expected storage location:**\n"
            f"- Fold predictions: `{output_dir}/backtests/{selected_run}/fold_predictions.parquet`\n"
            f"- Metrics: `{output_dir}/backtests/{selected_run}/metrics.parquet`\n\n"
            "**Common causes:**\n"
            "- Backtest has not completed yet (check Run Studio progress)\n"
            "- All models were excluded (low empirical coverage or high failure rate)\n"
            "- Backtest completed but produced no valid fold predictions\n\n"
            "**Debugging:** Check the backtest metrics file exists at the path above."
        )
        return
    
    if backtest_df.empty:
        st.error("Backtest results DataFrame is empty.")
        return
    
    # Compute risk metrics
    metrics = _compute_risk_metrics(backtest_df)
    
    if metrics is None:
        st.error("Unable to compute risk metrics. Check backtest data format.")
        return
    
    # Display metrics as KPI cards
    st.subheader("Risk-Adjusted Returns")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        sortino_val = metrics.get("sortino", np.nan)
        sortino_display = f"{sortino_val:.3f}" if not pd.isna(sortino_val) else "N/A"
        st.metric(
            "Sortino Ratio",
            sortino_display,
            help="Return per unit of downside volatility (higher is better)",
        )
    
    with col2:
        sharpe_val = metrics.get("sharpe", np.nan)
        sharpe_display = f"{sharpe_val:.3f}" if not pd.isna(sharpe_val) else "N/A"
        st.metric(
            "Sharpe Ratio",
            sharpe_display,
            help="Return per unit of total volatility",
        )
    
    with col3:
        dd_val = metrics.get("max_drawdown", np.nan)
        dd_display = f"{dd_val:.2%}" if not pd.isna(dd_val) else "N/A"
        st.metric(
            "Max Drawdown",
            dd_display,
            help="Peak-to-trough decline",
        )
    
    with col4:
        calmar_val = metrics.get("calmar", np.nan)
        calmar_display = f"{calmar_val:.3f}" if not pd.isna(calmar_val) else "N/A"
        st.metric(
            "Calmar Ratio",
            calmar_display,
            help="Annual return / max drawdown",
        )
    
    # Additional metrics
    st.subheader("Return and Risk Statistics")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        ret_val = metrics.get("total_return", np.nan)
        ret_display = f"{ret_val:.2%}" if not pd.isna(ret_val) else "N/A"
        st.metric("Total Return", ret_display)
    
    with col2:
        vol_val = metrics.get("volatility", np.nan)
        vol_display = f"{vol_val:.2%}" if not pd.isna(vol_val) else "N/A"
        st.metric("Annual Volatility", vol_display)
    
    with col3:
        wr_val = metrics.get("win_rate", 0.0)
        st.metric("Win Rate", f"{wr_val:.1%}")
    
    with col4:
        trades = metrics.get("num_trades", 0)
        st.metric("Trade Count", f"{trades}")
    
    # Visualizations
    st.subheader("Performance Curves")
    
    tab1, tab2, tab3 = st.tabs(["Equity Curve", "Rolling Sortino", "Drawdown"])
    
    with tab1:
        fig_equity = _plot_equity_curve(backtest_df)
        if fig_equity:
            st.plotly_chart(fig_equity, use_container_width=True)
        else:
            st.info("Unable to render equity curve. Check data format.")
    
    with tab2:
        fig_sortino = _plot_rolling_sortino(backtest_df, window=30)
        if fig_sortino:
            st.plotly_chart(fig_sortino, use_container_width=True)
        else:
            st.info("Insufficient data for rolling Sortino visualization (need >30 periods).")
    
    with tab3:
        fig_dd = _plot_drawdown(backtest_df)
        if fig_dd:
            st.plotly_chart(fig_dd, use_container_width=True)
        else:
            st.info("Unable to render drawdown chart. Check data format.")
    
    # Export metrics
    st.subheader("Export")
    if st.button("Save Risk Metrics as JSON"):
        report_dir = _report_dir(cfg)
        report_dir.mkdir(parents=True, exist_ok=True)
        metrics_file = report_dir / f"{selected_run}_risk_metrics.json"
        with open(metrics_file, "w") as f:
            # Convert NaN/inf to null for JSON serialization
            metrics_json = {}
            for k, v in metrics.items():
                if pd.isna(v) or np.isinf(v):
                    metrics_json[k] = None
                else:
                    metrics_json[k] = v
            json.dump(metrics_json, f, indent=2, default=str)
        st.success(f"Metrics saved to {metrics_file.name}")
    
    # Display raw metrics JSON
    with st.expander("Raw metrics JSON", expanded=False):
        st.json(metrics)



def main() -> None:
    _apply_style()
    _init_state()
    cfg: AppConfig = st.session_state.cfg
    cfg = _render_profile_box(cfg)
    st.session_state.cfg = cfg

    st.title("sktime_quant Uplift UI")
    st.markdown(
        '<div class="sq-card"><b>Operator flow</b><br/>1) Configure in <b>Run Studio</b> '
        '2) Start pipeline once 3) Review that run in <b>Run Explorer</b> '
        '4) Analyze performance in <b>Performance Analytics</b> '
        '5) Inspect trends in <b>Governance</b> 6) Export in <b>Orders</b>.</div>',
        unsafe_allow_html=True,
    )

    tabs = st.tabs(["Run Studio", "Run Explorer", "Performance Analytics", "Governance", "Orders", "Config Lab"])

    with tabs[0]:
        st.markdown("### Run Studio")
        st.caption("Set data, model, risk, and execution controls. Then run the full pipeline.")
        with st.expander("Data", expanded=True):
            _render_data_inputs(cfg)
        with st.expander("Modeling + Backtest", expanded=True):
            _render_model_inputs(cfg)
        with st.expander("Risk + Execution", expanded=True):
            _render_risk_execution_inputs(cfg)

        run_col1, run_col2 = st.columns([1, 2])
        if run_col1.button("Run Pipeline", type="primary"):
            _run_pipeline(cfg)
        if run_col2.button("Generate fresh run_id"):
            cfg.run_id = _generate_run_id()
            st.session_state.cfg = cfg
            st.rerun()

        if st.session_state.last_error:
            st.error(f"Last run failed: {st.session_state.last_error}")
        if st.session_state.progress_events:
            with st.expander("Latest progress log", expanded=False):
                for evt in st.session_state.progress_events[-50:]:
                    st.text(_fmt_event(evt))

        result = st.session_state.result
        if result is not None:
            if result.run_status == "completed":
                st.success("Run status: completed")
            elif result.run_status == "no_new_data":
                st.warning("Run status: no_new_data")
            else:
                st.error(f"Run status: {result.run_status}")
            if not result.backtest.metrics.empty:
                runtime_health = summarize_runtime_health(
                    result.backtest.metrics,
                    max_failure_rate=cfg.backtest.max_failure_rate,
                    confidence_floor=cfg.backtest.confidence_floor,
                )
                if not runtime_health.empty:
                    st.markdown("#### Runtime model health (latest run)")
                    _show_df(runtime_health, height=220)

        if st.session_state.run_history:
            with st.expander("Session run history", expanded=False):
                _show_df(pd.DataFrame(st.session_state.run_history), height=220)

    with tabs[1]:
        _render_run_explorer(cfg)

    with tabs[2]:
        _render_performance_analytics(cfg)

    with tabs[3]:
        _render_governance(cfg)

    with tabs[4]:
        _render_orders(cfg)

    with tabs[5]:
        cfg = _render_config_lab(cfg)
        st.session_state.cfg = cfg


if __name__ == "__main__":
    main()
