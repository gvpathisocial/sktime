"""Signal blending policies."""

from __future__ import annotations


def blend_signals(
    *,
    forecast_signal: int,
    rule_signal: int,
    classifier_signal: int,
    policy: str = "weighted_vote",
    forecast_weight: float = 0.34,
    rule_weight: float = 0.33,
    classifier_weight: float = 0.33,
    vote_threshold: float = 0.1,
) -> int:
    fs = int(forecast_signal)
    rs = int(rule_signal)
    cs = int(classifier_signal)

    if policy == "and":
        if fs == rs == cs and fs != 0:
            return fs
        return 0

    if policy == "or":
        signals = [x for x in [cs, rs, fs] if x != 0]
        if not signals:
            return 0
        if all(s == signals[0] for s in signals):
            return int(signals[0])
        return 0

    if policy == "weighted_vote":
        score = (
            float(forecast_weight) * fs
            + float(rule_weight) * rs
            + float(classifier_weight) * cs
        )
        if score > float(vote_threshold):
            return 1
        if score < -float(vote_threshold):
            return -1
        return 0

    raise ValueError(f"Unsupported blend policy: {policy}")
