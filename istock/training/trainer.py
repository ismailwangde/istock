# OFFLINE only — never import this at runtime
"""Offline trainer for brain v2 per-ticker logistic regression.

**This module is OFFLINE-ONLY.** Importing it from the live request path
is a bug. It should only be invoked from `scripts/train_brain_v2.py`.

S22 scope: implements ONE walk-forward fold —

    train:      first 18 months of the eligible-trade timeline
    validation: next 6 months  (C selection from {0.1, 0.3, 1.0, 3.0, 10.0})
    test:       last 12 months (frozen — only touched once at the end)
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from istock.training import diagnostics as diag
from istock.features.spec import (
    FEATURE_NAMES,
    N_FEATURES,
    apply_costs,
    extract_features,
    extract_target,
    is_eligible_trade,
    verify_feature_names_against_dataset,
)
from istock.model.weights import (
    DISABLED_FILENAME_SUFFIX,
    POOLED_FILENAME,
    WEIGHTS_DIR_DEFAULT,
    WeightSet,
    save_weight_set,
)


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
@dataclass
class TrainConfig:
    """All knobs for a single training run. Defaults match §3-§8 of the doc."""
    candidate_C: Tuple[float, ...] = (0.1, 0.3, 1.0, 3.0, 10.0)
    min_train_trades: int = 50
    max_abs_coef: float = 3.0
    val_wr_floor: float = 0.28
    per_ticker_pf_raw_floor: float = 1.40
    per_ticker_pf_bootstrap_p5_floor: float = 1.20
    train_test_pf_ratio_floor: float = 0.80
    bootstrap_resamples: int = 1000
    bootstrap_seed: int = 42
    fold_train_months: int = 18
    fold_val_months: int = 6
    fold_test_months: int = 12


# --------------------------------------------------------------------------- #
# Data prep
# --------------------------------------------------------------------------- #
def load_eligible_trades(backtest_path: Path) -> List[Dict[str, Any]]:
    """Read `results/advisor_backtest.json`, filter to eligible trades, verify
    S21.5 backfill columns are present. Returns trades sorted by sample_date."""
    with open(backtest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    raw = data.get("trades", [])
    eligible = [t for t in raw if is_eligible_trade(t)]
    if not eligible:
        raise ValueError("No eligible trades found in backtest dataset.")

    sample = eligible[0]
    required_flat = ["smc_order_block_bullish", "vwap_above", "atr_regime_high",
                     "sector_relative_strength_20d", "earnings_within_5d",
                     "fib_retracement_near"]
    missing = [k for k in required_flat if k not in sample]
    if missing:
        raise ValueError(
            "S21.5 backfill missing — run `python scripts/backfill_brain_v2_features.py` first.\n"
            f"Missing columns on sample trade: {missing}"
        )

    verify_feature_names_against_dataset(eligible)
    eligible.sort(key=lambda t: t["sample_date"])
    return eligible


@dataclass(frozen=True)
class FoldSpec:
    """A single walk-forward fold definition."""
    name: str
    train_months: int
    val_months: int
    test_months: int
    anchor: str  # "end_of_data" | "start_of_data"


FOLD1 = FoldSpec(
    name="fold1",
    train_months=18, val_months=6, test_months=12,
    anchor="end_of_data",
)

FOLD2 = FoldSpec(
    name="fold2",
    train_months=12, val_months=6, test_months=12,
    anchor="start_of_data",
)

ALL_FOLDS: Dict[str, FoldSpec] = {f.name: f for f in (FOLD1, FOLD2)}


def walk_forward_split(
    trades: List[Dict[str, Any]],
    cfg: TrainConfig,
    fold: FoldSpec = FOLD1,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split sorted trades into (train, val, test) by sample_date."""
    if not trades:
        return [], [], []
    first = datetime.strptime(trades[0]["sample_date"], "%Y-%m-%d").date()
    last = datetime.strptime(trades[-1]["sample_date"], "%Y-%m-%d").date()

    train_end = first + timedelta(days=int(fold.train_months * 30.44))
    val_end = train_end + timedelta(days=int(fold.val_months * 30.44))

    if fold.anchor == "end_of_data":
        test_start = last - timedelta(days=int(fold.test_months * 30.44))
        test_end = last + timedelta(days=1)
    elif fold.anchor == "start_of_data":
        test_start = val_end
        test_end = test_start + timedelta(days=int(fold.test_months * 30.44))
    else:
        raise ValueError(f"Unknown fold anchor: {fold.anchor!r}")

    train, val, test = [], [], []
    for t in trades:
        d = datetime.strptime(t["sample_date"], "%Y-%m-%d").date()
        if d < train_end:
            train.append(t)
        elif d < val_end:
            val.append(t)
        elif test_start <= d < test_end:
            test.append(t)
    return train, val, test


