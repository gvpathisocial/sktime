"""Streamlit UI for sktime_quant workflows."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from sktime_quant.config.loader import load_config
from sktime_quant.config.profiles import save_profile
from sktime_quant.config.schema import AppConfig
from sktime_quant.pipelines.orchestrator import Orchestrator
from sktime_quant.ui.artifact_diff import (
    build_governance_alert_diff,
    build_model_selection_diff,
    build_summary_diff,
    load_json,
)


st.set_page_config(page_title="sktime quant", layout="wide")
st.title("sktime quant")

page = st.sidebar.radio(
    "Page", ["Data", "Backtest", "Forecast", "Portfolio", "Orders", "Runs"]
)

if "cfg" not in st.session_state:
    st.session_state.cfg = AppConfig()
if "result" not in st.session_state:
    st.session_state.result = None
if "run_history" not in st.session_state:
    st.session_state.run_history = []
if "profile_path" not in st.session_state:
    st.session_state.profile_path = "profiles/quant_profile.yaml"
if "artifact_reports" not in st.session_state:
    st.session_state.artifact_reports = []

cfg: AppConfig = st.session_state.cfg

with st.sidebar.expander("Config Profiles", expanded=False):
    st.session_state.profile_path = st.text_input(
        "Profile path",
        value=st.session_state.profile_path,
        help="YAML path for save/load profile",
    )
    col_save, col_load = st.columns(2)
    if col_save.button("Save profile"):
        saved = save_profile(cfg, st.session_state.profile_path)
        st.success(f"Saved: {saved}")
    if col_load.button("Load profile"):
        loaded = load_config(st.session_state.profile_path)
        st.session_state.cfg = loaded
        cfg = loaded
        st.success(f"Loaded: {st.session_state.profile_path}")

if page == "Data":
    st.subheader("Data source")
    source = st.selectbox("Source", ["timescale", "csv", "folder"], index=0)
    cfg.data.source_type = source
    cfg.data.incremental_mode = st.checkbox(
        "Incremental mode", value=cfg.data.incremental_mode
    )
    if source == "timescale":
        cfg.data.connection_uri = st.text_input("Connection URI", cfg.data.connection_uri or "")
        cfg.data.market_table = st.text_input("Market table", cfg.data.market_table)
        cfg.data.exog_table = st.text_input("Exog table", cfg.data.exog_table or "")
        cfg.data.incremental_state_path = st.text_input(
            "Incremental state path (optional)", cfg.data.incremental_state_path or ""
        )
    if source == "csv":
        cfg.data.csv_path = st.text_input("CSV path", cfg.data.csv_path or "")
    if source == "folder":
        cfg.data.folder_path = st.text_input("Folder path", cfg.data.folder_path or "")

if page == "Backtest":
    st.subheader("Backtest settings")
    cfg.backtest.splitter_type = st.selectbox("Splitter", ["expanding", "sliding"], index=0)
    cfg.backtest.window_length = st.number_input("Window length", value=cfg.backtest.window_length, min_value=10)
    cfg.backtest.step_length = st.number_input("Step length", value=cfg.backtest.step_length, min_value=1)
    cfg.backtest.horizon = st.number_input("Horizon", value=cfg.backtest.horizon, min_value=1)
    cfg.backtest.strategy_policy = st.selectbox(
        "Signal policy",
        ["sign", "threshold", "confidence_threshold"],
        index=["sign", "threshold", "confidence_threshold"].index(cfg.backtest.strategy_policy),
    )
    cfg.backtest.signal_threshold = st.number_input(
        "Signal threshold", value=float(cfg.backtest.signal_threshold), min_value=0.0, step=0.001
    )
    cfg.backtest.objective = st.selectbox(
        "Objective",
        ["composite", "sharpe", "sortino", "calmar"],
        index=["composite", "sharpe", "sortino", "calmar"].index(cfg.backtest.objective),
    )
    cfg.model.candidates = st.multiselect(
        "Candidate models",
        ["naive_last", "naive_mean", "theta", "arima"],
        default=cfg.model.candidates,
    )

if page == "Forecast":
    st.subheader("Forecast and confidence")
    cfg.risk.target_confidence = st.slider("Target confidence", 0.5, 0.99, float(cfg.risk.target_confidence), 0.01)

if page == "Portfolio":
    st.subheader("Portfolio and risk")
    cfg.risk.max_turnover = st.slider("Max turnover", 0.01, 1.0, float(cfg.risk.max_turnover), 0.01)
    cfg.risk.max_weight = st.slider("Max asset weight", 0.01, 1.0, float(cfg.risk.max_weight), 0.01)
    cfg.portfolio.cash_buffer = st.slider("Cash buffer", 0.0, 0.5, float(cfg.portfolio.cash_buffer), 0.01)
    cfg.execution.no_trade_band = st.slider(
        "No-trade band (weight delta)",
        0.0,
        0.1,
        float(cfg.execution.no_trade_band),
        0.001,
    )
    cfg.execution.min_order_notional = st.number_input(
        "Min order notional",
        min_value=0.0,
        value=float(cfg.execution.min_order_notional),
        step=100.0,
    )
    cfg.execution.max_order_notional = st.number_input(
        "Max order notional (0 = disabled)",
        min_value=0.0,
        value=float(cfg.execution.max_order_notional),
        step=100.0,
    )
    cfg.execution.max_turnover_notional_per_asset = st.number_input(
        "Max turnover notional per asset/day (0 = disabled)",
        min_value=0.0,
        value=float(cfg.execution.max_turnover_notional_per_asset),
        step=100.0,
    )

with st.sidebar.expander("Run History", expanded=False):
    if st.session_state.run_history:
        st.dataframe(pd.DataFrame(st.session_state.run_history))
    else:
        st.write("No runs yet.")

with st.sidebar.expander("Artifact Browser", expanded=False):
    report_dir = Path(cfg.execution.output_dir) / "reports"
    if report_dir.exists():
        files = sorted(report_dir.glob("*.json"), reverse=True)
        names = [f.name for f in files]
        if names:
            chosen = st.selectbox("Report files", names, key="artifact_pick")
            selected = report_dir / chosen
            try:
                st.json(json.loads(selected.read_text(encoding="utf-8")))
            except Exception as exc:
                st.error(f"Failed reading {selected}: {exc}")
        else:
            st.write("No report files found.")
    else:
        st.write("No report directory yet.")

if st.sidebar.button("Run pipeline"):
    result = Orchestrator().run(cfg)
    st.session_state.result = result
    st.session_state.run_history.append(
        {
            "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "run_id": cfg.run_id,
            "orders_path": result.orders_path,
            "summary_path": result.summary_path,
            "data_quality_path": result.data_quality_path,
            "model_selection_path": result.model_selection_path,
            "model_governance_path": result.model_governance_path,
            "run_status": result.run_status,
        }
    )
    if Path(result.summary_path).exists():
        st.session_state.artifact_reports.append(result.summary_path)

result = st.session_state.result
if result is not None:
    if result.run_status == "completed":
        st.success("Run status: completed")
    elif result.run_status == "no_new_data":
        st.warning("Run status: no_new_data")
    else:
        st.error(f"Run status: {result.run_status}")

    if page == "Backtest":
        st.dataframe(result.backtest.metrics)
        best = (
            result.backtest.metrics.sort_values("risk_adjusted_score", ascending=False)
            .groupby("asset", as_index=False)
            .first()[["asset", "model", "risk_adjusted_score", "objective"]]
        )
        st.subheader("Model Selection Diagnostics")
        st.dataframe(best)
        excluded = result.backtest.metrics[result.backtest.metrics["excluded"]]
        if not excluded.empty:
            st.subheader("Excluded Models")
            st.dataframe(
                excluded[
                    [
                        "asset",
                        "model",
                        "excluded_reason",
                        "failure_rate",
                        "empirical_coverage",
                    ]
                ]
            )
    if page == "Forecast":
        st.dataframe(result.forecast.predictions)
    if page == "Portfolio":
        st.dataframe(result.allocation.allocations)
        st.json(result.allocation.diagnostics)
    if page == "Orders":
        st.write(f"Orders file: {result.orders_path}")
        path = Path(result.orders_path)
        if path.exists():
            st.dataframe(pd.read_csv(path))
    if page == "Runs":
        st.subheader("Recent Runs")
        if st.session_state.run_history:
            st.dataframe(pd.DataFrame(st.session_state.run_history))
        else:
            st.write("No runs yet.")
        summary_path = Path(result.summary_path)
        quality_path = Path(result.data_quality_path)
        selection_path = Path(result.model_selection_path)
        governance_path = Path(result.model_governance_path)
        if summary_path.exists():
            st.subheader("Latest Summary")
            st.json(json.loads(summary_path.read_text(encoding="utf-8")))
        if quality_path.exists():
            st.subheader("Latest Data Quality Report")
            st.json(json.loads(quality_path.read_text(encoding="utf-8")))
        if selection_path.exists():
            st.subheader("Latest Model Selection Rationale")
            st.json(json.loads(selection_path.read_text(encoding="utf-8")))
        if governance_path.exists():
            st.subheader("Latest Model Governance")
            st.json(json.loads(governance_path.read_text(encoding="utf-8")))

        st.subheader("Browse Historical Artifacts")
        report_dir = Path(cfg.execution.output_dir) / "reports"
        if report_dir.exists():
            hist_files = sorted(report_dir.glob("*.json"), reverse=True)
            if hist_files:
                picked = st.selectbox(
                    "Historical report",
                    [f.name for f in hist_files],
                    key="hist_report_pick",
                )
                st.json(json.loads((report_dir / picked).read_text(encoding="utf-8")))
            else:
                st.write("No historical report files found.")

        st.subheader("Compare Two Runs")
        if report_dir.exists():
            summary_files = sorted(report_dir.glob("*_summary.json"), reverse=True)
            if len(summary_files) >= 2:
                names = [f.name for f in summary_files]
                col_a, col_b = st.columns(2)
                run_a = col_a.selectbox("Run A summary", names, key="cmp_run_a")
                run_b = col_b.selectbox(
                    "Run B summary",
                    names,
                    index=1 if len(names) > 1 else 0,
                    key="cmp_run_b",
                )
                if run_a == run_b:
                    st.info("Select two different runs to compare.")
                else:
                    summary_a = load_json(report_dir / run_a)
                    summary_b = load_json(report_dir / run_b)
                    st.markdown("**Summary Diff**")
                    st.dataframe(build_summary_diff(summary_a, summary_b))

                    sel_a = summary_a.get("model_selection_path")
                    sel_b = summary_b.get("model_selection_path")
                    if sel_a and sel_b and Path(sel_a).exists() and Path(sel_b).exists():
                        st.markdown("**Model Selection Diff**")
                        st.dataframe(
                            build_model_selection_diff(load_json(sel_a), load_json(sel_b))
                        )

                    gov_a = summary_a.get("model_governance_path")
                    gov_b = summary_b.get("model_governance_path")
                    if gov_a and gov_b and Path(gov_a).exists() and Path(gov_b).exists():
                        st.markdown("**Governance Alert Diff**")
                        st.dataframe(
                            build_governance_alert_diff(load_json(gov_a), load_json(gov_b))
                        )
            else:
                st.write("Need at least two summary artifacts to compare runs.")

        st.subheader("Governance Trend Charts")
        gov_hist_path = Path(cfg.execution.output_dir) / "governance" / "model_stability_history.json"
        if gov_hist_path.exists():
            hist_payload = json.loads(gov_hist_path.read_text(encoding="utf-8"))
            history = hist_payload.get("history", [])
            hist_df = pd.DataFrame(history)
            if not hist_df.empty:
                if "timestamp_utc" in hist_df.columns:
                    hist_df["timestamp_utc"] = pd.to_datetime(
                        hist_df["timestamp_utc"], errors="coerce", utc=True
                    )
                hist_df = hist_df.sort_values("timestamp_utc")

                assets = sorted(hist_df["asset"].dropna().astype(str).unique().tolist())
                models = sorted(hist_df["model"].dropna().astype(str).unique().tolist())
                col_asset, col_model = st.columns(2)
                selected_asset = col_asset.selectbox(
                    "Trend asset", ["All"] + assets, key="trend_asset"
                )
                selected_model = col_model.selectbox(
                    "Trend model", ["All"] + models, key="trend_model"
                )

                filt = hist_df.copy()
                if selected_asset != "All":
                    filt = filt[filt["asset"] == selected_asset]
                if selected_model != "All":
                    filt = filt[filt["model"] == selected_model]

                if not filt.empty:
                    st.caption(f"Rows in trend view: {len(filt)}")
                    if "empirical_coverage" in filt:
                        coverage_series = (
                            filt.groupby("timestamp_utc")["empirical_coverage"].mean().sort_index()
                        )
                        st.markdown("**Empirical Coverage Trend**")
                        st.line_chart(coverage_series)
                    if "failure_rate" in filt:
                        failure_series = (
                            filt.groupby("timestamp_utc")["failure_rate"].mean().sort_index()
                        )
                        st.markdown("**Failure Rate Trend**")
                        st.line_chart(failure_series)
                    if "risk_adjusted_score" in filt:
                        score_series = (
                            filt.groupby("timestamp_utc")["risk_adjusted_score"].mean().sort_index()
                        )
                        st.markdown("**Risk-Adjusted Score Trend**")
                        st.line_chart(score_series)
                else:
                    st.info("No governance history rows match selected filters.")
            else:
                st.write("Governance history exists but is empty.")
        else:
            st.write("No governance history file found yet.")

