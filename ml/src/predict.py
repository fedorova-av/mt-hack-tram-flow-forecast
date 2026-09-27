from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from features import add_calendar, predict_final_ensemble
from interventions import apply_known_future_interventions
from load_data import ROOT, load_hourly_labels, load_submission_grid


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "submission.csv")
    parser.add_argument(
        "--t1-factor", type=float, default=0.90,
        help="Steady route-7 demand multiplier after the T1 launch (default: 0.90)",
    )
    args = parser.parse_args()
    if not 0.75 <= args.t1_factor <= 1.0:
        raise ValueError("--t1-factor must be between 0.75 and 1.0")
    train = add_calendar(load_hourly_labels())
    future = add_calendar(load_submission_grid().drop(columns="prediction"))
    base_prediction = predict_final_ensemble(train, future)
    prediction, intervention_audit = apply_known_future_interventions(
        train, future, base_prediction, t1_steady_factor=args.t1_factor
    )
    # Competition accepts numeric predictions and states that they are rounded.
    # Integer output prevents locale/float serialization surprises.
    result = future[["route", "date", "hour"]].copy()
    result["prediction"] = np.rint(np.clip(prediction, 0, None)).astype("int64")
    result["date"] = result.date.dt.strftime("%Y-%m-%d")
    if len(result) != 14_640 or result.prediction.isna().any() or (result.prediction < 0).any():
        raise ValueError("Invalid submission values")
    if result[["route", "date", "hour"]].duplicated().any():
        raise ValueError("Duplicate submission keys")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, sep=";", index=False, encoding="utf-8")
    print(f"wrote {len(result)} rows to {args.output}")
    print(result.groupby("route").prediction.agg(["sum", "mean", "max"]).to_string())
    print("interventions", intervention_audit)


if __name__ == "__main__":
    main()
