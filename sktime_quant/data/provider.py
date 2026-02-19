"""Data provider facade across supported source types."""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from sktime_quant.config.schema import DataConfig
from sktime_quant.data.connectors.csv_loader import CSVDataProvider, FolderDataProvider
from sktime_quant.data.connectors.timescale import TimescaleDataProvider
from sktime_quant.data.schema import validate_exogenous_frame, validate_market_frame


class Loader(Protocol):
    def load_history(self, config: DataConfig) -> tuple[pd.DataFrame, pd.DataFrame | None]:
        ...


class DataProvider:
    def __init__(self) -> None:
        self._providers: dict[str, Loader] = {
            "timescale": TimescaleDataProvider(),
            "csv": CSVDataProvider(),
            "folder": FolderDataProvider(),
        }

    def load_history(self, config: DataConfig) -> tuple[pd.DataFrame, pd.DataFrame | None]:
        if config.source_type not in self._providers:
            raise ValueError(f"Unsupported data source: {config.source_type}")
        market, exog = self._providers[config.source_type].load_history(config)
        market_v = validate_market_frame(market)
        exog_v = validate_exogenous_frame(exog)
        return self._apply_common_filters(market_v, exog_v, config)

    def _apply_common_filters(
        self,
        market: pd.DataFrame,
        exog: pd.DataFrame | None,
        config: DataConfig,
    ) -> tuple[pd.DataFrame, pd.DataFrame | None]:
        frame = market.copy()
        if config.start:
            frame = frame[frame["timestamp"] >= pd.Timestamp(config.start, tz="UTC")]
        if config.end:
            frame = frame[frame["timestamp"] <= pd.Timestamp(config.end, tz="UTC")]
        if config.universe:
            frame = frame[frame["asset"].isin(config.universe)]
        frame = frame.reset_index(drop=True)

        exog_frame = exog
        if exog_frame is not None:
            exog_frame = exog_frame.copy()
            if config.start:
                exog_frame = exog_frame[
                    exog_frame["timestamp"] >= pd.Timestamp(config.start, tz="UTC")
                ]
            if config.end:
                exog_frame = exog_frame[
                    exog_frame["timestamp"] <= pd.Timestamp(config.end, tz="UTC")
                ]
            if config.universe:
                exog_frame = exog_frame[exog_frame["asset"].isin(config.universe)]
            exog_frame = exog_frame.reset_index(drop=True)

        return frame, exog_frame

