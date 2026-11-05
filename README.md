# The Tape — 1,150-Game Sportsbook vs. Polymarket Price-Discovery & Calibration Observatory (`v1.0.0`)

**Live Interactive Observatory:** [https://www.perplexity.ai/computer/a/the-tape-IIj3WOkLQjy6ZMTHorHKYw](https://www.perplexity.ai/computer/a/the-tape-IIj3WOkLQjy6ZMTHorHKYw)

**The Tape** joins historical sportsbook odds from **OpticOdds** (`1,332,476` price updates across Pinnacle, DraftKings, FanDuel, BetMGM, and Caesars), order-book trade/midpoint histories from **Polymarket CLOB** (`4,195,032` price samples across `3,387` markets and `$588.17M` moneyline volume), and official play-by-play scoring feeds with wall-clock timestamps from **Sportradar** (`35,060` events) across **`1,150` matched games in `13` leagues** (`2026-09-14 → 2026-10-14 UTC`).

---

## Four Headline Empirical Findings

| # | Research Question | Empirical Finding | Verification Metric |
|---|---|---|---|
| **01** | **Synchronized Live Game Tape** | Every game aligns 5 sportsbooks (de-vigged via multiplicative normalization), Polymarket CLOB ticks, and Sportradar scoring plays on a single wall-clock axis. In the hero game (**Baltimore Ravens @ Atlanta Falcons `30–23 OT`**), Baltimore opens at `74.0%`, drops to `58.0%` at kickoff, falls to a `12.0%` Q4 trough (`08:12`), ties regulation at `50.5%` (`Q4 00:44`), and closes at `99.95%` on the overtime touchdown. | `2,099` raw sportsbook updates + `1,318` Polymarket CLOB ticks (`1,693` synchronized moneyline series ticks) + `16` Sportradar play events |
| **02** | **Who Moves First? (Price Discovery)** | Across `210` sharp Polymarket pre-game moves (`>= 3.0 pp` within 60 minutes), Pinnacle had already priced at least half the move beforehand **`153` times (`72.9%`)**, while Polymarket moved independently **`57` times (`27.1%`)**. Across `261` sharp Pinnacle moves (`>= 3.0 pp`), Polymarket followed within 2 hours **`140` times (`53.6%`)** and was already there `73` times (`28.0%`). | Exact two-sided binomial test vs. 50/50 null: `p = 2.49e-11` (`471` total sharp move events cataloged in `analysis.json`) |
| **03** | **Closing Calibration & Accuracy** | Across `889` games with both closing prices (`T-1m`), Polymarket and Pinnacle agree within `2.0 pp` **`95.61%` (`~96%`) of the time** (`mean |diff| = 0.79 pp`, `mean signed diff = +0.16 pp`, `r = 0.9985`). On the `363`-game common 6-way evaluation set, Pinnacle (`0.2093`) and Polymarket (`0.2092`) finish in a statistical dead heat on Brier score (`paired t = -0.1014`, `p = 0.9192`). | Murphy (1973) Brier decomposition: Pinnacle `Rel = 0.00365, Res = 0.03843, Unc = 0.24467`; Polymarket `Rel = 0.00514, Res = 0.03853, Unc = 0.24467` |
| **04** | **Late-Move Lag Arbitrage vs. Placebo** | Fading late consensus sportsbook moves (`theta = 2.0 pp` between `T-6h` and `T-10m`, entering Polymarket at `T-10m`) triggers `197` bets and yields **`+$0.0096` per `$1` staked** after Polymarket taker fees (`+$0.0251` before fees), underperforming a `500`-run outcome-shuffled placebo (`+$0.1317`, `95% CI: [+$0.0330, +$0.2231]`). | Seeded Mulberry32 (`seed = 17`) 500-shuffle Monte Carlo placebo test: one-sided empirical `p = 0.994` |

---

## Reproducible Econometrics Verification Suite

Run `verify_econometrics.py` (`numpy`, `scipy`) to independently recompute all five verification modules directly from `data/derived/`:

```bash
python3 verify_econometrics.py
```

### Verified Output (`verification_report.json`)

- **`status`**: `"ALL_CHECKS_PASSED"`
- **`1_census`**: `1,150` matched games, `13` leagues (`NFL, NCAAF, MLB, NBA, NHL, WNBA, MLS, Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Champions League`), `1,332,476` sportsbook updates, `4,195,032` Polymarket CLOB samples, `$588,171,739` moneyline volume, `35,060` wall-clock plays.
- **`2_closing_calibration`**: `889` paired games (`mean_abs_diff_pp = 0.79`, `share_within_2pp = 0.9561`, `pearson_r = 0.998513`), `363`-game common 6-way Brier (`0.2093` Pinnacle vs `0.2092` Polymarket).
- **`3_price_discovery_lead_lag`**: `471` sharp events (`>= 3.0 pp`), `153 / 210` (`72.86%`) sportsbook-led vs `57 / 210` (`27.14%`) Polymarket-first (`p = 2.49e-11`).
- **`4_late_move_arbitrage_backtest`**: `197` bets (`+$0.0096` net ROI vs `+$0.1317` placebo mean, `p = 0.994`).
- **`5_hero_game_audit`**: `nfl:2026101240603BF9` (`Baltimore Ravens @ Atlanta Falcons`, `30–23 OT`, `1,693` synchronized moneyline ticks + `16` Sportradar play events).

---

## Repository Structure

- `app/` — Vanilla ES-module interactive observatory (`index.html`, `styles.css`, `js/wall.js`, `js/game.js`, `js/panels.js`, `js/lab.js`, `js/charts.js`, `js/common.js`, `build_deploy.py`, and self-hosted `Geist` + `GeistMono` fonts).
- `pipeline/` — Data joining, multiplicative de-vigging, event-study classification, and per-game JSON compiler scripts.
- `data/derived/` — Derived datasets (`wall.json`, `analysis.json`, `manifest.json`, `meta.json`, `today.json`, and hero game `games/nfl_2026101240603BF9.json`).
- `verify_econometrics.py` & `verification_report.json` — Standalone econometrics & market-microstructure verification suite and machine-readable output.
