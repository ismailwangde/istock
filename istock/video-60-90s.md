# istock: the short video (60 seconds)

One idea: **istock helps before a trade and after it.** Before: it shortlists the stocks worth a closer look and shows the case for and against each one. After: it checks whether your trading beat doing nothing. Tell it as a product idea: what I tried, where it failed, and the features I built from what still works.

Total spoken script: about 135 words, roughly 60 seconds at a relaxed pace.

---

## Before you record (10 minutes)

- **Start the app from `ismail_personal`:** `streamlit run istock/ui/app.py`.
- **Load each page once beforehand:** 🎯 Picks (the screener), MU in 🔍 Stock Deep-Dive, and 🏠 Home. First loads are slow; after that they're instant.
- **Check that "🧠 Why This Score?" has entries in both columns** (✅ Supporting and ⚠️ Risk). If one is empty, use ORCL or NVDA.
- **Home holds the sample portfolio,** with a blue "🧪 Sample portfolio" banner at the top. Keep the banner in shot when you first show Home.
- **Read the Trade Review numbers off the screen on the day.** Prices move daily. The script uses the Oct 2 close: $108 behind the S&P, AMD's 15 trades cost $40. If AMD is no longer the biggest cost, say whichever stock the page names.
- **Add "Not financial advice" as a caption** on the last shot.

---

## The script

| Time | Show | Say |
|---|---|---|
| **0:00–0:07** | 📈 Evidence-Based page, scrolling the tested-and-rejected list. | "I tried to predict whether stocks go up or down: 36 chart signals, news, momentum." |
| **0:07–0:14** | Same page, pause on "AUC ≈ 0.51". | "After trading costs, nothing beat a coin flip. So I built for what does work: measuring, not predicting." |
| **0:14–0:23** | 🎯 Picks: the screener list, sorted by score, quality band on each row. | "istock scores every stock from 0 to 100 and shortlists the high scorers, so an analyst knows where to look first." |
| **0:23–0:33** | Click a name → Deep-Dive → **🧠 Why This Score?** (✅ Supporting / ⚠️ Risk), then flick open Fundamentals and 📉 Risk & Volatility. | "Open one, and you get the case for and against it, right now: fundamentals, technicals, market context and risk." |
| **0:33–0:40** | 🏠 Home with the 🧪 Sample portfolio banner → scroll to **🧾 Trade Review**: the three result cards. | "And after the trade? Trade Review compares what you did with never selling, and with just buying the index." |
| **0:40–0:53** | Hold on the summary lines ("trailed S&P 500 by…", "Selling AMD cost you…"), then the table with AMD's "3 buy / 12 sell". | "This sample trader takes profits at 8% and holds losers. Twenty-eight trades later, they're $108 behind the S&P, and trading AMD fifteen times cost them $40." |
| **0:53–1:00** | The ✅ / ❌ "Beat index?" column. Caption: "Not financial advice." | "It doesn't make the call. It shows you the case before the trade, and the truth after." |

**If you're running long:** cut "So I built for what does work: measuring, not predicting" from the second row.

---

## One-line alternatives (swap in if they feel more like you)

- "Traders do the math before they buy. Almost nobody checks it after."
- "Their winners were smaller than their losers. That's what holding losers looks like in money."
- "Built for the analyst who wants the case, not the conclusion."
- "It doesn't tell you what to do. It tells you what's true."

## Don't say

- That the sample trader is real, or that these are your trades. Say "sample trader."
- "Buy signal," "AI picks stocks" or "it predicts." Nothing in it predicts direction.
- That analysts already use it. Say "built for."
- That Trade Review includes costs or taxes. It doesn't yet; the caption under the table says so.

---

## Numbers you'll say, and where they come from

| Claim | Source |
|---|---|
| 36 chart signals, coin flip | The scoring model's feature set; its out-of-sample AUC is 0.51, where 0.50 is chance. Shown on the Evidence page. |
| 0 to 100, shortlist | Quality bands: 80+ Excellent, 65 Strong, 55 Solid, 45 Average, 35 Mixed, 20 Weak, below 20 Poor. |
| The sample trader | A rule run on real closing prices from June 1: $250 in each of six stocks ($2,000 put in, including $125 buy-backs), sell half at +8%, never sell a loser, buy back after a 5% dip. Nobody picked the trades by hand. |
| $108 behind, AMD cost $40 | Trade Review on Home, Oct 2 close. "Index instead" puts each buy's cash into SPY that day. |

---

## Afterwards

Your six tracked picks from Aug 21 are saved in `results/holdings.tracked-picks-2026-08-21.json`. To bring them back, copy that file over `results/holdings.json`.
