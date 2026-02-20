"""Streamlit UI for sktime_quant workflows."""

from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import asdict
import json
from pathlib import Path
import random
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
import yaml

from sktime_quant.config.loader import load_config
from sktime_quant.config.profiles import save_profile
from sktime_quant.config.schema import AppConfig
from sktime_quant.models.registry import (
    get_available_model_names,
    get_excluded_from_daily_update,
    get_model_health,
    get_model_overview_rows,
    get_registered_model_names,
)
from sktime_quant.models.health import summarize_runtime_health
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
if "last_error" not in st.session_state:
    st.session_state.last_error = None
if "last_progress_event" not in st.session_state:
    st.session_state.last_progress_event = {}
if "use_history_window" not in st.session_state:
    st.session_state.use_history_window = False
if "history_years" not in st.session_state:
    st.session_state.history_years = 5
if "advanced_cfg_yaml" not in st.session_state:
    st.session_state.advanced_cfg_yaml = ""


def _generate_run_id() -> str:
    adjectives = [
        "amber",
        "brisk",
        "clear",
        "delta",
        "ember",
        "frost",
        "granite",
        "harbor",
        "ion",
        "jet",
    ]
    nouns = [
        "falcon",
        "atlas",
        "summit",
        "matrix",
        "ledger",
        "signal",
        "vector",
        "horizon",
        "anchor",
        "pulse",
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


def _load_report_payload(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _run_id_from_summary_file(name: str) -> str:
    suffix = "_summary.json"
    return name[: -len(suffix)] if name.endswith(suffix) else name


def _safe_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_object_dtype(out[col]):
            out[col] = out[col].map(lambda x: str(x) if x is not None else "")
    return out


def _show_df(df: pd.DataFrame, *, use_container_width: bool = True):
    st.dataframe(_safe_dataframe(df), use_container_width=use_container_width)

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
    if st.button("Generate run_id"):
        cfg.run_id = _generate_run_id()
        st.session_state.cfg = cfg
        st.info(f"run_id set to: {cfg.run_id}")

with st.sidebar.expander("Advanced Config Editor", expanded=False):
    if not st.session_state.advanced_cfg_yaml:
        st.session_state.advanced_cfg_yaml = yaml.safe_dump(
            asdict(cfg), sort_keys=False, allow_unicode=False
        )
    st.caption("Edit full AppConfig YAML. This supports profile-only fields.")
    st.session_state.advanced_cfg_yaml = st.text_area(
        "AppConfig YAML",
        value=st.session_state.advanced_cfg_yaml,
        height=360,
        key="advanced_cfg_yaml_textarea",
    )
    col_sync, col_apply = st.columns(2)
    if col_sync.button("Sync From Current"):
        st.session_state.advanced_cfg_yaml = yaml.safe_dump(
            asdict(st.session_state.cfg), sort_keys=False, allow_unicode=False
        )
        st.rerun()
    if col_apply.button("Validate + Apply"):
        try:
            payload = yaml.safe_load(st.session_state.advanced_cfg_yaml) or {}
            if not isinstance(payload, dict):
                raise ValueError("Root YAML object must be a mapping")
            new_cfg = AppConfig.from_dict(payload)
            st.session_state.cfg = new_cfg
            cfg = new_cfg
            st.success("Advanced YAML applied to current session config.")
        except Exception as exc:
            st.error(f"Invalid config YAML: {type(exc).__name__}: {exc}")

if page == "Data":
    st.subheader("Data source")
    st.caption(
        "CSV/folder loaders accept canonical schema and Yahoo-style raw OHLCV files "
        "(Price/Ticker/Date header pattern)."
    )
    source = st.selectbox("Source", ["timescale", "csv", "folder"], index=0)
    cfg.data.source_type = source
    st.session_state.use_history_window = st.checkbox(
        "Limit history window (years)",
        value=st.session_state.use_history_window,
        help="Applies a rolling start date from today; useful to reduce runtime.",
    )
    if st.session_state.use_history_window:
        st.session_state.history_years = int(
            st.number_input(
                "History years",
                min_value=1,
                max_value=30,
                value=int(st.session_state.history_years),
                step=1,
            )
        )
        start_ts = pd.Timestamp.now(tz="UTC") - pd.DateOffset(
            years=int(st.session_state.history_years)
        )
        cfg.data.start = start_ts.date().isoformat()
        st.caption(f"Computed start date: {cfg.data.start}")
    else:
        start_txt = st.text_input("Start date (YYYY-MM-DD, optional)", cfg.data.start or "")
        cfg.data.start = start_txt or None
    end_txt = st.text_input("End date (YYYY-MM-DD, optional)", cfg.data.end or "")
    cfg.data.end = end_txt or None
    cfg.data.incremental_mode = st.checkbox(
        "Incremental mode", value=cfg.data.incremental_mode
    )
    if source == "timescale":
        cfg.data.connection_uri = st.text_input("Connection URI", cfg.data.connection_uri or "")
        cfg.data.market_table = st.text_input("Market table", cfg.data.market_table)
        cfg.data.exog_table = st.text_input("Exog table", cfg.data.exog_table or "")
        cfg.data.enable_db_holidays = st.checkbox(
            "Enable DB holidays (Prophet)", value=cfg.data.enable_db_holidays
        )
        cfg.data.holiday_table = st.text_input("Holiday table", cfg.data.holiday_table)
        cfg.data.default_market = st.text_input(
            "Default market (optional)", cfg.data.default_market or ""
        )
        mapping_default = json.dumps(cfg.data.asset_market_map or {}, indent=2)
        mapping_text = st.text_area(
            "Asset->Market map JSON",
            value=mapping_default,
            help='Example: {"^NSEI":"NSE","AAPL":"NYSE"}',
        )
        try:
            parsed = json.loads(mapping_text) if mapping_text.strip() else {}
            cfg.data.asset_market_map = {
                str(k): str(v) for k, v in dict(parsed).items()
            }
        except Exception as exc:
            st.warning(f"Invalid asset->market JSON; keeping previous value. {exc}")
        cfg.data.incremental_state_path = st.text_input(
            "Incremental state path (optional)", cfg.data.incremental_state_path or ""
        )
    if source == "csv":
        cfg.data.csv_path = st.text_input("CSV path", cfg.data.csv_path or "")
    if source == "folder":
        cfg.data.folder_path = st.text_input("Folder path", cfg.data.folder_path or "")

if page == "Backtest":
    st.subheader("Backtest settings")
    configured_models = list(cfg.model.candidates)
    configured_health = get_model_health(configured_models)
    unavailable_configured = [r for r in configured_health if not bool(r["available"])]
    if unavailable_configured:
        st.warning(
            "Configured models with dependency/validation issues: "
            + ", ".join(str(r["model"]) for r in unavailable_configured)
        )

    available_models = get_available_model_names()
    registered_models = get_registered_model_names()
    health_all = get_model_health(registered_models)
    unavailable_rows = [r for r in health_all if not bool(r.get("available", False))]
    st.caption(f"Available models in this environment: {len(available_models)}")
    if available_models:
        st.caption(", ".join(available_models))
    else:
        st.error("No models are currently available. Check dependency health table below.")
    if unavailable_rows:
        st.warning(
            "Unavailable models: "
            + ", ".join(str(r["model"]) for r in unavailable_rows)
            + " (see health table for reasons)"
        )
    default_models = [m for m in cfg.model.candidates if m in available_models]
    if not default_models:
        default_models = [m for m in ["naive_last", "theta"] if m in available_models]
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
    ensemble_only = st.checkbox(
        "Ensemble-only mode (ensemble_blend)",
        value=False,
        help="Use only ensemble_blend for backtest/forecast candidate selection.",
    )
    cfg.model.update_mode = st.selectbox(
        "Forecast update mode",
        ["update", "refit"],
        index=["update", "refit"].index(cfg.model.update_mode),
        help="update: use delta updates where supported; refit otherwise",
    )
    picker_mode = st.radio(
        "Model picker mode",
        ["Simple", "Advanced"],
        horizontal=True,
        help="Simple uses available-model multiselect. Advanced provides full registry with reasons.",
    )
    if picker_mode == "Simple":
        cfg.model.candidates = st.multiselect(
            "Candidate models",
            available_models,
            default=default_models,
        )
    else:
        pick_df = pd.DataFrame(health_all)
        pick_df["selected"] = pick_df["model"].isin(cfg.model.candidates)
        st.caption("Advanced model selector (only available models are selectable)")
        edited = st.data_editor(
            pick_df[
                [
                    "selected",
                    "model",
                    "available",
                    "health",
                    "daily_update_supported",
                    "daily_update_reason",
                    "error",
                ]
            ],
            hide_index=True,
            use_container_width=True,
            disabled=[
                "model",
                "available",
                "health",
                "daily_update_supported",
                "daily_update_reason",
                "error",
            ],
            key="advanced_model_picker",
        )
        selected = []
        for _, row in edited.iterrows():
            if bool(row["selected"]) and bool(row["available"]):
                selected.append(str(row["model"]))
        cfg.model.candidates = selected
    if ensemble_only:
        if "ensemble_blend" in available_models:
            cfg.model.candidates = ["ensemble_blend"]
            st.info("Ensemble-only mode active: using ['ensemble_blend'].")
        else:
            st.error("ensemble_blend is not available in this environment.")
    if not cfg.model.candidates:
        st.warning("No candidate models selected. Auto-selection will use all available models at run time.")
    if cfg.model.update_mode == "update":
        excluded_update = get_excluded_from_daily_update(cfg.model.candidates)
        if excluded_update:
            st.warning("Some selected models are excluded from daily update and will refit.")
            st.dataframe(pd.DataFrame(excluded_update), use_container_width=True)
    candidate_health = get_model_health(cfg.model.candidates)
    healthy_count = sum(
        1
        for r in candidate_health
        if bool(r["available"]) and bool(r["params_ok"])
    )
    if candidate_health and healthy_count == len(candidate_health):
        st.success(
            f"Model availability health: healthy ({healthy_count}/{len(candidate_health)} ready)"
        )
    else:
        st.error(
            f"Model availability health: degraded ({healthy_count}/{len(candidate_health)} ready)"
        )
    st.dataframe(pd.DataFrame(candidate_health), use_container_width=True)
    st.caption("Model overview for selected candidates")
    selected_overview = get_model_overview_rows(cfg.model.candidates)
    if selected_overview:
        st.dataframe(pd.DataFrame(selected_overview), use_container_width=True)
        with st.expander("Selected model notes", expanded=False):
            for row in selected_overview:
                st.markdown(
                    f"**{row['model']}** ({row['family']}): {row['summary']} "
                    f"Best for: {row['best_for']} Notes: {row['notes']}"
                )
    else:
        st.info("Select at least one model to view overview details.")

    with st.expander("All available model overviews", expanded=False):
        all_overview = get_model_overview_rows(available_models)
        if all_overview:
            st.dataframe(pd.DataFrame(all_overview), use_container_width=True)

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
    st.session_state.last_error = None
    progress = st.sidebar.status("Running pipeline...", expanded=True)
    progress.write(f"run_id={cfg.run_id}")
    progress.write(f"source_type={cfg.data.source_type}")
    progress.write(f"source_detail={_source_details(cfg)}")
    progress.write(f"profile={st.session_state.profile_path}")

    def ui_progress(evt: dict[str, object]) -> None:
        st.session_state.last_progress_event = evt
        stage = str(evt.get("stage", "unknown"))
        event = str(evt.get("event", ""))
        if stage == "backtest" and event == "model_start":
            progress.write(
                f"backtest [{evt.get('task_index')}/{evt.get('task_total')}]: "
                f"{evt.get('asset')} -> {evt.get('model')}"
            )
        elif stage == "backtest" and event == "backtest_start":
            progress.write(
                f"backtest_start: assets={evt.get('asset_count')} models={evt.get('model_count')}"
            )
        elif stage == "forecast" and event == "forecast_start":
            progress.write(f"forecast_start: assets={evt.get('asset_count')}")
        elif stage == "orders" and event == "orders_done":
            progress.write(f"orders_done: count={evt.get('order_count')}")
        else:
            progress.write(f"{stage}:{event}")

    try:
        result = Orchestrator().run(cfg, progress_hook=ui_progress)
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
        progress.update(label=f"Pipeline completed: {result.run_status}", state="complete")
        st.sidebar.success(f"Run finished: {result.run_status}")
    except Exception as exc:
        st.session_state.result = None
        st.session_state.last_error = f"{type(exc).__name__}: {exc}"
        progress.update(label="Pipeline failed", state="error")
        st.sidebar.error(st.session_state.last_error)

result = st.session_state.result
if st.session_state.last_error:
    st.error(f"Last run failed: {st.session_state.last_error}")
if result is not None:
    if result.run_status == "completed":
        st.success("Run status: completed")
    elif result.run_status == "no_new_data":
        st.warning("Run status: no_new_data")
    else:
        st.error(f"Run status: {result.run_status}")

    if page == "Backtest":
        st.dataframe(result.backtest.metrics)
        runtime_health = summarize_runtime_health(
            result.backtest.metrics,
            max_failure_rate=cfg.backtest.max_failure_rate,
            confidence_floor=cfg.backtest.confidence_floor,
        )
        st.subheader("Runtime Model Health")
        if runtime_health.empty:
            st.info("No runtime model health available yet.")
        else:
            healthy_runtime = int((runtime_health["runtime_health"] == "healthy").sum())
            total_runtime = int(len(runtime_health))
            if healthy_runtime == total_runtime:
                st.success(
                    f"Runtime health: healthy ({healthy_runtime}/{total_runtime} models)"
                )
            else:
                st.warning(
                    f"Runtime health: degraded ({healthy_runtime}/{total_runtime} models healthy)"
                )
            st.dataframe(runtime_health, use_container_width=True)
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
        if st.session_state.last_progress_event:
            st.caption(
                "Last progress event: "
                + json.dumps(st.session_state.last_progress_event, default=str)
            )
        if st.session_state.run_history:
            _show_df(pd.DataFrame(st.session_state.run_history))
        else:
            st.write("No runs yet.")
        run_focus_mode = st.toggle(
            "Selected-run focus mode",
            value=True,
            help="Show one run report at a time to avoid mixed/merged context.",
        )
        summary_path = Path(result.summary_path)
        quality_path = Path(result.data_quality_path)
        selection_path = Path(result.model_selection_path)
        governance_path = Path(result.model_governance_path)
        if summary_path.exists() and not run_focus_mode:
            summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
            st.subheader("Latest Run Snapshot")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Run Status", str(summary_payload.get("run_status", "unknown")))
            col2.metric("Assets", len(summary_payload.get("assets", [])))
            col3.metric("Best Models", len(summary_payload.get("best_models", {})))
            col4.metric("Alerts", int(summary_payload.get("governance_alert_count", 0)))
            if "best_models" in summary_payload and isinstance(summary_payload["best_models"], dict):
                _show_df(
                    pd.DataFrame(
                        [{"asset": a, "model": m} for a, m in summary_payload["best_models"].items()]
                    )
                )
            with st.expander("Raw latest summary JSON", expanded=False):
                st.json(summary_payload)

        if quality_path.exists():
            dq = json.loads(quality_path.read_text(encoding="utf-8"))
            st.subheader("Latest Data Quality")
            dq_rows = []
            for k in [
                "row_count",
                "asset_count",
                "duplicate_asset_timestamp_rows",
                "missing_close_rows",
                "inferred_base_freq_seconds",
            ]:
                dq_rows.append({"metric": k, "value": dq.get(k)})
            _show_df(pd.DataFrame(dq_rows))
            with st.expander("Raw latest data quality JSON", expanded=False):
                st.json(dq)

        if governance_path.exists():
            gov = json.loads(governance_path.read_text(encoding="utf-8"))
            st.subheader("Latest Governance")
            st.write(f"Alert count: {gov.get('alert_count', 0)}")
            alerts = gov.get("alerts", [])
            if alerts:
                _show_df(pd.DataFrame(alerts))
            with st.expander("Raw latest governance JSON", expanded=False):
                st.json(gov)

        if selection_path.exists():
            sel = json.loads(selection_path.read_text(encoding="utf-8"))
            st.subheader("Latest Model Selection")
            top_rows = []
            if isinstance(sel, dict):
                for asset, recs in sel.items():
                    if isinstance(recs, list) and recs:
                        r0 = recs[0]
                        top_rows.append(
                            {
                                "asset": asset,
                                "model": r0.get("model"),
                                "rank": r0.get("rank"),
                                "score": r0.get("risk_adjusted_score"),
                            }
                        )
            if top_rows:
                _show_df(pd.DataFrame(top_rows))
            with st.expander("Raw latest model selection JSON", expanded=False):
                st.json(sel)

        report_dir = Path(cfg.execution.output_dir) / "reports"
        if not run_focus_mode:
            st.subheader("Browse Historical Artifacts")
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

        st.subheader("Per-Run Report View")
        if report_dir.exists():
            summary_files = sorted(report_dir.glob("*_summary.json"), reverse=True)
            if summary_files:
                run_pick = st.selectbox(
                    "Run to visualize",
                    [f.name for f in summary_files],
                    key="run_report_pick",
                )
                run_summary = _load_report_payload(report_dir / run_pick)
                run_id = _run_id_from_summary_file(run_pick)
                st.markdown(f"**Run ID:** `{run_id}`")

                # Core summary KPIs
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Run Status", str(run_summary.get("run_status", "unknown")))
                k2.metric(
                    "Governance Alerts",
                    int(run_summary.get("governance_alert_count", 0))
                    if str(run_summary.get("governance_alert_count", "")).isdigit()
                    else str(run_summary.get("governance_alert_count", 0)),
                )
                k3.metric(
                    "Holiday Assets",
                    int(run_summary.get("holiday_assets_count", 0))
                    if str(run_summary.get("holiday_assets_count", "")).isdigit()
                    else str(run_summary.get("holiday_assets_count", 0)),
                )
                best_models = run_summary.get("best_models", {})
                k4.metric("Selected Models", len(best_models) if isinstance(best_models, dict) else 0)

                if isinstance(best_models, dict) and best_models:
                    st.markdown("**Best Model by Asset**")
                    _show_df(
                        pd.DataFrame(
                            [{"asset": a, "model": m} for a, m in best_models.items()]
                        )
                    )

                upd_counts = run_summary.get("forecast_update_status_counts", {})
                if isinstance(upd_counts, dict) and upd_counts:
                    st.markdown("**Forecast Update Status**")
                    upd_df = pd.DataFrame(
                        [{"status": k, "count": v} for k, v in upd_counts.items()]
                    ).sort_values("count", ascending=False)
                    _show_df(upd_df)
                    st.bar_chart(upd_df.set_index("status")["count"])

                exec_diag = run_summary.get("execution_diagnostics", {})
                if isinstance(exec_diag, dict) and exec_diag:
                    st.markdown("**Execution Diagnostics**")
                    dropped = exec_diag.get("dropped_reason_counts", {})
                    st.json(exec_diag)
                    if isinstance(dropped, dict) and dropped:
                        dr_df = pd.DataFrame(
                            [{"reason": k, "count": v} for k, v in dropped.items()]
                        ).sort_values("count", ascending=False)
                        _show_df(dr_df)

                # Linked artifacts
                dq_path = run_summary.get("data_quality_path")
                if dq_path and Path(dq_path).exists():
                    dq = _load_report_payload(Path(dq_path))
                    st.markdown("**Data Quality (Structured)**")
                    dq_rows = []
                    for k in [
                        "row_count",
                        "asset_count",
                        "duplicate_asset_timestamp_rows",
                        "missing_close_rows",
                        "inferred_base_freq_seconds",
                    ]:
                        dq_rows.append({"metric": k, "value": dq.get(k)})
                    _show_df(pd.DataFrame(dq_rows))

                ms_path = run_summary.get("model_selection_path")
                if ms_path and Path(ms_path).exists():
                    ms = _load_report_payload(Path(ms_path))
                    if isinstance(ms, dict) and ms:
                        top_rows = []
                        for asset, recs in ms.items():
                            if isinstance(recs, list) and recs:
                                top = recs[0]
                                top_rows.append(
                                    {
                                        "asset": asset,
                                        "model": top.get("model"),
                                        "rank": top.get("rank"),
                                        "score": top.get("risk_adjusted_score"),
                                        "excluded": top.get("excluded"),
                                    }
                                )
                        if top_rows:
                            st.markdown("**Model Selection Top Rank (per asset)**")
                            _show_df(pd.DataFrame(top_rows))
            else:
                st.write("No summary artifacts found for run visualization.")

        if not run_focus_mode:
            st.subheader("Compare Two Runs")
        if report_dir.exists() and not run_focus_mode:
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
                    _show_df(build_summary_diff(summary_a, summary_b))

                    sel_a = summary_a.get("model_selection_path")
                    sel_b = summary_b.get("model_selection_path")
                    if sel_a and sel_b and Path(sel_a).exists() and Path(sel_b).exists():
                        st.markdown("**Model Selection Diff**")
                        _show_df(build_model_selection_diff(load_json(sel_a), load_json(sel_b)))

                    gov_a = summary_a.get("model_governance_path")
                    gov_b = summary_b.get("model_governance_path")
                    if gov_a and gov_b and Path(gov_a).exists() and Path(gov_b).exists():
                        st.markdown("**Governance Alert Diff**")
                        _show_df(build_governance_alert_diff(load_json(gov_a), load_json(gov_b)))
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
