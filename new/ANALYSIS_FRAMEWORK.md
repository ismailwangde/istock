# Master Equity Analysis Framework

> A machine-usable due-diligence checklist for analyzing **any** publicly traded
> company. Synthesizes the process used by value investors (Buffett, Munger,
> Lynch), distressed/credit (Marks), valuation (Damodaran), quant funds, and
> sell-side equity research.
>
> **How to read priority tags:** `[C]` Critical (never skip), `[I]` Important,
> `[N]` Nice-to-have. **Honest-edge tags** reflect what is empirically robust vs.
> decorative (grounded in this repo's own tests + the academic record):
> `⭐ robust` · `➖ weak/context-only` · `☠️ near-zero predictive power`.
>
> **Meta-rule that overrides everything:** almost no single metric predicts
> returns out-of-sample. Value comes from (a) the *conjunction* of many
> confirming signals, (b) *trend* of a metric over 3–5 years, not its latest
> point, and (c) *industry-relative* comparison, never absolute. A number in
> isolation is noise. See §17 (cross-metric traps) — that is where real analysis
> lives.

---

## PART 0 — HOW AN AI SHOULD USE THIS

1. **Classify the company first** — sector, sub-industry, business model
   (asset-light SaaS vs. capital-intensive utility vs. bank vs. commodity vs.
   biotech pre-revenue). *Every threshold below is industry-conditional.* Banks
   and insurers need an entirely separate statement model (no revenue/COGS; use
   NIM, efficiency ratio, loan-loss provisions, Tier-1 capital, book value).
2. **Establish the investment thesis type** — is this a value, quality-compounder,
   growth, turnaround, cyclical, or deep-distressed case? The weighting of
   categories changes (see §18).
3. **Pull the data** (see per-category sources), compute the metrics, then
   **evaluate trend (5–10y), industry-relative percentile, and cross-metric
   consistency** — not raw values.
4. **Score each category, weight by thesis type, and produce a red-flag list**
   before any buy/hold/avoid verdict.
5. **Always run the forensic/earnings-quality screen (§2E) as a gate** — a
   company that fails accounting-integrity checks is un-analyzable; stop.

---

## PART 1 — BUSINESS & QUALITATIVE (the moat)

*The most important and least quantifiable layer. Buffett/Munger/Lynch weight
this above all financials. Data sources: 10-K (Item 1 Business, Item 1A Risk),
earnings calls, investor days, industry reports, customer reviews, expert
networks (Tegus, AlphaSense). Frequency: annual, revisited each earnings.
Trend matters more than snapshot; qualitative.*

| Factor | Why it matters | Prio | What "good" looks like | Pitfall / misleading when |
|---|---|---|---|---|
| **Business model durability** | Will this exist & earn in 10y? | [C] | Recurring revenue, essential product, low obsolescence | Tech disruption invisible until sudden |
| **Economic moat (type)** | Sustains excess returns (ROIC>WACC) | [C] | Identify which: network effects, switching costs, cost advantage, intangibles/brand, efficient scale | "Moat" narratives with no ROIC evidence |
| **Moat direction (widening/narrowing)** | Moats decay | [C] | Gross-margin & market-share trend rising or stable | Peak-moat right before disruption |
| **Pricing power** | Ability to raise price w/o volume loss = inflation defense, margin durability | [C] | Price increases stick; gross margin stable/rising through cycles | Commodity businesses have none; masked by mix |
| **Switching costs** | Locks in customers → recurring rev, low churn | [I] | High integration, data lock-in, retraining cost | Low in undifferentiated software |
| **Brand strength** | Pricing power + demand durability | [I] | Premium pricing vs peers, unaided awareness | Brand ≠ moat if no repeat purchase |
| **Network effects** | Value rises with users; winner-take-most | [I] | 2-sided marketplaces, platforms | Fake/one-sided "networks" |
| **Customer concentration** | Revenue fragility | [C] | No customer >10% of revenue | 10-K discloses; >20% single customer = red flag |
| **Supplier concentration** | Input/cost fragility | [I] | Diversified, substitutable suppliers | Single-source components |
| **TAM & runway** | Growth ceiling | [I] | Large, growing, under-penetrated | TAM inflation in pitches |
| **Unit economics** | Does the core transaction make money? | [C] | LTV/CAC > 3, payback < 24mo, positive contribution margin | "Growth" masking negative unit economics |
| **Innovation capability / R&D productivity** | Future moat | [I] | R&D → new revenue, patent quality, product cadence | R&D spend ≠ R&D output |
| **Regulatory exposure** | Existential/margin risk | [C] | Low regulatory dependence; not one-ruling-from-ruin | Pharma, fintech, tobacco, utilities |
| **Geographic/political risk** | Expropriation, FX, sanctions | [I] | Diversified, rule-of-law jurisdictions | EM concentration, single-country |
| **Cyclicality / demand elasticity** | Earnings stability | [I] | Non-discretionary demand | Cyclical peak earnings look "cheap" |
| **Key-person dependence** | Fragility to founder/CEO exit | [N] | Deep bench, institutionalized | Founder-cult with no succession |

---

## PART 2 — FINANCIAL STATEMENT ANALYSIS

*Source: 10-K/10-Q (SEC EDGAR, free), or aggregators (stockanalysis.com,
Koyfin, FMP, Bloomberg, S&P CapitalIQ). Frequency: quarterly. **Always pull
5–10 years** — trend and consistency dominate any single quarter. Restate for
one-offs.*

### 2A. Income Statement
| Metric | Formula | Prio | Ideal / interpret | Pitfall |
|---|---|---|---|---|
| Revenue & 3/5/10y CAGR | — | [C] | Consistent > lumpy; organic > acquired | M&A-inflated "growth" |
| Revenue quality (organic vs acquired vs FX vs price/volume) | decompose | [C] | Price+volume organic | One-time price hikes |
| Gross margin & trend | (Rev−COGS)/Rev | [C] | Stable/rising = pricing power | Mix shift, capitalized costs |
| Operating margin (EBIT) | EBIT/Rev | [C] | Rising with scale | Adjusted-EBIT games |
| Net margin | NI/Rev | [I] | Industry-relative | Tax/one-off distortion |
| SG&A / R&D as % rev (operating leverage) | — | [I] | Falling % as rev grows | Under-investment masquerading as leverage |
| EPS & EPS growth | NI/shares | [I] | Growth from ops, not buybacks | See §17 buyback trap |
| Share count trend (diluted) | — | [C] | Flat/falling | SBC dilution creeping up |

### 2B. Balance Sheet
| Metric | Formula | Prio | Ideal | Pitfall |
|---|---|---|---|---|
| Cash & equivalents | — | [I] | Ample vs. debt maturities | Trapped foreign cash |
| Total debt & net debt | Debt − cash | [C] | Manageable vs EBITDA/FCF | Off-balance-sheet/leases |
| Debt maturity ladder | — | [I] | Staggered, no near wall | Refi risk in high-rate regime |
| Goodwill & intangibles % assets | — | [I] | Low; watch for impairments | Serial-acquirer goodwill bombs |
| Working capital & trend | CA−CL | [I] | Efficient, stable | Rising receivables/inventory = demand cracks |
| Book value / tangible book | Equity − intangibles | [I] | Relevant for financials/asset-heavy | Meaningless for asset-light |
| Deferred revenue trend | — | [I] | Rising = demand (SaaS) | — |

### 2C. Liquidity & Solvency
| Metric | Formula | Prio | Threshold (industry-adj.) | High/Low |
|---|---|---|---|---|
| Current ratio | CA/CL | [I] | ~1.5–3 (tech ~1.5, retail lower ok) | <1 liquidity stress; >3 idle assets |
| Quick ratio | (CA−inv)/CL | [I] | ≥1 | Excludes inventory |
| Debt/Equity | TotalDebt/Equity | [C] | Tech ~0.4; utilities 2–3 ok | High = fragility OR leverage-boosted ROE |
| Net debt / EBITDA | — | [C] | <3 generally; <1 strong | >4–5 danger (ex-utilities) |
| Interest coverage | EBIT/Interest | [C] | >5 safe; >8 strong | <2 distress; tech ~65x |
| Altman Z-score | multivariate | [I] | **>3 safe; <1.8 bankruptcy risk** | Manufacturing-calibrated; use Z" for others |

### 2D. Cash Flow (often the most honest statement)
| Metric | Formula | Prio | Ideal | Pitfall |
|---|---|---|---|---|
| Operating cash flow (OCF) & trend | — | [C] | Rising, > net income | — |
| Free cash flow (FCF) | OCF − capex | [C] | Positive, growing, converts | Capex-light this year, catch-up later |
| FCF margin | FCF/Rev | [I] | >10% strong | — |
| FCF conversion | FCF/NI | [C] | ~100%+ | <70% = earnings quality flag |
| Cash conversion cycle | DSO+DIO−DPO | [I] | Low/negative (Amazon) | Stretching payables to fake it |
| Capex intensity | capex/rev | [I] | Low for compounders | Maintenance vs growth capex split |
| SBC as % of OCF | — | [I] | Low | SBC add-back inflates "adjusted" FCF |

### 2E. EARNINGS QUALITY / FORENSIC (GATE — run first) ⭐
*The single highest-ROI screen. A failure here invalidates everything else.*
| Metric | Formula / threshold | Prio | Interpretation |
|---|---|---|---|
| **Sloan accruals ratio** ⭐ | (NI − OCF)/avg assets | [C] | High accruals → earnings won't persist; **low-accrual firms outperform** (Sloan anomaly, one of the most robust) |
| **Beneish M-score** ⭐ | 8-var; **> −1.89 = likely manipulator** | [C] | TATA (accruals) is the dominant term; caught Enron ex-ante |
| **Piotroski F-score** ⭐ | 9 binary criteria; **8–9 strong, 0–2 weak** | [I] | Works best on cheap/small value stocks |
| Cash-flow vs net-income divergence | OCF ≥ NI over time | [C] | Persistent NI>OCF = aggressive accrual |
| Days sales outstanding (DSO) trend | AR/rev×365 | [I] | Rising fast = channel stuffing / demand pull-forward |
| Inventory trend vs sales | — | [I] | Inventory > sales growth = demand cracking |
| Tax rate anomalies | effective vs statutory | [N] | Sudden drops flatter EPS |
| Non-GAAP vs GAAP gap | — | [I] | Widening gap = adjustment abuse |
| Auditor changes / restatements / late filings | 8-K | [C] | Any = major red flag |
| Related-party transactions | 10-K notes | [I] | Governance/fraud risk |

---

## PART 3 — PROFITABILITY & RETURNS ON CAPITAL

*The core of quality investing. Source: financials. Trend > snapshot;
industry-adjust heavily.*

| Metric | Formula | Prio | Threshold | High/Low interpretation | Pitfall |
|---|---|---|---|---|---|
| **ROIC** ⭐ | NOPAT/InvestedCapital | [C] | >WACC (creates value); retail median ~16%, mfg ~11%, utility ~6% | Sustained ROIC>WACC = moat | Goodwill deflates it; leases; a flat "15% good" lies across sectors |
| ROIC − WACC (economic spread) | — | [C] | Positive & widening | The single best moat proxy | WACC estimation is fuzzy |
| **ROE** | NI/Equity | [I] | Buffett: >15% sustained | 15–20%+ = good business | **Inflated by leverage/buybacks — decompose!** (§17) |
| ROA | NI/Assets | [I] | >5% (ex-financials) | Removes leverage distortion | Asset-light inflates it |
| DuPont decomposition ⭐ | ROE = margin × turnover × leverage | [C] | Know WHICH driver | Reveals leverage-driven ROE | — |
| CROIC / cash ROIC | FCF/InvestedCapital | [I] | Positive, high | Cash version, harder to fake | — |
| Incremental ROIC | ΔNOPAT/Δinvested capital | [I] | High = reinvestment moat | Best forward compounding signal | Noisy year-to-year |
| Gross profitability | GrossProfit/Assets | [I] | High (Novy-Marx: predicts returns) ⭐ | Robust quality factor | — |

---

## PART 4 — GROWTH ANALYSIS

| Metric | Prio | Ideal | Pitfall |
|---|---|---|---|
| Revenue growth (organic, 3/5/10y) | [C] | Consistent, decelerating gracefully | Acquired/FX growth |
| EPS growth (and its *source*) | [I] | From revenue+margin, not buybacks | §17 buyback trap |
| FCF growth | [C] | Tracks or exceeds earnings | Growth w/o FCF = red flag |
| Growth durability / deceleration curve | [I] | Long runway | Law of large numbers |
| Reinvestment rate × ROIC = intrinsic growth | [I] | High-quality growth | Growth funded by dilution/debt |
| Same-store / cohort / net revenue retention (NRR) | [I] | NRR >110% (SaaS) | Vanity metrics |
| PEG ratio | [N] | <1 cheap growth | Fragile for cyclicals/negative earnings |
| Rule of 40 (SaaS: growth% + FCF margin%) | [I] | ≥40 | — |

---

## PART 5 — CAPITAL ALLOCATION & DIVIDENDS

*Munger/Buffett: the CEO's #1 job. Look at a decade of decisions. Source:
cash-flow statement financing section, proxy, buyback announcements.*

| Factor | Prio | Good | Bad / pitfall |
|---|---|---|---|
| Capital-allocation track record | [C] | Reinvests at high ROIC; buys back when cheap | Empire-building M&A, buybacks at highs |
| M&A discipline & ROI on deals | [C] | Accretive, integrated | Serial overpayer, goodwill impairments |
| Buyback quality (price paid vs value) | [I] | Below intrinsic value, reduces share count | Buying high to offset SBC (fake reduction) |
| Dividend policy sustainability | [I] | Payout <60% FCF, growing | Payout >100% FCF = cut coming |
| Dividend history / streak | [N] | Aristocrat consistency | Dividend held while borrowing to pay it |
| Reinvestment vs return-of-capital balance | [I] | Matches opportunity set | Returning cash when high-ROIC options exist (or vice-versa) |
| Insider/management incentive alignment | [I] | Comp tied to ROIC/FCF/per-share value | Comp tied to revenue/size/adjusted-EPS |

### Dividend-specific metrics
| Metric | Formula | Threshold | Pitfall |
|---|---|---|---|
| Dividend yield | DPS/price | Sector-relative | High yield = distress signal (yield trap) |
| Payout ratio (of FCF, not EPS) | Div/FCF | <60% | EPS-based hides the truth |
| Dividend growth rate | — | Steady | Recent cut history |
| Coverage | FCF/Div | >1.5x | <1 unsustainable |

---

## PART 6 — VALUATION

*No metric is "cheap" or "expensive" absolutely — only vs. history, peers,
growth, and quality. Damodaran: story → drivers → value. Source: financials +
market price. Update: price daily, fundamentals quarterly.*

### 6A. Multiples (relative valuation)
| Multiple | Best for | Prio | Interpretation | Pitfall |
|---|---|---|---|---|
| P/E (trailing & forward) | profitable, stable | [I] | Low vs history/peers/growth | Meaningless if earnings volatile/negative; cyclical peak = low P/E trap |
| EV/EBITDA | cross-capital-structure compare | [C] | Neutralizes leverage/D&A | Ignores capex (bad for capital-heavy) |
| EV/EBIT | capital-intensive | [I] | Includes D&A | — |
| EV/Sales | unprofitable/high-growth | [I] | Only if margins will come | Justifies bubbles |
| EV/FCF & FCF yield | quality/compounders ⭐ | [C] | FCF yield >5% attractive | Capex timing distorts |
| P/B | banks, asset-heavy | [I] | <1 = below liquidation (or value trap) | Useless for asset-light |
| P/S | early growth | [N] | — | No profit anchor |
| PEG | growth | [N] | <1 | Unstable inputs |
| Shiller CAPE (index-level) | market timing | [N] | Weak timing signal | Terrible timing precision |
| Dividend discount model | mature payers/financials | [N] | — | Sensitive to assumptions |

### 6B. Intrinsic valuation
| Method | Prio | Notes / pitfall |
|---|---|---|
| **DCF (2-stage FCFF/FCFE)** | [C] | Garbage-in-garbage-out; terminal value = ~70% of value; test sensitivity to WACC & g |
| **Reverse DCF** ⭐ | [C] | Best tool: solve for the growth the *price* implies, then judge if realistic. Cuts through narrative |
| Sum-of-the-parts (SOTP) | [I] | Conglomerates, hidden assets |
| Residual income / EVA | [I] | Ties value to ROIC−WACC spread |
| Replacement value / liquidation (NAV) | [I] | Distressed, asset-heavy, net-nets |
| Scenario/Monte-Carlo (bull/base/bear) | [I] | Range > point estimate; assign probabilities |
| Margin of safety | [C] | Buy < intrinsic by 20–50%; the core risk control |

---

## PART 7 — RISK ANALYSIS

| Risk type | How to assess | Prio |
|---|---|---|
| Financial/leverage risk | net debt/EBITDA, coverage, maturity wall, covenant headroom | [C] |
| Liquidity/refinancing risk | debt maturities vs FCF, in high-rate regime | [C] |
| Business/operating risk | operating leverage, fixed-cost base, cyclicality | [I] |
| Customer/supplier concentration | 10-K | [C] |
| Regulatory/litigation risk | 10-K Item 3, legal proceedings, 8-K | [C] |
| FX/currency exposure | % foreign revenue vs cost, hedging | [I] |
| Commodity/input-cost exposure | — | [I] |
| Technological disruption risk | qualitative | [C] |
| Governance/fraud risk | §2E + §10 | [C] |
| Concentration/single-point-of-failure | one product/geo/customer | [I] |
| Beta & volatility | vs market (quant risk) | [N] |
| Tail risk / drawdown history | max historical drawdown | [I] |
| Short-thesis stress test | actively argue the bear case | [C] |

---

## PART 8 — INDUSTRY & COMPETITIVE ANALYSIS

*Porter's Five Forces + structure. Source: industry reports (IBISWorld,
Gartner), 10-K, trade data.*

