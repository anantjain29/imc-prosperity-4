# Round 3 Trader

Round 3 trades the Hydrogel and Velvetfruit products plus the main VEV voucher
strip. The implementation is deliberately direct: it looks for visible book
prices that are far enough from configured fair-value thresholds, crosses those
levels, and clips every order to the product's position limit.

## Products and Limits

| Product | Limit | Role |
| --- | ---: | --- |
| `HYDROGEL_PACK` | 200 | Delta-1 threshold trading |
| `VELVETFRUIT_EXTRACT` | 200 | Underlying and direct threshold trading |
| `VEV_4000` through `VEV_5500` | 300 each | Voucher threshold and option-surface trading |

`VEV_6000` and `VEV_6500` are intentionally ignored by this trader.

## Strategy Mechanics

The bot has static buy and sell thresholds for Hydrogel, Velvetfruit, and most
voucher products. On each tick it walks the visible order book:

- buy asks priced at or below the active buy threshold;
- sell bids priced at or above the active sell threshold;
- stop walking a side as soon as the price no longer has enough edge;
- update a local position estimate while building orders so it does not exceed
  the round limit.

For the voucher strip, the static thresholds are guarded by a simple linear
option model:

```text
voucher_fair = intercept + delta * (VELVETFRUIT_EXTRACT_mid - 5250)
```

That model prevents the bot from using stale voucher thresholds after a broad
move in the underlying. `VEV_5100` has its own relative-value model around a
reference underlying level instead of using the same static table as the rest of
the strip.

## Risk Controls

- Product-level limits are hard-coded and enforced before every order.
- Voucher thresholds tighten when the Velvetfruit mid moves outside the central
  `5200` to `5305` regime.
- The Velvetfruit direct strategy also tightens when the underlying is outside
  that range.
- Orders are only sent for products with both the required order book and a
  configured model.
- The trader does not quote passively; it only takes visible levels that already
  satisfy its edge checks.

## Dataset

Included files:

- `datasets/prices_round_3_day_0.csv`
- `datasets/prices_round_3_day_1.csv`
- `datasets/prices_round_3_day_2.csv`
- `datasets/trades_round_3_day_0.csv`
- `datasets/trades_round_3_day_1.csv`
- `datasets/trades_round_3_day_2.csv`

## Run Locally

From the repo root:

```bash
python3 tools/backtester.py --trader round3/trader.py --dataset round3/datasets
```

Current local result:

| Day | Fills | Final PnL |
| ---: | ---: | ---: |
| 0 | 1,228 | 276,841.50 |
| 1 | 1,556 | 292,859.00 |
| 2 | 1,471 | 256,481.00 |
| **Total** |  | **826,181.50** |