def walk_forward_split_purged(
    trades: List[Dict[str, Any]],
    cfg: TrainConfig,
    fold: FoldSpec = FOLD1,
    max_hold_calendar_days: int = 90,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Purged walk-forward split (Retrain-1, MODEL.md §15 item 0b).

    Same boundaries as walk_forward_split, plus the PURGE rule: a trade
    belongs to a fold only if its forward window RESOLVED inside that fold —
    a trade entered before a boundary whose outcome is decided after it is
    dropped entirely (its label would leak next-fold prices into this fold).

    Resolution date comes from the trade's `resolved_date` (written by
    istock.training.backtester). Legacy trades without it are approximated as
    sample_date + max_hold_calendar_days (conservative: purges more).
    """
    train_raw, val_raw, test_raw = walk_forward_split(trades, cfg, fold)
    if not trades:
        return [], [], []

    first = datetime.strptime(trades[0]["sample_date"], "%Y-%m-%d").date()
    train_end = first + timedelta(days=int(fold.train_months * 30.44))
    val_end = train_end + timedelta(days=int(fold.val_months * 30.44))

    def _resolved(t: Dict[str, Any]) -> date:
        rd = t.get("resolved_date")
        if rd:
            try:
                return datetime.strptime(rd, "%Y-%m-%d").date()
            except ValueError:
                pass
        d = datetime.strptime(t["sample_date"], "%Y-%m-%d").date()
        return d + timedelta(days=max_hold_calendar_days)

    train = [t for t in train_raw if _resolved(t) < train_end]
    val = [t for t in val_raw if _resolved(t) < val_end]
    test = test_raw  # last fold: nothing after it to leak into

    n_purged = (len(train_raw) - len(train)) + (len(val_raw) - len(val))
    if n_purged:
        print(f"  [purge] dropped {n_purged} boundary-crossing trades "
              f"(train {len(train_raw)}→{len(train)}, val {len(val_raw)}→{len(val)})")
    return train, val, test


def build_xy(
    trades: List[Dict[str, Any]],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Materialize feature matrix X (n×36), target vector y (n,), net-pnl vector (n,)."""
    use = [t for t in trades if is_eligible_trade(t) and t.get("pnl_pct") is not None]
    if not use:
        return (np.zeros((0, N_FEATURES), dtype=np.int8),
                np.zeros((0,), dtype=int),
                np.zeros((0,), dtype=float))
    X = np.zeros((len(use), N_FEATURES), dtype=np.int8)
    y = np.zeros(len(use), dtype=int)
    pnl_net = np.zeros(len(use), dtype=float)
    for i, t in enumerate(use):
        X[i] = extract_features(t)
        y[i] = extract_target(t)
        pnl_net[i] = apply_costs(float(t["pnl_pct"]))
    return X, y, pnl_net


