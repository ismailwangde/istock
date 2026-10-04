# NEXT_STEPS.md — Roadmap (updated 2026-07-11)

> Context: the original single-name swing predictor has no predictive skill
> (OOS AUC 0.51, IV of all 38 features < 0.005 = "useless"). The pivot to
> cross-sectional momentum ranking is now **validated survivorship-free**.
> Full evidence dossier: [EDGE.md](EDGE.md).

---

## ⚠️ SLEEVE 2 — DOWNGRADED after pre-registered stress test (2026-07-13).
##    It is a MOMENTUM-FACTOR BET, not standalone alpha. Not "FINAL".

The 2018–2026 QC result (+13.5 pp/yr, −51.6% DD) stands as data, but the
stress test (pre-registration: results/analysis/stress_test_preregistration.md)
failed the conjunction:

1. **Through-cycle (French CRSP momentum deciles, survivorship-free, 1999–2026,
   incl. 2000-02 & 2008-09):** long-only top decile edge is **+3.5 pp/yr VW**
   (+4.7 EW), beat market 17/28 years. 2009: **−18.9 pp** (long-only version of
   the momentum crash); 2021: −28.9 pp. Sub-windows: 1999-2009 +3.0, 2010-17
   +1.7, 2018-26 +5.9. → The +13.5 was concentration (top-20) × the friendliest
   momentum regime in the sample. EDGE.md's 2-5 pp/yr ceiling CONFIRMED.
2. **Alpha vs UMD:** French decile alpha after Mkt+UMD control: **−0.6%/yr
   (t=−0.32) — DEAD** (R²=0.83, UMD beta 0.6). Local sleeve: +6.0%/yr but
   t=1.25 (n.s., and survivor-inflated). **FAILS the t>2 requirement.**
   The sleeve = market beta 1.3–1.4 + UMD beta 0.6–0.7 in a wrapper.
3. **Risk-matched levered SPY (2018-26, financing RF+1%):** vol-matched 2.06×
   → 24.4%; maxDD-matched 2.35× → 26.4% vs sleeve 27.5%. **Effectively a tie**
   in the sleeve's own best regime.
4. **After-tax (35% ST, taxable):** turnover ~360%/yr one-way → all gains
   short-term. Sleeve 27.5% → ~17.9% after tax vs SPY B&H ~13.5%. Edge shrinks
   to ~4 pp in the best regime; **through-cycle (+3.5 pre-tax) it goes ≈ NEGATIVE
   after tax**. In taxable accounts the DIY sleeve loses to buy-and-hold.

**What survives, honestly stated:**
- Momentum factor exposure is real through-cycle (+3.5 pp/yr, 17/28 years) —
  but it is FACTOR BETA, cheaply available via **MTUM (0.15% fee)**, which also
  avoids personal tax drag (ETF in-kind redemptions). A DIY top-20 sleeve adds
  concentration risk and tax cost without significant alpha beyond UMD.
- If wanted at all: small satellite position, tax-advantaged account only,
  sized to survive a −19 pp relative year (2009) and a −29 pp one (2021).

## ☐ SLEEVE 2 — remaining open items (downgraded priority)
- [ ] Gold-standard confirmation: re-run QC backtest from **1999** (file updated:
      istock/research/qc_momentum_ranker.py). Expect the French-decile picture.
- [ ] If any momentum exposure is kept: decide DIY-in-IRA vs simply buying MTUM.
- [ ] Optional: live paper-trade continues as a learning exercise, not as
      validation of an edge already explained by UMD.

---

## 🟡 SLEEVE 4 — MULTI-FACTOR COMBO (momentum + value + quality). BEST result so far.
##    Pre-reg: results/analysis/multifactor_preregistration.md

Equal 1/3 blend of French survivorship-free top deciles (mom + value(B/M) +
quality(OP)), monthly, NO weight tuning. Through-cycle 1999–2026 (incl. 2000-02,
2008-09):

