from __future__ import annotations

import numpy as np
import pandas as pd

from features import predict_config, predict_final_ensemble


ROUTE5_START = pd.Timestamp("2025-12-16")
T1_START = pd.Timestamp("2025-11-12")
T1_FULL_EFFECT = pd.Timestamp("2025-11-19")
WEEKEND_RESTORE = pd.Timestamp("2025-11-15")


def apply_known_future_interventions(
    train: pd.DataFrame,
    future: pd.DataFrame,
    base_prediction: np.ndarray,
    *,
    t1_steady_factor: float = 0.90,
) -> tuple[np.ndarray, dict[str, float]]:
    """Apply deterministic, pre-specified changes not learnable from route 5 history.

    The supplied GTFS reference is the authority for the route 5 start date.  No
    observed November/December target is used.  Route 5 demand is anchored to a
    conservative fraction of route 25, while its hourly/weekday shape comes from
    the already-fitted production forecast for route 25.

    Public operations notices are used for the route 7/50 weekend restoration
    and the route T1 network change.  The T1 effect is deliberately exposed as
    a scenario parameter because its exact cannibalisation cannot be observed
    in the supplied target history.
    """
    prediction = np.asarray(base_prediction, dtype=float).copy()
    audit: dict[str, float] = {}

    # 1 November was an officially transferred working Saturday.  Blend the
    # Friday service profile with a small Saturday component to retain the
    # shortened/pre-holiday character.  Route 50 is kept as a hedge between the
    # working-day profile and its construction-closure regime.
    work_mask = future.date.eq("2025-11-01").to_numpy()
    if work_mask.any():
        working_grid = future.loc[work_mask].copy().reset_index(drop=True)
        working_grid["dow"] = 4
        friday_prediction = predict_final_ensemble(train, working_grid)
        original = prediction[work_mask].copy()
        routes = working_grid.route.to_numpy()
        # Route 50 was observed operating on the transferred working Saturday;
        # use the same shortened-working-day hedge as the other routes.
        weights = np.full(len(routes), 0.85)
        prediction[work_mask] = weights * friday_prediction + (1.0 - weights) * original
        audit["nov01_added_boardings"] = float(prediction[work_mask].sum() - original.sum())

    # Cold start: the route does not exist in the target history, so a boosting
    # model cannot infer it.  Route 25 is the closest conservative volume anchor
    # among the supplied targets.  A short launch ramp avoids assuming full
    # steady-state demand from the first hour.
    route25 = future.route.eq(25).to_numpy()
    route5 = future.route.eq(5).to_numpy()
    if route25.sum() == route5.sum() and route5.any():
        route25_frame = future.loc[route25, ["date", "hour"]].copy()
        route25_frame["anchor"] = prediction[route25]
        route5_frame = future.loc[route5, ["date", "hour"]].copy()
        route5_anchor = route5_frame.merge(
            route25_frame, on=["date", "hour"], how="left", validate="one_to_one"
        ).anchor.to_numpy()
        active = route5_frame.date.ge(ROUTE5_START).to_numpy()
        ramp = np.ones(len(route5_frame), dtype=float)
        ramp[route5_frame.date.eq(ROUTE5_START).to_numpy()] = 0.75
        ramp[route5_frame.date.eq(ROUTE5_START + pd.Timedelta(days=1)).to_numpy()] = 0.90
        cold_start = np.where(active, 0.75 * route5_anchor * ramp, 0.0)
        prediction[route5] = cold_start
        audit["route5_total"] = float(cold_start.sum())

    # Route T1 replaced route 90 and extended its service through the eastern
    # segment shared with route 7.  Route 90's partial overlap had already
    # produced a small observed step in September; only the incremental T1
    # effect is applied here, with a one-week adoption ramp.
    route7_t1 = (future.route.eq(7) & future.date.ge(T1_START)).to_numpy()
    if route7_t1.any():
        dates = future.loc[route7_t1, "date"]
        ramp_factor = (1.0 + t1_steady_factor) / 2.0
        factors = np.where(dates.lt(T1_FULL_EFFECT), ramp_factor, t1_steady_factor)
        original = prediction[route7_t1].copy()
        prediction[route7_t1] *= factors
        audit["route7_t1_removed_boardings"] = float(original.sum() - prediction[route7_t1].sum())

    # The late-evening truncation announced from 28 October remained in force
    # until normal weekend routes were restored.  It changes only low-volume
    # hours, so use a conservative 10% reduction rather than zeroing service.
    early_night_restriction = (
        future.route.isin([7, 50])
        & future.date.lt(WEEKEND_RESTORE)
        & future.hour.ge(22)
    ).to_numpy()
    if early_night_restriction.any():
        original = prediction[early_night_restriction].copy()
        prediction[early_night_restriction] *= 0.90
        audit["early_night_removed_boardings"] = float(
            original.sum() - prediction[early_night_restriction].sum()
        )

    # From 15 November routes 7 and 50 again ran their normal weekend paths.
    # Use only history strictly before the 6 September construction regime.
    route7_restore = (
        future.route.eq(7)
        & future.date.ge(WEEKEND_RESTORE)
        & future.dow.ge(5)
    ).to_numpy()
    if route7_restore.any():
        preclosure = train[train.route.eq(7) & train.date.lt("2025-09-06")]
        normal = predict_config(
            preclosure,
            future.loc[route7_restore],
            ("regime", "median", 20, 1.0, "sunday"),
        )
        dates = future.loc[route7_restore, "date"]
        ramp_factor = (1.0 + t1_steady_factor) / 2.0
        t1_factor = np.where(dates.lt(T1_FULL_EFFECT), ramp_factor, t1_steady_factor)
        original = prediction[route7_restore].copy()
        prediction[route7_restore] = normal * t1_factor
        audit["route7_restore_added_boardings"] = float(
            prediction[route7_restore].sum() - original.sum()
        )

    route50_restore = (
        future.route.eq(50)
        & future.date.ge(WEEKEND_RESTORE)
        & future.dow.ge(5)
    ).to_numpy()
    if route50_restore.any():
        preclosure = train[train.route.eq(50) & train.date.lt("2025-09-06")]
        normal = predict_config(
            preclosure,
            future.loc[route50_restore],
            ("recent", "median", 8, 1.0, "sunday"),
        )
        original = prediction[route50_restore].copy()
        prediction[route50_restore] = 0.90 * normal
        audit["route50_restore_added_boardings"] = float(
            prediction[route50_restore].sum() - original.sum()
        )

    # From 13 December weekend operations in the centre end/shorten earlier.
    # Only hour 23 is materially affected in the competition grid.
    late_weekend = (
        future.route.isin([7, 50])
        & future.date.ge("2025-12-13")
        & future.dow.ge(5)
        & future.hour.eq(23)
    ).to_numpy()
    if late_weekend.any():
        original = prediction[late_weekend].copy()
        route_factor = np.where(future.loc[late_weekend, "route"].eq(7), 0.80, 0.85)
        prediction[late_weekend] *= route_factor
        audit["late_weekend_removed_boardings"] = float(
            original.sum() - prediction[late_weekend].sum()
        )

    return np.clip(prediction, 0.0, None), audit
