"""Classifier-based signal generation."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _build_label_from_close(close: pd.Series) -> pd.Series:
    nxt = close.shift(-1)
    ret = (nxt / close) - 1.0
    return ret.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))


def _make_classifier(classifier_type: str):
    try:
        if classifier_type == "decision_tree":
            from sklearn.tree import DecisionTreeClassifier

            return DecisionTreeClassifier(max_depth=4, random_state=42)
        if classifier_type == "random_forest":
            from sklearn.ensemble import RandomForestClassifier

            return RandomForestClassifier(
                n_estimators=80, max_depth=5, random_state=42, n_jobs=1
            )
    except ImportError:
        return None
    raise ValueError(f"Unsupported classifier_type: {classifier_type}")


def predict_classifier_signal_at(
    *,
    feature_frame: pd.DataFrame | None,
    close_series: pd.Series | None,
    cutoff: pd.Timestamp,
    classifier_type: str = "random_forest",
    min_train_samples: int = 30,
    probability_threshold: float = 0.55,
) -> tuple[int, float]:
    if feature_frame is None or feature_frame.empty or close_series is None or close_series.empty:
        return 0, 0.0

    frame = feature_frame.copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        return 0, 0.0
    frame = frame.sort_index()
    close = close_series.copy().sort_index()
    if not isinstance(close.index, pd.DatetimeIndex):
        return 0, 0.0

    common = frame.index.intersection(close.index)
    if len(common) < max(5, int(min_train_samples)):
        return 0, 0.0

    frame = frame.loc[common]
    y_cls = _build_label_from_close(close.loc[common])
    data = frame.copy()
    data["target"] = y_cls
    data = data.dropna(how="any")
    if data.empty:
        return 0, 0.0

    cutoff = pd.Timestamp(cutoff)
    train = data[data.index < cutoff]
    test = data[data.index == cutoff]
    if test.empty:
        prior = data[data.index <= cutoff]
        if prior.empty:
            return 0, 0.0
        test = prior.tail(1)
        train = data[data.index < test.index[0]]

    if len(train) < max(5, int(min_train_samples)):
        return 0, 0.0

    x_cols = [c for c in train.columns if c != "target"]
    if not x_cols:
        return 0, 0.0

    x_train = train[x_cols]
    y_train = train["target"].astype(int)
    x_test = test[x_cols]

    model = _make_classifier(classifier_type)
    if model is None:
        return 0, 0.0
    try:
        model.fit(x_train, y_train)
        pred = int(model.predict(x_test)[0])
        if hasattr(model, "predict_proba"):
            probs = model.predict_proba(x_test)[0]
            cls = getattr(model, "classes_", np.array([pred]))
            prob_map = {int(c): float(p) for c, p in zip(cls, probs)}
            conf = float(max(prob_map.values())) if prob_map else 0.0
        else:
            conf = 0.5
        if conf < float(probability_threshold):
            return 0, conf
        return pred if pred in {-1, 0, 1} else 0, conf
    except Exception:
        return 0, 0.0
