from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from features import (
    CV_ROUTE_CONFIGS,
    FINAL_ROUTE_STABLE_WEIGHTS,
    SHARE_PROFILE_CORRECTIONS,
    STABLE_ROUTE_CONFIGS,
)
from load_data import ROOT, load_hourly_labels
from validate import backtest


def serialize_configs(configs):
    return {str(route): list(config) for route, config in configs.items()}


def main() -> None:
    (ROOT / "models").mkdir(exist_ok=True)
    (ROOT / "predictions").mkdir(exist_ok=True)
    data = load_hourly_labels()
    prod_metrics, prod_oof = backtest(data, "production")
    cv_metrics, _ = backtest(data, "cv")
    final_metrics, _ = backtest(data, "final")
    model = {
        "model": "route-specific regime-aware robust seasonal ensemble",
        "seed": 20250926,
        "stable_weight": 0.75,
        "cv_weight": 0.25,
        "final_route_stable_weights": FINAL_ROUTE_STABLE_WEIGHTS,
        "share_profile_corrections": SHARE_PROFILE_CORRECTIONS,
        "stable_route_configs": serialize_configs(STABLE_ROUTE_CONFIGS),
        "cv_route_configs": serialize_configs(CV_ROUTE_CONFIGS),
        "training_end": "2025-10-31",
        "excluded_tail": "test.csv 2025-11-01",
        "forecast_interventions": {
            "working_weekend": "2025-11-01",
            "route5_start_from_supplied_gtfs": "2025-12-16",
            "route7_and_route50_weekend_restore": "2025-11-15",
            "route_t1_start_and_route7_scenario": "2025-11-12; steady factor 0.90",
        },
        "validation": final_metrics.to_dict(orient="records"),
    }
    (ROOT / "models" / "seasonal_route_model.json").write_text(
        json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    prod_oof.to_csv(ROOT / "predictions" / "oof_production.csv", index=False)
    comparison = prod_metrics.rename(columns={"score": "production_score"}).merge(
        cv_metrics[["fold", "score"]].rename(columns={"score": "cv_model_score"}), on="fold"
    )
    comparison = comparison.merge(
        final_metrics[["fold", "score"]].rename(columns={"score": "final_score"}), on="fold"
    )
    comparison.to_csv(ROOT / "predictions" / "validation_scores.csv", index=False)
    print(comparison.to_string(index=False))
    main_scores = comparison[comparison.fold.str.startswith("fold_")].production_score
    print(f"production main CV mean={main_scores.mean():.6f}, std={main_scores.std(ddof=0):.6f}")


if __name__ == "__main__":
    main()
