# EDGE.md — What Actually Works in Markets (Evidence Dossier)

> **Purpose.** A primary-source-verified survey of what genuinely produces
> profit in public equity markets, commissioned to answer one question:
> *is there a real, durable edge we can capture — and is our current
> single-name swing-prediction system one of them?*
>
> **Verdict up front:** Our system (predict whether one liquid stock rises
> over ~2 weeks from technicals) is **not** an edge — our own test shows
> AUC 0.51 / negative IC, exactly what the literature predicts. Real,
> surviving edges are either **diversified-and-small** (combined factors,
> 2–5 pp/yr) or **structural-and-manual** (spin-offs, micro-caps — where a
> small account size is an advantage over institutions).
>
> **Research method.** Parallel research agents pulled academic papers,
> regulator disclosures, and live fund/ETF records; one agent downloaded the
> Ken French Data Library and computed factor returns directly. Every number
> below is flagged verified / secondary-source / unverified. Compiled 2026-07-10.

---

## 0. Terminology

- **pp/yr** = percentage points per year — the *gap* between two returns, not a
  return. If the S&P returns 10% and you return 13%, your edge is **3 pp/yr**
  (10% → 13%, flat addition — not 10%×1.03).
- **Why a 2–5 pp/yr edge matters:** on $100k, 3 pp/yr = +$3,000/yr, but
  compounded over 20 years it turns ~$672k (index @10%) into ~$1.15M (@13%) —
  it nearly doubles ending wealth. Nobody sustains 30 pp/yr; a durable
  2–5 pp/yr is the honest, life-changing target.
- **Long-short vs long-only:** academic "factor premiums" are long-short
  (buy winners, short losers). Live retail products (ETFs) are long-only and
  carry ~50%+ market beta. A long-only ETF beating the index says little about
  whether the underlying long-short premium survived.
- **IC** (information coefficient) = rank correlation between a signal's
  prediction and realized forward return. ~0 = no skill.

---

## 1. Do full-time / retail traders actually make money? — Mostly NO

