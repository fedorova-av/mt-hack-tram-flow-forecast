from __future__ import annotations

import numpy as np
import pandas as pd

from features import (
    CV_ROUTE_CONFIGS,
    add_calendar,
    predict_final_ensemble,
    predict_production_ensemble,
    predict_route_model,
)
from metrics import wape_score


FOLDS = [
    ("fold_may_jun", "2025-05-01", "2025-06-30"),
    ("fold_jul_aug", "2025-07-01", "2025-08-31"),
    ("fold_sep_oct", "2025-09-01", "2025-10-31"),
    ("diagnostic_oct", "2025-10-01", "2025-10-31"),
]


def backtest(data: pd.DataFrame, model: str = "production") -> tuple[pd.DataFrame, pd.DataFrame]:
    data = add_calendar(data)
    metrics = []
    oof = []
    for fold, start, end in FOLDS:
        train = data[data.date.lt(start)]
        valid = data[data.date.between(start, end)].copy().reset_index(drop=True)
        if model == "production":
            pred = predict_production_ensemble(train, valid)
        elif model == "final":
            pred = predict_final_ensemble(train, valid)
        elif model == "cv":
            pred = predict_route_model(train, valid, CV_ROUTE_CONFIGS)
        else:
            raise ValueError(model)
        valid["prediction"] = pred
        valid["fold"] = fold
        metrics.append({"fold": fold, "score": wape_score(valid.boardings, pred), "target_sum": valid.boardings.sum()})
        oof.append(valid[["fold", "route", "date", "hour", "boardings", "prediction"]])
    return pd.DataFrame(metrics), pd.concat(oof, ignore_index=True)
