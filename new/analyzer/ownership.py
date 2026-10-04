"""Ownership, insiders & short interest (framework §9). The ⭐robust signal is
opportunistic CLUSTER insider buying (many insiders buying, not routine grants).
Insider SELLING is deliberately down-weighted (many benign reasons)."""
from __future__ import annotations

import numpy as np

from .data import CompanyData


def _num(df, col, row_label=None, row_idx=None):
    try:
        if row_label is not None:
            r = df[df.iloc[:, 0] == row_label]
            return float(r[col].iloc[0])
        return float(df[col].iloc[row_idx])
    except Exception:
        return np.nan


def run_ownership(c: CompanyData) -> dict:
    info = c.info
    out = {"flags": [], "signals": []}

    # --- insider 6-month net activity + cluster detection ---
    ip = c.insider_purchases
    net_shares = purch_trans = sale_trans = np.nan
    if ip is not None and not ip.empty and "Insider Purchases Last 6m" in ip.columns:
        def find(label):
            r = ip[ip["Insider Purchases Last 6m"] == label]
            if r.empty:
                return np.nan, np.nan
            shares = _f(r["Shares"].iloc[0]) if "Shares" in ip.columns else np.nan
            trans = _f(r["Trans"].iloc[0]) if "Trans" in ip.columns else np.nan
            return shares, trans
        net_shares, _ = find("Net Shares Purchased (Sold)")
        _, purch_trans = find("Purchases")
        _, sale_trans = find("Sales")

    out["insider_net_shares_6m"] = None if np.isnan(net_shares) else int(net_shares)
    out["insider_buy_transactions_6m"] = None if np.isnan(purch_trans) else int(purch_trans)
    out["insider_sell_transactions_6m"] = None if np.isnan(sale_trans) else int(sale_trans)

    # cluster buy: multiple distinct insiders buying + net positive
    distinct_buyers = _distinct_buyers(c.insider_transactions)
    out["distinct_insider_buyers_recent"] = distinct_buyers
    if not np.isnan(net_shares) and net_shares > 0 and distinct_buyers >= 3:
        out["signals"].append(f"Cluster insider buying: {distinct_buyers} distinct buyers, net positive (⭐ robust signal)")
    elif not np.isnan(net_shares) and net_shares > 0:
        out["signals"].append("Net insider buying (mild positive)")

    # --- ownership structure ---
    out["insider_pct_held"] = _pct(info.get("heldPercentInsiders"))
    out["institution_pct_held"] = _pct(info.get("heldPercentInstitutions"))

    # --- short interest ---
    sp = info.get("shortPercentOfFloat")
    out["short_pct_float"] = _pct(sp)
    out["short_ratio_days"] = info.get("shortRatio")
    if sp is not None and sp > 0.10:
        out["flags"].append(f"High short interest {sp*100:.1f}% of float (bearish bets or squeeze fuel)")

    out["note"] = ("insider CLUSTER buying is the robust signal; insider selling is "
                   "down-weighted (taxes/diversification). 13F/short data is stale/context.")
    return out


def _distinct_buyers(txns):
    if txns is None or txns.empty or "Text" not in txns.columns or "Insider" not in txns.columns:
        return 0
    try:
        buys = txns[txns["Text"].str.contains("Purchase|Buy", case=False, na=False)]
        return int(buys["Insider"].nunique())
    except Exception:
        return 0


def _pct(x):
    try:
        return None if x is None else round(float(x) * 100, 1)
    except Exception:
        return None


def _f(x):
    try:
        import pandas as pd
        if x is None or pd.isna(x):
            return np.nan
        return float(x)
    except Exception:
        return np.nan
