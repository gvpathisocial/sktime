"""CSV and folder data loaders."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from sktime_quant.config.schema import DataConfig


class CSVDataProvider:
    def load_history(self, config: DataConfig) -> tuple[pd.DataFrame, pd.DataFrame | None]:
        if not config.csv_path:
            raise ValueError("csv_path is required for source_type='csv'")
        frame = pd.read_csv(config.csv_path)
        return frame, None


class FolderDataProvider:
    def load_history(self, config: DataConfig) -> tuple[pd.DataFrame, pd.DataFrame | None]:
        if not config.folder_path:
            raise ValueError("folder_path is required for source_type='folder'")

        folder = Path(config.folder_path)
        files = sorted(folder.glob("*.csv"))
        if not files:
            raise ValueError("No csv files found in folder_path")

        frames = [pd.read_csv(path) for path in files]
        market = pd.concat(frames, ignore_index=True)
        return market, None

