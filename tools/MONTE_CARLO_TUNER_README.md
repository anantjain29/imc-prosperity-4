# Monte Carlo Tuner

`monte_carlo_tuner.py` searches near the current trader parameters by randomly
nudging multiple class-level numeric constants at the same time. It runs those
candidates in parallel, reports stability metrics, and ranks the trials by a
risk-adjusted score.

Use this after the directed tuner when you want to test small parameter
interactions around an already-good baseline.

## Usage

Run from the repo root:

```bash
python3 tools/monte_carlo_tuner.py \
  --trader round5/trader.py \
  --dataset round5/datasets \
  --trials 200 \
  --workers 8
```

Tune a specific set of params:

```bash
python3 tools/monte_carlo_tuner.py \
  --trader round4/trader.py \
  --dataset round4/datasets \
  --params HYDROGEL_BUY_TH HYDROGEL_SELL_TH HYDROGEL_SKEW_MULT \
  --trials 300 \
  --seed 7 \
  --workers 8
```

Write the best patched version:

```bash
python3 tools/monte_carlo_tuner.py \
  --trader round5/trader.py \
  --dataset round5/datasets \
  --trials 200 \
  --materialize-best round5/trader_mc_best.py
```

## Parameter Selection

If `--params` is omitted, the tuner auto-detects class-level numeric constants
whose names contain parameter-like words such as:

```text
TH, LIMIT, SPREAD, WIDTH, MULT, CAP, ALPHA, WEIGHT, QTY, DECAY
```

Use `--max-params` to control how many auto-detected constants are included.
Each trial mutates a random subset of those params. The subset size is controlled
by `--mutation-rate`, which defaults to `0.35`.

## Nudges

The tuner keeps trials near the current parameter values:

- large constants are changed additively, for example threshold-like values move
  by a few ticks;
- smaller constants are changed multiplicatively, usually within about 10%;
- integer constants stay integers;
- `--nudge-scale` widens or tightens all random nudges.

Useful examples:

```bash
# Smaller local search
python3 tools/monte_carlo_tuner.py --trader round4/trader.py --dataset round4/datasets --nudge-scale 0.5

# Wider local search
python3 tools/monte_carlo_tuner.py --trader round4/trader.py --dataset round4/datasets --nudge-scale 2.0
```

## Metrics and Score

Every candidate reports:

- total PnL;
- mean daily PnL;
- daily PnL standard deviation;
- Sharpe-like ratio, computed from daily PnL;
- max drawdown across cumulative daily PnL;
- minimum day PnL.

The default score is:

```text
score = mean_daily_pnl - std_penalty * daily_pnl_std
```

`--std-penalty` defaults to `1.0`. Available score modes are:

- `mean_std`: mean daily PnL minus standard-deviation penalty;
- `total_std`: total PnL minus standard-deviation penalty;
- `sharpe`: rank by Sharpe-like ratio;
- `std`: rank by lowest daily standard deviation;
- `total`: rank by raw total PnL.

## Output

The full results are written to `monte_carlo_tuner_results.csv` by default. The
CSV includes the tested parameter patch for every trial, so you can inspect or
replay promising candidates later.