- CAGR **12.1%** vs market 9.1% → **+3.0 pp/yr**; Sharpe **0.61 vs 0.51**; vol
  18.4% (down from momentum's 22.5%); maxDD −53.9%.
- **First automatable strategy to BEAT risk-matched levered SPY**: vol-matched
  1.17× market = 9.9%, DD-matched 1.10× = 9.6% — combo 12.1% wins by ~+2.2pp.
  (Momentum-alone only TIED levered SPY; the combo genuinely adds something.)
- Diversification thesis VALIDATED in momentum's crash years: 2000 mom −22.3 →
  combo −2.9; 2009 mom +9.7 → combo +24.5; 2021 mom −5.0 → combo +21.6.
- Beat market 18/28 years.

**Pre-registered scorecard (strict):** ✅ Sharpe>market · ❌ maxDD not shallower
than momentum-alone (−53.9 vs −51.2; value's −69.8% dragged it; a broad crash
sinks ALL equity factors, so maxDD was arguably the wrong diversification metric)
· ✅ beats risk-matched leverage. Conjunction fails on the drawdown letter, but
the diversification benefit is real in volatility/Sharpe and in the crash years.

**Caveats (stay sober):** +2.3pp vs market has t≈1.94 (borderline, not bulletproof);
no protection in broad crashes (−54% in 2008-type events); still honest-sized
(~3pp), in EDGE.md's 2-5pp band. Surprise: QUALITY alone was the best single
sleeve (Sharpe 0.65, maxDD −41.2%).

**Implementation (buyable, tax-efficient — the actual recommendation):**
- ☐ 1/3 **MTUM** + 1/3 **VLUE** (or VTV) + 1/3 **QUAL**, or a single multifactor
  ETF (e.g. LRGF). Rebalance ~quarterly. 2/3 (value+quality) turns over slowly;
  ETF in-kind redemptions shed almost no taxable gains → fixes the tax problem
  that killed DIY momentum.
- ☐ Optional worth-a-look: QUAL-heavy tilt given its standout single-sleeve
  risk-adjusted numbers (do NOT overfit to it — it's one 27-yr sample).

## ☐ SLEEVE 3 (MANUAL, where small-account size is the edge)
- [ ] **Spin-off tracker**: flag announced US spin-offs (Form 10 filings; forced
      index-fund selling is the edge; ~10%/yr excess over 50 yrs, +38pp vs S&P
      since 2020). Claude pre-digests filings; human verifies and decides.
- [ ] **Insider cluster-buy alert**: parse Form 4s (EDGAR, free), flag
      opportunistic cluster buys at small firms. Screen overlay, not standalone.

## ☐ Housekeeping
- [ ] Log in MODEL.md §15: LightGBM result (AUC 0.51, IC −0.08 on corrected
      features) + IV/WOE audit (all 38 features "useless") = the features were
      never the problem; single-name short-horizon direction is unpredictable.
- [x] Benchmark bug fixed: factor_ranker now uses SPY total-return (dividends);
      partial trailing months dropped. (Old ^GSPC price-only bar overstated our
      edge by ~1.7 pp/yr.)

---

## ✗ TESTED AND REJECTED (each idea got a fair harness run — don't revisit
##   without NEW data; the harness makes any retest ~10 minutes)

| Idea | Test | Verdict |
|---|---|---|
| Single-name swing prediction (36 features, logistic/LightGBM) | AUC 0.51, IC −0.08; IV all <0.005 | No signal exists at this horizon |
| News sentiment as feature/signal | 3 ways: daily IC (0.007), event drift, 21d-trailing rank (−2.2 edge at short holds) | Dead. Priced in seconds; long-horizon "signal" is momentum in disguise |
| React-to-news / react-to-earnings trading | Event studies: reaction complete by next close (±0.25%) | Retail is structurally last in line |
| Textbook technical events (golden cross, RSI, MACD...) as triggers | Unconditional event study, every day every ticker | Best event +0.35%/21d < 0.6% costs; ALL bearish signals fail (stocks rise after them) |
| Jump-chain count as ranking signal | Standalone: −38% DD, dies in bear years. As tiebreak: +0.5pp = noise | Chains ARE momentum; redundant. Mechanism insight kept: drift = slow herd |
| Frog-in-the-pan (smooth risers better) | mom→smooth tiebreak | 0/9 years vs baseline in our universe |
| Recency-weighted event-accumulator score (decayed sum of all events + news) | Standalone: −0.2 edge (= the market). As tiebreak: DEGRADES momentum +16.2→+5.7 | Price already accumulates all events, weighted by real money. Hand-built copies are noise |
| LSTM / sequence models | Declined by design: 27k samples, S/N ~0.05 → memorizes noise (Gu-Kelly-Xiu: NN gains marginal, micro-caps only) | Recency intuition tested via recency_w signal instead: jagged curve, not robust |
| Per-ticker models | ~85 independent trades/ticker vs 36 features | Mathematically hopeless; pooled only |
| PEAD/earnings-drift feature ("Bit 4") | Literature verified | Dead in tradeable stocks since ~2006 |
| Hourly-data training | yfinance caps hourly at ~730 days; features have no daily signal to begin with | Not pursued |
| Sleeve 2 as standalone alpha ("+13.5 pp/yr") | Pre-registered stress test: French CRSP deciles 1999-2026 + Mkt/UMD regression + levered-SPY baseline | FAILED. Through-cycle edge +3.5pp/yr; alpha after UMD control −0.6%/yr (t=−0.32); ties 2.35× SPY; ≈negative after tax through-cycle. It's UMD factor beta — buy MTUM if wanted |
| ML sector rotation + 2-stage stock ranking (LightGBM, 11 SPDR sectors → top-3, top-5 stocks each, weekly) | Rank IC 0.022 (real but thin), 30× annual turnover, 9.1%/yr cost drag | Net 11.4% CAGR vs SPY 15.3% and vs plain momentum top-15 36.3%. Following the model's top-3 SECTORS returned 0.4% CAGR — actively harmful. Confirms "easy to automate on liquid stocks = dead" |

## Key numbers to remember
- Realistic momentum edge, honest THROUGH-CYCLE data (French CRSP 1999-2026):
  **+3.5 pp/yr** (VW top decile), with −19 to −29 pp relative-loss years.
  The QC +13.5 (2018-26) was concentration × best-ever regime; MTUM live: +2.2.
- 2026 illustration ($2,000, Jan→Jun, survivor universe — inflated, illustrative
  only): momentum $4,334 (+117%) vs SPY $2,202 (+10%).
- Survivorship inflation in local backtests: ~5–13 pp/yr. Always compare shapes
  and ranks locally; trust levels only from QC / live records.