| Population | Result | Source |
|---|---|---|
| Brazil day traders — all 19,646 who started 2013–15 | Of the 1,551 who lasted 300+ days: **97% lost money**; 1.1% beat minimum wage; 0.5% out-earned a bank teller | Chague, De-Losso & Giovannetti, [SSRN 3423101](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3423101) (2020) |
| Taiwan, complete exchange records, ~450k day traders/yr, 1992–2006 | **<1% (~4,000) reliably profitable** after fees. Top 500 earned +37.9bp/day net, persistently | Barber, Lee, Liu & Odean, [J. Financial Markets 2014](https://faculty.haas.berkeley.edu/odean/papers/day%20traders/The%20Cross-Section%20of%20Speculator%20Skill.pdf) |
| Taiwan, all individuals, 1995–99 | Individuals lose **3.8 pp/yr**; aggregate losses = **2.2% of Taiwan's GDP**; institutions gain +1.5 pp | [Review of Financial Studies 22(2), 2009](https://faculty.haas.berkeley.edu/odean/papers%20current%20versions/justhowmuchdoindividualinvestorslose_rfs_2009.pdf) |
| EU/UK retail CFD accounts (regulator-mandated disclosure) | **51–89% lose money** (eToro 51%, IG 69%, Plus500 ~76–80% as of 2026) | [ESMA 2018](https://www.esma.europa.eu/press-news/esma-news/esma-agrees-prohibit-binary-options-and-restrict-cfds-protect-retail-investors), [FCA CP16/40](https://www.fca.org.uk/publications/consultation-papers/cp16-40-enhancing-conduct-firms-contract-difference-products-retail-clients) |
| US households — 66,465 discount-broker accounts, 1991–96 | Highest-turnover quintile underperformed market by **6.5 pp/yr**; more trading → lower returns | Barber & Odean, [J. Finance 2000](https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00226) |
| Robinhood herding, 2018–2020 | Most intensely herd-bought stocks did **−4.7% over next 20 days** — retail attention is a *fade* signal | Barber, Huang, Odean & Schwarz, [J. Finance 2022](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.13183) |
| Retail options, Nov 2019–Jun 2021 | Retail lost **$2.1B**, paying 12.6% avg spreads on weeklies | Bryzgalova, Pavlova & Sikorskaya, [J. Finance 2023](https://onlinelibrary.wiley.com/doi/full/10.1111/jofi.13285) |

**Takeaway.** The 97% are the product, not the players. Skill exists (Taiwan's
top 0.1%, persistently +38bp/day) but it came from high-frequency
market-making/liquidity provision — **not** chart-reading or single-name
direction bets. The winners are not doing what "trading" is imagined to be.

---

## 2. Our own system, in this context

LightGBM on **corrected** continuous features (Wilder-smoothed RSI/ADX/ATR/Stoch),
purged walk-forward, Jansen-style evaluation:

- Pooled OOS **AUC 0.5085** (0.50 = no skill)
- **IC −0.08** (slightly *negative* — confidence anti-correlated with outcome)
- Decile lift **not monotone**; collapsed to AUC 0.446 in the most recent fold

Fixing the broken indicators **changed nothing**. The ceiling was never the
features — **single-name ~2-week direction from technicals is unpredictable**,
exactly as the retail-loss studies above and the factor literature below predict.

---

## 3. Classic factors — decay is real, but they don't vanish

**Anchor:** McLean & Pontiff ([J. Finance 2016](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12365)) —
97 published predictors shrink **26% out-of-sample, 58% post-publication**
(the ~32pp gap = publication/arbitrage effect). But **Jensen-Kelly-Pedersen
([J. Finance 2023](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.13249)):
82% of 153 factors replicate** across 93 countries. Smaller, not dead.
Jacobs & Müller ([JFE 2020](https://www.sciencedirect.com/science/article/abs/pii/S0304405X19301618)):
post-publication decay is reliably present **only in the US** (most arbitrage capital).

### Fama-French factor returns, computed directly from Ken French data (vintage May 2026)

| Year | Mkt-RF | SMB | HML | RMW (quality) | CMA | UMD (mom) |
|---|---|---|---|---|---|---|
| 2020 | +23.65 | +3.74 | **−46.94** | −5.21 | −11.70 | +7.36 |
| 2021 | +23.87 | −1.02 | **+25.61** | **+26.72** | +11.67 | −2.34 |
| 2022 | −21.28 | −1.59 | **+25.68** | +6.61 | **+22.50** | +15.98 |
| 2023 | +21.75 | −6.28 | −13.97 | +6.18 | −20.59 | **−24.26** |
| 2024 | +19.78 | −13.48 | −8.44 | +5.08 | −9.74 | **+19.76** |
| 2025 | +13.30 | −9.53 | +9.23 | −11.30 | −5.31 | −2.06 |
| 2026 YTD (May) | +9.2 | +2.2 | +6.6 | −11.0 | +1.4 | **+19.9** |

### Per-factor verdict (live long-only ETFs = the honest test)

| Factor | Live product | Verdict |
|---|---|---|
| **Momentum** | MTUM: ~16.4%/yr vs 13.4% S&P since 2013 | **Beat index long-only.** But long-short UMD down to ~2-3%/yr; **crashed −83.8% in 2009** (crashes come from the short side in post-panic rebounds — Daniel & Moskowitz, [JFE 2016](https://www.kentdaniel.net/papers/published/jfe_16.pdf)) |
| **Value (small) + quality** | AVUV: ~16%/yr vs 11.4% S&P since 2019 | **Beat index.** Small-value with profitability screen is the strongest live long-only |
| **Value (large)** | VLUE: lagged since 2013 | Survived −58% drawdown (2007→2020), then +26%/+26% in 2021-22. Regime-dependent; AQR & Arnott publicly predicted the rebound at 4σ spreads |
| **Quality** | QUAL: ≈ market since 2013 | Essentially a **wash** live — index-hugger. Best *survivor* in factor data (+27% cum. 2020-25) but long-only captured little |
| **Low-vol** | USMV: 10.1% vs 15.6% SPY over decade | **Lagged −5.5 pp/yr.** Defense only (did protect in 2022). Academic claim is risk-adjusted, not raw return; critics say it's a sector/rates bet |
| **Size** | — | **Dead.** Long-short negative over 44 years (−7.3% cum. since 1982). Alquist-Israel-Moskowitz: no reliable standalone premium |
| **Trend-following** | DBMF/KMLM/AQMIX | **Crisis insurance, not alpha.** +21% to +35% in 2022 while stocks & bonds fell; gives it back in calm years. AQR "Century of Evidence": positive every decade since 1880 |

### The real lesson: combine, don't isolate
AQR's *multifactor market-neutral* funds (momentum + value + quality together):
**+17.6% (2021), +27.2% (2022), +17.1% (2023), +25.3% (2024)** — QMNIX, four
consecutive exceptional years, uncorrelated to the market
([Bloomberg](https://www.bloomberg.com/news/articles/2023-01-06/aqr-s-longest-running-fund-has-a-record-year-posting-43-5-gain),
[CNBC](https://www.cnbc.com/2024/01/04/cliff-asness-aqr-absolute-return-fund-returns-18point5percent-in-2023-boosted-by-value-picks.html)).
Single factors are weak and streaky; **combination is where the money was.**

---

## 4. Sentiment / Reddit / news — a trap for retail

| Claim | Reality |
|---|---|
| WSB posts predict returns | True (+5%/qtr) **only until GameStop (Jan 2021)**, then predictability *eliminated* — Bradley et al., [RFS 2024](https://academic.oup.com/rfs/advance-article-abstract/doi/10.1093/rfs/hhad098/7486572) |
| Mention/attention spikes = buy signal | They predict **reversal, not continuation** — a *fade* signal (Huang & Shum Nolan, [SSRN 4384743](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4384743)) |
| Sentiment ETF | **BUZZ underperformed SPY by ~5-6 pp/yr** for 5 years — the live, audited test of the thesis, and it failed |
| "Twitter predicts the Dow" (Bollen 2011) | **Failed replication** (data snooping); Derwent Capital (Twitter hedge fund) **died in <1 year**, assets auctioned for £120k |
| News sentiment (RavenPack) | Edge decays in minutes–hours (HFT latency game retail can't win); slow residual lives in illiquid names where spreads eat it. Data is institutional-priced anyway |
| "Lazy Prices" — 10-K/10-Q language changes | Real backtest (30–188bp/mo, [J. Finance 2020](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12885)); free EDGAR data, slow horizon — **but** published/known, no verified live retail record |
| Open-source Reddit sentiment bots | **Zero** with verified live P&L. All backtest or vibes |

**Takeaway.** The only sentiment signal retail can cheaply see (mention spikes)
is contrarian. If sentiment enters a system at all, it's as an **avoid/fade
filter**, never a buy trigger.

---

## 5. Non-ML edges — where structure protects a small account

| Edge | Verdict | Notes |
|---|---|---|
| **Micro-cap deep value / special situations** | **REAL (strongest case)** | 65–82% of anomalies concentrate in microcaps institutions can't touch (Hou-Xue-Zhang). Momentum capacity ~$5B; a retail account is 4-5 orders of magnitude below — the institutional cost objection doesn't bind. Graham net-nets: 20-34%/yr in various samples. Price: illiquid, lumpy, labor-intensive |
| **Spin-offs** | **REAL** | ~10%/yr excess over 50 years (Cusatis et al., Purdue extension); Bloomberg spinoff index beat S&P by ~38pp since 2020. Mechanism = **forced selling** by index funds/mandate-constrained holders — structural, can't be arbitraged by the people forced to sell. Requires reading Form 10s |
| **Odd-lot tenders** | **REAL, tiny** | Hold ≤99 shares, tender without proration; ~18% on capital per deal but a few hundred $ each. Uninvestable beyond 99 shares |
| **Insider cluster-buys** (opportunistic, small firms) | **Weak-real overlay** | Cohen-Malloy-Pomorski: 82bp/mo pre-decay; ~half survives. Form 4s public within 2 days. Use as a screen, not a system |
| **SPAC-below-trust arb (2020–22)** | **WAS real, now CLOSED** | 9–24% annualized, near-riskless; the archetype of an episodic structural edge that opened and closed. Illustrates that real retail edges are temporary |
| **Merger arb** | Diversifier, not alpha | MERFX 7.5%/yr since 1989 but only ~3-4%/yr last decade; genuinely uncorrelated cash-plus |
| **Covered calls / put-selling (VRP)** | **Weak** | Higher Sharpe 1986–2018 (PUT 9.54% vs 9.80% S&P at lower vol) but lower CAGR since; BXM 8.4% vs 10.9% S&P long-run. De-risking tool, not an edge |
| **Trend timing (GTAA/GEM)** | **Weak** | Live GTAA ETF: **4.95% vs 11.64%** buy-and-hold, then closed 2017. Crash insurance that costs return |
| **Congress-following (NANC/KRUZ)** | **Weak** | ~+1.2pp/yr unadjusted, but it's levered mega-cap-tech beta; no factor-adjusted alpha; 0.75% fee, 45-day disclosure lag |
| **PEAD (earnings drift)** | **DEAD** in tradeable stocks | Gone from large caps by ~2006 (decimalization/HFT); residual sits in illiquid names where costs eat it. **This kills "Bit 4" as originally planned** |
| **Index inclusion** | **DEAD** | Addition pop 7.4% (1990s) → 1.0% insignificant (2010s) — Greenwood & Sammon, [J. Finance 2025](https://onlinelibrary.wiley.com/doi/10.1111/jofi.13410) |
| **Calendar effects** (turn-of-month, January, Sell-in-May) | **DEAD/weak** net of costs & taxes in the US last decade |

---

## 6. Synthesis & recommendation

**The meta-rule:** *anything easy to automate on liquid stocks is dead by
construction* — publication + index funds arbitraged it away. Surviving edges
are either **diversified-and-small** (combined factors, a few pp/yr) or
**structural-and-manual** (spin-offs, micro-caps — where illiquidity IS the moat
and a small account is an advantage).

**Realistic edge ceiling for a retail account: 2–5 pp/yr over the index**, with
discipline. Anyone promising more is selling a course.

### Proposed three-sleeve approach (all buildable on our existing honest backtester)

1. **Core (most capital): index fund.** SPY beat our system (+103% vs +65%) on
   zero effort. This is the verified baseline, not a concession.
2. **Systematic sleeve: monthly multifactor ranker** over our 269-name universe —
   **momentum (12-1) × quality filter**, hold top 15–20, rebalance monthly.
   Honest expected edge 2–4 pp/yr; testable against our purged backtester.
   Reuses everything already built.
3. **Manual sleeve (optional, where size is the edge): spin-offs + insider
   cluster-buys.** A watchlist/alert system, not a model — flag every announced
   spin-off and Form-4 cluster buy; human decides. This is where the +10%/yr-class
   structural edges live, and they can't be automated away because the edge *is*
   the illiquidity.

### Explicitly ruled out by this research
- Single-name daily/swing direction prediction from technicals (our current system)
- Sentiment/Reddit as a *buy* signal
- Standalone size factor; PEAD in liquid stocks; index-inclusion; calendar effects
- Trend timing / options income as *alpha* (fine as risk-shaping only)

---

## 7. Key citations
McLean-Pontiff [SSRN 2156623](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2156623) ·
Jensen-Kelly-Pedersen [J. Finance 2023](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.13249) ·
Jacobs-Müller [JFE 2020](https://www.sciencedirect.com/science/article/abs/pii/S0304405X19301618) ·
Daniel-Moskowitz [JFE 2016](https://www.kentdaniel.net/papers/published/jfe_16.pdf) ·
Arnott et al. value [FAJ 2021](https://www.tandfonline.com/doi/full/10.1080/0015198X.2020.1842704) ·
AQR "Is Systematic Value Investing Dead?" [SSRN 3554267](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3554267) ·
AQR "Century of Evidence on Trend-Following" [SSRN 2993026](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2993026) ·
Alquist-Israel-Moskowitz size [AQR](https://www.aqr.com/-/media/AQR/Documents/Whitepapers/Fact-Fiction-and-the-Size-Effect.pdf) ·
Chague et al. Brazil [SSRN 3423101](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3423101) ·
Barber-Lee-Liu-Odean Taiwan skill [PDF](https://faculty.haas.berkeley.edu/odean/papers/day%20traders/The%20Cross-Section%20of%20Speculator%20Skill.pdf) ·
Barber-Odean "Trading Is Hazardous" [J. Finance 2000](https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00226) ·
Barber et al. Robinhood [J. Finance 2022](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.13183) ·
Bradley et al. WSB [RFS 2024](https://academic.oup.com/rfs/advance-article-abstract/doi/10.1093/rfs/hhad098/7486572) ·
Cohen-Malloy-Nguyen "Lazy Prices" [J. Finance 2020](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12885) ·
Greenwood-Sammon index inclusion [J. Finance 2025](https://onlinelibrary.wiley.com/doi/10.1111/jofi.13410) ·
Hou-Xue-Zhang replication [RFS 2020](https://academic.oup.com/rfs/advance-article/doi/10.1093/rfs/hhy131/5236964) ·
Ken French Data Library (factor returns computed directly, vintage May 2026)

*Numbers flagged unverified in the raw research (not independently confirmed to the decimal): momentum-specific M-P decay row; exact long-run UMD/HML/QMJ premia; the −73% 2009 decile-WML figure; AQR century-paper 0.76 gross Sharpe; VLUE precise numbers; exact BUZZ cumulative gap; Robeco per-year fund alphas. Directions and orders of magnitude are robust across sources.*
