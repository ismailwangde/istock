"""On-disk weight format for brain v2.

Each weight file is JSON with this shape:

    {
      "ticker": "AAPL",
      "feature_names": [... 36 names — must equal features.FEATURE_NAMES ...],
      "intercept": -0.123,
      "coefficients": [...36 floats...],
      "C": 1.0,
      "class_weight": "balanced",
      "n_train": 312,
      "n_val": 102,
      "n_test": 164,
      "source": "per_ticker",     // or "pooled"
      "fold_label": "2025-05_to_2026-05",
      "fit_at": "2026-05-18T22:15:00",
      "diagnostics": { ... }
    }
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from istock.features.spec import FEATURE_NAMES, N_FEATURES


WEIGHTS_DIR_DEFAULT = Path(__file__).resolve().parent.parent.parent / "results" / "brain_v2_weights"
POOLED_FILENAME = "_pooled.json"
DISABLED_FILENAME_SUFFIX = ".disabled.json"


@dataclass
class WeightSet:
    """In-memory representation of one weight file (per-ticker or pooled)."""
    ticker: str
    intercept: float
    coefficients: np.ndarray
    C: float
    class_weight: str
    n_train: int
    n_val: int
    n_test: int
    source: str
    fold_label: str
    fit_at: str
    feature_names: List[str]
    diagnostics: Dict[str, object] = field(default_factory=dict)


def save_weight_set(ws: WeightSet, path: Path) -> None:
    if list(ws.feature_names) != list(FEATURE_NAMES):
        raise ValueError(
            f"Cannot save weights for {ws.ticker}: "
            f"feature_names ({len(ws.feature_names)} cols) does not match "
            f"FEATURE_NAMES ({N_FEATURES} cols). Roster changed since fit."
        )
    if ws.coefficients.shape != (N_FEATURES,):
        raise ValueError(
            f"Cannot save weights for {ws.ticker}: "
            f"coefficients.shape={ws.coefficients.shape}, expected ({N_FEATURES},)."
        )
    payload: Dict[str, Any] = {
        "ticker": ws.ticker,
        "feature_names": list(ws.feature_names),
        "intercept": float(ws.intercept),
        "coefficients": [float(c) for c in ws.coefficients],
        "C": float(ws.C),
        "class_weight": ws.class_weight,
        "n_train": int(ws.n_train),
        "n_val": int(ws.n_val),
        "n_test": int(ws.n_test),
        "source": ws.source,
        "fold_label": ws.fold_label,
        "fit_at": ws.fit_at,
        "diagnostics": ws.diagnostics,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=_json_default)


def load_weight_set(path: Path) -> WeightSet:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if list(data.get("feature_names", [])) != list(FEATURE_NAMES):
        raise ValueError(
            f"Weight file {path.name} has a stale feature roster "
            f"({len(data.get('feature_names', []))} cols vs current {N_FEATURES}). "
            "Re-train brain v2 to refresh."
        )
    coef = np.asarray(data["coefficients"], dtype=float)
    if coef.shape != (N_FEATURES,):
        raise ValueError(
            f"Weight file {path.name} has coefficients of shape {coef.shape}; "
            f"expected ({N_FEATURES},)."
        )
    return WeightSet(
        ticker=data["ticker"],
        intercept=float(data["intercept"]),
        coefficients=coef,
        C=float(data["C"]),
        class_weight=data.get("class_weight", "balanced"),
        n_train=int(data.get("n_train", 0)),
        n_val=int(data.get("n_val", 0)),
        n_test=int(data.get("n_test", 0)),
        source=data.get("source", "per_ticker"),
        fold_label=data.get("fold_label", ""),
        fit_at=data.get("fit_at", ""),
        feature_names=list(data["feature_names"]),
        diagnostics=data.get("diagnostics", {}),
    )


def find_weight_for_ticker(
    ticker: str,
    weights_dir: Path = WEIGHTS_DIR_DEFAULT,
) -> Optional[WeightSet]:
    """Return the pooled WeightSet for any ticker (r3: per-ticker disabled)."""
    weights_dir = Path(weights_dir)
    pooled_path = weights_dir / POOLED_FILENAME
    if pooled_path.exists():
        return load_weight_set(pooled_path)
    return None


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
