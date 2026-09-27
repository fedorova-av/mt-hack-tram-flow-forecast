from __future__ import annotations

import numpy as np
import pandas as pd


# Deterministic calendar information available before the forecast.
HOLIDAYS_2025 = {
    "2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04",
    "2025-01-05", "2025-01-06", "2025-01-07", "2025-01-08",
    "2025-02-23", "2025-03-08", "2025-05-01", "2025-05-02",
    "2025-05-08", "2025-05-09", "2025-06-12", "2025-06-13",
    "2025-11-03", "2025-11-04", "2025-12-31",
}

# (history pool, robust statistic, occurrences per weekday, EW decay, holiday rule)
CV_ROUTE_CONFIGS = {
    1: ("regime", "mean", 32, 1.0, "sunday"),
    5: ("recent", "mean", 1, 1.0, "sunday"),
    7: ("regime", "mean", 32, 1.0, "sunday"),
    11: ("regime", "mean", 20, 1.0, "sunday"),
    12: ("regime", "ewm", 24, 0.97, "sunday"),
    17: ("regime", "median", 20, 1.0, "sunday"),
    25: ("regime", "ewm", 20, 0.93, "sunday"),
    26: ("regime", "trimmed", 20, 1.0, "sunday"),
    28: ("regime", "mean", 20, 1.0, "sunday"),
    50: ("regime", "mean", 24, 1.0, "sunday"),
}

# Selected on two stable regular-period diagnostics (Mar-Apr and Oct), then
# blended with the more conservative 61-day-CV configuration above.
STABLE_ROUTE_CONFIGS = {
    1: ("regime", "median", 20, 1.0, "sunday"),
    5: ("recent", "mean", 1, 1.0, "sunday"),
    7: ("regime", "mean", 4, 1.0, "sunday"),
    11: ("regime", "trimmed", 32, 1.0, "sunday"),
    12: ("regime", "trimmed", 32, 1.0, "sunday"),
    17: ("regime", "median", 24, 1.0, "sunday"),
    25: ("regime", "ewm", 6, 0.75, "sunday"),
    26: ("recent", "trimmed", 3, 1.0, "sunday"),
    28: ("regime", "trimmed", 24, 1.0, "sunday"),
    50: ("regime", "median", 6, 1.0, "sunday"),
}

# Stable-regime meta-weights estimated from the two non-summer diagnostics
# (Mar-Apr and October).  They are used only for the final regular-period
# forecast; the fixed 75/25 ensemble remains the conservative CV reference.
FINAL_ROUTE_STABLE_WEIGHTS = {
    1: 0.80,
    5: 1.00,
    7: 0.90,
    11: 1.00,
    12: 1.00,
    17: 1.00,
    25: 1.00,
    26: 1.00,
    28: 0.85,
    50: 0.95,
}

# A small normalized-profile correction selected only when it was stable on
# both regular-regime diagnostics and did not hurt the long 61-day backtests.
# Keeping the weight at 25% avoids replacing the stronger direct hourly model.
SHARE_PROFILE_CORRECTIONS = {
    7: ("raw_mean", 32, 1.0, 0.25),
    25: ("median", 8, 1.0, 0.25),
}


