"""CLI: python run.py AAPL [MSFT ...]  — analyze one or more tickers."""
import sys

from analyzer import analyze
from analyzer.report import to_markdown

if __name__ == "__main__":
    tickers = sys.argv[1:] or ["AAPL"]
    for tk in tickers:
        r = analyze(tk)
        if r.get("error"):
            print(f"{tk}: {r['error']}")
            continue
        print(to_markdown(r))
        print("\n" + "=" * 70 + "\n")