| Dimension | What to check | Prio |
|---|---|---|
| Industry growth & stage | secular growth vs mature vs declining | [C] |
| Porter: threat of new entrants | barriers to entry | [I] |
| Porter: supplier power | input concentration | [I] |
| Porter: buyer power | customer concentration, price sensitivity | [I] |
| Porter: substitutes | alternative solutions | [I] |
| Porter: rivalry | fragmentation, price wars, capacity | [I] |
| Market share & trend ⭐ | gaining/losing share = moat direction | [C] |
| Industry profitability (avg ROIC) | is the pond fishable? | [I] |
| Cyclicality & position in cycle | early/mid/late | [I] |
| Regulation & policy trajectory | tailwind/headwind | [I] |
| Value-chain position & margin pool | where the profit sits | [I] |
| Disruption vectors | tech, business-model shifts | [C] |

---

## PART 9 — OWNERSHIP, INSIDERS & INSTITUTIONAL SIGNALS

*Source: SEC 13F (quarterly, 45-day lag), 13D/G (activist), Form 4 (insiders,
2-day lag), NPORT (funds), short-interest (biweekly, exchanges/FINRA).*

| Signal | Source | Prio | Interpretation | Pitfall / honest-edge |
|---|---|---|---|---|
| **Insider buying (opportunistic cluster)** ⭐ | Form 4 | [I] | Cluster buys at small firms predict returns (~82bp/mo pre-decay) | Routine buys = noise; **only non-routine cluster buys**; decayed post-publication |
| Insider selling | Form 4 | [N] | Weak signal — many benign reasons (taxes, diversification) | ☠️ selling ≠ bearish |
| Institutional ownership % & trend | 13F | [N] | Rising smart-money holding | 45-day stale; herding |
| Activist/13D filings | 13D | [I] | Catalyst potential | — |
| Hedge-fund "cloning" (super-investor holdings) | 13F | [N] | Idea generation only | Stale, no sell-side |
| Mutual fund / ETF ownership & flows | NPORT, flow data | [N] | Passive flow pressure | — |
| **Short interest % float** | exchange | [I] | High = bearish bets OR squeeze fuel | Structural (arb/convertible) shorts mislead |
| Days-to-cover (short ratio) | SI/avg vol | [I] | High = squeeze potential | — |
| Short-squeeze setup | high SI + low float + catalyst + rising | [N] | Speculative | ☠️ not investable systematically |
| Cost-to-borrow / utilization | securities-lending data | [I] | High = crowded short | — |
| Share buyback execution | 10-Q | [I] | Real float reduction | Offsetting SBC only (§17) |
| Dilution / SBC / secondary issuance | cash-flow, 8-K | [C] | Share count rising = value leak | Serial issuers |

