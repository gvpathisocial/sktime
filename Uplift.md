**combined specification document** in Markdown format, integrating the requirements, pipeline architecture, and TimescaleDB schema into one cohesive artifact:

---

# `sktime_quant` Uplift Specification

## 1. Overview
The `sktime_quant` extension enhances time-series forecasting and backtesting for financial strategies. It integrates technical indicators, AI model internals, and classifier-based rule discovery into a blended pipeline. Persistence is TimescaleDB-first, with Streamlit and CLI interfaces for usability.

---

## 2. Requirements

### Data Ingestion
- **Sources**: TimescaleDB (primary), CSV/folder (secondary).
- **Schema**: OHLCV + derived technical indicators + model internals.
- **Storage**: Forecasts, signals, trades, metrics, and order execution status persisted in TimescaleDB.

### Strategy Engine
- **Indicator Layer**:
  - Technical indicators (RSI, MACD, Bollinger Bands, etc.) used both as lagging features and regressors.
  - Rule chaining support with configurable logic (UI-driven).
- **Model Internals Layer**:
  - Extract seasonal, trend, residuals, and uncertainty intervals from fbprophet-like models.
  - Flexible design for multiple models with differing internals.
  - Internals used as regressors for classifiers (decision tree, random forest).
- **Blended Studio Concept**:
  - Split AI model state space into regressors.
  - Feed regressors into rule engine or classifier.
  - Pipeline supports blending, not “either/or.”

### Backtesting & Metrics
- **Walk-forward testing** with rolling windows and re-training.
- **Metrics**: Sortino, Sharpe, Calmar, max drawdown, rolling volatility, win/loss ratio.
- **Persistence**: Metrics stored in TimescaleDB alongside forecasts, trades, and orders.

### Execution Layer
- **Order Export**: Broker-ready CSV format.
- **Portfolio Optimization**:
  - Risk-aware rebalancing integrated with strategy outputs.
  - Modular weight engine to allow both coupled and decoupled modes.

### Interfaces
- **Streamlit UI**:
  - Dual mode: AI forecast vs. Rule-based strategy.
  - Intermediate pipeline step: build regressors from AI internals + technical indicators.
  - Rule chaining builder with visual logic editor.
- **CLI Runner**:
  - Unified runner for blended strategies.
  - Supports switching between sktime models, fbprophet-like regressors, and pure indicator strategies.
  - Export metrics, trades, and orders.
- **Tests**:
  - Unit + integration tests for ingestion, strategy logic, metrics, and order export.

### Non-Functional Requirements
- **Flexibility**: Modular design to plug in new models and indicators.
- **Reproducibility**: Walk-forward backtests documented and reproducible.
- **Performance**: Efficient ingestion and backtesting with TimescaleDB-first design.
- **Extensibility**: Support for additional regressors and classifiers without major refactoring.

---

## 3. Pipeline Architecture

```
                ┌───────────────────────────┐
                │       Data Ingestion       │
                │  - TimescaleDB (OHLCV)     │
                │  - CSV/folder fallback     │
                └─────────────┬─────────────┘
                              │
                              ▼
                ┌───────────────────────────┐
                │   Feature Construction     │
                │  - Technical Indicators    │
                │  - AI Model Internals      │
                │    (trend, seasonality,    │
                │     residuals, intervals)  │
                └─────────────┬─────────────┘
                              │
                              ▼
                ┌───────────────────────────┐
                │   Strategy Engine Layer    │
                │                           │
                │  1. Rule Engine            │
                │     - Configurable logic   │
                │       (chaining, UI)       │
                │                           │
                │  2. Classifier Engine      │
                │     - Decision Tree / RF   │
                │     - Learns rules from    │
                │       indicators + internals│
                │                           │
                │  3. Blended Studio         │
                │     - Split AI state space │
                │     - Feed regressors into │
                │       rule engine or ML    │
                └─────────────┬─────────────┘
                              │
                              ▼
                ┌───────────────────────────┐
                │       Backtesting          │
                │  - Walk-forward windows    │
                │  - Metrics: Sortino, Sharpe│
                │    Calmar, Drawdown, Vol   │
                │  - Portfolio simulation    │
                └─────────────┬─────────────┘
                              │
                              ▼
                ┌───────────────────────────┐
                │       Execution Layer      │
                │  - Broker-ready CSV orders │
                │  - Portfolio optimization  │
                │    (risk-aware rebalancing)│
                │  - Option: decouple weights│
                │    from strategy testing   │
                └─────────────┬─────────────┘
                              │
                              ▼
                ┌───────────────────────────┐
                │        Interfaces          │
                │  - Streamlit UI (dual mode)│
                │  - CLI Runner (blended)    │
                │  - Tests (unit + integ.)   │
                └───────────────────────────┘
```

---

## 4. TimescaleDB Schema

### Market Data
```sql
CREATE TABLE ohlcv (
    id SERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume NUMERIC,
    UNIQUE(symbol, timestamp)
);
```

### Forecasts & Internals
```sql
CREATE TABLE forecasts (
    id SERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    model_name TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    forecast_value NUMERIC,
    lower_bound NUMERIC,
    upper_bound NUMERIC,
    trend NUMERIC,
    seasonality NUMERIC,
    residual NUMERIC,
    UNIQUE(symbol, model_name, timestamp)
);
```

### Strategy Signals
```sql
CREATE TABLE signals (
    id SERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    signal TEXT CHECK (signal IN ('ENTRY','EXIT','NOENTRY')),
    indicators JSONB,
    regressors JSONB,
    classifier_output JSONB,
    UNIQUE(symbol, strategy_name, timestamp)
);
```

### Trades & Orders
```sql
CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    action TEXT CHECK (action IN ('BUY','SELL')),
    quantity NUMERIC,
    price NUMERIC,
    pnl NUMERIC,
    execution_status TEXT CHECK (execution_status IN ('PENDING','EXECUTED','FAILED')),
    order_id TEXT
);
```

### Metrics
```sql
CREATE TABLE metrics (
    id SERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    sortino NUMERIC,
    sharpe NUMERIC,
    calmar NUMERIC,
    max_drawdown NUMERIC,
    rolling_volatility NUMERIC,
    win_loss_ratio NUMERIC
);
```

### Portfolio Weights (Decoupled)
```sql
CREATE TABLE portfolio_weights (
    id SERIAL PRIMARY KEY,
    portfolio_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    weight NUMERIC,
    strategy_name TEXT,
    UNIQUE(portfolio_name, symbol, timestamp)
);
```

---

## 5. Persistence Flow Mapping

- **Data Ingestion** → `ohlcv`  
- **Forecasts/Internals** → `forecasts`  
- **Strategy Engine Outputs** → `signals`  
- **Backtesting Results** → `metrics`  
- **Execution Layer** → `trades` (orders + status)  
- **Portfolio Optimization** → `portfolio_weights`  

---

✅ This single document now gives you:  
- Requirements spec  
- Pipeline architecture diagram  
- TimescaleDB schema  
- Persistence flow mapping  

