# Directed Tuner

`directed_tuner.py` is the conservative one-constant-at-a-time tuner. It nudges
one class-level numeric constant, runs the Python backtester, scores the result,
then moves to the next candidate. This is useful when you want to understand
which individual parameter change helped.

## Usage

Run from the repo root:

```bash
python3 tools/directed_tuner.py \
  --trader round4/trader.py \
  --dataset round4/datasets \
  --params HYDROGEL_BUY_TH HYDROGEL_SELL_TH
```

Write the best patched version:

```bash
python3 tools/directed_tuner.py \
  --trader round4/trader.py \
  --dataset round4/datasets \
  --params HYDROGEL_BUY_TH HYDROGEL_SELL_TH \
  --materialize-best round4/trader_directed_best.py
```

If `--params` is omitted, the tuner picks a small set of class constants whose
names look like thresholds, spreads, caps, multipliers, limits, or weights.

## Score

The directed tuner ranks candidates with:

```text
score = total_pnl - variance_penalty * daily_pnl_std
```

The default `variance_penalty` is `0.5`. Increase it when you want smoother
performance across days; decrease it when you want the ranking to behave more
like raw PnL.

## Output

The full results are written to `directed_tuner_results.csv` by default. The
table includes candidate name, score, total PnL, daily standard deviation,
minimum day PnL, and the constant patch that was tested.