def add_calendar(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["regime"] = "regular"
    result.loc[result.date.dt.month.between(6, 8), "regime"] = "summer"
    # Dec 25-30 are ordinary working dates in Russia. Dec 31 is handled by
    # the holiday rule, using a recent Sunday profile instead of January demand.
    result.loc[(result.date.dt.month.eq(1)) & result.date.dt.day.le(8), "regime"] = "winter_break"
    result["holiday"] = result.date.dt.strftime("%Y-%m-%d").isin(HOLIDAYS_2025)
    return result


def _aggregate(grouped, kind: str) -> pd.Series:
    if kind == "mean":
        return grouped.mean()
    if kind == "median":
        return grouped.median()
    if kind == "trimmed":
        def trimmed(values):
            a = np.sort(values.to_numpy())
            return float(a[1:-1].mean()) if len(a) >= 5 else float(a.mean())
        return grouped.agg(trimmed)
    raise ValueError(kind)


def predict_config(train: pd.DataFrame, future: pd.DataFrame, config: tuple) -> np.ndarray:
    pool, kind, n_occurrences, decay, holiday_rule = config
    target = future.copy()
    target["lookup_dow"] = target.dow
    if holiday_rule == "sunday":
        target.loc[target.holiday, "lookup_dow"] = 6
    predictions = []
    for regime, index in target.groupby("regime").groups.items():
        history = train
        if pool == "regime":
            same_regime = train[train.regime.eq(regime)]
            if not same_regime.empty:
                history = same_regime
        keys = ["route", "dow", "hour"]
        history = history.sort_values("date").groupby(keys, observed=True, group_keys=False).tail(n_occurrences).copy()
        if kind == "ewm":
            history["rank"] = history.groupby(keys, observed=True).cumcount(ascending=False)
            history["weight"] = np.power(decay, history["rank"])
            history["weighted_y"] = history.weight * history.boardings
            agg = history.groupby(keys, observed=True).agg(weighted_y=("weighted_y", "sum"), weight=("weight", "sum"))
            statistic = agg.weighted_y / agg.weight
        else:
            statistic = _aggregate(history.groupby(keys, observed=True).boardings, kind)
        part = target.loc[index].merge(
            statistic.rename("prediction").reset_index().rename(columns={"dow": "lookup_dow"}),
            on=["route", "lookup_dow", "hour"], how="left", sort=False,
        )
        part.index = index
        predictions.append(part.prediction)
    return pd.concat(predictions).sort_index().fillna(0.0).to_numpy()


def predict_route_model(train: pd.DataFrame, future: pd.DataFrame, configs: dict[int, tuple]) -> np.ndarray:
    pred = np.zeros(len(future), dtype=float)
    for route, index in future.groupby("route").groups.items():
        pred[index] = predict_config(train, future.loc[index], configs[int(route)])
    return pred


def predict_production_ensemble(train: pd.DataFrame, future: pd.DataFrame) -> np.ndarray:
    stable = predict_route_model(train, future, STABLE_ROUTE_CONFIGS)
    conservative = predict_route_model(train, future, CV_ROUTE_CONFIGS)
    prediction = 0.75 * stable + 0.25 * conservative
    return np.clip(prediction, 0.0, None)


def predict_final_ensemble(train: pd.DataFrame, future: pd.DataFrame) -> np.ndarray:
    stable = predict_route_model(train, future, STABLE_ROUTE_CONFIGS)
    conservative = predict_route_model(train, future, CV_ROUTE_CONFIGS)
    prediction = np.zeros(len(future), dtype=float)
    for route, index in future.groupby("route").groups.items():
        weight = FINAL_ROUTE_STABLE_WEIGHTS[int(route)]
        prediction[index] = weight * stable[index] + (1.0 - weight) * conservative[index]
    prediction = apply_share_profile_corrections(train, future, prediction)
    return np.clip(prediction, 0.0, None)


def _share_profile(train: pd.DataFrame, route: int, kind: str, n: int, decay: float) -> pd.Series:
    keys = ["route", "dow", "hour"]
    history = train[train.route.eq(route)].sort_values("date")
    history = history.groupby(keys, observed=True, group_keys=False).tail(n).copy()
    history["daily"] = history.groupby(["route", "date"], observed=True).boardings.transform("sum")
    history["share"] = history.boardings / history.daily.replace(0, np.nan)
    if kind == "raw_mean":
        raw = history.groupby(keys, observed=True).boardings.mean()
        share = raw / raw.groupby(level=[0, 1]).transform("sum")
    elif kind == "median":
        share = history.groupby(keys, observed=True).share.median()
        share = share / share.groupby(level=[0, 1]).transform("sum")
    elif kind == "ewm":
        history["rank"] = history.groupby(keys, observed=True).cumcount(ascending=False)
        history["weight"] = np.power(decay, history["rank"])
        history["weighted_share"] = history.weight * history.share
        agg = history.groupby(keys, observed=True).agg(
            weighted_share=("weighted_share", "sum"), weight=("weight", "sum")
        )
        share = agg.weighted_share / agg.weight
        share = share / share.groupby(level=[0, 1]).transform("sum")
    else:
        raise ValueError(kind)
    return share


def apply_share_profile_corrections(
    train: pd.DataFrame,
    future: pd.DataFrame,
    base_prediction: np.ndarray,
) -> np.ndarray:
    prediction = np.asarray(base_prediction, dtype=float).copy()
    for route, (kind, n, decay, weight) in SHARE_PROFILE_CORRECTIONS.items():
        index = future.index[future.route.eq(route)].to_numpy()
        if not len(index):
            continue
        part = future.loc[index, ["route", "date", "hour", "dow", "holiday"]].copy()
        part["lookup_dow"] = np.where(part.holiday, 6, part.dow)
        part["base"] = prediction[index]
        part["daily"] = part.groupby(["route", "date"], observed=True).base.transform("sum")
        share = _share_profile(train, route, kind, n, decay).rename("share").reset_index()
        share = share.rename(columns={"dow": "lookup_dow"})
        part = part.merge(
            share, on=["route", "lookup_dow", "hour"], how="left", sort=False, validate="many_to_one"
        )
        corrected = (part.daily * part.share.fillna(0.0)).to_numpy()
        prediction[index] = (1.0 - weight) * prediction[index] + weight * corrected
    return prediction