---

## PART 10 — EARNINGS & ANALYST SIGNALS

*Source: consensus (Visible Alpha, FactSet, Refinitiv, yfinance for basic),
transcripts (AlphaSense, Tikr), company IR.*

| Signal | Prio | Interpretation | Honest-edge / pitfall |
|---|---|---|---|
| Earnings surprise history (SUE) | [I] | Consistent beats = execution or sandbagging | PEAD largely arbitraged out of liquid large-caps since ~2006 ➖ |
| **Analyst estimate revisions (direction/breadth)** ⭐ | [I] | Rising revisions → drift up (one of the more durable signals) | Needs estimate data; decays |
| Guidance (given? raised/cut? beat-and-raise?) | [C] | Raise = confidence | Sandbagging; guidance withdrawal = red flag |
| Forward estimates & implied growth | [I] | Feed into reverse-DCF | Consensus herds/lags |
| Consensus dispersion | [N] | Wide = uncertainty/opportunity | — |
| Earnings-call tone/sentiment (NLP) | [N] | Management confidence, hedging language, "Lazy Prices" 10-K text-change signal ⭐(slow-horizon) | ☠️ headline sentiment near-zero at daily horizon (this repo's test); text-*change* > text-*level* |
| Quality of beat (revenue vs one-off/tax) | [C] | Ops-driven beats matter | Low-quality beats fade |
| Whisper number vs consensus | [N] | Real expectation bar | Unofficial |

---

## PART 11 — SENTIMENT, NEWS & ALTERNATIVE DATA

*Honest framing from this repo's own tests: news/social sentiment as a **buy
signal is near-zero to negative** at retail-accessible horizons — the edge is a
seconds-latency game HFT wins, and attention spikes predict mean-reversion.
Treat this whole section as **context and risk-flagging, not alpha**, except the
slow-horizon fundamental-text signals.*

### 11A. News & events
| Signal | Prio | Use | Honest-edge |
|---|---|---|---|
| Material news classification (M&A, product, partnership, exec change, legal, gov action) | [I] | Event/catalyst mapping, thesis update | Priced in fast ☠️ as a trade trigger |
| Litigation / regulatory actions | [C] | Risk flag | — |
| Acquisitions/divestitures | [I] | Capital-allocation read | — |
| Executive/board changes | [I] | Governance/strategy shift | — |
| Government/policy actions | [I] | Sector re-rating | — |

### 11B. Sentiment
| Signal | Source | Prio | Honest-edge |
|---|---|---|---|
| News sentiment (NLP) | RavenPack, Bloomberg | [N] | Decays in minutes; ☠️ retail |
| Social sentiment (Reddit/X/StockTwits) | scrapers | [N] | ☠️ predicts *reversal*; use as **fade/avoid** filter only |
| Options-implied sentiment | see §12B | [I] | Positioning, not direction |
| Analyst sentiment (rating changes) | consensus | [N] | Lagging |

### 11C. Alternative data (institutional; expensive but leading)
*Used by >90% of systematic funds; leads reported financials. Sources:
Similarweb (web), data.ai/Sensor Tower/AppFigures (apps), Bloomberg Second
Measure/Earnest/YipitData (card panels), Thinknum/Revelio (hiring), Orbital
Insight/Planet Labs (satellite), Google Trends (free).*

| Data type | Predicts | Prio | Cost/pitfall |
|---|---|---|---|
| Credit-card / transaction panels ⭐ | revenue ahead of print | [I] (inst.) | $$$; panel bias, coverage drift |
| Web traffic (Similarweb) | digital-business demand | [I] | free-ish; proxy only |
| App downloads/DAU/MAU | consumer app revenue | [I] | store-level noise |
| Hiring / job postings (Revelio, Thinknum) | expansion/contraction, margin | [I] | lagged, noisy |
| Patent filings / R&D output | innovation pipeline | [N] | long lead time |
| Google Trends (free) | consumer interest/brand | [N] | correlation, not causation |
| Satellite (parking lots, oil tanks, crops) | physical activity | [N] | $$$$; weather/seasonality |
| Product reviews / app ratings | product health, churn | [N] | manipulation |
| Supply-chain / shipping / customs | demand, input flows | [N] | — |

---

## PART 12 — TECHNICAL ANALYSIS

*Honest framing (this repo proved it): single-name daily/weekly technical signals
have **~zero out-of-sample predictive power** (AUC ~0.51; every indicator's
Information Value <0.005). Use technicals for **execution/timing and risk
management, not stock selection**. The one price-based signal with a real (if
modest, ~2–4pp/yr) through-cycle edge is **cross-sectional relative-strength
momentum** — and it's a portfolio/ranking tool, not a single-stock predictor.
Source: price/volume feeds. Update: intraday–daily.*

### 12A. Indicators (execution/context only)
| Tool | What it shows | Prio | Interpretation | Honest-edge |
|---|---|---|---|---|
| **Relative strength / 12-1 momentum** ⭐ | trend vs market/peers | [I] | Rank tool; top decile drifts up | ⭐ the only robust one — cross-sectional, monthly |
| Trend (structure of highs/lows) | direction | [I] | HH/HL up, LH/LL down | ➖ context |
| Moving averages (50/200, golden/death cross) | trend/regime | [N] | Price>200MA = uptrend regime | ➖ death cross fails on equities |
| Support & resistance | levels | [N] | Entry/exit zones | self-fulfilling, subjective |
| RSI (14) | momentum/OB-OS | [N] | >70 OB, <30 OS | ☠️ mean-reversion unreliable single-name |
| MACD | momentum crossovers | [N] | Bull/bear cross | ☠️ lagging |
| ADX | trend *strength* | [N] | >25 trending | filter, not direction |
| Bollinger Bands | volatility/mean-rev | [N] | squeeze → breakout | — |
| ATR | volatility (position sizing/stops) ⭐ | [I] | Stop distance, risk sizing | genuinely useful for risk, not direction |
| VWAP | intraday fair value (execution) | [N] | institutions use for fills | intraday only |
| Volume profile / volume analysis | conviction, liquidity | [N] | volume confirms moves | — |
| Fibonacci retracement | pullback zones | [N] | 38.2/50/61.8% | ☠️ numerology |
| Candlestick patterns | short reversal cues | [N] | — | ☠️ no edge net of costs |
| Breakouts / market structure | regime change | [N] | new-high breakouts | many false breaks |
| 52-week high proximity | momentum proxy | [N] | near-high drifts up mildly ➖ | — |

### 12B. Options-derived technicals (positioning)
| Signal | Prio | Interpretation |
|---|---|---|
| Put/call ratio (vol & OI) | [I] | Falling P/C + rising calls = bullish; extreme = contrarian |
| Implied volatility (IV) & IV rank/percentile | [I] | High IV = fear/event; sell-vol vs buy-vol context |
| **25-delta skew / risk reversal** | [I] | Steep put skew = downside fear; widens before catalysts |
| IV term structure | [I] | Backwardation = near-term event risk (earnings) |
| Gamma exposure (GEX) / gamma flip | [N] | Positive-gamma dampens vol; below flip = amplified swings |
| Max pain | [N] | Weak pin tendency near expiry |
| Unusual options activity | [N] | Possible informed flow — or noise |

---

## PART 13 — CREDIT MARKET INDICATORS

*Credit markets often lead equity; distress shows here first. Source: bond
quotes, CDS (where available), FRED for spreads.*

| Signal | Prio | Interpretation |
|---|---|---|
| Credit rating & outlook (Moody's/S&P/Fitch) | [I] | IG vs HY; downgrade watch |
| Credit spread (issuer bond vs treasury) & trend | [I] | Widening = rising default risk (leads equity down) |
| CDS spread (if traded) | [I] | Real-time default-risk pricing |
| Bond price vs par | [I] | Distressed <70c = equity often near-zero |
| Cost/availability of financing | [I] | Refi risk |
| Altman Z / distress models | [I] | See §2C |
| Covenant headroom | [I] | Breach → forced actions |
| **Market-wide credit spreads (HY OAS)** | [I] | Macro risk-appetite gauge (see §14) |

---

## PART 14 — MACRO & MARKET-WIDE INDICATORS

*Top-down context; sets the discount rate and risk appetite for ALL equities.
Source: FRED (free), BLS, central banks, CBOE. Frequency varies (daily→monthly).
Regime context, not stock selection.*

| Indicator | What it drives | Prio | Interpretation |
|---|---|---|---|
| **Interest rates / policy rate & path** | discount rate → ALL valuations | [C] | Rising rates compress multiples (esp. long-duration/growth) |
| **Yield curve (10y-2y, 10y-3m)** | recession signal | [I] | Inversion → recession lead (12–18mo) |
| Real yields (10y TIPS) | valuation of long-duration assets | [I] | Rising real yields hit growth stocks (the 2022 story) |
| **Inflation (CPI/PCE)** | rates, margins, real returns | [C] | Erodes real returns; drives Fed |
| **VIX** | equity fear/volatility regime | [I] | >20 stress, >30 fear; spikes = capitulation (contrarian) |
| GDP growth & nowcasts | cyclical demand | [I] | Recession = cyclical earnings risk |
| **PMI (ISM mfg/services)** | leading activity | [I] | <50 contraction |
| Unemployment & jobless claims | consumer health, Fed | [I] | Rising claims lead downturns |
| Consumer confidence / retail sales | discretionary demand | [N] | — |
| **HY credit spreads (OAS)** | risk appetite | [I] | Widening = risk-off |
| Dollar index (DXY) | multinational earnings, EM, commodities | [I] | Strong USD hurts US multinationals & EM |
| Oil / energy prices | input costs, inflation, energy sector | [I] | — |
| Commodity prices (copper "Dr. Copper", ags) | cyclical demand, input costs | [N] | — |
| M2 / liquidity / central-bank balance sheet | asset-price tailwind/headwind | [N] | — |
| Sector rotation / breadth (adv-decline, % >200MA) | market internals | [N] | Deteriorating breadth = fragility |

---

## PART 15 — QUANTITATIVE / FACTOR SCORES

*The academically-validated return factors. Honest note: premia are real
long-run but **decay ~50% post-publication** (McLean-Pontiff) and endure
5–15y droughts. Best used **combined** (multi-factor), cross-sectionally, as a
ranking overlay. Source: computed from fundamentals+price.*

| Factor | Proxy metrics | Prio | Honest-edge | Style |
|---|---|---|---|---|
| **Value** | low EV/EBIT, P/B, P/FCF, high earnings/FCF yield | [I] | Real, regime-dependent; deep drawdown 2010-20 then rebound | Value/quant |
| **Momentum (12-1)** ⭐ | trailing 12-1m relative return | [I] | Most robust; ~3.5pp/yr through-cycle; crashes post-panic (2009 −84%) | Momentum/quant |
| **Quality** ⭐ | high ROIC, gross profitability, low accruals, stable margins, low debt | [I] | Best 2010s+ survivor; combines well | Quality/quant |
| **Low volatility / low beta** | realized/idiosyncratic vol | [N] | Risk-adjusted edge; lags raw bull markets | Defensive/quant |
| **Size (small-cap)** | market cap | [N] | ➖ weak standalone; ~dead since 1981; works via *interaction* (small×value×quality) | — |
| **Profitability/investment (Fama-French)** | RMW, CMA | [I] | Real; part of 5-factor | Quant |
| Composite multi-factor score ⭐ | rank-combine value+quality+momentum | [I] | Combination smooths single-factor droughts (AQR) | Quant |
| Piotroski F / Beneish M / Altman Z | see §2E | [I] | Quality/forensic overlays | Value/quant |

---

## PART 16 — ESG (OPTIONAL / RISK-LENS)

*Treat as risk-management and long-tail factor, not alpha. Data quality is poor
and ratings disagree wildly across providers. Source: MSCI/Sustainalytics/ISS,
company sustainability reports.*

| Factor | Prio | Use |
|---|---|---|
| Governance (the "G" — most financially material) ⭐ | [I] | Overlaps §10; board quality, incentives, accounting integrity actually predict risk |
| Environmental liabilities / transition risk | [N] | Stranded-asset, regulatory, litigation risk |
| Social / labor / supply-chain / controversy risk | [N] | Headline/boycott/regulatory risk |
| Carbon intensity / regulatory exposure | [N] | Sector-dependent (energy, utilities, materials) |
| ESG rating & controversy flags | [N] | Ratings disagree — verify underlying, don't trust the score |

---

## PART 17 — CROSS-METRIC RELATIONSHIPS & RED-FLAG TRAPS

*This is where real analysis happens — no metric is read alone. An AI must run
these consistency checks and surface contradictions.*

| Trap | What to check | What it reveals |
|---|---|---|
| **High ROE from leverage** | DuPont: is ROE from margin/turnover or equity multiplier? | Fragile, not quality |
| **Revenue growth without FCF** | rev↑ but FCF flat/negative | Growth is unprofitable or working-capital-funded |
| **EPS growth only from buybacks** | EPS↑ but net income flat & share count↓ | No operational growth |
| **Buybacks offsetting SBC** | share count flat despite buybacks | "Return" is really employee comp |
| **Margin expansion from one-offs** | strip out one-time items, FX, price spikes | Non-repeatable |
| **Earnings > cash flow (accruals)** | NI persistently > OCF; DSO rising | Aggressive/fraudulent accounting (§2E) |
| **Growth funded by dilution/debt** | share count↑ or debt↑ funding growth | Value leaks to financiers |
| **Low P/E cyclical at peak** | earnings at cycle top → optically cheap | Value trap |
| **High yield = distress** | payout>FCF, price falling | Dividend cut coming |
| **ROIC < WACC but "growing"** | growth destroys value | Un-investable compounding of losses |
| **Rising inventory/receivables vs sales** | working-capital bloat | Demand cracking / channel stuffing |
| **Adjusted-EBITDA vs GAAP gap widening** | serial add-backs | Management flattering results |
| **Goodwill > equity** | acquisition-driven balance sheet | Impairment time-bomb |
| **Insider buying + high short interest** | conflicting signals | Deep-dive the disagreement |
| **Multiple expansion, not earnings, driving stock** | decompose return: Δmultiple vs Δearnings | Sentiment-driven, mean-reverts |

---

## PART 18 — STYLE-SPECIFIC WEIGHTING PROFILES

*Which categories each archetype weights heaviest — so the AI can run the lens
the user wants.*

| Style | Heaviest weights | Ignores/underweights |
|---|---|---|
| **Buffett/Munger (quality-compounder)** | Moat (§1), ROIC & spread (§3), capital allocation (§5), owner-earnings/FCF, management integrity, margin of safety | Technicals, macro, short-term sentiment |
| **Graham / deep value** | P/B, net-nets/NAV (§6B), Altman Z, balance-sheet safety, margin of safety | Growth, narrative, moat premium |
| **Lynch (GARP)** | PEG, growth durability (§4), category runway, "invest in what you know," inventory/receivables checks | Deep macro |
| **Damodaran (intrinsic)** | DCF & reverse-DCF (§6B), story-to-number discipline, cost of capital, lifecycle stage | Chart technicals |
| **Howard Marks (credit/cycle)** | Credit spreads (§13), cycle position, downside/second-level thinking, risk (§7) | Momentum |
| **Growth/venture-style** | TAM, NRR, Rule of 40, unit economics, revisions (§10) | Current P/E, dividends |
| **Quant/factor** | §15 factor scores, §2E forensic, momentum, cross-sectional ranking | Qualitative moat narrative |
| **Momentum/trend** | Relative strength/12-1 (§12), earnings revisions, breadth | Valuation, DCF |
| **Activist** | SOTP gap, capital-allocation failures, governance (§9/§16-G), 13D | — |

---

## PART 19 — THE CONSOLIDATED MASTER CHECKLIST (machine-usable)

**Run in this order. Gate at each ⛔ before proceeding.**

**STEP 0 — Classify:** sector, sub-industry, business model, thesis type,
lifecycle stage. Load industry-specific thresholds. (Banks/insurers/REITs/miners/
biotech use specialized models.)

**STEP 1 — ⛔ FORENSIC GATE (§2E):** Beneish M > −1.89? Accruals high? OCF < NI
persistently? Restatements/auditor changes? Rising DSO? → If fails, **STOP: flag
as un-analyzable / high fraud risk.**

**STEP 2 — ⛔ SOLVENCY GATE (§2C, §13):** Net debt/EBITDA, interest coverage,
Altman Z, maturity wall, credit spread trend. → If distressed, switch to
distressed/credit framework.

**STEP 3 — Business & moat (§1):** model durability, moat type & direction,
pricing power, concentration, regulatory risk. Score.

**STEP 4 — Profitability & returns (§3):** ROIC vs WACC (spread & trend), DuPont,
gross profitability, incremental ROIC. Score.

**STEP 5 — Financial statements (§2A-D):** revenue quality, margin trends, FCF
generation & conversion, balance-sheet strength. 5–10y trend. Score.

**STEP 6 — Growth (§4):** organic growth, durability, reinvestment×ROIC, source
of EPS growth. Score.

**STEP 7 — Capital allocation & dividends (§5):** decade track record, M&A
discipline, buyback quality, payout sustainability. Score.

**STEP 8 — Industry & competition (§8):** structure, share trend, cycle position,
disruption. Score.

**STEP 9 — Valuation (§6):** multiples vs history/peers, DCF + **reverse-DCF
reality check**, margin of safety, decompose expected return. Score + target range.

**STEP 10 — Ownership/insiders/earnings signals (§9, §10):** cluster insider
buys, dilution/SBC, short interest, guidance, **estimate revisions**. Score.

**STEP 11 — Risk register (§7):** enumerate all risks; write the explicit **bear
thesis**. Stress test.

**STEP 12 — Factor/quant overlay (§15):** value/quality/momentum composite
percentile vs universe.

**STEP 13 — Context (non-scoring): technicals (§12) for entry/timing/sizing,
sentiment (§11) as fade-filter only, macro (§14) for regime & discount-rate.

**STEP 14 — CROSS-METRIC CONSISTENCY (§17):** run every trap check; surface
contradictions.

**STEP 15 — SYNTHESIZE:** weight by thesis style (§18) → conviction score,
valuation range with scenarios, margin of safety, ranked risk list, and a
**pre-registered "what would prove this thesis wrong"** statement.

---

### Appendix: universal honesty rules for the analyzing AI
1. **Trend & consistency (5–10y) > latest value** for almost every fundamental.
2. **Industry-relative percentile > absolute threshold** — always.
3. **Conjunction > any single metric** — one flashing signal is noise.
4. **Cash flow > earnings** when they disagree.
5. **Decompose every "good" number** — ask what's really driving it (§17).
6. **Distinguish priced-in from predictive** — most public info is already in
   the price; edge is in *differentiated* interpretation, forced-flow structure,
   or time-horizon arbitrage, not in re-reading the same data.
7. **Separate robust signals (⭐) from decorative ones (☠️)** — don't let a
   dashboard of weak technicals outvote moat + ROIC + valuation.
8. **State confidence and disconfirming evidence** — a thesis without a written
   bear case is incomplete.

*Sources for thresholds/vendors: SEC EDGAR; ReadyRatios/CSIMarket (sector ratio
benchmarks); Piotroski (2000), Altman (1968), Beneish (1999), Sloan (1996),
Novy-Marx (2013) forensic/factor definitions; McLean-Pontiff (2016) on decay;
Similarweb/YipitData/Bloomberg Second Measure/Thinknum/Orbital Insight (alt-data);
CBOE/FRED (options & macro). Empirical "honest-edge" tags additionally grounded
in this repo's own out-of-sample tests (see EDGE.md, NEXT_STEPS.md).*




