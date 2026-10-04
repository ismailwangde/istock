"""Data layer: fetch + normalize a company's financials from yfinance (free).

Everything downstream reads from the normalized `CompanyData` object so the
metric modules never touch yfinance's messy row labels directly. If a line item
is missing we return NaN and let the metric decide how to degrade.

Statements come back with columns = period-end dates (most recent first). We
keep up to 5 annual periods so we can measure TREND, which the framework insists
matters more than any single year.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


def _row(df: Optional[pd.DataFrame], *names: str) -> pd.Series:
    """First matching row from a statement as a float Series (NaN if absent).
    Tries each candidate label in order (yfinance labels drift)."""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    for n in names:
        if n in df.index:
            return pd.to_numeric(df.loc[n], errors="coerce")
    return pd.Series(dtype=float)


@dataclass
class CompanyData:
    ticker: str
    info: dict = field(default_factory=dict)
    income: pd.DataFrame = field(default_factory=pd.DataFrame)
    balance: pd.DataFrame = field(default_factory=pd.DataFrame)
    cashflow: pd.DataFrame = field(default_factory=pd.DataFrame)
    price: pd.DataFrame = field(default_factory=pd.DataFrame)
    insider_purchases: pd.DataFrame = field(default_factory=pd.DataFrame)
    insider_transactions: pd.DataFrame = field(default_factory=pd.DataFrame)
    major_holders: pd.DataFrame = field(default_factory=pd.DataFrame)

    # ---- convenience accessors (each returns a period-indexed Series) ----
    def rev(self):       return _row(self.income, "Total Revenue", "Operating Revenue")
    def cogs(self):      return _row(self.income, "Cost Of Revenue", "Reconciled Cost Of Revenue")
    def gross(self):     return _row(self.income, "Gross Profit")
    def ebit(self):      return _row(self.income, "EBIT", "Operating Income")
    def ebitda(self):    return _row(self.income, "EBITDA", "Normalized EBITDA")
    def net_income(self):return _row(self.income, "Net Income", "Net Income Common Stockholders")
    def interest_exp(self): return _row(self.income, "Interest Expense", "Interest Expense Non Operating").abs()
    def tax(self):       return _row(self.income, "Tax Provision")
    def pretax(self):    return _row(self.income, "Pretax Income")
    def sga(self):       return _row(self.income, "Selling General And Administration")
    def dep_inc(self):   return _row(self.income, "Reconciled Depreciation")
    def dil_shares(self):return _row(self.income, "Diluted Average Shares", "Basic Average Shares")

    def assets(self):    return _row(self.balance, "Total Assets")
    def cur_assets(self):return _row(self.balance, "Current Assets")
    def cur_liab(self):  return _row(self.balance, "Current Liabilities")
    def receivables(self): return _row(self.balance, "Accounts Receivable", "Receivables")
    def inventory(self): return _row(self.balance, "Inventory")
    def ppe_net(self):   return _row(self.balance, "Net PPE")
    def cur_ppe_gross(self): return _row(self.balance, "Gross PPE")
    def total_debt(self):return _row(self.balance, "Total Debt")
    def net_debt(self):  return _row(self.balance, "Net Debt")
    def cash(self):      return _row(self.balance, "Cash And Cash Equivalents",
                                     "Cash Cash Equivalents And Short Term Investments")
    def equity(self):    return _row(self.balance, "Stockholders Equity", "Common Stock Equity")
    def retained(self):  return _row(self.balance, "Retained Earnings")
    def working_cap(self): return _row(self.balance, "Working Capital")
    def invested_cap(self): return _row(self.balance, "Invested Capital")
    def total_liab(self): return _row(self.balance, "Total Liabilities Net Minority Interest")
    def cur_ltd(self):   return _row(self.balance, "Long Term Debt")

    def ocf(self):       return _row(self.cashflow, "Operating Cash Flow",
                                     "Cash Flow From Continuing Operating Activities")
    def capex(self):     return _row(self.cashflow, "Capital Expenditure").abs()
    def fcf(self):       return _row(self.cashflow, "Free Cash Flow")
    def dep_cf(self):    return _row(self.cashflow, "Depreciation Amortization Depletion",
                                     "Depreciation And Amortization")
    def sbc(self):       return _row(self.cashflow, "Stock Based Compensation")
    def dividends(self): return _row(self.cashflow, "Cash Dividends Paid").abs()
    def buybacks(self):  return _row(self.cashflow, "Repurchase Of Capital Stock").abs()

    @property
    def market_cap(self):
        return self.info.get("marketCap", np.nan)

    @property
    def sector(self):
        return self.info.get("sector", "Unknown")

    @property
    def industry(self):
        return self.info.get("industry", "Unknown")

    @property
    def n_periods(self):
        return self.income.shape[1] if not self.income.empty else 0


def fetch(ticker: str) -> CompanyData:
    """Pull annual statements + info + recent price for one ticker."""
    import yfinance as yf
    t = yf.Ticker(ticker)
    try:
        info = t.info or {}
    except Exception:
        info = {}
    try:
        price = t.history(period="1y", interval="1d")
    except Exception:
        price = pd.DataFrame()
    return CompanyData(
        ticker=ticker.upper(),
        info=info,
        income=_safe(t, "income_stmt"),
        balance=_safe(t, "balance_sheet"),
        cashflow=_safe(t, "cashflow"),
        price=price,
        insider_purchases=_safe(t, "insider_purchases"),
        insider_transactions=_safe(t, "insider_transactions"),
        major_holders=_safe(t, "major_holders"),
    )


def _safe(t, attr) -> pd.DataFrame:
    try:
        df = getattr(t, attr)
        return df if df is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()
