# Running istock

A transparency-first equity-research tool. It shortlists stocks by a 0–100 quality
score, shows the case for and against each one, and checks after the fact whether
trading beat doing nothing. It never issues a buy/sell call. See
[istock/CONCLUSIONS.md](istock/CONCLUSIONS.md) for why.

## Setup

```bash
git clone https://github.com/ismailwangde/istock.git
cd istock
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run the app

```bash
streamlit run istock/ui/app.py --client.toolbarMode minimal
```

Then open the URL Streamlit prints (default http://localhost:8501).
`--client.toolbarMode minimal` hides Streamlit's Deploy button, which is useful when
screen recording.

> Run the command from **this top folder** (the one holding `istock/`, `ismail_p/`
> and `results/`). The app finds `results/` and `ismail_p/config.py` relative to it.

## What's in here

| Path | Purpose |
|---|---|
| `istock/` | The application: Streamlit UI, scoring engine, decision logic, docs |
| `ismail_p/config.py` | Watchlist, scanner universe, thresholds and profile; the app imports it as `config` |
| `results/brain_v2_weights/` | Trained model weights (**required** for scoring) |
| `results/holdings.json` | A **sample portfolio**: a rule-based trader on real prices, labelled as a sample in the app |
| `results/holdings.tracked-picks-2026-08-21.json` | The tool's top six picks as of 2026-08-21, tracked since. Copy over `holdings.json` to use. |
| `new/` | The fundamental analyzer and forward-logging snapshot tool (runs on its own) |
| `istock/video-60-90s.md` | The 60-second demo video script |

## Notes

- The first load fetches live market data from Yahoo Finance, so it needs internet
  and takes a few seconds; after that it's cached.
- A price cache and `profile.json` are created automatically on first run.
- Not financial advice. Educational project.