# --------------------------------------------------------------------------- #
# Fitting
# --------------------------------------------------------------------------- #
def _fit_logreg(X_train: np.ndarray, y_train: np.ndarray, C: float):
    from sklearn.linear_model import LogisticRegression
    classes = np.unique(y_train)
    if classes.size < 2:
        return None
    model = LogisticRegression(
        C=C, penalty="l2", class_weight="balanced",
        solver="liblinear", max_iter=5000,
    )
    model.fit(X_train, y_train)
    return model


def _predict_for_metric(model, X) -> np.ndarray:
    return model.predict(X)


def select_C(
    X_train: np.ndarray, y_train: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    val_pnl: np.ndarray,
    cfg: TrainConfig,
) -> Tuple[Optional[float], Dict[str, float]]:
    """Try each C; return the one that maximises val PF (net) above the WR floor."""
    best: Tuple[Optional[float], float, Dict[str, float]] = (None, -np.inf, {})
    for C in cfg.candidate_C:
        model = _fit_logreg(X_train, y_train, C)
        if model is None:
            continue
        pred = _predict_for_metric(model, X_val)
        picked = pred == 1
        if picked.sum() == 0:
            continue
        picked_pnl = val_pnl[picked]
        wr = diag.win_rate(picked_pnl)
        if wr < cfg.val_wr_floor:
            continue
        pf = diag.profit_factor(picked_pnl)
        if pf > best[1]:
            best = (C, pf, {"val_pf_net": pf, "val_wr_net": wr,
                            "n_val_picked": int(picked.sum())})
    if best[0] is None:
        return None, {"reason": "no_C_survived_val_wr_floor"}
    return best[0], best[2]


def _picked_pnl(model, X: np.ndarray, pnl: np.ndarray) -> np.ndarray:
    if X.shape[0] == 0:
        return pnl[:0]
    picked = _predict_for_metric(model, X) == 1
    return pnl[picked]


