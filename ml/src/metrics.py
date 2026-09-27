from __future__ import annotations

import numpy as np


def wape_score(y_true, y_pred) -> float:
    """Exact competition metric with a defined all-zero edge case."""
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    denominator = y.sum()
    if denominator == 0:
        return 1.0 if np.abs(p).sum() == 0 else 0.0
    return max(0.0, 1.0 - np.abs(y - p).sum() / denominator)
