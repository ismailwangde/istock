"""Forward-logging: record scores (weekly) and prices (daily) so we can later
measure whether the analyzer's quality_score actually predicts returns.
Survivorship-free & lookahead-free by construction (we log as-of today).

Usage:
    python snapshot.py prices     # daily  — fast batch price log
    python snapshot.py scores     # weekly — full analyze() score log

Universe = watchlist.txt (editable) UNION the S&P 500 (toggle below).
A ticker added to watchlist.txt simply starts appearing from its first run.
"""
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
LOGS = ROOT / "logs"
WATCHLIST = ROOT / "watchlist.txt"
TRACK_SP500 = True     # set False to log ONLY your watchlist (faster)
_YF_CACHE = ROOT / ".yf_cache"   # isolated cache dir (fixes launchd sqlite locks)


def _already_logged(path, today):
    """True if today's date already appears in the log (keeps RunAtLoad / same-day
    reruns idempotent — one row-set per date)."""
    if not path.exists():
        return False
    try:
        return today in set(pd.read_csv(path, usecols=["date"])["date"].astype(str))
    except Exception:
        return False


def _setup_yf():
    """Point yfinance's tz cache at an isolated, writable dir. Under launchd the
    default cache path is often unreachable/contended, which surfaces as the
    'unable to open database file' errors that half-failed our runs."""
    import yfinance as yf
    try:
        _YF_CACHE.mkdir(parents=True, exist_ok=True)
        yf.set_tz_cache_location(str(_YF_CACHE))
    except Exception as e:
        print(f"[warn] could not set yf cache location: {e}")
    return yf


def universe():
    tks = []
    if WATCHLIST.exists():
        for line in WATCHLIST.read_text().splitlines():
            line = line.split("#")[0].strip().upper()
            if line:
                tks.append(line)
    if TRACK_SP500:
        try:
            from analyzer.peers import sp500_constituents
            tks += list(sp500_constituents()["ticker"])
        except Exception as e:
            print(f"[warn] S&P list unavailable: {e}")
    # dedupe, preserve order
    seen, out = set(), []
    for t in tks:
        if t not in seen:
            seen.add(t); out.append(t)
    return out


def _download_closes(tks, chunk=100, retries=2):
    """Latest close per ticker, fetched in chunks with retry+throttle so one
    flaky batch can't wipe the whole run. Returns {ticker: close}."""
    yf = _setup_yf()
    closes = {}
    for i in range(0, len(tks), chunk):
        batch = tks[i:i + chunk]
        for attempt in range(retries + 1):
            try:
                df = yf.download(batch, period="2d", progress=False,
                                 auto_adjust=False, threads=False)
                if df is None or df.empty:
                    raise ValueError("empty frame")
                close = df["Close"] if "Close" in df else df
                latest = close.iloc[-1]
                if isinstance(latest, pd.Series):          # multi-ticker batch
                    for t in latest.index:
                        if pd.notna(latest[t]):
                            closes[t] = round(float(latest[t]), 4)
                else:                                       # single-ticker batch
                    if pd.notna(latest):
                        closes[batch[0]] = round(float(latest), 4)
                break
            except Exception as e:
                if attempt < retries:
                    time.sleep(2 * (attempt + 1))
                else:
                    print(f"[warn] batch {i}-{i + len(batch)} failed: {e}")
        time.sleep(0.5)   # gentle throttle between batches
    return closes


def log_prices():
    """Robust batch daily close for the whole universe -> logs/prices.csv."""
    tks = universe()
    LOGS.mkdir(exist_ok=True)
    today = date.today().isoformat()
    path = LOGS / "prices.csv"
    if _already_logged(path, today):
        print(f"[prices] {today}: already logged — skipping.")
        return
    closes = _download_closes(tks)

    # guard: don't pollute the log with a near-empty (fetch-failed) day
    if TRACK_SP500 and len(closes) < max(50, 0.5 * len(tks)):
        print(f"[prices] {today}: ONLY {len(closes)}/{len(tks)} fetched — likely a "
              f"fetch failure. Skipping write; will retry next run.")
        return

    rows = [{"date": today, "ticker": t, "close": c} for t, c in closes.items()]
    out = pd.DataFrame(rows)
    path = LOGS / "prices.csv"
    out.to_csv(path, mode="a", header=not path.exists(), index=False)
    print(f"[prices] {today}: logged {len(out)}/{len(tks)} closes -> {path}")


def log_scores():
    """Full analyze() score for each name -> logs/scores.csv (weekly)."""
    from analyzer import analyze
    _setup_yf()                       # isolated cache for the analyzer's fetches too
    tks = universe()
    LOGS.mkdir(exist_ok=True)
    today = date.today().isoformat()
    if _already_logged(LOGS / "scores.csv", today):
        print(f"[scores] {today}: already logged — skipping.")
        return
    rows = []
    for i, t in enumerate(tks):
        try:
            r = analyze(t, write=False, include_news=False)
            if r.get("error"):
                continue
            price = (r.get("valuation", {}).get("multiples", {}) or {})
            rows.append({
                "date": today, "ticker": t,
                "sector": r["classification"]["type"],
                "quality_score": r["quality_score"],
                "verdict": r["verdict"],
                "forensic": r["forensic"]["verdict"],
                "solvency": r["solvency"]["verdict"],
                "n_flags": len(r["all_flags"]),
            })
        except Exception as e:
            print(f"  skip {t}: {e}")
        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(tks)}] scored")
    out = pd.DataFrame(rows)
    path = LOGS / "scores.csv"
    out.to_csv(path, mode="a", header=not path.exists(), index=False)
    print(f"[scores] {today}: logged {len(out)} scores -> {path}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "prices"
    if mode == "prices":
        log_prices()
    elif mode == "scores":
        log_scores()
    else:
        print("usage: python snapshot.py [prices|scores]")
