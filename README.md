# IMC Prosperity 2026 Trading Bots

This repository is a compact archive of the final Python traders and released
CSV datasets used for IMC Prosperity rounds 3, 4, and 5. Each round folder keeps
one self-contained `trader.py` with the standard `Trader.run(state)` entrypoint,
plus the market data needed to replay it locally.

The repo also includes a small Python backtester plus two parameter tuners: a
directed one-constant tuner and a parallel Monte Carlo tuner. The tools are
intentionally lightweight: useful for sanity checks, strategy comparison, and
quick parameter experiments, but not a full exchange simulator.

## Competition Result

Secured **Global Rank 340** and **India Rank 46** among **18,803 teams** from
**1,549 universities** across **117 countries** in **IMC Prosperity 4**.

## Repository Layout

```text
round3/
  trader.py        # Hydrogel, Velvetfruit, and VEV voucher threshold strategy
  datasets/        # round 3 price/trade CSVs for days 0, 1, and 2
  README.md        # round-specific strategy notes

round4/
  trader.py        # robust Hydrogel + Velvetfruit/voucher strategy
  datasets/        # round 4 price/trade CSVs for days 0, 1, and 2
  README.md

round5/
  trader.py        # 50-product relationship and lead/lag strategy
  datasets/        # round 5 price/trade CSVs for days 2, 3, and 4
  README.md

tools/
  backtester.py    # local IMC-style CSV replay simulator
  directed_tuner.py
                   # one-constant-at-a-time ablation tuner
  monte_carlo_tuner.py
                   # parallel nearby-parameter random search
```

## Quickstart

Run these commands from the repository root:

```bash
python3 tools/backtester.py --trader round3/trader.py --dataset round3/datasets
python3 tools/backtester.py --trader round4/trader.py --dataset round4/datasets
python3 tools/backtester.py --trader round5/trader.py --dataset round5/datasets
```

Use `--products full` to show per-product PnL, or `--products off` for a shorter
daily summary:

```bash
python3 tools/backtester.py --trader round5/trader.py --dataset round5/datasets --products full
```

## Strategy Summary

| Round | Products | Main idea |
| --- | --- | --- |
| 3 | `HYDROGEL_PACK`, `VELVETFRUIT_EXTRACT`, `VEV_4000` through `VEV_5500` | Cross visible book levels only when static or model-guarded thresholds show enough edge. |
| 4 | Same core products plus zero-bid handling for `VEV_6000` and `VEV_6500` | Adds Hydrogel flow skew, synthetic-underlying voucher checks, passive maker quotes, cooldowns, and spread/volume risk rooms. |
| 5 | 50-product universe | Combines pair-spread, momentum/reversion, leader/follower, and Microchip lag votes into target positions of `+10` or `-10`. |

Each round README gives the concrete mechanics, limits, datasets, and local
backtest output for that bot.

## Current Local Backtest Results

These totals are from `tools/backtester.py` against the CSVs included in this
checkout. The fill model only matches against visible order-book levels and
marks open inventory to each day's final mid price.

| Round | Days in dataset | Total PnL |
| --- | --- | ---: |
| 3 | 0, 1, 2 | 826,181.50 |
| 4 | 0, 1, 2 | 830,733.00 |
| 5 | 2, 3, 4 | 1,073,428.00 |

## Tools

`tools/backtester.py`:

- installs a local `datamodel` shim compatible with the submitted traders;
- loads `prices_round_*_day_*.csv` and matching `trades_round_*_day_*.csv`;
- builds `TradingState` objects timestamp by timestamp;
- simulates visible-book fills with position-limit clipping;
- reports daily totals and optional per-product PnL.

`tools/directed_tuner.py`:

- finds class-level numeric constants in a trader;
- tests nearby values one constant at a time;
- scores each candidate as `total_pnl - variance_penalty * daily_pnl_std`;
- writes a ranked `directed_tuner_results.csv`;
- can materialize the best patched trader with `--materialize-best`.

`tools/monte_carlo_tuner.py`:

- finds class-level numeric constants automatically, with `--params` override;
- randomly nudges multiple parameters together near their current values;
- runs candidates in parallel with `--workers`;
- reports total PnL, mean daily PnL, daily std dev, Sharpe, max drawdown, and
  minimum day PnL;
- writes a ranked `monte_carlo_tuner_results.csv`;
- can materialize the best patched trader with `--materialize-best`.

Example directed tuner run:

```bash
python3 tools/directed_tuner.py \
  --trader round4/trader.py \
  --dataset round4/datasets \
  --params HYDROGEL_BUY_TH HYDROGEL_SELL_TH
```

Example Monte Carlo tuner run:

```bash
python3 tools/monte_carlo_tuner.py \
  --trader round5/trader.py \
  --dataset round5/datasets \
  --trials 200 \
  --workers 8
```

More tool details:

- `tools/BACKTESTER_README.md`
- `tools/DIRECTED_TUNER_README.md`
- `tools/MONTE_CARLO_TUNER_README.md`

## Notes

- The backtester is a local approximation, not the official competition engine.
  It does not model queue priority, hidden liquidity, latency, or all exchange
  edge cases.
- The checked-in round folders contain only the final trader for each round, not
  the full research history.
- Round 4 in this checkout contains days 0-2 only. If you add day 3 CSVs later,
  the backtester will pick them up automatically because it scans the dataset
  directory by filename.