def _picked_per_trade(model, X: np.ndarray, trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if X.shape[0] == 0:
        return []
    pred = _predict_for_metric(model, X) == 1
    out = []
    for keep, t in zip(pred, trades):
        if keep:
            out.append({**t, "pnl_net": apply_costs(float(t["pnl_pct"]))})
    return out


def _build_weight_set(
    ticker: str, model, C: float,
    n_train: int, n_val: int, n_test: int,
    source: str, fold_label: str,
    diagnostics_payload: Dict[str, Any],
    cfg: TrainConfig,
) -> WeightSet:
    coef = np.asarray(model.coef_).ravel().astype(float)
    coef = np.clip(coef, -cfg.max_abs_coef, cfg.max_abs_coef)
    intercept = float(np.asarray(model.intercept_).ravel()[0])
    return WeightSet(
        ticker=ticker, intercept=intercept, coefficients=coef,
        C=float(C), class_weight="balanced",
        n_train=n_train, n_val=n_val, n_test=n_test,
        source=source, fold_label=fold_label,
        fit_at=datetime.now().isoformat(timespec="seconds"),
        feature_names=list(FEATURE_NAMES),
        diagnostics=diagnostics_payload,
    )


def fit_ticker(
    ticker: str,
    train: List[Dict[str, Any]],
    val: List[Dict[str, Any]],
    test: List[Dict[str, Any]],
    cfg: TrainConfig,
    fold_label: str,
    vix_daily=None,
) -> Tuple[Optional[WeightSet], str, Dict[str, Any]]:
    """Fit a per-ticker model. Returns (WeightSet, "ok", diag) on success,
    (None, reason, diag) on failure."""
    diagnostic: Dict[str, Any] = {
        "ticker": ticker,
        "n_train": len(train), "n_val": len(val), "n_test": len(test),
    }
    if len(train) < cfg.min_train_trades:
        diagnostic["reason"] = "low_n"
        return None, "low_n", diagnostic

    X_tr, y_tr, pnl_tr = build_xy(train)
    X_val, y_val, pnl_val = build_xy(val)
    X_test, y_test, pnl_test = build_xy(test)

    if X_tr.shape[0] < cfg.min_train_trades or X_val.shape[0] == 0 or X_test.shape[0] == 0:
        diagnostic["reason"] = "low_n"
        return None, "low_n", diagnostic

    C, val_metrics = select_C(X_tr, y_tr, X_val, y_val, pnl_val, cfg)
    if C is None:
        diagnostic.update(val_metrics)
        diagnostic["reason"] = "val_wr_fail"
        return None, "val_wr_fail", diagnostic

    model = _fit_logreg(X_tr, y_tr, C)
    if model is None:
        diagnostic["reason"] = "degenerate_train_class"
        return None, "degenerate_train_class", diagnostic

    train_picked = _picked_pnl(model, X_tr, pnl_tr)
    test_picked = _picked_pnl(model, X_test, pnl_test)

    train_pf_net = diag.profit_factor(train_picked)
    train_wr_net = diag.win_rate(train_picked)
    test_pf_net, test_p5, test_p95 = diag.bootstrap_pf(
        test_picked, n_resamples=cfg.bootstrap_resamples, seed=cfg.bootstrap_seed,
    )
    test_wr_net = diag.win_rate(test_picked)
    test_avg_pnl_net = float(test_picked.mean()) if test_picked.size else 0.0

    coef = np.asarray(model.coef_).ravel()
    max_abs_coef = float(np.abs(coef).max()) if coef.size else 0.0

    vix_strat: Dict[str, Optional[float]] = {"low": None, "mid": None, "high": None}
    if vix_daily is not None and test_picked.size:
        test_picked_records = _picked_per_trade(model, X_test, test)
        vix_strat = diag.stratified_pf_by_vix(test_picked_records, vix_daily)

    corr = diag.compute_correlation_matrix(X_tr)
    top3 = diag.top_correlated_pairs(corr, FEATURE_NAMES, k=3)

    diagnostic.update({
        "C": C,
        "n_test_picked": int(test_picked.size),
        "n_train_picked": int(train_picked.size),
        "train_pf_net": train_pf_net, "train_wr_net": train_wr_net,
        "val_pf_net": val_metrics.get("val_pf_net"),
        "val_wr_net": val_metrics.get("val_wr_net"),
        "test_pf_net": test_pf_net,
        "test_pf_bootstrap_p5": test_p5, "test_pf_bootstrap_p95": test_p95,
        "test_wr_net": test_wr_net, "test_avg_pnl_net": test_avg_pnl_net,
        "max_abs_coef": max_abs_coef,
        "vix_stratified_pf": vix_strat,
        "top_3_correlated_pairs": top3,
    })

    if test_pf_net < cfg.per_ticker_pf_raw_floor:
        diagnostic["reason"] = "pf_raw_fail"
        return None, "pf_raw_fail", diagnostic
    if test_p5 < cfg.per_ticker_pf_bootstrap_p5_floor:
        diagnostic["reason"] = "pf_bootstrap_fail"
        return None, "pf_bootstrap_fail", diagnostic
    if train_pf_net > 0 and (test_pf_net < cfg.train_test_pf_ratio_floor * train_pf_net):
        diagnostic["reason"] = "train_test_stability_fail"
        return None, "train_test_stability_fail", diagnostic

    diagnostic["reason"] = "ok"
    ws = _build_weight_set(
        ticker, model, C,
        n_train=int(X_tr.shape[0]), n_val=int(X_val.shape[0]), n_test=int(X_test.shape[0]),
        source="per_ticker", fold_label=fold_label,
        diagnostics_payload=diagnostic, cfg=cfg,
    )
    return ws, "ok", diagnostic


def fit_pooled(
    train: List[Dict[str, Any]],
    val: List[Dict[str, Any]],
    test: List[Dict[str, Any]],
    cfg: TrainConfig,
    fold_label: str,
    vix_daily=None,
) -> Tuple[WeightSet, Dict[str, Any]]:
    """Fit the global pooled model. Always returns a WeightSet — pooled is the floor."""
    X_tr, y_tr, pnl_tr = build_xy(train)
    X_val, y_val, pnl_val = build_xy(val)
    X_test, y_test, pnl_test = build_xy(test)

    C, val_metrics = select_C(X_tr, y_tr, X_val, y_val, pnl_val, cfg)
    if C is None:
        C = 1.0
        val_metrics = {"val_pf_net": 0.0, "val_wr_net": 0.0, "note": "val_selection_failed"}
    model = _fit_logreg(X_tr, y_tr, C)
    assert model is not None, "Pooled training data must have both classes"

    train_picked = _picked_pnl(model, X_tr, pnl_tr)
    test_picked = _picked_pnl(model, X_test, pnl_test)
    train_pf_net = diag.profit_factor(train_picked)
    test_pf_net, test_p5, test_p95 = diag.bootstrap_pf(test_picked, cfg.bootstrap_resamples, cfg.bootstrap_seed)
    train_wr_net = diag.win_rate(train_picked)
    test_wr_net = diag.win_rate(test_picked)

    vix_strat = {"low": None, "mid": None, "high": None}
    if vix_daily is not None and test_picked.size:
        test_picked_records = _picked_per_trade(model, X_test, test)
        vix_strat = diag.stratified_pf_by_vix(test_picked_records, vix_daily)

    coef = np.asarray(model.coef_).ravel()
    max_abs_coef = float(np.abs(coef).max()) if coef.size else 0.0

    diagnostics_payload = {
        "ticker": "__POOLED__", "C": C,
        "n_train": int(X_tr.shape[0]), "n_val": int(X_val.shape[0]), "n_test": int(X_test.shape[0]),
        "train_pf_net": train_pf_net, "train_wr_net": train_wr_net,
        "val_pf_net": val_metrics.get("val_pf_net"),
        "val_wr_net": val_metrics.get("val_wr_net"),
        "test_pf_net": test_pf_net,
        "test_pf_bootstrap_p5": test_p5, "test_pf_bootstrap_p95": test_p95,
        "test_wr_net": test_wr_net, "max_abs_coef": max_abs_coef,
        "vix_stratified_pf": vix_strat,
    }
    ws = _build_weight_set(
        "__POOLED__", model, C,
        n_train=int(X_tr.shape[0]), n_val=int(X_val.shape[0]), n_test=int(X_test.shape[0]),
        source="pooled", fold_label=fold_label,
        diagnostics_payload=diagnostics_payload, cfg=cfg,
    )
    return ws, diagnostics_payload


# --------------------------------------------------------------------------- #
# Gates
# --------------------------------------------------------------------------- #
@dataclass
class GateResult:
    ticker: str
    passed: bool
    reason: str = ""
    train_pf_net: float = 0.0
    val_pf_net: float = 0.0
    test_pf_net: float = 0.0
    test_pf_bootstrap_p5: float = 0.0
    test_pf_bootstrap_p95: float = 0.0
    n_train: int = 0
    n_val: int = 0
    n_test: int = 0
    max_abs_coef: float = 0.0


def evaluate_per_ticker_gates(
    model_intercept: float,
    model_coef: np.ndarray,
    X_test: np.ndarray, y_test: np.ndarray, test_pnl: np.ndarray,
    train_pf_net: float, val_pf_net: float,
    n_train: int, n_val: int,
    cfg: TrainConfig,
    ticker: str = "?",
) -> GateResult:
    logits = model_intercept + X_test.astype(float) @ model_coef
    picks = logits > 0
    picked_pnl = test_pnl[picks]
    test_pf_net, test_p5, test_p95 = diag.bootstrap_pf(
        picked_pnl, cfg.bootstrap_resamples, cfg.bootstrap_seed,
    )
    max_abs_coef = float(np.abs(model_coef).max()) if model_coef.size else 0.0

    reason = "ok"
    passed = True
    if test_pf_net < cfg.per_ticker_pf_raw_floor:
        passed = False; reason = "pf_raw_fail"
    elif test_p5 < cfg.per_ticker_pf_bootstrap_p5_floor:
        passed = False; reason = "pf_bootstrap_fail"
    elif train_pf_net > 0 and test_pf_net < cfg.train_test_pf_ratio_floor * train_pf_net:
        passed = False; reason = "train_test_stability_fail"
    elif max_abs_coef > cfg.max_abs_coef:
        passed = False; reason = "weight_clipped"

    return GateResult(
        ticker=ticker, passed=passed, reason=reason,
        train_pf_net=train_pf_net, val_pf_net=val_pf_net,
        test_pf_net=test_pf_net,
        test_pf_bootstrap_p5=test_p5, test_pf_bootstrap_p95=test_p95,
        n_train=n_train, n_val=n_val, n_test=int(X_test.shape[0]),
        max_abs_coef=max_abs_coef,
    )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def train_all(
    backtest_path: Path,
    weights_dir: Path,
    cfg: TrainConfig,
    dry_run: bool = False,
    log=print,
    fold: FoldSpec = FOLD1,
) -> Dict[str, Any]:
    """End-to-end training run. Returns a summary dict for rendering into _diagnostics.md."""
    log(f"[load] reading backtest dataset... (fold={fold.name})")
    trades = load_eligible_trades(backtest_path)
    log(f"[load] {len(trades)} eligible trades ({trades[0]['sample_date']} -> {trades[-1]['sample_date']})")

    train, val, test = walk_forward_split(trades, cfg, fold)
    log(f"[split] train={len(train)}  val={len(val)}  test={len(test)}  (fold={fold.name})")
    if train:
        log(f"  train range: {train[0]['sample_date']} -> {train[-1]['sample_date']}")
    if val:
        log(f"  val   range: {val[0]['sample_date']} -> {val[-1]['sample_date']}")
    if test:
        log(f"  test  range: {test[0]['sample_date']} -> {test[-1]['sample_date']}")

    fold_label = (
        f"{fold.name}_train_{train[0]['sample_date']}-{train[-1]['sample_date']}_"
        f"val_{val[0]['sample_date']}-{val[-1]['sample_date']}_"
        f"test_{test[0]['sample_date']}-{test[-1]['sample_date']}"
        if (train and val and test) else f"{fold.name}_incomplete"
    )

    try:
        from istock.training.diagnostics import load_vix_daily
        vix_daily = load_vix_daily(backtest_path.parent / "cache")
    except FileNotFoundError as e:
        log(f"[warn] VIX cache missing — strat will be all None. {e}")
        vix_daily = None

    log("[pooled] fitting pooled model on all-ticker trades...")
    pooled_ws, pooled_diag = fit_pooled(train, val, test, cfg, fold_label, vix_daily=vix_daily)
    log(f"[pooled] C={pooled_ws.C}  train_pf={pooled_diag['train_pf_net']:.3f}  "
        f"test_pf={pooled_diag['test_pf_net']:.3f} "
        f"(boot p5={pooled_diag['test_pf_bootstrap_p5']:.3f})")

    log("[per-ticker] fitting per-ticker models...")
    trades_by_ticker = defaultdict(list)
    for t in trades:
        trades_by_ticker[t["ticker"]].append(t)

    per_ticker_diag: List[Dict[str, Any]] = []
    weight_sets_to_write: List[Tuple[str, WeightSet]] = []

    for ticker in sorted(trades_by_ticker.keys()):
        tk_train, tk_val, tk_test = walk_forward_split(trades_by_ticker[ticker], cfg, fold)
        ws, reason, dlog = fit_ticker(
            ticker, tk_train, tk_val, tk_test, cfg, fold_label, vix_daily=vix_daily,
        )
        status = "confident" if ws is not None else "pooled"
        dlog["status"] = status
        per_ticker_diag.append(dlog)
        if ws is not None:
            weight_sets_to_write.append((f"{ticker}.json", ws))
            log(f"  [OK]   {ticker:<6} C={ws.C}  "
                f"train_pf={dlog['train_pf_net']:.3f}  test_pf={dlog['test_pf_net']:.3f}  "
                f"(boot p5={dlog['test_pf_bootstrap_p5']:.3f})")
        else:
            log(f"  [FALL] {ticker:<6} -> pooled ({reason})")

    pair_counter: Counter = Counter()
    pair_r_values: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for d in per_ticker_diag:
        for pa, pb, r in d.get("top_3_correlated_pairs", []) or []:
            if abs(r) >= 0.7:
                key = tuple(sorted([pa, pb]))
                pair_counter[key] += 1
                pair_r_values[key].append(r)
    sys_flags = []
    for key, n in pair_counter.most_common():
        if n >= 5:
            median_r = float(np.median(pair_r_values[key]))
            sys_flags.append((key[0], key[1], median_r, n))

    severe = [(a, b, r, n) for (a, b, r, n) in sys_flags if abs(r) >= 0.9]
    if len(severe) > 5:
        msg = (
            f"[STOP] severe multicollinearity: {len(severe)} pairs system-wide "
            f"have |r| >= 0.9. Investigate before writing weights.\n"
            + "\n".join(f"  - {a} <-> {b}  r={r:.3f}  n_tickers={n}" for a, b, r, n in severe)
        )
        log(msg)
        return {
            "fold_label": fold_label,
            "fit_at": datetime.now().isoformat(timespec="seconds"),
            "halted_reason": "severe_multicollinearity",
            "system_wide_corr_flags": sys_flags,
            "pooled": pooled_diag,
            "per_ticker": per_ticker_diag,
        }

    aggregate_test_pf = float(pooled_diag["test_pf_net"])
    log(f"[aggregate] pooled-on-all test PF (net) = {aggregate_test_pf:.3f}")

    if aggregate_test_pf < 1.20:
        log(f"[STOP] aggregate pooled test PF {aggregate_test_pf:.3f} < 1.20 — "
            "below v1 baseline. Investigate before writing weights.")
        return {
            "fold_label": fold_label,
            "fit_at": datetime.now().isoformat(timespec="seconds"),
            "halted_reason": "aggregate_test_pf_below_1.20",
            "system_wide_corr_flags": sys_flags,
            "pooled": pooled_diag,
            "per_ticker": per_ticker_diag,
        }

    n_pooled_fallback = sum(1 for d in per_ticker_diag if d["status"] == "pooled")
    log(f"[note] {n_pooled_fallback}/57 tickers fell back to pooled.")

    over_cap = [d for d in per_ticker_diag if d.get("max_abs_coef", 0) > 5.0]
    if over_cap:
        log(f"[STOP] {len(over_cap)} tickers have |coef| > 5.0 after L2. Regularization broken.")
        return {
            "fold_label": fold_label,
            "fit_at": datetime.now().isoformat(timespec="seconds"),
            "halted_reason": "coef_over_cap",
            "over_cap_tickers": [d["ticker"] for d in over_cap],
            "system_wide_corr_flags": sys_flags,
            "pooled": pooled_diag,
            "per_ticker": per_ticker_diag,
        }

    if not dry_run:
        weights_dir.mkdir(parents=True, exist_ok=True)
        save_weight_set(pooled_ws, weights_dir / POOLED_FILENAME)
        log(f"[write] {POOLED_FILENAME}")
        for filename, ws in weight_sets_to_write:
            save_weight_set(ws, weights_dir / filename)
            log(f"[write] {filename}")

    return {
        "fold_label": fold_label,
        "fit_at": datetime.now().isoformat(timespec="seconds"),
        "n_trades_train": len(train),
        "n_trades_val": len(val),
        "n_trades_test": len(test),
        "pooled": pooled_diag,
        "per_ticker": per_ticker_diag,
        "system_wide_corr_flags": sys_flags,
        "dry_run": dry_run,
    }
