# Round 5 Trader

Round 5 trades the 50-product universe with a sparse relationship engine. Every
product has a position limit of 10, so the bot focuses on choosing direction
rather than sizing: positive evidence targets `+10`, negative evidence targets
`-10`, and conflicting evidence cancels through additive votes.

## Strategy Shape

The trader builds mid-price snapshots from the visible book, updates compact
state in `traderData`, scores relationship signals, then crosses the book toward
the target position only when the market is tight enough.

The implementation avoids day-specific switches and timestamp branches. It is
intended to behave the same way across the included round 5 days.

## Signal Families

Pair rules compare two related products by their spread:

- reversion rules buy the first leg and sell the second when the spread is low,
  and do the opposite when it is high;
- momentum rules follow the spread direction instead;
- each spread is filtered through fast and slow EMAs before it becomes a vote.

Lead/follower rules use one product's EMA signal as a directional input for a
related follower. Examples include Pebbles, Translators, Microchips, UV Visors,
Galaxy Sounds, and Robots.

Microchip lag rules keep a short history of `MICROCHIP_CIRCLE` and use larger
moves over fixed lags as slower directional signals for:

- `MICROCHIP_SQUARE`;
- `MICROCHIP_RECTANGLE`.

## Execution

For each product with a nonzero score:

- score above zero targets `+10`;
- score below zero targets `-10`;
- current position is compared with the target;
- the bot crosses visible asks or bids until it reaches the target or exhausts
  available volume;
- it refuses to trade when the best ask minus best bid is greater than
  `MAX_TAKE_SPREAD` (`19`).

The bot does not place passive orders in this round. It only crosses visible
book liquidity when a relationship vote is active.

## State

`traderData` stores:

- pair-rule EMA states;
- lead-rule EMA states;
- recent `MICROCHIP_CIRCLE` mids;
- the last timestamp seen.

If timestamps move backward, which can happen when a local backtest advances to a
new independent day, the state is reset so history does not leak between days.

## Dataset

Included files:

- `datasets/prices_round_5_day_2.csv`
- `datasets/prices_round_5_day_3.csv`
- `datasets/prices_round_5_day_4.csv`
- `datasets/trades_round_5_day_2.csv`
- `datasets/trades_round_5_day_3.csv`
- `datasets/trades_round_5_day_4.csv`

## Run Locally

From the repo root:

```bash
python3 tools/backtester.py --trader round5/trader.py --dataset round5/datasets
```

Current local result:

| Day | Fills | Final PnL |
| ---: | ---: | ---: |
| 2 | 495 | 408,877.00 |
| 3 | 474 | 297,738.00 |
| 4 | 494 | 366,813.00 |
| **Total** |  | **1,073,428.00** |
