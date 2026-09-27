from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "work" / "dataset"
ROUTES = [1, 5, 7, 11, 12, 17, 25, 26, 28, 50]


def load_hourly_labels(data_dir: Path = DEFAULT_DATA) -> pd.DataFrame:
    frames = []
    for filename in ("labels_day_train.csv", "labels_day_test.csv"):
        frame = pd.read_csv(data_dir / "labels" / filename, sep=";")
        frame["date"] = pd.to_datetime(frame["date"], errors="raise")
        frames.append(frame)
    positive = pd.concat(frames, ignore_index=True)
    positive = positive[positive.date.le("2025-10-31")]
    grid = pd.MultiIndex.from_product(
        [ROUTES, pd.date_range("2025-01-01", "2025-10-31"), range(24)],
        names=["route", "date", "hour"],
    ).to_frame(index=False)
    full = grid.merge(positive, on=["route", "date", "hour"], how="left", validate="one_to_one")
    full["boardings"] = full.boardings.fillna(0.0).astype(float)
    full["dow"] = full.date.dt.dayofweek.astype("int8")
    return full


def load_submission_grid(data_dir: Path = DEFAULT_DATA) -> pd.DataFrame:
    grid = pd.read_csv(data_dir / "test_submission.csv", sep=";")
    grid["date"] = pd.to_datetime(grid["date"], errors="raise")
    expected = ["route", "date", "hour", "prediction"]
    if grid.columns.tolist() != expected:
        raise ValueError(f"Unexpected submission schema: {grid.columns.tolist()}")
    if len(grid) != 14_640 or grid[["route", "date", "hour"]].duplicated().any():
        raise ValueError("Submission grid is not the expected unique 14,640-row grid")
    grid["dow"] = grid.date.dt.dayofweek.astype("int8")
    return grid
