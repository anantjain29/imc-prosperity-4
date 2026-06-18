# Round 4 Trader

Round 4 keeps the Hydrogel, Velvetfruit, and VEV voucher universe, then adds a
more defensive execution layer around it. Compared with the Round 3 bot, this
version uses market-trade flow, synthetic-underlying checks, passive maker
quotes, cooldowns, visible-liquidity guards, and special handling for deep
out-of-the-money vouchers.

## Products and Limits

| Product | Limit | Role |
| --- | ---: | --- |
| `HYDROGEL_PACK` | 200 | Flow-skewed threshold trading plus passive quoting |
| `VELVETFRUIT_EXTRACT` | 200 | Underlying threshold trading and option anchor |
| `VEV_4000` through `VEV_5500` | 300 each | Voucher threshold, fair-value, and passive quote logic |
| `VEV_6000`, `VEV_6500` | 300 each | Zero/one-price recycling only |

## Hydrogel Logic

Hydrogel has the most custom behavior in this round:

- fixed buy and sell thresholds define the main edge-taking range;
- public trades from named participants adjust a decaying flow score;
- the flow score skews both buy and sell thresholds, capped to avoid overreaction;
- taker orders are capped by `HYDROGEL_MAX_TAKE`;
- after taking obvious edges, the bot may place inventory-scaled passive quotes
  inside the spread when the market is not too wide.

## Velvetfruit and Voucher Logic

The trader estimates the underlying in two ways:

- direct midpoint of `VELVETFRUIT_EXTRACT`;
- synthetic estimates from liquid vouchers, mainly `VEV_4000 + 4000` and
  `VEV_4500 + 4500`.

When the voucher-derived estimates agree closely enough, the bot blends the
synthetic value with the direct Velvetfruit midpoint. That blended underlying is
used by the option fair-value model:

```text
option_fair = intercept + delta * (underlying_mid - 5250)
```

`VEV_4500` and `VEV_5000` use hybrid guarded thresholds around that model. Other
active vouchers use the base threshold table and can also receive passive maker
quotes when the spread, fair value, and inventory state are acceptable.

## Risk and Execution

The order path is built around "risk rooms": before trading a product, the bot
computes how much buy and sell capacity is allowed. That capacity can shrink to
position-reducing orders only when conditions are unsafe.

Important guards:

- product-level spread caps;
- minimum visible bid/ask volume for selected products;
- one-tick move cooldowns for products that just moved too sharply;
- voucher crash cooldowns when the underlying trend falls quickly;
- level-one imbalance threshold shift for Velvetfruit;
- passive quote limits by product-specific spread, edge, and quantity settings;
- zero-cost orders for `VEV_6000` and `VEV_6500` instead of active fair-value
  trading.

## Dataset

Included files:

- `datasets/prices_round_4_day_0.csv`
- `datasets/prices_round_4_day_1.csv`
- `datasets/prices_round_4_day_2.csv`
- `datasets/trades_round_4_day_0.csv`
- `datasets/trades_round_4_day_1.csv`
- `datasets/trades_round_4_day_2.csv`

This checkout does not include round 4 day 3 CSVs. If those files are added with
the same naming pattern, `tools/backtester.py` will include them automatically.

## Run Locally

From the repo root:

```bash
python3 tools/backtester.py --trader round4/trader.py --dataset round4/datasets
```

Current local result:

| Day | Fills | Final PnL |
| ---: | ---: | ---: |
| 0 | 1,306 | 233,592.00 |
| 1 | 1,936 | 301,066.00 |
| 2 | 1,936 | 296,075.00 |
| **Total** |  | **830,733.00** |
